from odoo import models, fields

class AccountMove(models.Model):
    _inherit = 'account.move'

    periode_id = fields.Many2one('souscription.periode', string='Période facturée')

    souscription_id = fields.Many2one(
        related='periode_id.souscription_id',
        string="Souscription",
        store=True,
        readonly=True,
    )
