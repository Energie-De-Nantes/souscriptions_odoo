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