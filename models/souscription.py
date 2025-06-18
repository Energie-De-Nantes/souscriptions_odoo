from odoo import models, fields, api
from odoo.exceptions import UserError
from datetime import date, timedelta

import logging
_logger = logging.getLogger(__name__)

class SouscriptionEtat(models.Model):
    _name = 'souscription.etat'
    _description = "États de facturation"
    _order = "sequence"

    name = fields.Char("Nom", required=True)
    sequence = fields.Integer("Ordre", default=10)
    color = fields.Integer("Couleur")

class Souscription(models.Model):
    _name = 'souscription'
    _description = 'Souscription Électricité'
    _inherit = ['mail.thread']

    name = fields.Char(string='Référence', required=True, copy=False, readonly=True, default='Nouveau')
    partner_id = fields.Many2one('res.partner', string='Souscripteur·trice')
    active = fields.Boolean(string='Active', default=True)

    date_debut = fields.Date(string="Début de la souscription")
    date_fin = fields.Date(string="Fin de la souscription")
    etat_facturation_id = fields.Many2one(
        'souscription.etat',
        string="État de facturation",
        required=True
    )
    # facture_ids = fields.One2many(
    #     'account.move',
    #     'souscription_id',
    #     string='Factures')
    facture_ids = fields.One2many(
        'account.move',
        compute='_compute_factures_via_periodes',
        string="Factures",
        store=False
    )
    periode_ids = fields.One2many(
        'souscription.periode', 
        'souscription_id', 
        string='Périodes de facturation'
    )
    # Données métier 

    ## Utiles facturation
    pdl = fields.Char(string="pdl")
    lisse = fields.Boolean(string='Lissé', default=False)
    puissance_souscrite = fields.Selection(
    selection=[
        ('3', '3 kVA'),
        ('6', '6 kVA'),
        ('9', '9 kVA'),
        ('12', '12 kVA'),
        ('15', '15 kVA'),
        ('18', '18 kVA'),
        ('24', '24 kVA'),
        ('30', '30 kVA'),
        ('36', '36 kVA'),
    ],
    string='Puissance souscrite (kVA)',
    required=True,
    tracking=True
    )
    provision_mensuelle_kwh = fields.Float(
        string="Provision mensuelle (kWh)",
        help="Énergie estimée mensuelle à facturer si lissage activé.",
        tracking=True
    )
    type_tarif = fields.Selection(
        [('base', 'Base'), ('hphc', 'Heures Pleines / Heures Creuses')],
        default='base',
        string='Type de tarif',
        required=True,
        tracking=True
    )
    tarif_solidaire = fields.Boolean(string="Tarif solidaire", default=False, tracking=True)
    
    ## Utiles paiement 

    mode_paiement = fields.Selection([
        ('prelevement', 'Prélèvement'),
        ('cheque_energie', 'Chèque énergie'),
        ('monnaie_locale', 'Monnaie locale'),
        ('especes', 'Espèces'),
        ('virement', 'Virement'),
        ('cheque', 'Chèque'),
    ], string="Mode de paiement", tracking=True)
    ## Informations
    ref_compteur = fields.Char(string="Référence compteur")
    numero_depannage = fields.Char(string="Numéro de dépannage")

    # Computed fields métier déplacés vers souscription_metier_mixin.py
    # pour découplage des dépendances métier
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nouveau') == 'Nouveau':
                vals['name'] = self.env['ir.sequence'].next_by_code('souscription.sequence') or 'Nouveau'
        return super().create(vals_list)
    
    @api.depends('periode_ids.facture_id')
    def _compute_factures_via_periodes(self):
        for sous in self:
            sous.facture_ids = sous.periode_ids.mapped('facture_id')

    # Computed fields métier déplacés vers souscription_metier_mixin.py
    
    def creer_factures(self):
        """
        Crée les factures à partir des périodes de facturation.
        Utilise les données historisées de chaque période pour générer les bonnes lignes.
        """
        _logger.info(f"Créer factures appelé pour {len(self)} souscriptions")

        for souscription in self:
            if not souscription.partner_id:
                _logger.warning(f"Souscription {souscription.name} sans partenaire, ignorée")
                continue

            # Pour chaque période sans facture
            for periode in souscription.periode_ids.filtered(lambda p: not p.facture_id):
                try:
                    facture = souscription._creer_facture_periode(periode)  # Utiliser la souscription spécifique
                    periode.facture_id = facture
                    _logger.info(f"Facture {facture.name} créée pour période {periode.mois_annee}")
                except Exception as e:
                    _logger.error(f"Erreur création facture pour période {periode.mois_annee}: {e}")
                    raise UserError(f"Erreur création facture pour {periode.mois_annee}: {e}")

    def _get_produit_abonnement(self, puissance, tarif_solidaire):
        """Trouve le variant de produit d'abonnement correspondant aux critères"""
        # Recherche du template selon le type d'abonnement
        if tarif_solidaire:
            template_xmlid = 'souscriptions.souscriptions_product_template_abonnement_solidaire'
        else:
            template_xmlid = 'souscriptions.souscriptions_product_template_abonnement'
        
        template = self.env.ref(template_xmlid, raise_if_not_found=False)
        if not template:
            type_abo = "solidaire" if tarif_solidaire else "standard"
            raise UserError(f"Template d'abonnement {type_abo} non trouvé")
        
        # Recherche du variant avec la bonne puissance
        variant = template.product_variant_ids.filtered(
            lambda v: puissance in v.name or puissance.replace(' ', '') in v.name.replace(' ', '')
        )
        
        if not variant:
            type_abo = "solidaire" if tarif_solidaire else "standard" 
            raise UserError(f"Aucun variant d'abonnement {type_abo} trouvé pour {puissance}")
        
        return variant[0]  # Premier variant trouvé
    
    def _get_produit_energie(self, type_energie):
        """Trouve le produit d'énergie correspondant au type (base, hp, hc)"""
        xmlid_map = {
            'base': 'souscriptions.souscriptions_product_energie_base',
            'hp': 'souscriptions.souscriptions_product_energie_hp', 
            'hc': 'souscriptions.souscriptions_product_energie_hc'
        }
        
        xmlid = xmlid_map.get(type_energie.lower())
        if not xmlid:
            raise UserError(f"Type d'énergie non reconnu : {type_energie}")
            
        produit = self.env.ref(xmlid, raise_if_not_found=False)
        if not produit:
            raise UserError(f"Produit d'énergie {type_energie} non trouvé")
        
        return produit

    def _creer_facture_periode(self, periode):
        """
        Crée une facture pour une période donnée en utilisant les données historisées
        et la grille de prix active.
        """
        # 1. Récupération de la grille active et des prix
        grille_active = self.env['grille.prix'].get_grille_active(periode.date_fin)
        prix_dict = grille_active.get_prix_dict()  # {product_id: prix_interne}
        
        # 2. Utilisation des données historisées de la période
        puissance = periode.puissance_souscrite_periode or self.puissance_souscrite
        tarif_solidaire = periode.tarif_solidaire_periode
        type_tarif = periode.type_tarif_periode or dict(self._fields['type_tarif'].selection).get(self.type_tarif, self.type_tarif)
        
        if not puissance:
            raise UserError(f"Aucune puissance définie pour la période {periode.mois_annee}")

        # 3. Création des lignes de facture avec vrais produits
        lines_vals = []
        
        # Ligne abonnement
        produit_abo = self._get_produit_abonnement(puissance, tarif_solidaire)
        prix_abo_journalier = prix_dict.get(produit_abo.id)
        
        if prix_abo_journalier is None:
            raise UserError(f"Prix non trouvé dans la grille pour le produit : {produit_abo.name}")

        lines_vals.append((0, 0, {
            'product_id': produit_abo.id,
            'name': f"{produit_abo.name} - {periode.mois_annee} ({periode.jours} jours)",
            'quantity': periode.jours,
            'price_unit': prix_abo_journalier,
        }))

        # Lignes énergie selon type de tarif historisé
        if type_tarif == 'Base':
            if periode.provision_base_kwh > 0:
                produit_base = self._get_produit_energie('base')
                prix_base = prix_dict.get(produit_base.id)
                if prix_base is None:
                    raise UserError(f"Prix non trouvé dans la grille pour le produit : {produit_base.name}")
                    
                lines_vals.append((0, 0, {
                    'product_id': produit_base.id,
                    'name': f"{produit_base.name} {periode.provision_base_kwh:.2f} kWh - {periode.mois_annee}",
                    'quantity': periode.provision_base_kwh,
                    'price_unit': prix_base,
                }))
        else:  # HP/HC
            if periode.provision_hp_kwh > 0:
                produit_hp = self._get_produit_energie('hp')
                prix_hp = prix_dict.get(produit_hp.id)
                if prix_hp is None:
                    raise UserError(f"Prix non trouvé dans la grille pour le produit : {produit_hp.name}")
                    
                lines_vals.append((0, 0, {
                    'product_id': produit_hp.id,
                    'name': f"{produit_hp.name} {periode.provision_hp_kwh:.2f} kWh - {periode.mois_annee}",
                    'quantity': periode.provision_hp_kwh,
                    'price_unit': prix_hp,
                }))
                
            if periode.provision_hc_kwh > 0:
                produit_hc = self._get_produit_energie('hc')
                prix_hc = prix_dict.get(produit_hc.id)
                if prix_hc is None:
                    raise UserError(f"Prix non trouvé dans la grille pour le produit : {produit_hc.name}")
                    
                lines_vals.append((0, 0, {
                    'product_id': produit_hc.id,
                    'name': f"{produit_hc.name} {periode.provision_hc_kwh:.2f} kWh - {periode.mois_annee}",
                    'quantity': periode.provision_hc_kwh,
                    'price_unit': prix_hc,
                }))

        # Lignes TURPE si présentes (sans produit pour l'instant)
        if periode.turpe_fixe > 0:
            lines_vals.append((0, 0, {
                'name': f"TURPE Fixe - {periode.mois_annee}",
                'quantity': 1,
                'price_unit': periode.turpe_fixe,
            }))
            
        if periode.turpe_variable > 0:
            lines_vals.append((0, 0, {
                'name': f"TURPE Variable - {periode.mois_annee}",
                'quantity': 1,
                'price_unit': periode.turpe_variable,
            }))

        # 6. Création de la facture
        facture_vals = {
            'move_type': 'out_invoice',
            'partner_id': self.partner_id.id,
            'invoice_date': periode.date_fin,
            'periode_id': periode.id,
            'invoice_line_ids': lines_vals,
        }

        return self.env['account.move'].create(facture_vals)
    
    @api.model
    def ajouter_periodes_mensuelles(self):
        """
        Crée une période de facturation (du 1er au dernier jour du mois précédent)
        pour chaque souscription active.
        L'historisation des paramètres se fait automatiquement dans create().
        """
        # Calcul du 1er jour du mois en cours
        premier_mois_courant = date.today().replace(day=1)

        # 1er jour du mois précédent  
        premier_mois_precedent = (premier_mois_courant - timedelta(days=1)).replace(day=1)

        souscriptions = self.search([('active', '=', True)])
        periodes_creees = 0
        
        for souscription in souscriptions:
            # Vérifier qu'une période n'existe pas déjà pour ce mois
            periode_existante = self.env['souscription.periode'].search([
                ('souscription_id', '=', souscription.id),
                ('date_debut', '=', premier_mois_precedent),
                ('date_fin', '=', premier_mois_courant)
            ])
            
            if not periode_existante:
                self.env['souscription.periode'].create({
                    'souscription_id': souscription.id,
                    'date_debut': premier_mois_precedent,
                    'date_fin': premier_mois_courant,
                    'type_periode': 'mensuelle',
                    # Les cadrans énergétiques restent à 0 (à remplir via pont externe)
                    'energie_hph_kwh': 0,
                    'energie_hpb_kwh': 0, 
                    'energie_hch_kwh': 0,
                    'energie_hcb_kwh': 0,
                    'turpe_fixe': 0,
                    'turpe_variable': 0,
                    # L'historisation se fait automatiquement dans create()
                })
                periodes_creees += 1
            
        _logger.info(f"{periodes_creees} périodes créées pour {len(souscriptions)} souscriptions actives")
    
    # === API POUR PONT EXTERNE ===
    
    @api.model
    def get_souscriptions_by_pdl(self, pdl_list):
        """Récupère les souscriptions par liste de PDL - API pour pont externe"""
        return self.search([('pdl', 'in', pdl_list)]).read([
            'name', 'pdl', 'partner_id', 'date_debut', 'date_fin',
            'puissance_souscrite', 'type_tarif', 'lisse', 'provision_mensuelle_kwh',
            'tarif_solidaire', 'mode_paiement'
        ])
    
    def get_billing_periods(self, date_start=None, date_end=None):
        """Récupère les périodes de facturation pour cette souscription"""
        domain = [('souscription_id', '=', self.id)]
        if date_start:
            domain.append(('date_debut', '>=', date_start))
        if date_end:
            domain.append(('date_fin', '<=', date_end))
        
        periods = self.env['souscription.periode'].search(domain)
        return periods.read([
            'date_debut', 'date_fin', 'type_periode', 'energie_kwh', 'provision_kwh',
            'turpe_fixe', 'turpe_variable', 'facture_id'
        ])
    
    @api.model
    def create_billing_period(self, vals):
        """Crée une période de facturation - API pour pont externe"""
        return self.env['souscription.periode'].create(vals)
    
    def update_consumption_data(self, period_data):
        """Met à jour les données de consommation - API pour pont externe"""
        for period_vals in period_data:
            period_id = period_vals.pop('id')
            period = self.env['souscription.periode'].browse(period_id)
            period.write(period_vals)
        return True