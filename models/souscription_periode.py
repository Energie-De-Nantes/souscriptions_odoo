from odoo import models, fields, api
from babel.dates import format_date

class SouscriptionPeriode(models.Model):
    _name = 'souscription.periode'
    _description = 'Période de facturation énergétique'
    _order = 'date_debut'

    souscription_id = fields.Many2one(
        'souscription', 
        required=True,
        readonly=True,
        ondelete='cascade', 
        string='Souscription')
    
    date_debut = fields.Date(required=True, readonly=True)
    date_fin = fields.Date(required=True, readonly=True)
    mois_annee = fields.Char(string='Mois', compute='_compute_mois_annee', store=True, readonly=True)

    pdl = fields.Char(string="pdl", readonly=True)
    lisse = fields.Boolean(string='Lissé', readonly=True) # related='souscription_id.lisse',  store=True)

    # Consommations détaillées par cadrans (pour calcul TURPE)
    energie_hph_kwh = fields.Float(string='Énergie HPH (kWh)', help="Heures Pleines saison Haute")
    energie_hpb_kwh = fields.Float(string='Énergie HPB (kWh)', help="Heures Pleines saison Basse")
    energie_hch_kwh = fields.Float(string='Énergie HCH (kWh)', help="Heures Creuses saison Haute")
    energie_hcb_kwh = fields.Float(string='Énergie HCB (kWh)', help="Heures Creuses saison Basse")

    # Consommations facturables (selon contrat)
    energie_hp_kwh = fields.Float(string='Énergie HP (kWh)', compute='_compute_hp_hc', store=True)
    energie_hc_kwh = fields.Float(string='Énergie HC (kWh)', compute='_compute_hp_hc', store=True)
    energie_base_kwh = fields.Float(string='Énergie BASE (kWh)', compute='_compute_base', store=True)
    
    # Provisions (lissage) - selon type de contrat
    provision_hp_kwh = fields.Float(string='Provision HP (kWh)')
    provision_hc_kwh = fields.Float(string='Provision HC (kWh)')
    provision_base_kwh = fields.Float(string='Provision BASE (kWh)')
    
    # TURPE (calculé sur tous les cadrans)
    turpe_fixe = fields.Float(string='TURPE Fixe (€)')
    turpe_variable = fields.Float(string='TURPE Variable (€)', help="Utilise HPH+HPB+HCH+HCB")
    
    # Métadonnées période
    type_periode = fields.Selection([
        ('mensuelle', 'Mensuelle'),
        ('regularisation', 'Régularisation'),
        ('ajustement', 'Ajustement')
    ], default='mensuelle', string='Type de période')
    jours = fields.Integer(compute='_compute_jours', store=True)
    
    # État de la souscription au moment de la création de la période
    # (copie en texte pour historisation - ces valeurs peuvent changer dans la souscription)
    type_tarif_periode = fields.Char(
        string='Type tarif (période)', readonly=True, 
        help="Type de tarif au moment de la création de cette période"
    )
    
    tarif_solidaire_periode = fields.Boolean(
        string="Tarif solidaire (période)", readonly=True,
        help="État du tarif solidaire au moment de la création de cette période"
    )
    
    lisse_periode = fields.Boolean(
        string='Lissé (période)', readonly=True,
        help="État du lissage au moment de la création de cette période"
    )
    
    puissance_souscrite_periode = fields.Char(
        string='Puissance souscrite (période)', readonly=True,
        help="Puissance souscrite au moment de la création de cette période"
    )
    
    provision_mensuelle_kwh_periode = fields.Float(
        string="Provision mensuelle (période)", readonly=True,
        help="Provision mensuelle au moment de la création de cette période"
    )
    
    # Compatibilité (deprecated - à supprimer plus tard)
    energie_kwh = fields.Float(string='Énergie consommée (kWh)', compute='_compute_energie_kwh_compat', store=False)
    provision_kwh = fields.Float(string='Énergie provisionnée (kWh)', compute='_compute_provision_kwh_compat', store=False)
    _fix_provision = fields.Boolean(default=False, readonly=True)

    facture_id = fields.Many2one('account.move', string='Facture associée')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            sous = self.env['souscription'].browse(vals['souscription_id'])

            # Copie de l'état de la souscription au moment de la création
            vals.update({
                'type_tarif_periode': dict(sous._fields['type_tarif'].selection).get(sous.type_tarif, sous.type_tarif),
                'tarif_solidaire_periode': sous.tarif_solidaire,
                'lisse_periode': sous.lisse,
                'puissance_souscrite_periode': f"{sous.puissance_souscrite} kVA" if sous.puissance_souscrite else '',
                'provision_mensuelle_kwh_periode': sous.provision_mensuelle_kwh,
                'pdl': sous.pdl,  # Copie du PDL aussi
                'lisse': sous.lisse,  # Compatibilité ancien champ
            })

            # Gestion des provisions selon type de tarif
            if sous.lisse and sous.provision_mensuelle_kwh:
                if sous.type_tarif == 'base':
                    vals['provision_base_kwh'] = sous.provision_mensuelle_kwh
                else:  # HP/HC - répartition temporaire 70% HP / 30% HC
                    vals['provision_hp_kwh'] = sous.provision_mensuelle_kwh * 0.7
                    vals['provision_hc_kwh'] = sous.provision_mensuelle_kwh * 0.3
                vals['_fix_provision'] = True

        return super().create(vals_list)
    
    @api.depends('date_debut', 'date_fin')
    def _compute_jours(self):
        for p in self:
            if p.date_debut and p.date_fin:
                p.jours = (p.date_fin - p.date_debut).days
            else:
                p.jours = 0

    @api.depends('energie_hph_kwh', 'energie_hpb_kwh', 'energie_hch_kwh', 'energie_hcb_kwh')
    def _compute_hp_hc(self):
        """Calcule les consommations HP/HC à partir des 4 cadrans"""
        for periode in self:
            periode.energie_hp_kwh = periode.energie_hph_kwh + periode.energie_hpb_kwh
            periode.energie_hc_kwh = periode.energie_hch_kwh + periode.energie_hcb_kwh

    @api.depends('energie_hp_kwh', 'energie_hc_kwh')  
    def _compute_base(self):
        """Calcule la consommation BASE à partir de HP+HC"""
        for periode in self:
            periode.energie_base_kwh = periode.energie_hp_kwh + periode.energie_hc_kwh
    
    @api.depends('souscription_id.type_tarif', 'souscription_id.lisse')
    def _compute_provisions(self):
        """Calcule les provisions selon le type de contrat et le lissage"""
        for periode in self:
            if periode.souscription_id.lisse:
                # Provisions fixes pour lissage - à implémenter selon les champs souscription
                # TODO: ajouter provision_mensuelle_hp_kwh, provision_mensuelle_hc_kwh, etc.
                if periode.souscription_id.type_tarif == 'base':
                    periode.provision_base_kwh = periode.souscription_id.provision_mensuelle_kwh or 0
                else:  # HP/HC - répartition à définir
                    total_provision = periode.souscription_id.provision_mensuelle_kwh or 0
                    # Répartition temporaire 70% HP / 30% HC
                    periode.provision_hp_kwh = total_provision * 0.7
                    periode.provision_hc_kwh = total_provision * 0.3
            else:
                # Provisions = consommations réelles
                periode.provision_hp_kwh = periode.energie_hp_kwh
                periode.provision_hc_kwh = periode.energie_hc_kwh
                periode.provision_base_kwh = periode.energie_base_kwh
    
    # === COMPATIBILITÉ (deprecated) ===
    
    @api.depends('energie_base_kwh')
    def _compute_energie_kwh_compat(self):
        """Compatibilité avec ancien champ energie_kwh"""
        for periode in self:
            periode.energie_kwh = periode.energie_base_kwh
    
    @api.depends('provision_base_kwh', 'provision_hp_kwh', 'provision_hc_kwh', 'souscription_id.type_tarif')
    def _compute_provision_kwh_compat(self):
        """Compatibilité avec ancien champ provision_kwh"""
        for periode in self:
            if periode.souscription_id.type_tarif == 'base':
                periode.provision_kwh = periode.provision_base_kwh
            else:
                periode.provision_kwh = periode.provision_hp_kwh + periode.provision_hc_kwh
                

    @api.depends('date_debut')
    def _compute_mois_annee(self):
        for rec in self:
            if rec.date_debut:
                rec.mois_annee = format_date(rec.date_debut, format='MMMM yyyy', locale='fr_FR').capitalize()
            else:
                rec.mois_annee = ''
