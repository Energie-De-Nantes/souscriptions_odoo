from odoo import models, fields

class MesureIndex(models.Model):
    _name = "metier.mesure.index"
    _description = "Index de consommation mensuelle"

    souscription_id = fields.Many2one("souscription", string="Souscription", required=False, index=True)
    date = fields.Date(string="Date du relevé", required=True, index=True)
    source = fields.Char(string="Source de la donnée")
    pdl = fields.Char(string="pdl")

    hph = fields.Float(string="HPH", required=False, default=None)
    hpb = fields.Float(string="HPB", required=False, default=None)
    hch = fields.Float(string="HCH", required=False, default=None)
    hcb = fields.Float(string="HCB", required=False, default=None)
    hp = fields.Float(string="HP", required=False, default=None)
    hc = fields.Float(string="HC", required=False, default=None)
    base = fields.Float(string="BASE", required=False, default=None)

    validite = fields.Selection(
        selection=[
            ('debut', 'Valide comme début'),
            ('fin', 'Valide comme fin'),
            ('both', 'Valide comme début et fin'),
            ('none', 'Non valide'),
        ],
        string="Validité",
        default='both',
        required=True,
        help=(
            "Indique si cet index peut être utilisé comme début, fin ou les deux "
            "dans un calcul d'énergie consommée. "
            "Utiliser 'Non valide' pour ignorer cet index dans les calculs automatiques."
        ),
    )

    # _sql_constraints = [
    #     ('uniq_pdl_date_source', 'unique(pdl, date, source, validite)', "Un relevé par pdl, date et source.")
    # ]