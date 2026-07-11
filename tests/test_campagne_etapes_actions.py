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
    # Un @contextmanager est à usage unique. Le vrai client rend un flux frais à
    # chaque appel de meta_periodes() ; on le mime avec side_effect (rappelé par
    # appel) et non return_value (une seule instance réutilisée → le 2e run du
    # test d'idempotence ré-entrait un CM déjà consommé → AttributeError, #158).
    client.meta_periodes.side_effect = lambda *args, **kwargs: _stream(metas)
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

    def test_bouton_pull_agit_directement_et_retourne_une_notification(self):
        """AC #176 : le bouton n'ouvre plus de fenêtre — il tire directement
        (Périmètre de campagne du mois) et retourne un toast, pas une
        ouverture de fenêtre."""
        client = _fake_electricore_client([_periode_meta()])
        with patch.object(fabrique_module.SouscriptionElectricoreClient, 'client', return_value=client):
            action = self.campagne.action_pull_meta_periodes()

        self.assertEqual(action['type'], 'ir.actions.client')
        self.assertEqual(action['tag'], 'display_notification')
        params = action['params']
        self.assertIn('Créées : 1', params['message'])
        self.assertIn('Déjà présentes : 0', params['message'])
        self.assertIn('Erreurs : 0', params['message'])
        self.assertEqual(params['type'], 'success')
        self.assertFalse(params['sticky'], "pas d'erreur -> toast auto-dismiss")

        periode = self.env['souscription.periode'].search(
            [('souscription_id', '=', self.souscription_base.id), ('mois', '=', self.MOIS)]
        )
        self.assertEqual(len(periode), 1)

    def test_bouton_pull_toast_sticky_quand_une_souscription_echoue(self):
        """AC #176 : skip-and-report préservé — un échec sur une souscription
        n'interrompt pas le lot, apparaît au compteur d'erreurs, et rend le
        toast sticky."""
        meta_invalide = _periode_meta(debut=None)  # déclenche une erreur de mapping (Date invalide)
        client = _fake_electricore_client([meta_invalide])
        with patch.object(fabrique_module.SouscriptionElectricoreClient, 'client', return_value=client):
            action = self.campagne.action_pull_meta_periodes()

        params = action['params']
        self.assertIn('Erreurs : 1', params['message'])
        self.assertEqual(params['type'], 'warning')
        self.assertTrue(params['sticky'], 'une erreur -> toast sticky')

    def test_pull_idempotent_via_la_campagne(self):
        """AC #176 : rejouer le pull deux fois ne double pas la période
        (create-missing-only préservé, #77/#158)."""
        client = _fake_electricore_client([_periode_meta()])
        for _run in range(2):
            with patch.object(fabrique_module.SouscriptionElectricoreClient, 'client', return_value=client):
                self.campagne.action_pull_meta_periodes()

        periode = self.env['souscription.periode'].search(
            [('souscription_id', '=', self.souscription_base.id), ('mois', '=', self.MOIS)]
        )
        self.assertEqual(len(periode), 1, 'idempotent : une seule période après deux runs')

    def test_bouton_generique_dispatch_vers_pull(self):
        """`action_executer` de la ligne d'étape « pull » délègue à
        `campagne.action_pull_meta_periodes` — un seul point de dispatch (#158)."""
        etape = self.campagne.etape_ids.filtered(lambda e: e.code == 'pull_meta_periodes')
        client = _fake_electricore_client([])
        with patch.object(fabrique_module.SouscriptionElectricoreClient, 'client', return_value=client):
            action = etape.action_executer()
        self.assertEqual(action['tag'], 'display_notification')

    def test_wizard_ad_hoc_fonctionne_toujours(self):
        """Non-régression : le wizard « Récupérer les périodes du mois » et
        son bouton d'en-tête restent inchangés (chemin secondaire, #176)."""
        wizard = self.env['souscription.pull.meta.periodes.wizard'].create({'mois': self.MOIS})
        client = _fake_electricore_client([_periode_meta()])
        with patch.object(fabrique_module.SouscriptionElectricoreClient, 'client', return_value=client):
            action = wizard.action_lancer()

        self.assertEqual(action['type'], 'ir.actions.act_window')
        self.assertEqual(wizard.state, 'done')
        self.assertIn('Créées : 1', wizard.resultat)


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

    def test_lancer_sync_f15_debloque_verif_refacturations(self):
        """Le pull F15 gate sa vérif : « vérif refacturations » est bloquée
        tant que sync F15 n'a pas tourné, puis prête une fois lancé."""
        sync = self.campagne.etape_ids.filtered(lambda e: e.code == 'sync_f15')
        verif = self.campagne.etape_ids.filtered(lambda e: e.code == 'verif_refacturations')
        self.assertFalse(sync.fait)
        self.assertEqual(verif.etat_prerequis, 'bloquee')

        with patch.object(refacturation_module.SouscriptionRefacturation, '_tirer_prestations', return_value=[]):
            sync.action_executer()
        self.campagne.etape_ids.invalidate_recordset()

        self.assertTrue(sync.fait)
        self.assertEqual(verif.etat_prerequis, 'prete')


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


@tagged('souscriptions', 'souscriptions_campagne', 'post_install', '-at_install')
class TestCampagneEtapePreparerPrelevements(SouscriptionsTestCase):
    """#186, PRD #183 : étape après « Émettre factures », son domaine
    s'appuie sur `account.move.mode_paiement` porté par la Facture (#185,
    slice 1 de cette même PR)."""

    MOIS = date(2024, 3, 1)
    FIN_MOIS = date(2024, 3, 31)

    def setUp(self):
        super().setUp()
        # Comme TestCampagneEtapeEmettreFactures : seule souscription_base
        # est RSC-acquise (en_service), donc seule facturable — hphc reste
        # en_instance, hors du décompte « emettre_factures ».
        self.souscription_base.with_context(rsc_automatisme=True).write(
            {'ref_situation_contractuelle': 'RSC-CAMPAGNE-PRELEV'}
        )
        self.campagne = self.env['souscription.campagne.facturation'].create({'mois': self.MOIS})

    def _etape(self):
        return self.campagne.etape_ids.filtered(lambda e: e.code == 'preparer_prelevements')

    def _emettre_factures_du_mois(self):
        """Amène `emettre_factures` à « fait » (prérequis de l'étape testée)
        en postant la facture du mois de souscription_base."""
        periode = self.create_test_periode(self.souscription_base, date_debut=self.MOIS, date_fin=self.FIN_MOIS)
        facture = periode._creer_facture()
        facture.action_post()
        self.campagne.etape_ids.invalidate_recordset()
        return facture

    def test_etape_apparait_apres_emettre_factures_avec_prerequis(self):
        """AC : dans le DAG, après « Émettre factures », gated dessus."""
        codes = list(self.env['souscription.campagne.etape']._selection_code())
        codes_ordonnes = [c for c, _ in codes]
        self.assertEqual(codes_ordonnes[-1], 'preparer_prelevements')
        self.assertEqual(codes_ordonnes[-2], 'emettre_factures')

        etape = self._etape()
        self.assertEqual(etape.etat_prerequis, 'bloquee', 'emettre_factures pas encore faite')

        self._emettre_factures_du_mois()
        etape.invalidate_recordset()
        self.assertEqual(etape.etat_prerequis, 'prete')

    def test_action_bloquee_si_emettre_factures_pas_faite(self):
        with self.assertRaises(UserError):
            self.campagne.action_preparer_prelevements()

    def test_bouton_retourne_une_liste_postees_residu_positif_mode_prelevement(self):
        """AC : postées, résidu > 0, mode = prélèvement, TOUTES périodes
        (pas seulement le mois de la campagne)."""
        self.souscription_base.mode_paiement = 'prelevement'
        facture_mois = self._emettre_factures_du_mois()

        # Facture d'un mois antérieur, restée due : doit apparaître (le batch
        # mensuel embarque les rattrapages, comme en prod).
        periode_janvier = self.create_test_periode(
            self.souscription_base, date_debut=date(2024, 1, 1), date_fin=date(2024, 1, 31)
        )
        facture_janvier = periode_janvier._creer_facture()
        facture_janvier.action_post()

        action = self.campagne.action_preparer_prelevements()
        self.assertEqual(action['res_model'], 'account.move')
        resultat = self.env['account.move'].search(
            action['domain'] + [('id', 'in', (facture_mois | facture_janvier).ids)]
        )
        self.assertEqual(set(resultat.ids), {facture_mois.id, facture_janvier.id})

    def test_facture_mode_vide_ou_soldee_jamais_dans_la_liste(self):
        """AC : le mode vide n'entre jamais dans ce domaine (il relève de la
        vue « Règlements en attente », #185) ; une facture soldée (chèque
        énergie, 0 €) non plus."""
        # mode_paiement vide (jamais mis à prélèvement) -> exclue malgré
        # résidu > 0.
        facture_mois = self._emettre_factures_du_mois()
        self.assertFalse(self.souscription_base.mode_paiement)

        action = self.campagne.action_preparer_prelevements()
        resultat = self.env['account.move'].search(action['domain'] + [('id', '=', facture_mois.id)])
        self.assertFalse(resultat, 'mode vide : jamais dans ce domaine')

    def test_fait_reste_a_faire_tant_quun_residu_positif_sans_paiement(self):
        """AC : « fait » dérivé des factures DU MOIS et de leurs paiements —
        aucun champ de verrou. Reste à faire tant qu'une facture prélèvement
        du mois a un résidu > 0 ; fait une fois le paiement enregistré."""
        self.souscription_base.mode_paiement = 'prelevement'
        facture_mois = self._emettre_factures_du_mois()
        etape = self._etape()

        self.assertGreater(facture_mois.amount_residual, 0.0)
        self.assertFalse(etape.fait)
        self.assertEqual(etape.nb_reste_a_faire, 1)

        journal = self.env['account.journal'].search([('type', '=', 'bank')], limit=1)
        wizard = (
            self.env['account.payment.register']
            .with_context(active_model='account.move', active_ids=facture_mois.ids)
            .create({'journal_id': journal.id})
        )
        wizard._create_payments()
        facture_mois.invalidate_recordset(['amount_residual'])
        etape.invalidate_recordset()

        self.assertAlmostEqual(facture_mois.amount_residual, 0.0, places=2)
        self.assertTrue(etape.fait)
        self.assertEqual(etape.nb_reste_a_faire, 0)

    def test_bouton_generique_dispatch_vers_preparer_prelevements(self):
        self.souscription_base.mode_paiement = 'prelevement'
        self._emettre_factures_du_mois()
        etape = self._etape()

        action = etape.action_executer()

        self.assertEqual(action['type'], 'ir.actions.act_window')
        self.assertEqual(action['res_model'], 'account.move')

    def test_aucun_champ_verrou_ajoute_sur_periode_ou_facture(self):
        """AC (esprit ADR 0025) : aucun nouveau champ de verrou sur Période ni
        sur account.move au-delà du related `mode_paiement` (#185, plomberie
        dérivée, jamais un verrou)."""
        for modele in ('souscription.periode', 'account.move'):
            for nom_champ in self.env[modele]._fields:
                self.assertNotIn('prelevement', nom_champ.lower(), f'{modele}.{nom_champ} : champ inattendu')
