from odoo import fields, models


class ResCompany(models.Model):
    """Pointeurs de rôle sur journal possédé par la société (#290/#292/#298,
    ADR 0033).

    Calqués sur `res.company.currency_exchange_journal_id` / `res.company.
    tax_cash_basis_journal_id` du core : un rôle de journal possédé par la
    société est un pointeur `Many2one` sur `res.company`, jamais résolu par
    `type` — `type` regroupe une FAMILLE de journaux, il ne nomme pas un rôle
    singulier. « Moneko » et le journal de prélèvement SDD sont des rôles
    nommés parmi plusieurs journaux `bank` que `type` ne sait pas distinguer ;
    la caisse espèces est un rôle nommé parmi plusieurs journaux `cash` (le
    journal CHEN du chèque énergie, posé par le `post_init_hook` à chaque
    install, en est un autre) que `type` ne sait pas distinguer non plus.
    Consommés par `account.move._resoudre_journal_encaissement()` (modes
    `monnaie_locale` / `especes` de l'encaissement une-clic) et par
    `souscription.sepa.mandat._resoudre_journal_sdd()`.

    Exposition dans `res.config.settings` « Souscriptions » : hors périmètre
    de #290/#292/#298, chantier propre (#291) — ces champs la préparent sans
    rework.
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

    journal_especes_id = fields.Many2one(
        'account.journal',
        string='Journal espèces',
        domain=[('type', '=', 'cash')],
        check_company=True,
        help="Journal de caisse dédié aux espèces — cible de l'encaissement "
        'une-clic pour le mode de paiement « espèces ». Robuste au journal '
        "CHEN du chèque énergie (autre journal type='cash' de la société) "
        'car ce pointeur nomme LE journal, jamais deviné par type.',
    )
