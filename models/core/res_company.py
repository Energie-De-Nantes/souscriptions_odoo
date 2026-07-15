from odoo import fields, models


class ResCompany(models.Model):
    """Pointeurs de rôle sur journal bancaire (#290/#292, ADR 0033).

    Calqués sur `res.company.currency_exchange_journal_id` du core : un rôle
    nommé parmi plusieurs journaux `bank` que `type` seul ne sait pas
    distinguer — jamais résolu par nom.

    Exposition dans `res.config.settings` « Souscriptions » : hors périmètre,
    chantier propre (#291) — ces champs la préparent sans rework.
    """

    _inherit = 'res.company'

    journal_monnaie_locale_id = fields.Many2one(
        'account.journal',
        string='Journal monnaie locale',
        domain=[('type', '=', 'bank')],
        check_company=True,
        help='Journal bancaire dédié à la monnaie locale (Moneko) — cible de '
        "l'encaissement une-clic pour le mode de paiement « monnaie locale ». "
        'Consommé par `account.move._resoudre_journal_encaissement()` (#290).',
    )

    journal_prelevement_sdd_id = fields.Many2one(
        'account.journal',
        string='Journal de prélèvement SDD',
        domain=[('type', '=', 'bank')],
        check_company=True,
        help='Journal portant la méthode SDD à utiliser pour les mandats de prélèvement '
        "quand plusieurs journaux l'exposent (#292). Consommé par "
        '`souscription.sepa.mandat._resoudre_journal_sdd()`.',
    )
