"""Chèque énergie — tiers-payeur (ADR 0026).

Config comptable posée par `hooks.setup_cheque_energie_compta` (#170 —
journal « Chèques énergie » + compte « à recevoir de l'État »). Le modèle
propre `souscription.cheque_energie` (#171) et l'imputation FIFO à la
facturation (#172) sont testés dans des slices suivantes.
"""

from odoo.tests.common import TransactionCase, tagged


@tagged('souscriptions', 'souscriptions_cheque_energie', 'post_install', '-at_install')
class TestChequeEnergieConfig(TransactionCase):
    """#170 : le journal + le compte existent après install, posés idempotents."""

    def test_journal_et_compte_existent(self):
        journal = self.env.ref('souscriptions_odoo.souscriptions_journal_cheque_energie')
        compte = self.env.ref('souscriptions_odoo.souscriptions_account_cheque_energie_a_recevoir')

        self.assertEqual(journal.type, 'cash')
        self.assertEqual(journal.default_account_id, compte)
        self.assertEqual(compte.account_type, 'asset_current')

        # Outstanding receipts account posé explicitement sur la méthode de
        # paiement entrante : sans lui, action_post() sur un account.payment
        # échoue dès que la comptabilité complète est installée (cf. hooks.py).
        self.assertTrue(journal.inbound_payment_method_line_ids)
        self.assertEqual(journal.inbound_payment_method_line_ids.payment_account_id, compte)

    def test_setup_idempotent_sur_reexecution(self):
        """Rejouer le setup (upgrade répété) ne duplique ni le journal ni le compte."""
        from odoo.addons.souscriptions_odoo.hooks import setup_cheque_energie_compta

        setup_cheque_energie_compta(self.env)

        self.assertEqual(self.env['account.journal'].search_count([('code', '=', 'CHEN')]), 1)
        self.assertEqual(self.env['account.account'].search_count([('code', '=', '511800')]), 1)
