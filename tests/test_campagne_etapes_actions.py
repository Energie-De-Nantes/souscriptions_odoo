"""Tests des boutons d'étape de la Campagne de facturation (#158, ADR 0025).

Chaque étape délègue à une action déjà couverte ailleurs — aucune nouvelle
couture réseau : `_ouvrir_flux` (pull, cf. test_pull_meta_periodes.py) et
`_tirer_prestations` (sync F15, cf. test_sync_prestations.py) sont patchées
exactement comme dans ces suites. Créer/émettre factures délèguent à
`creer_factures()`/`action_post()`, déjà couverts par test_periode_facture.py.

Dates dans la couverture de la grille de prix fixture (2024, tests/common.py).
"""

from contextlib import contextmanager
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from odoo.addons.souscriptions_odoo.models.core import electricore_client_fabrique as fabrique_module
from odoo.addons.souscriptions_odoo.models.core import souscription_refacturation as refacturation_module
from odoo.exceptions import UserError
from odoo.tests.common import tagged

from .common import SouscriptionsTestCase


def _periode_meta(**kwargs):
    """Stub duck-typé de `PeriodeMeta` (contrat v3) — cf. test_pull_meta_periodes.py."""
    base = dict(
        ref_situation_contractuelle='RSC-CAMPAGNE-BASE',
        pdl='14000000000099',
        mois_annee='2024-03',
        debut='2024-03-01',
        fin='2024-04-01',
        nb_jours=31,
        puissance_moyenne_kva=6.0,
        formule_tarifaire_acheminement='CU4',
        energie_base_kwh=280.0,
        energie_hp_kwh=None,
        energie_hc_kwh=None,
        turpe_fixe_eur=8.5,
        turpe_variable_eur=4.2,
        cta_eur=1.1,
        taux_accise_eur_mwh=21.0,
        has_changement=False,
        qualite='réelle',
        statut_communication='communicante',
        releves_utilises=[],
        source_hash='hash-campagne',
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


@contextmanager
def _stream(metas):
    yield iter(metas)


def _fake_electricore_client(metas=()):
    client = MagicMock()
    client.meta_periodes.return_value = _stream(metas)
    return client


@tagged('souscriptions', 'souscriptions_campagne', 'post_install', '-at_install')
class TestCampagneEtapePullMetaPeriodes(SouscriptionsTestCase):
    MOIS = date(2024, 3, 1)

    def setUp(self):
        super().setUp()
        self.souscription_base.with_context(rsc_automatisme=True).write(
            {'ref_situation_contractuelle': 'RSC-CAMPAGNE-BASE'}
        )
        self.campagne = self.env['souscription.campagne.facturation'].create({'mois': self.MOIS})

    def test_bouton_pull_ouvre_le_wizard_avec_le_mois_pre_rempli(self):
        """AC : le step pull ouvre le wizard, mois pré-rempli."""
        action = self.campagne.action_pull_meta_periodes()
        self.assertEqual(action['res_model'], 'souscription.pull.meta.periodes.wizard')
        self.assertEqual(action['context']['default_mois'], self.campagne.mois)

    def test_bouton_pull_delegue_a_laction_deja_couverte(self):
        """Le bouton délègue à l'action wizard déjà couverte par
        test_pull_meta_periodes.py — même couture réseau (_ouvrir_flux),
        aucune nouvelle."""
        action = self.campagne.action_pull_meta_periodes()
        wizard = self.env['souscription.pull.meta.periodes.wizard'].with_context(**action['context']).create({})
        self.assertEqual(wizard.mois, self.campagne.mois)

        client = _fake_electricore_client([_periode_meta()])
        with patch.object(fabrique_module.SouscriptionElectricoreClient, 'client', return_value=client):
            wizard.action_lancer()

        periode = self.env['souscription.periode'].search(
            [('souscription_id', '=', self.souscription_base.id), ('mois', '=', self.MOIS)]
        )
        self.assertEqual(len(periode), 1)

    def test_pull_idempotent_via_le_wizard(self):
        """AC : rejouer le pull deux fois ne double pas la période
        (create-missing-only, #77/#158)."""
        action = self.campagne.action_pull_meta_periodes()
        client = _fake_electricore_client([_periode_meta()])
        for _run in range(2):
            wizard = self.env['souscription.pull.meta.periodes.wizard'].with_context(**action['context']).create({})
            with patch.object(fabrique_module.SouscriptionElectricoreClient, 'client', return_value=client):
                wizard.action_lancer()

        periode = self.env['souscription.periode'].search(
            [('souscription_id', '=', self.souscription_base.id), ('mois', '=', self.MOIS)]
        )
        self.assertEqual(len(periode), 1, 'idempotent : une seule période après deux runs')

    def test_bouton_generique_dispatch_vers_pull(self):
        """`action_executer` de la ligne d'étape « pull » délègue à
        `campagne.action_pull_meta_periodes` — un seul point de dispatch (#158)."""
        etape = self.campagne.etape_ids.filtered(lambda e: e.code == 'pull_meta_periodes')
        action = etape.action_executer()
        self.assertEqual(action['res_model'], 'souscription.pull.meta.periodes.wizard')


@tagged('souscriptions', 'souscriptions_campagne', 'post_install', '-at_install')
class TestCampagneEtapeSyncF15(SouscriptionsTestCase):
    MOIS = date(2024, 3, 1)

    def setUp(self):
        super().setUp()
        self.fake_client = MagicMock(url='https://electricore.example.test', api_key='fake-api-key')
        patcher = patch.object(fabrique_module.SouscriptionElectricoreClient, 'client', return_value=self.fake_client)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.souscription_base.with_context(rsc_automatisme=True).write(
            {'ref_situation_contractuelle': 'RSC-CAMPAGNE-F15'}
        )
        self.campagne = self.env['souscription.campagne.facturation'].create({'mois': self.MOIS})

    def test_bouton_sync_f15_delegue_a_laction_deja_couverte(self):
        """AC : le step sync F15 déclenche la sync, indépendamment du pull —
        même couture (_tirer_prestations, #147), aucune nouvelle."""
        ligne = {
            'reference': 'F15-CAMPAGNE-001',
            'pdl': 'PDL_TEST_STANDARD',
            'ref_situation_contractuelle': 'RSC-CAMPAGNE-F15',
            'id_ev': 'F180B',
            'libelle_ev': 'Mise en service',
            'taux_tva_applicable': '20.00',
            'prix_unitaire': 30.37,
            'quantite': 1.0,
        }
        with patch.object(refacturation_module.SouscriptionRefacturation, '_tirer_prestations', return_value=[ligne]):
            self.campagne.action_sync_f15()

        presta = self.env['souscription.refacturation'].search([('reference', '=', 'F15-CAMPAGNE-001')])
        self.assertEqual(presta.souscription_id, self.souscription_base)

    def test_bouton_generique_dispatch_vers_sync_f15(self):
        etape = self.campagne.etape_ids.filtered(lambda e: e.code == 'sync_f15')
        with patch.object(refacturation_module.SouscriptionRefacturation, '_tirer_prestations', return_value=[]):
            action = etape.action_executer()
        self.assertEqual(action['type'], 'ir.actions.client')


@tagged('souscriptions', 'souscriptions_campagne', 'post_install', '-at_install')
class TestCampagneEtapeCreerFactures(SouscriptionsTestCase):
    MOIS = date(2024, 3, 1)
    FIN_MOIS = date(2024, 3, 31)

    def setUp(self):
        super().setUp()
        # _souscriptions_facturables() ne cible que l'état en_service (RSC
        # acquise, #157) : sans RSC, souscription_base resterait en_instance
        # et action_creer_factures() n'aurait rien à facturer.
        self.souscription_base.with_context(rsc_automatisme=True).write(
            {'ref_situation_contractuelle': 'RSC-CAMPAGNE-CREER'}
        )
        self.campagne = self.env['souscription.campagne.facturation'].create({'mois': self.MOIS})

    def _valider(self, code):
        self.campagne.etape_ids.filtered(lambda e: e.code == code).write({'valide': True})

    def test_creer_factures_bloque_si_les_deux_portes_ne_sont_pas_validees(self):
        with self.assertRaises(UserError):
            self.campagne.action_creer_factures()

    def test_creer_factures_bloque_si_une_seule_porte_validee(self):
        self._valider('verif_periodes')
        with self.assertRaises(UserError):
            self.campagne.action_creer_factures()

    def test_creer_factures_delegue_une_fois_les_deux_portes_validees(self):
        """AC : créer factures tourne, gated sur les deux vérifs — délègue à
        (recordset).creer_factures(), déjà couvert (test_periode_facture.py)."""
        self.create_test_periode(self.souscription_base, date_debut=self.MOIS, date_fin=self.FIN_MOIS)
        self._valider('verif_periodes')
        self._valider('verif_refacturations')

        self.campagne.action_creer_factures()

        self.assertEqual(len(self.souscription_base.facture_ids), 1)

    def test_creer_factures_idempotent(self):
        self.create_test_periode(self.souscription_base, date_debut=self.MOIS, date_fin=self.FIN_MOIS)
        self._valider('verif_periodes')
        self._valider('verif_refacturations')

        self.campagne.action_creer_factures()
        self.campagne.etape_ids.invalidate_recordset()
        self.campagne.action_creer_factures()

        self.assertEqual(len(self.souscription_base.facture_ids), 1, 'idempotent : pas de doublon')

    def test_bouton_generique_dispatch_vers_creer_factures(self):
        self._valider('verif_periodes')
        self._valider('verif_refacturations')
        etape = self.campagne.etape_ids.filtered(lambda e: e.code == 'creer_factures')
        etape.action_executer()  # ne doit pas lever


@tagged('souscriptions', 'souscriptions_campagne', 'post_install', '-at_install')
class TestCampagneEtapeEmettreFactures(SouscriptionsTestCase):
    MOIS = date(2024, 3, 1)
    FIN_MOIS = date(2024, 3, 31)

    def setUp(self):
        super().setUp()
        # emettre_factures gate lit creer_factures.fait, dérivé des
        # souscriptions *en service* (#157) : sans RSC, souscription_base
        # resterait en_instance et hors de tout décompte.
        self.souscription_base.with_context(rsc_automatisme=True).write(
            {'ref_situation_contractuelle': 'RSC-CAMPAGNE-EMETTRE'}
        )
        self.campagne = self.env['souscription.campagne.facturation'].create({'mois': self.MOIS})

    def test_emettre_factures_bloque_si_creer_factures_pas_fait(self):
        """`creer_factures` n'est « fait » que si 0 souscription facturable
        reste « à facturer » (#157). Ici souscription_base a une période sans
        facture (« à facturer ») : creer_factures reste non fait, emettre
        reste bloquée."""
        self.create_test_periode(self.souscription_base, date_debut=self.MOIS, date_fin=self.FIN_MOIS)
        self.campagne.etape_ids.invalidate_recordset()
        with self.assertRaises(UserError):
            self.campagne.action_emettre_factures()

    def test_emettre_factures_poste_les_brouillons_du_mois(self):
        """AC : émettre pose les brouillons, gated sur créer factures."""
        periode = self.create_test_periode(self.souscription_base, date_debut=self.MOIS, date_fin=self.FIN_MOIS)
        periode._creer_facture()
        self.campagne.etape_ids.invalidate_recordset()

        self.campagne.action_emettre_factures()

        self.assertEqual(periode.facture_id.state, 'posted')

    def test_emettre_factures_idempotent(self):
        periode = self.create_test_periode(self.souscription_base, date_debut=self.MOIS, date_fin=self.FIN_MOIS)
        periode._creer_facture()
        self.campagne.etape_ids.invalidate_recordset()

        self.campagne.action_emettre_factures()
        self.campagne.etape_ids.invalidate_recordset()
        self.campagne.action_emettre_factures()  # 2e appel : plus rien en brouillon, no-op

        self.assertEqual(periode.facture_id.state, 'posted')

    def test_bouton_generique_dispatch_vers_emettre_factures(self):
        periode = self.create_test_periode(self.souscription_base, date_debut=self.MOIS, date_fin=self.FIN_MOIS)
        periode._creer_facture()
        self.campagne.etape_ids.invalidate_recordset()
        etape = self.campagne.etape_ids.filtered(lambda e: e.code == 'emettre_factures')

        etape.action_executer()

        self.assertEqual(periode.facture_id.state, 'posted')
