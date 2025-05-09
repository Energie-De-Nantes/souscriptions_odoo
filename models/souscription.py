from odoo import models, fields

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

    name = fields.Char(string='Nom', required=True, tracking=True)
    client_id = fields.Many2one('res.partner', string='Client')
    date_debut = fields.Date(string='Date de début')
    date_fin = fields.Date(string='Date de fin')
    active = fields.Boolean(string='Active', default=True)
    etat_facturation_id = fields.Many2one(
        'souscription.etat',
        string="État de facturation",
        required=True
    )
    facture_ids = fields.One2many('account.move', 'souscription_id', string='Factures')

    def action_creer_facture(self):
        self.ensure_one()
        facture = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.client_id.id,
            'invoice_date': fields.Date.today(),
            'souscription_id': self.id,
            'invoice_line_ids': [(0, 0, {
                'name': f'Facture liée à la souscription {self.name}',
                'quantity': 1,
                'price_unit': 100.0,  # ou dynamique
            })],
        })
        return {
            'type': 'ir.actions.act_window',
            'name': 'Facture',
            'res_model': 'account.move',
            'res_id': facture.id,
            'view_mode': 'form',
            'target': 'current',
        }