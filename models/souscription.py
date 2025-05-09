from odoo import models, fields, api
from odoo.exceptions import UserError
from datetime import date, timedelta

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
    facture_ids = fields.One2many(
        'account.move',
        'souscription_id',
        string='Factures')
    periode_ids = fields.One2many(
        'souscription.periode', 
        'souscription_id', 
        string='Périodes de facturation'
    )
    # Données métier 

    ## Utiles facturation
    lisse = fields.Boolean(string='Lissé', default=False)
    puissance_souscrite = fields.Selection(
    selection=[
        ('3', '3 kVA'),
        ('6', '6 kVA'),
        ('9', '9 kVA'),
        ('12', '12 kVA'),
        ('15', '15 kVA'),
        ('18', '18 kVA'),
        ('24', '24 kVA'),
        ('30', '30 kVA'),
        ('36', '36 kVA'),
    ],
    string='Puissance souscrite (kVA)',
    required=True,
    tracking=True
    )
    provision_mensuelle_kwh = fields.Float(
        string="Provision mensuelle (kWh)",
        help="Énergie estimée mensuelle à facturer si lissage activé.",
        tracking=True
    )
    type_tarif = fields.Selection(
        [('base', 'Base'), ('hphc', 'Heures Pleines / Heures Creuses')],
        default='base',
        string='Type de tarif',
        required=True,
        tracking=True
    )
    tarif_solidaire = fields.Boolean(string="Tarif solidaire", default=False, tracking=True)


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
        
        #factures = self.env['account.move']

        _logger.info(f"Créer factures appelé pour {len(self)} souscriptions")

        for souscription in self:
            if not souscription.partner_id or not souscription.puissance_souscrite:
                continue

            product_template = self.env.ref(
                'souscriptions.souscriptions_product_template_abonnement_solidaire'
                if souscription.tarif_solidaire
                else 'souscriptions.souscriptions_product_template_abonnement'
            )

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
    @api.model
    def ajouter_periodes_mensuelles(self):
        """
        Crée une période de facturation (du 1er au dernier jour du mois précédent)
        pour chaque souscription active.
        """
        # Calcul du 1er jour du mois en cours
        premier_mois_courant = date.today().replace(day=1)

        # 1er jour du mois précédent
        premier_mois_precedent = (premier_mois_courant - timedelta(days=1)).replace(day=1)

        souscriptions = self.search([('active', '=', True)])
        for souscription in souscriptions:
            self.env['souscription.periode'].create({
                'souscription_id': souscription.id,
                'date_debut': premier_mois_precedent,
                'date_fin': premier_mois_courant,
                'energie_kwh': 0,
                'turpe_fixe': 0,
                'turpe_variable': 0,
            })
    
    # def button_creer_factures(self):
    #     self.creer_factures()