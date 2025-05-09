from odoo import models, fields, api

class SouscriptionPeriode(models.Model):
    _name = 'souscription.periode'
    _description = 'Période de facturation énergétique'
    _order = 'date_debut'

    souscription_id = fields.Many2one('souscription', required=True, ondelete='cascade', string='Souscription')
    
    date_debut = fields.Date(required=True)
    date_fin = fields.Date(required=True)

    jours = fields.Integer(compute='_compute_jours', store=True)
    energie_kwh = fields.Float(string='Énergie consommée (kWh)')
    
    turpe_fixe = fields.Float(string='TURPE Fixe (€)')
    turpe_variable = fields.Float(string='TURPE Variable (€)')

    facture_id = fields.Many2one('account.move', string='Facture associée')

    @api.depends('date_debut', 'date_fin')
    def _compute_jours(self):
        for p in self:
            if p.date_debut and p.date_fin:
                p.jours = (p.date_fin - p.date_debut).days
            else:
                p.jours = 0
