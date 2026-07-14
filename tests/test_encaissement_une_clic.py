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

import ast

from lxml import etree
from odoo.exceptions import UserError
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


@tagged('souscriptions', 'souscriptions_paiements', 'post_install', '-at_install')
class TestJournalEspecesField(SouscriptionsTestCase):
    """AC : `res.company.journal_especes_id`, `Many2one('account.journal',
    domain=[('type','=','cash')], check_company=True)` (#298, ADR 0033
    amendé) — même idiome que `journal_monnaie_locale_id`."""

    def test_champ_existe_domaine_cash_check_company(self):
        field = self.env['res.company']._fields['journal_especes_id']
        self.assertEqual(field.type, 'many2one')
        self.assertEqual(field.comodel_name, 'account.journal')
        self.assertEqual(field.domain, [('type', '=', 'cash')])
        self.assertTrue(field.check_company)

    def test_champ_se_pose_et_se_lit(self):
        journal = self.env['account.journal'].create(
            {'name': 'Caisse Test', 'code': 'CAISS', 'type': 'cash', 'company_id': self.env.company.id}
        )
        self.env.company.journal_especes_id = journal
        self.assertEqual(self.env.company.journal_especes_id, journal)


@tagged('souscriptions', 'souscriptions_paiements', 'post_install', '-at_install')
class TestResoudreJournalEncaissement(SouscriptionsTestCase):
    """`account.move._resoudre_journal_encaissement()` : résolution jamais
    par nom, garde explicite si absent/ambigu (même idiome que
    `souscription.sepa.mandat._resoudre_journal_sdd`)."""

    def _facture_avec_mode(self, mode_paiement, **periode_kwargs):
        self.souscription_base.mode_paiement = mode_paiement
        periode, facture = self.create_test_invoice(self.souscription_base, **periode_kwargs)
        facture.action_post()
        return facture

    def _isoler_journaux_cash(self):
        """Neutralise les journaux `cash` préexistants de la société (données
        de démo/fixtures) pour rendre le test déterministe — la garde
        cotise ensuite les journaux qu'on pose nous-mêmes, jamais un mélange
        avec l'état ambiant."""
        self.env['account.journal'].search([('type', '=', 'cash'), ('company_id', '=', self.env.company.id)]).write(
            {'active': False}
        )

    # -- monnaie_locale --

    def test_monnaie_locale_resout_le_journal_configure(self):
        journal = self.env['account.journal'].create(
            {'name': 'Moneko', 'code': 'MNLO', 'type': 'bank', 'company_id': self.env.company.id}
        )
        self.env.company.journal_monnaie_locale_id = journal
        facture = self._facture_avec_mode('monnaie_locale')
        self.assertEqual(facture._resoudre_journal_encaissement(), journal)

    def test_monnaie_locale_absent_leve_erreur_explicite(self):
        self.assertFalse(self.env.company.journal_monnaie_locale_id)
        facture = self._facture_avec_mode('monnaie_locale')
        with self.assertRaises(UserError) as cm:
            facture._resoudre_journal_encaissement()
        self.assertIn('Journal monnaie locale', str(cm.exception))

    # -- especes --

    def test_especes_resout_le_journal_cash_unique(self):
        self._isoler_journaux_cash()
        journal = self.env['account.journal'].create(
            {'name': 'Caisse Test', 'code': 'CAISS', 'type': 'cash', 'company_id': self.env.company.id}
        )
        facture = self._facture_avec_mode('especes')
        self.assertEqual(facture._resoudre_journal_encaissement(), journal)

    def test_especes_absent_leve_erreur(self):
        self._isoler_journaux_cash()
        facture = self._facture_avec_mode('especes')
        with self.assertRaises(UserError) as cm:
            facture._resoudre_journal_encaissement()
        self.assertIn('Aucun journal de caisse', str(cm.exception))

    def test_especes_ambigu_leve_erreur(self):
        self._isoler_journaux_cash()
        self.env['account.journal'].create(
            {'name': 'Caisse A', 'code': 'CAA', 'type': 'cash', 'company_id': self.env.company.id}
        )
        self.env['account.journal'].create(
            {'name': 'Caisse B', 'code': 'CAB', 'type': 'cash', 'company_id': self.env.company.id}
        )
        facture = self._facture_avec_mode('especes')
        with self.assertRaises(UserError) as cm:
            facture._resoudre_journal_encaissement()
        self.assertIn('Plusieurs', str(cm.exception))

    # -- mode hors attestation-pure : défensif, ne devrait jamais être appelé
    # (le bouton ne l'exhibe pas) mais ne devine jamais un journal si un
    # appelant le fait quand même. --

    def test_mode_hors_attestation_pure_leve_erreur(self):
        facture = self._facture_avec_mode('virement')
        with self.assertRaises(UserError):
            facture._resoudre_journal_encaissement()


@tagged('souscriptions', 'souscriptions_paiements', 'post_install', '-at_install')
class TestActionEncaisser(SouscriptionsTestCase):
    """`account.move.action_encaisser()` : effet observable du bouton
    une-clic (#290, ADR 0033) — paiement créé/posté/lettré, résidu à zéro,
    sortie du domaine de l'action « Règlements en attente », et le paiement
    ne naît qu'au clic, jamais à l'émission seule."""

    def _facture_avec_mode(self, mode_paiement, **periode_kwargs):
        self.souscription_base.mode_paiement = mode_paiement
        periode, facture = self.create_test_invoice(self.souscription_base, **periode_kwargs)
        facture.action_post()
        return facture

    def _isoler_journaux_cash(self):
        self.env['account.journal'].search([('type', '=', 'cash'), ('company_id', '=', self.env.company.id)]).write(
            {'active': False}
        )

    def _dans_la_vue(self, facture):
        action = self.env.ref('souscriptions_odoo.action_facture_reglements_attente')
        domaine = ast.literal_eval(action.domain)
        return facture in self.env['account.move'].search(domaine + [('id', '=', facture.id)])

    def test_especes_solde_la_facture_et_la_sort_de_la_vue(self):
        self._isoler_journaux_cash()
        journal = self.env['account.journal'].create(
            {'name': 'Caisse Test', 'code': 'CAISS', 'type': 'cash', 'company_id': self.env.company.id}
        )
        facture = self._facture_avec_mode('especes')
        residuel_avant = facture.amount_residual
        self.assertGreater(residuel_avant, 0.0)
        self.assertTrue(self._dans_la_vue(facture))

        facture.action_encaisser()
        facture.invalidate_recordset(['amount_residual', 'payment_state'])

        self.assertAlmostEqual(facture.amount_residual, 0.0, places=2)
        self.assertEqual(facture.payment_state, 'paid')
        self.assertFalse(self._dans_la_vue(facture))

        paiement = self.env['account.payment'].search([('partner_id', '=', facture.partner_id.id)])
        self.assertEqual(len(paiement), 1)
        self.assertEqual(paiement.journal_id, journal)
        self.assertEqual(paiement.payment_type, 'inbound')
        self.assertAlmostEqual(paiement.amount, residuel_avant, places=2)

    def test_monnaie_locale_solde_la_facture_et_la_sort_de_la_vue(self):
        journal = self.env['account.journal'].create(
            {'name': 'Moneko', 'code': 'MNLO', 'type': 'bank', 'company_id': self.env.company.id}
        )
        self.env.company.journal_monnaie_locale_id = journal
        facture = self._facture_avec_mode('monnaie_locale')
        self.assertGreater(facture.amount_residual, 0.0)

        facture.action_encaisser()
        facture.invalidate_recordset(['amount_residual', 'payment_state'])

        self.assertAlmostEqual(facture.amount_residual, 0.0, places=2)
        self.assertEqual(facture.payment_state, 'paid')
        self.assertFalse(self._dans_la_vue(facture))

        paiement = self.env['account.payment'].search([('partner_id', '=', facture.partner_id.id)])
        self.assertEqual(len(paiement), 1)
        self.assertEqual(paiement.journal_id, journal)

    def test_paiement_nait_seulement_au_clic_jamais_a_lemission(self):
        """AC : le paiement n'existe qu'après le clic — l'émission seule
        (action_post) ne crée ni ne réconcilie rien."""
        self._isoler_journaux_cash()
        self.env['account.journal'].create(
            {'name': 'Caisse Test', 'code': 'CAISS', 'type': 'cash', 'company_id': self.env.company.id}
        )
        facture = self._facture_avec_mode('especes')

        self.assertGreater(facture.amount_residual, 0.0)
        self.assertFalse(self.env['account.payment'].search([('partner_id', '=', facture.partner_id.id)]))

    def test_journal_absent_ne_cree_aucun_paiement(self):
        """AC : journal cible absent -> UserError, aucun paiement créé (pas
        de repli deviné)."""
        self.assertFalse(self.env.company.journal_monnaie_locale_id)
        facture = self._facture_avec_mode('monnaie_locale')

        with self.assertRaises(UserError):
            facture.action_encaisser()

        self.assertFalse(self.env['account.payment'].search([('partner_id', '=', facture.partner_id.id)]))
        self.assertGreater(facture.amount_residual, 0.0)


@tagged('souscriptions', 'souscriptions_paiements', 'post_install', '-at_install')
class TestBoutonEncaisserVisibilite(SouscriptionsTestCase):
    """AC : le bouton n'apparaît que pour `mode_paiement ∈ {monnaie_locale,
    especes}` ET `amount_residual > 0` — absent pour prélèvement / virement /
    chèque et pour le groupe « (vide) ». Assertion structurelle sur l'arch
    résolu (lxml), même méthode que `test_facture_provenance.py`/
    `test_souscription_form.py` — pas de rendu client réel."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        action = cls.env.ref('souscriptions_odoo.action_facture_reglements_attente')
        view = cls.env['account.move'].get_view(view_id=action.view_id.id, view_type='list')
        cls.arch = etree.fromstring(view['arch'])

    def test_action_pointe_la_vue_dediee(self):
        action = self.env.ref('souscriptions_odoo.action_facture_reglements_attente')
        self.assertEqual(action.view_id, self.env.ref('souscriptions_odoo.view_move_reglements_attente_list'))

    def test_bouton_present_avec_condition_mode_et_residuel(self):
        bouton = self.arch.find(".//button[@name='action_encaisser']")
        self.assertIsNotNone(bouton, 'le bouton action_encaisser doit être dans la vue liste dédiée')
        invisible = bouton.get('invisible')
        self.assertIn('monnaie_locale', invisible)
        self.assertIn('especes', invisible)
        self.assertIn('amount_residual', invisible)

        # Les modes bancaire-rapprochable et le prélèvement doivent être hors
        # de l'ensemble autorisé — jamais de bouton pour eux (100 % natif).
        for mode in ('prelevement', 'virement', 'cheque'):
            self.assertNotIn(f"'{mode}'", invisible)

    def test_champs_conditionnants_charges_dans_la_vue(self):
        """`mode_paiement` et `amount_residual` doivent être chargés (au
        moins en colonne) pour que la condition `invisible` soit évaluable
        par ligne — même garde que `test_facture_provenance.py`."""
        self.assertTrue(self.arch.findall(".//field[@name='mode_paiement']"))
        self.assertTrue(self.arch.findall(".//field[@name='amount_residual']"))
