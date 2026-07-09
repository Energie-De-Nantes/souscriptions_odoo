"""Chèque énergie — tiers-payeur (ADR 0026).

Deux niveaux : la config comptable posée par `hooks.setup_cheque_energie_compta`
(#170 — journal « Chèques énergie » + compte « à recevoir de l'État »), puis le
modèle propre `souscription.cheque_energie` et son gate `action_valider()`
(#171 — couture 1). L'imputation FIFO à la facturation (#172) est testée côté
`test_periode_facture.py`, au point de couture le plus haut (`_creer_facture()`).
"""

from datetime import date

from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase, tagged

from .common import SouscriptionsTestCase


@tagged('souscriptions', 'souscriptions_cheque_energie', 'post_install', '-at_install')
class TestChequeEnergieConfig(TransactionCase):
    """#170 : le setup pose le journal + le compte, idempotent.

    Note : on exerce `setup_cheque_energie_compta` directement plutôt que de
    dépendre de la persistance du `post_init_hook`. En install *sans plan
    comptable préexistant* (CI/test), le provisioning du plan comptable par le
    module `account` (`chart_template._load`) *purge* en fin d'install les
    journaux/comptes « nus » — dont ceux posés par notre post_init. En prod
    (plan comptable déjà en place) ils survivent, et `action_valider` les
    (re)pose de toute façon à la volée (get-or-create). Le livrable #170, c'est
    la *fonction* de setup : c'est elle qu'on teste ici."""

    def test_journal_et_compte_existent(self):
        from odoo.addons.souscriptions_odoo.hooks import setup_cheque_energie_compta

        journal = setup_cheque_energie_compta(self.env)
        compte = self.env['account.account'].search([('code', '=', '467100')], limit=1)
        self.assertTrue(journal, 'le journal « Chèques énergie » doit être posé par le setup')
        self.assertTrue(compte, "le compte « à recevoir de l'État » doit être posé par le setup")

        self.assertEqual(journal.type, 'cash')
        self.assertEqual(journal.default_account_id, compte)
        self.assertEqual(compte.account_type, 'asset_receivable')

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
        self.assertEqual(self.env['account.account'].search_count([('code', '=', '467100')]), 1)


@tagged('souscriptions', 'souscriptions_cheque_energie', 'post_install', '-at_install')
class TestChequeEnergieModel(SouscriptionsTestCase):
    """#171, couture 1 : cycle de vie + payment posté + solde."""

    def _new_cheque(self, **kwargs):
        vals = {
            'numero': 'CHQ-0001',
            'partner_id': self.partner_test.id,
            'montant': 194.0,
            'date_reception': date(2024, 1, 5),
            'date_expiration': date(2025, 3, 31),
        }
        vals.update(kwargs)
        return self.env['souscription.cheque_energie'].create(vals)

    def test_action_valider_recu_vers_valide_cree_payment_poste(self):
        """Le gate : reçu -> validé crée et poste l'account.payment ; solde == montant."""
        cheque = self._new_cheque()
        self.assertEqual(cheque.state, 'recu')
        self.assertFalse(cheque.payment_id)

        cheque.action_valider()

        self.assertEqual(cheque.state, 'valide')
        self.assertTrue(cheque.payment_id)
        # Odoo 19 n'a pas d'état 'posted' sur account.payment (draft/in_process/
        # paid/canceled/rejected) : action_post() aboutit à 'in_process' tant que
        # le compte de liquidité du paiement (compte à recevoir, classe 4) n'est
        # pas de type asset_cash (account_payment.py:action_post()).
        self.assertEqual(cheque.payment_id.state, 'in_process')
        self.assertEqual(cheque.payment_id.payment_type, 'inbound')
        self.assertEqual(cheque.payment_id.partner_id, self.partner_test)
        self.assertEqual(cheque.payment_id.journal_id.code, 'CHEN')
        self.assertEqual(cheque.solde, cheque.montant)

    def test_action_valider_etat_interdit_leve_erreur(self):
        """Un chèque déjà validé, ou rejeté/expiré, ne peut pas être (re)validé."""
        deja_valide = self._new_cheque(numero='CHQ-0002')
        deja_valide.action_valider()
        with self.assertRaises(UserError):
            deja_valide.action_valider()

        rejete = self._new_cheque(numero='CHQ-0003')
        rejete.state = 'rejete'
        with self.assertRaises(UserError):
            rejete.action_valider()

    def test_numero_deja_saisi_refuse(self):
        """Un `numero` déjà utilisé par un autre chèque est refusé (unicité)."""
        self._new_cheque(numero='CHQ-DUP')
        with self.assertRaises(ValidationError):
            self._new_cheque(numero='CHQ-DUP')
