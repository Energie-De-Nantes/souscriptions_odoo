"""Encaissement une-clic pour les modes attestation-pure (#290, ADR 0033).

Le bouton « Encaisser » de la vue « Règlements en attente » n'existe que
pour `mode_paiement ∈ {monnaie_locale, especes}` — les deux modes
attestation-pure (CONTEXT.md « Mode de paiement ») qui n'ont **aucune** trace
bancaire, jamais. Un clic délègue au wizard natif
`account.payment.register._create_payments()` (jamais réimplémenté, même
gate que `action_valider()` du chèque énergie, ADR 0026) : crée, poste et
lettre un `account.payment` entrant du reste-à-payer intégral sur le journal
résolu par `account.move._resoudre_journal_encaissement()` — jamais par nom
(même idiome que `souscription.sepa.mandat._resoudre_journal_sdd`).
"""

from odoo.tests.common import tagged

from .common import SouscriptionsTestCase

MODES_ATTESTATION_PURE = ('monnaie_locale', 'especes')


@tagged('souscriptions', 'souscriptions_paiements', 'post_install', '-at_install')
class TestJournalMonnaieLocaleField(SouscriptionsTestCase):
    """AC : `res.company.journal_monnaie_locale_id`, `Many2one('account.journal',
    domain=[('type','=','bank')], check_company=True)`."""

    def test_champ_existe_domaine_bank_check_company(self):
        field = self.env['res.company']._fields['journal_monnaie_locale_id']
        self.assertEqual(field.type, 'many2one')
        self.assertEqual(field.comodel_name, 'account.journal')
        self.assertEqual(field.domain, [('type', '=', 'bank')])
        self.assertTrue(field.check_company)

    def test_champ_se_pose_et_se_lit(self):
        journal = self.env['account.journal'].create(
            {'name': 'Monnaie locale', 'code': 'MNLO', 'type': 'bank', 'company_id': self.env.company.id}
        )
        self.env.company.journal_monnaie_locale_id = journal
        self.assertEqual(self.env.company.journal_monnaie_locale_id, journal)
