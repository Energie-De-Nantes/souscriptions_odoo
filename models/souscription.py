from odoo import models, fields, api

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
    date_debut = fields.Date(string='Date de début')
    date_fin = fields.Date(string='Date de fin')
    active = fields.Boolean(string='Active', default=True)
    etat_facturation_id = fields.Many2one(
        'souscription.etat',
        string="État de facturation",
        required=True
    )
    facture_ids = fields.One2many('account.move', 'souscription_id', string='Factures')

    # Données métier 

    ## Utiles facturation
    puissance_souscrite = fields.Integer(
        string='Puissance souscrite (kVA)', 
        required=True,
        tracking=True)
    type_tarif = fields.Selection(
        [('base', 'Base'), ('hphc', 'Heures Pleines / Heures Creuses')],
        default='base',
        string='Type de tarif',
        required=True,
        tracking=True
    )

    ## Informations
    ref_compteur = fields.Char(string="Référence compteur")
    numero_depannage = fields.Char(string="Numéro de dépannage")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nouveau') == 'Nouveau':
                vals['name'] = self.env['ir.sequence'].next_by_code('souscription.sequence') or 'Nouveau'
        return super().create(vals_list)
    
    def action_creer_facture(self):
        self.ensure_one()
        facture = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner_id.id,
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