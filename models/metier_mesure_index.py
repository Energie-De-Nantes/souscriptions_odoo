from odoo import models, fields

class MesureIndex(models.Model):
    _name = "metier.mesure.index"
    _description = "Index de consommation mensuelle"

    souscription_id = fields.Many2one("souscription", string="Souscription", required=True, index=True)
    date = fields.Date(string="Date du relevé", required=True, index=True)
    source = fields.Char(String="Source de la donnée")
    pdl = fields.Char(String="pdl")

    hph = fields.Float(string="HPH")
    hpb = fields.Float(string="HPB")
    hch = fields.Float(string="HCH")
    hcb = fields.Float(string="HCB")
    hp = fields.Float(string="HP")
    hc = fields.Float(string="HC")
    base = fields.Float(string="BASE")

    _sql_constraints = [
        ('uniq_souscription_date', 'unique(souscription_id, date)', "Un relevé par mois et par souscription.")
    ]