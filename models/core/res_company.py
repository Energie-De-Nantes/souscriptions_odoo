from odoo import fields, models


class ResCompany(models.Model):
    """Pointeur de rôle « journal monnaie locale » (#290, ADR 0033).

    Calqué sur `res.company.currency_exchange_journal_id` du core : « Moneko »
    est un rôle nommé parmi plusieurs journaux `bank` que `type` seul ne sait
    pas distinguer — jamais résolu par nom (idiome confirmé par
    `_resoudre_journal_sdd`). Consommé par
    `account.move._resoudre_journal_encaissement()` pour le mode de paiement
    `monnaie_locale` de l'encaissement une-clic.

    Exposition dans `res.config.settings` « Souscriptions » : hors périmètre
    de #290, chantier propre (#291) — ce champ la prépare sans rework.
    """

    _inherit = 'res.company'

    journal_monnaie_locale_id = fields.Many2one(
        'account.journal',
        string='Journal monnaie locale',
        domain=[('type', '=', 'bank')],
        check_company=True,
        help='Journal bancaire dédié à la monnaie locale (Moneko) — cible de '
        "l'encaissement une-clic pour le mode de paiement « monnaie locale ».",
    )
