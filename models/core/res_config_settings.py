from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    """Amorce de la page « Souscriptions » sous Paramètres (#291).

    Seed d'un chantier de configuration plus large (journaux, seuils,
    paramètres electricore…) — le périmètre complet reste à cadrer en
    session dédiée. Cette tranche n'expose que le pointeur posé sur
    `res.company` par le chantier « Encaissement une-clic » (#290, ADR 0033),
    via le `related` idiomatique (`readonly=False` pour le rendre éditable et
    persisté par société).
    """

    _inherit = 'res.config.settings'

    journal_monnaie_locale_id = fields.Many2one(
        'account.journal',
        related='company_id.journal_monnaie_locale_id',
        readonly=False,
        string='Journal monnaie locale',
        domain=[('type', '=', 'bank')],
        check_company=True,
    )
