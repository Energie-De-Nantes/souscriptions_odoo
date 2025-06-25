from odoo import models, fields, api
import json

class AccountMove(models.Model):
    _inherit = 'account.move'

    periode_id = fields.Many2one('souscription.periode', string='Période facturée')

    souscription_id = fields.Many2one(
        related='periode_id.souscription_id',
        string="Souscription",
        store=True,
        readonly=True,
    )

    is_facture_energie = fields.Boolean(
        string="Facture d'énergie", 
        compute='_compute_is_facture_energie',
        store=True
    )

    @api.depends('periode_id', 'souscription_id')
    def _compute_is_facture_energie(self):
        """Détermine si c'est une facture d'énergie (souscription électricité)"""
        for move in self:
            move.is_facture_energie = bool(move.periode_id and move.souscription_id)

    def _get_report_base_filename(self):
        """Nom de fichier personnalisé pour les factures d'énergie"""
        self.ensure_one()
        if self.is_facture_energie and self.souscription_id:
            return f"Facture_Energie_{self.souscription_id.name}_{self.name}"
        return super()._get_report_base_filename()

    def get_historical_consumption_data(self):
        """Récupère les données de consommation des 12 dernières périodes pour le graphique"""
        self.ensure_one()
        if not self.souscription_id:
            return {}
        
        # Récupérer les 12 dernières périodes facturées (hors période courante)
        periodes = self.env['souscription.periode'].search([
            ('souscription_id', '=', self.souscription_id.id),
            ('id', '!=', self.periode_id.id if self.periode_id else False),
            ('facture_id', '!=', False)  # Seulement les périodes facturées
        ], order='date_debut desc', limit=12)
        
        if not periodes:
            return {}
        
        # Construire les données pour le graphique
        labels = []
        data_base = []
        data_hp = []
        data_hc = []
        
        # Inverser l'ordre pour avoir chronologique (du plus ancien au plus récent)
        for periode in reversed(periodes):
            labels.append(periode.mois_annee)
            
            if self.souscription_id.type_tarif == 'base':
                # Pour BASE, additionner tous les cadrans
                total_kwh = (periode.energie_hph_kwh + periode.energie_hpb_kwh + 
                           periode.energie_hch_kwh + periode.energie_hcb_kwh)
                data_base.append(round(total_kwh, 2))
            else:
                # Pour HP/HC, séparer HP et HC
                hp_kwh = periode.energie_hph_kwh + periode.energie_hpb_kwh
                hc_kwh = periode.energie_hch_kwh + periode.energie_hcb_kwh
                data_hp.append(round(hp_kwh, 2))
                data_hc.append(round(hc_kwh, 2))
        
        return {
            'has_data': len(labels) > 0,
            'type_tarif': self.souscription_id.type_tarif,
            'labels': labels,
            'data_base': data_base,
            'data_hp': data_hp, 
            'data_hc': data_hc,
            'nb_periodes': len(labels)
        }
    
    def get_historical_consumption_data_json(self):
        """Retourne les données de consommation au format JSON pour le template"""
        self.ensure_one()
        data = self.get_historical_consumption_data()
        return json.dumps(data) if data else '{}'
