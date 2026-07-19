"""Chèque énergie — tiers-payeur (ADR 0026).

Trois niveaux, tous rapatriés sur le modèle par #255 (revue d'architecture,
« le Chèque énergie possède toute son histoire ») : la config comptable
posée par `_setup_compta()` (#170 — journal « Chèques énergie » + compte
« à recevoir de l'État »), le modèle propre `souscription.cheque_energie` et
son gate `action_valider()` (#171 — couture 1), puis l'imputation FIFO
`imputer()` (#172 ; déplacée de la création à l'émission par #265). Le
câblage au point de couture de l'émission (`account.move._post()`) est
couvert en intégration côté `test_periode_facture.py`.
"""

from datetime import date

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged
from odoo.tools import mute_logger
from psycopg2 import IntegrityError

from .common import SouscriptionsTestCase


@tagged('souscriptions', 'souscriptions_cheque_energie', 'post_install', '-at_install')
class TestChequeEnergieConfig(TransactionCase):
    """#170 : le setup pose le journal + le compte, idempotent.

    Note : on exerce `_setup_compta()` directement plutôt que de dépendre de
    la persistance du `post_init_hook` (shim `hooks.setup_cheque_energie_compta`,
    rapatrié sur le modèle par #255 — même code path, pas de test dédié au
    shim). En install *sans plan comptable préexistant* (CI/test), le
    provisioning du plan comptable par le module `account`
    (`chart_template._load`) *purge* en fin d'install les journaux/comptes
    « nus » — dont ceux posés par notre post_init. En prod (plan comptable
    déjà en place) ils survivent, et `action_valider` les (re)pose de toute
    façon à la volée (get-or-create). Le livrable #170, c'est la *méthode*
    de setup : c'est elle qu'on teste ici."""

    def test_journal_et_compte_existent(self):
        journal = self.env['souscription.cheque_energie']._setup_compta()
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
        Cheque = self.env['souscription.cheque_energie']
        Cheque._setup_compta()
        Cheque._setup_compta()

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
        """Un `numero` déjà utilisé par un autre chèque est refusé (unicité,
        portée par une contrainte SQL — #355)."""
        self._new_cheque(numero='CHQ-DUP')
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'), self.cr.savepoint():
            self._new_cheque(numero='CHQ-DUP')

    def test_cheques_projetes_sur_la_souscription_par_partner(self):
        """La fiche souscription projette les chèques de son partner, pas ceux
        des autres (rattachement par partner_id, ADR 0026)."""
        du_souscripteur = self._new_cheque(numero='CHQ-PROJ-1')
        self._new_cheque(numero='CHQ-PROJ-2', partner_id=self.partner_company.id)

        self.assertEqual(self.souscription_base.cheque_energie_ids, du_souscripteur)


@tagged('souscriptions', 'souscriptions_cheque_energie', 'post_install', '-at_install')
class TestChequeEnergieImputer(SouscriptionsTestCase):
    """#172/#265, rapatriée par #255 (revue d'architecture) : `imputer()`
    porte toute la règle — validés seuls, solde > 0, FIFO par expiration,
    plafond `min(solde, total)`, lettrage natif délégué (`_seek_for_lines()`
    + `reconcile()`, ADR 0026). Testée directement contre une Facture
    `out_invoice` NUE (ni `periode_id` ni `regularisation_id`) : le câblage
    réel (`account.move._post()` -> `imputer()`) est couvert une seule fois,
    en intégration, côté `test_periode_facture.py`."""

    def _new_cheque(self, **kwargs):
        vals = {
            'numero': 'CHQ-IMP-A',
            'partner_id': self.partner_test.id,
            'montant': 10.0,
            'date_reception': date(2024, 1, 5),
            'date_expiration': date(2025, 3, 31),
        }
        vals.update(kwargs)
        return self.env['souscription.cheque_energie'].create(vals)

    def _new_facture(self, total, partner=None):
        """Facture `out_invoice` NUE et déjà POSTÉE : `imputer()` délègue au
        lettrage natif, qui exige des écritures postées des deux côtés — la
        Facture n'étant ni Période ni Régularisation (`is_facture_energie`
        False), `account.move._post()` ne déclenche pas lui-même `imputer()`
        ici, la couture reste isolée pour ces tests."""
        produit = self.env.ref('souscriptions_odoo.souscriptions_product_energie_base')
        facture = self.env['account.move'].create(
            {
                'move_type': 'out_invoice',
                'partner_id': (partner or self.partner_test).id,
                'invoice_date': date(2024, 1, 31),
                'invoice_line_ids': [(0, 0, {'product_id': produit.id, 'quantity': 1.0, 'price_unit': total})],
            }
        )
        facture.action_post()
        return facture

    def test_cheque_valide_impute_plafonne_a_min_solde_total(self):
        """Plafond `min(solde, total)`, jamais de résiduel négatif : un chèque
        plus gros que la Facture l'épuise sans la rendre négative."""
        cheque = self._new_cheque(montant=1000.0)
        cheque.action_valider()
        facture = self._new_facture(10.0)

        consommes = self.env['souscription.cheque_energie'].imputer(facture)

        self.assertEqual(consommes, cheque)
        self.assertAlmostEqual(facture.amount_residual, 0.0, places=2)
        self.assertGreaterEqual(facture.amount_residual, 0.0)
        self.assertAlmostEqual(cheque.solde, 990.0, places=2)

    def test_aucun_cheque_valide_no_op(self):
        """Un chèque 'reçu' (non validé) n'impute rien : la Facture garde son
        residual plein (non-régression #170/#265) — l'état est la seule porte."""
        self._new_cheque(montant=1000.0)  # jamais validé
        facture = self._new_facture(10.0)
        residual_avant = facture.amount_residual

        consommes = self.env['souscription.cheque_energie'].imputer(facture)

        self.assertFalse(consommes)
        self.assertAlmostEqual(facture.amount_residual, residual_avant, places=2)

    def test_cheque_valide_expire_reste_imputable(self):
        """Contrat figé (#255, grill 2026-07-13) : l'expiration ne borne QUE
        la validation, jamais l'imputation — un chèque validé à date passée
        reste imputable, seul `state == 'valide'` fait foi."""
        cheque = self._new_cheque(montant=10.0, date_expiration=date(2020, 1, 1))
        cheque.action_valider()
        facture = self._new_facture(10.0)

        consommes = self.env['souscription.cheque_energie'].imputer(facture)

        self.assertEqual(consommes, cheque)
        self.assertAlmostEqual(facture.amount_residual, 0.0, places=2)

    def test_fifo_par_expiration_le_plus_proche_consomme_en_premier(self):
        """Deux chèques validés : celui qui périme le plus tôt est consommé
        en premier, quel que soit l'ordre de création/montant."""
        cheque_tardif = self._new_cheque(numero='CHQ-IMP-TARD', montant=1000.0, date_expiration=date(2026, 3, 31))
        cheque_tardif.action_valider()
        cheque_proche = self._new_cheque(numero='CHQ-IMP-PROCHE', montant=5.0, date_expiration=date(2024, 3, 31))
        cheque_proche.action_valider()
        facture = self._new_facture(10.0)

        consommes = self.env['souscription.cheque_energie'].imputer(facture)

        self.assertEqual(set(consommes.ids), {cheque_proche.id, cheque_tardif.id})
        self.assertAlmostEqual(cheque_proche.solde, 0.0, places=2)
        self.assertAlmostEqual(cheque_tardif.solde, 1000.0 - 5.0, places=2)
        self.assertAlmostEqual(facture.amount_residual, 0.0, places=2)

    def test_reliquat_se_reporte_sur_la_facture_suivante(self):
        """Un chèque plus gros qu'une Facture se reporte sur la Facture
        suivante jusqu'à épuisement — report natif du lettrage, pas de code
        métier. Chaque Facture est imputée séparément."""
        cheque = self._new_cheque(montant=1000.0)
        cheque.action_valider()

        facture_janvier = self._new_facture(10.0)
        self.env['souscription.cheque_energie'].imputer(facture_janvier)
        solde_apres_janvier = cheque.solde
        self.assertGreater(solde_apres_janvier, 0.0)

        facture_fevrier = self._new_facture(15.0)
        self.env['souscription.cheque_energie'].imputer(facture_fevrier)

        self.assertAlmostEqual(facture_fevrier.amount_residual, 0.0, places=2)
        self.assertAlmostEqual(cheque.solde, solde_apres_janvier - 15.0, places=2)
