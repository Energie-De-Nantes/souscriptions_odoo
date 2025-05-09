from odoo import models, fields

class AccountMove(models.Model):
    _inherit = 'account.move'

    souscription_id = fields.Many2one('souscription', string='Souscription')