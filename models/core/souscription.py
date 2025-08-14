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
    _name = 'souscription.souscription'
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
        help="Énergie estimée mensuelle à facturer si lissage activé (tarif Base).",
        tracking=True
    )
    provision_hp_kwh = fields.Float(
        string="Provision HP mensuelle (kWh)",
        help="Énergie estimée mensuelle Heures Pleines si lissage activé (tarif HP/HC).",
        tracking=True
    )
    provision_hc_kwh = fields.Float(
        string="Provision HC mensuelle (kWh)",
        help="Énergie estimée mensuelle Heures Creuses si lissage activé (tarif HP/HC).",
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
    
    # Coefficient PRO personnalisé  
    coeff_pro = fields.Float("Majoration PRO (%)", default=0.0, digits=(5, 2),
                            help="Majoration en % appliquée au tarif de base (0% pour les particuliers)", tracking=True)
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

    def _get_produit_abonnement(self, tarif_solidaire):
        """Trouve le produit d'abonnement selon le type"""
        product_ref = 'souscriptions_product_abonnement_solidaire' if tarif_solidaire else 'souscriptions_product_abonnement_standard'
        
        try:
            return self.env.ref(f'souscriptions_odoo.{product_ref}')
        except:
            type_abo = "solidaire" if tarif_solidaire else "standard"
            raise UserError(f"Produit d'abonnement {type_abo} non trouvé")
    
    def _get_produit_energie(self, type_energie):
        """Trouve le produit d'énergie correspondant au type (base, hp, hc)"""
        xmlid_map = {
            'base': 'souscriptions_odoo.souscriptions_product_energie_base',
            'hp': 'souscriptions_odoo.souscriptions_product_energie_hp', 
            'hc': 'souscriptions_odoo.souscriptions_product_energie_hc'
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
        et la grille de prix active avec calcul dynamique.
        """
        # 1. Récupération de la grille active
        grille_active = self.env['grille.prix'].get_grille_active(periode.date_fin)
        prix_dict = grille_active.get_prix_dict()  # {product_id: prix_interne} pour les énergies
        
        # 2. Utilisation des données historisées de la période
        puissance_str = periode.puissance_souscrite_periode or self.puissance_souscrite
        tarif_solidaire = periode.tarif_solidaire_periode
        type_tarif = periode.type_tarif_periode or dict(self._fields['type_tarif'].selection).get(self.type_tarif, self.type_tarif)
        
        if not puissance_str:
            raise UserError(f"Aucune puissance définie pour la période {periode.mois_annee}")

        # Extraction de la puissance numérique (ex: "6 kVA" -> 6.0)
        try:
            puissance_kva = float(puissance_str.replace(' kVA', '').replace(',', '.'))
        except:
            raise UserError(f"Format de puissance invalide : {puissance_str}")

        # 3. Création des lignes de facture
        lines_vals = []
        
        # Section Abonnement
        lines_vals.append((0, 0, {
            'display_type': 'line_section',
            'name': "Abonnement",
        }))
        
        # Ligne abonnement avec calcul dynamique (utilise le coefficient historisé)
        coeff_pro_historise = periode.coeff_pro_periode if hasattr(periode, 'coeff_pro_periode') else self.coeff_pro
        produit_abo = self._get_produit_abonnement(tarif_solidaire)
        prix_abo_journalier = grille_active.get_prix_abonnement(
            puissance_kva, 
            coeff_pro=coeff_pro_historise,
            is_solidaire=tarif_solidaire
        )
        
        # Nom descriptif de la ligne
        type_client = "PRO" if coeff_pro_historise > 0 else "PART"
        puissance_desc = f"{puissance_kva:g} kVA"  # :g supprime les .0 inutiles
        
        lines_vals.append((0, 0, {
            'product_id': produit_abo.id,
            'name': f"{produit_abo.name} {puissance_desc} {type_client}",
            'quantity': periode.jours,
            'price_unit': prix_abo_journalier,
        }))
        
        # Note TURPE fixe sous l'abonnement
        if periode.turpe_fixe > 0:
            lines_vals.append((0, 0, {
                'display_type': 'line_note',
                'name': f"Dont turpe fixe: {periode.turpe_fixe:.2f}€",
            }))

        # Section Énergie
        lines_vals.append((0, 0, {
            'display_type': 'line_section',
            'name': "Énergie",
        }))
        
        # Lignes énergie selon type de tarif historisé
        # Le type_tarif peut être la clé ('base', 'hphc') ou le libellé complet
        is_base_tarif = (
            type_tarif == 'base' or 
            type_tarif == 'Base' or 
            'Base' in str(type_tarif)
        )
        
        if is_base_tarif:
            # Tarif BASE : toujours afficher la ligne énergie base (même si 0)
            produit_base = self._get_produit_energie('base')
            prix_base = prix_dict.get(produit_base.id)
            if prix_base is None:
                raise UserError(f"Prix non trouvé dans la grille pour le produit : {produit_base.name}")
                
            lines_vals.append((0, 0, {
                'product_id': produit_base.id,
                'name': produit_base.name,
                'quantity': periode.provision_base_kwh,
                'price_unit': prix_base,
            }))
        else:  # HP/HC
            # Tarif HP/HC : toujours afficher les deux lignes HP et HC (même si 0)
            # Ligne HP
            produit_hp = self._get_produit_energie('hp')
            prix_hp = prix_dict.get(produit_hp.id)
            if prix_hp is None:
                raise UserError(f"Prix non trouvé dans la grille pour le produit : {produit_hp.name}")
                
            lines_vals.append((0, 0, {
                'product_id': produit_hp.id,
                'name': produit_hp.name,
                'quantity': periode.provision_hp_kwh,
                'price_unit': prix_hp,
            }))
            
            # Ligne HC
            produit_hc = self._get_produit_energie('hc')
            prix_hc = prix_dict.get(produit_hc.id)
            if prix_hc is None:
                raise UserError(f"Prix non trouvé dans la grille pour le produit : {produit_hc.name}")
                
            lines_vals.append((0, 0, {
                'product_id': produit_hc.id,
                'name': produit_hc.name,
                'quantity': periode.provision_hc_kwh,
                'price_unit': prix_hc,
            }))

        # Note TURPE variable sous l'énergie
        if periode.turpe_variable > 0:
            lines_vals.append((0, 0, {
                'display_type': 'line_note', 
                'name': f"Dont turpe variable: {periode.turpe_variable:.2f}€",
            }))

        # 4. Création de la facture
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

    @api.model
    def generer_lot_prelevement_mensuel(self):
        """Génère un lot de prélèvement pour les souscriptions en prélèvement automatique"""
        # Fonctionnalité à implémenter dans une version ultérieure
        # Pour l'instant, on retourne un message d'information
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Génération de lot de prélèvement',
                'message': 'Fonctionnalité en cours de développement - Version minimale',
                'type': 'info',
                'sticky': False,
            }
        }