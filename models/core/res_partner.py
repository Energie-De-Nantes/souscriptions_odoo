from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # Champ d'atterrissage migration (#106, ADR 0023) : nom d'usage choisi par
    # le contact, distinct du nom légal (`name`) — repris de `x_blaze` (prod).
    blaze = fields.Char(
        string='Blaze',
        help="Nom d'usage choisi par le contact, distinct de son nom légal.",
    )
