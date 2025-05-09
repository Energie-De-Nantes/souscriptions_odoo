from odoo import models, fields, api
from babel.dates import format_date

class SouscriptionPeriode(models.Model):
    _name = 'souscription.periode'
    _description = 'Période de facturation énergétique'
    _order = 'date_debut'

    souscription_id = fields.Many2one('souscription', required=True, ondelete='cascade', string='Souscription')
    
    date_debut = fields.Date(required=True)
    date_fin = fields.Date(required=True)
    mois_annee = fields.Char(string='Mois', compute='_compute_mois_annee', store=True, readonly=True)

    lisse = fields.Boolean(related='souscription_id.lisse', string='Lissé', store=True)

    jours = fields.Integer(compute='_compute_jours', store=True)
    energie_kwh = fields.Float(string='Énergie consommée (kWh)')
    provision_kwh = fields.Float(
        string='Énergie provisionnée (kWh)',
        compute='_compute_provision_kwh',
        store=True,
    )
    _fix_provision = fields.Boolean(default=False)
    
    turpe_fixe = fields.Float(string='TURPE Fixe (€)')
    turpe_variable = fields.Float(string='TURPE Variable (€)')

    facture_id = fields.Many2one('account.move', string='Facture associée')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            sous = self.env['souscription'].browse(vals['souscription_id'])

            if sous.lisse and sous.provision_mensuelle_kwh:
                vals['provision_kwh'] = sous.provision_mensuelle_kwh
                vals['_fix_provision'] = True

        return super().create(vals_list)
    
    @api.depends('date_debut', 'date_fin')
    def _compute_jours(self):
        for p in self:
            if p.date_debut and p.date_fin:
                p.jours = (p.date_fin - p.date_debut).days
            else:
                p.jours = 0

    @api.depends('energie_kwh')
    def _compute_provision_kwh(self):
        for p in self:
            if not p._fix_provision:
                p.provision_kwh = p.energie_kwh
                

    @api.depends('date_debut')
    def _compute_mois_annee(self):
        for rec in self:
            if rec.date_debut:
                rec.mois_annee = format_date(rec.date_debut, format='MMMM yyyy', locale='fr_FR').capitalize()
            else:
                rec.mois_annee = ''
