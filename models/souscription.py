from odoo import models, fields, api
from odoo.exceptions import UserError

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
    _name = 'souscription'
    _description = 'Souscription Électricité'
    _inherit = ['mail.thread']

    name = fields.Char(string='Référence', required=True, copy=False, readonly=True, default='Nouveau')
    partner_id = fields.Many2one('res.partner', string='Souscripteur·trice')
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
    
    def creer_factures(self):
        product_template = self.env.ref('souscriptions.souscriptions_product_template_abonnement')
        factures = self.env['account.move']

        _logger.info(f"Créer factures appelé pour {len(self)} souscriptions")

        for souscription in self:
            if not souscription.partner_id or not souscription.puissance_souscrite:
                continue

            variant = product_template.product_variant_ids.filtered(
                lambda p: p.product_template_attribute_value_ids.filtered(
                    lambda v: v.attribute_id.name == 'Puissance' and v.name == f"{souscription.puissance_souscrite} kVA"
                )
            )
            if not variant:
                raise UserError(f"Aucune variante produit pour {souscription.puissance_souscrite} kVA")

            facture = self.env['account.move'].create({
                'move_type': 'out_invoice',
                'partner_id': souscription.partner_id.id,
                'invoice_date': fields.Date.today(),
                'souscription_id': souscription.id,
                'invoice_line_ids': [(0, 0, {
                    'product_id': variant.id,
                    'name': variant.name,
                    'quantity': 30.5,
                    # 'price_unit': variant.list_price,
                })],
            })

        def action_creer_factures(self):
            self.creer_factures()
            return {
                'type': 'ir.actions.act_window',
                'name': 'Factures créées',
                'res_model': 'account.move',
                'view_mode': 'tree,form',
                'domain': [('souscription_id', 'in', self.ids)],
                'target': 'current',
            }
    
    def button_creer_factures(self):
        self.creer_factures()