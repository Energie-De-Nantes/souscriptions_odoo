"""Tests des boutons d'étape de la Campagne de facturation (#158, ADR 0025).

Chaque étape délègue à une action déjà couverte ailleurs — aucune nouvelle
couture réseau : `_ouvrir_flux` (pull, cf. test_pull_meta_periodes.py) et
`_tirer_prestations` (sync F15, cf. test_sync_prestations.py) sont patchées
exactement comme dans ces suites. Créer/émettre factures délèguent à
`creer_factures()`/`action_post()`, déjà couverts par test_periode_facture.py.

Dates dans la couverture de la grille de prix fixture (2024, tests/common.py).
"""

import os
import runpy
from datetime import date
from unittest.mock import MagicMock, patch

from odoo.addons.souscriptions_odoo.models.core import souscription_refacturation as refacturation_module
from odoo.exceptions import UserError
from odoo.tests.common import tagged

from .common import (
    SouscriptionsTestCase,
    build_grille_lignes,
    client_flux_factice,
    patcher_client_fabrique,
    patcher_transport,
)
from .common import periode_meta as _periode_meta_partage


def _periode_meta(**kwargs):
    """Overrides locaux de campagne (RSC/PDL/mois de mars) par-dessus le stub
    partagé (`periode_meta`, tests/common.py, #356)."""
    overrides = dict(
        ref_situation_contractuelle='RSC-CAMPAGNE-BASE',
        pdl='14000000000099',
        mois_annee='2024-03',
        debut='2024-03-01',
        fin='2024-04-01',
        source_hash='hash-campagne',
    )
    overrides.update(kwargs)
    return _periode_meta_partage(**overrides)


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
        client = client_flux_factice('meta_periodes', [_periode_meta()])
        with patcher_client_fabrique(client):
            action = self.campagne.action_pull_meta_periodes()

        self.assertEqual(action['type'], 'ir.actions.client')
        self.assertEqual(action['tag'], 'display_notification')
        params = action['params']
        self.assertIn('Créées : 1', params['message'])
        self.assertIn('Rafraîchies : 0', params['message'])
        self.assertIn('Erreurs : 0', params['message'])
        self.assertEqual(params['type'], 'success')
        self.assertFalse(params['sticky'], "pas d'erreur -> toast auto-dismiss")

        periode = self.env['souscription.periode'].search(
            [('souscription_id', '=', self.souscription_base.id), ('mois', '=', self.MOIS)]
        )
        self.assertEqual(len(periode), 1)

    def test_bouton_pull_pose_demande(self):
        """Symétrie avec l'automate d'amorçage (#343, grill 19/07) : le clic
        manuel pose aussi `demande` sur cette étape 'derive' — même
        sémantique post-succès que la passe d'amorçage, et la campagne sort
        de la recherche du cron (`demande=False`)."""
        client = client_flux_factice('meta_periodes', [_periode_meta()])
        with patcher_client_fabrique(client):
            self.campagne.action_pull_meta_periodes()

        etape = self.campagne.etape_ids.filtered(lambda e: e.code == 'pull_meta_periodes')
        self.assertTrue(etape.demande)

    def test_bouton_pull_toast_sticky_quand_une_souscription_echoue(self):
        """AC #176 : skip-and-report préservé — un échec sur une souscription
        n'interrompt pas le lot, apparaît au compteur d'erreurs, et rend le
        toast sticky."""
        meta_invalide = _periode_meta(debut=None)  # déclenche une erreur de mapping (Date invalide)
        client = client_flux_factice('meta_periodes', [meta_invalide])
        with patcher_client_fabrique(client):
            action = self.campagne.action_pull_meta_periodes()

        params = action['params']
        self.assertIn('Erreurs : 1', params['message'])
        self.assertEqual(params['type'], 'warning')
        self.assertTrue(params['sticky'], 'une erreur -> toast sticky')

    def test_pull_idempotent_via_la_campagne(self):
        """AC #176 : rejouer le pull deux fois ne double pas la période
        (create-missing-only préservé, #77/#158)."""
        client = client_flux_factice('meta_periodes', [_periode_meta()])
        for _run in range(2):
            with patcher_client_fabrique(client):
                self.campagne.action_pull_meta_periodes()

        periode = self.env['souscription.periode'].search(
            [('souscription_id', '=', self.souscription_base.id), ('mois', '=', self.MOIS)]
        )
        self.assertEqual(len(periode), 1, 'idempotent : une seule période après deux runs')

    def test_bouton_generique_dispatch_vers_pull(self):
        """`action_executer` de la ligne d'étape « pull » délègue à
        `campagne.action_pull_meta_periodes` — un seul point de dispatch (#158)."""
        etape = self.campagne.etape_ids.filtered(lambda e: e.code == 'pull_meta_periodes')
        client = client_flux_factice('meta_periodes', [])
        with patcher_client_fabrique(client):
            action = etape.action_executer()
        self.assertEqual(action['tag'], 'display_notification')

    def test_methode_donnees_rend_le_tuple_sans_passer_par_le_toast(self):
        """#341, ADR 0036 décision 13 : `_pull_meta_periodes_donnees` — la
        méthode-données consommée par le bouton — est exercée directement,
        sans passer par le payload `display_notification`. Même gabarit que
        les deux autres pulls (sorties C15, sync F15)."""
        client = client_flux_factice('meta_periodes', [_periode_meta()])
        with patcher_client_fabrique(client):
            creees, rafraichies, inchangees, conservees, erreurs = self.campagne._pull_meta_periodes_donnees()

        self.assertEqual(len(creees), 1)
        self.assertFalse(rafraichies)
        self.assertFalse(inchangees)
        self.assertFalse(conservees)
        self.assertFalse(erreurs)


@tagged('souscriptions', 'souscriptions_campagne', 'post_install', '-at_install')
class TestCampagneEtapeSyncF15(SouscriptionsTestCase):
    MOIS = date(2024, 3, 1)

    def setUp(self):
        super().setUp()
        self.fake_client = MagicMock(url='https://electricore.example.test', api_key='fake-api-key')
        patcher = patcher_client_fabrique(self.fake_client)
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
        with patcher_transport(
            refacturation_module.SouscriptionRefacturation, '_tirer_prestations', return_value=[ligne]
        ):
            self.campagne.action_sync_f15()

        presta = self.env['souscription.refacturation'].search([('reference', '=', 'F15-CAMPAGNE-001')])
        self.assertEqual(presta.souscription_id, self.souscription_base)

    def test_bouton_generique_dispatch_vers_sync_f15(self):
        etape = self.campagne.etape_ids.filtered(lambda e: e.code == 'sync_f15')
        with patcher_transport(refacturation_module.SouscriptionRefacturation, '_tirer_prestations', return_value=[]):
            action = etape.action_executer()
        self.assertEqual(action['type'], 'ir.actions.client')

    def test_lancer_sync_f15_debloque_verif_refacturations(self):
        """Le pull F15 gate sa vérif : « vérif refacturations » est bloquée
        tant que sync F15 n'a pas tourné, puis prête une fois lancé."""
        sync = self.campagne.etape_ids.filtered(lambda e: e.code == 'sync_f15')
        verif = self.campagne.etape_ids.filtered(lambda e: e.code == 'verif_refacturations')
        self.assertFalse(sync.fait)
        self.assertEqual(verif.etat_prerequis, 'bloquee')

        with patcher_transport(refacturation_module.SouscriptionRefacturation, '_tirer_prestations', return_value=[]):
            sync.action_executer()
        self.campagne.etape_ids.invalidate_recordset()

        self.assertTrue(sync.fait)
        self.assertEqual(verif.etat_prerequis, 'prete')


@tagged('souscriptions', 'souscriptions_campagne', 'post_install', '-at_install')
class TestCampagneEtapeCreerFactures(SouscriptionsTestCase):
    """#327, ADR 0035 : « créer factures » rejoint le harnais posé pour
    l'émission (#326) — migration ASSUMÉE et VISIBLE des tests qui
    attendaient une création synchrone, même idiome que
    TestCampagneEtapeEmettreFactures. Deux seams :

    - seam 1, `action_executer()`/`action_creer_factures()` : la porte
      (gate), l'intention (`demande`) posée avec son auteur
      (`demande_par_id`) — ne fait PLUS le travail elle-même ;
    - seam 2, le cron RÉEL dédié (`ir_cron_vidange_creer_factures`, #327) :
      `method_direct_trigger()` dans `self.enter_registry_test_mode()`.

    Aucun test ici ne s'accroche à la taille de paquet, au nombre de passes
    du cron, ni au contenu d'`ir.cron.progress` — `_vider()` boucle jusqu'à
    convergence (`etape.demande` retombée) sans présumer combien de passes
    ça prend."""

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
        self.cron = self.env.ref('souscriptions_odoo.ir_cron_vidange_creer_factures')

    def _valider(self, code):
        self.campagne.etape_ids.filtered(lambda e: e.code == code).write({'valide': True})

    def _etape(self, code='creer_factures'):
        return self.campagne.etape_ids.filtered(lambda e: e.code == code)

    def _preparer_gates(self):
        self._valider('verif_periodes')
        self._valider('verif_refacturations')

    def _vider(self, max_passes=5):
        """Vidange réellement, via le second seam (#327) : le cron dédié
        réel. Plusieurs passes tolérées — la règle « pas de progrès » (ADR
        0035 décision 3) ne retombe l'intention qu'à une passe qui n'a RIEN
        traité."""
        etape = self._etape()
        with self.enter_registry_test_mode():
            for _ in range(max_passes):
                self.cron.method_direct_trigger()
                etape.invalidate_recordset()
                if not etape.demande:
                    break

    def _creer_et_vider(self):
        """Clic (pose l'intention, déclenche le cron) puis vidange réelle —
        remplace l'ancien appel synchrone unique à `action_creer_factures()`."""
        self.campagne.action_creer_factures()
        self._vider()

    def test_creer_factures_bloque_si_les_deux_portes_ne_sont_pas_validees(self):
        with self.assertRaises(UserError):
            self.campagne.action_creer_factures()
        self.assertFalse(self._etape().demande, "la porte a bloqué avant même de poser l'intention")

    def test_creer_factures_bloque_si_une_seule_porte_validee(self):
        self._valider('verif_periodes')
        with self.assertRaises(UserError):
            self.campagne.action_creer_factures()

    def test_clic_rend_la_main_immediatement_et_ne_cree_rien(self):
        """AC #327 : le clic (seam 1) rend la main immédiatement — pose
        l'intention et son auteur, mais AUCUNE facture n'est créée avant que
        le cron (seam 2) n'ait tourné."""
        self.create_test_periode(self.souscription_base, date_debut=self.MOIS, date_fin=self.FIN_MOIS)
        self._preparer_gates()
        self.campagne.etape_ids.invalidate_recordset()
        etape = self._etape()

        etape.action_executer()

        self.assertTrue(etape.demande, "l'intention est posée")
        self.assertEqual(etape.demande_par_id, self.env.user, "l'intention porte son auteur")
        self.assertEqual(len(self.souscription_base.facture_ids), 0, 'le clic ne fait pas le travail lui-même')

    def test_creer_factures_delegue_une_fois_les_deux_portes_validees(self):
        """AC : créer factures tourne, gated sur les deux vérifs — désormais
        en tâche de fond (#327) : le clic déclenche, le cron réel fait le
        travail, délègue à (recordset).creer_factures(), déjà couvert
        (test_periode_facture.py)."""
        self.create_test_periode(self.souscription_base, date_debut=self.MOIS, date_fin=self.FIN_MOIS)
        self._preparer_gates()
        self.campagne.etape_ids.invalidate_recordset()
        self.assertEqual(self._etape().nb_reste_a_faire, 1, 'reste-à-faire dérivé, avant vidange')

        self._creer_et_vider()

        self.assertEqual(len(self.souscription_base.facture_ids), 1)
        self.assertEqual(self.souscription_base.facture_ids.state, 'draft', 'créer ne poste pas')
        self.assertEqual(
            self._etape().nb_reste_a_faire, 0, 'le reste-à-faire décroît tout seul, aucun champ de progression'
        )

    def test_creer_factures_idempotent(self):
        """AC #327 : recliquer ne crée aucun doublon — l'anti-doublon par
        période suffit, rien n'est ajouté pour la vidange."""
        self.create_test_periode(self.souscription_base, date_debut=self.MOIS, date_fin=self.FIN_MOIS)
        self._preparer_gates()
        self.campagne.etape_ids.invalidate_recordset()

        self._creer_et_vider()
        self.campagne.etape_ids.invalidate_recordset()
        self._creer_et_vider()  # reclic sur une étape déjà terminée

        self.assertEqual(len(self.souscription_base.facture_ids), 1, 'idempotent : pas de doublon')
        self.assertFalse(self._etape().demande, "l'intention ne reste jamais posée sans travail")

    def test_bouton_generique_dispatch_vers_creer_factures(self):
        self._preparer_gates()
        etape = self._etape()

        etape.action_executer()  # ne doit pas lever

        self.assertTrue(etape.demande)

    def test_brouillons_portent_le_facturiste_demandeur(self):
        """AC #327 : les brouillons portent le·la Facturiste demandeur·se,
        jamais l'utilisateur technique du cron (`with_user(demande_par_id)`,
        même identité que l'émission #326)."""
        facturiste = self.env['res.users'].create(
            {
                'name': 'Facturiste identité test création',
                'login': 'facturiste-identite-creation',
                'email': 'facturiste-identite-creation@souscriptions.test',
                'group_ids': [
                    (
                        6,
                        0,
                        [
                            self.env.ref('souscriptions_odoo.group_souscriptions_manager').id,
                            self.env.ref('account.group_account_invoice').id,
                        ],
                    )
                ],
            }
        )
        self.create_test_periode(self.souscription_base, date_debut=self.MOIS, date_fin=self.FIN_MOIS)
        self._preparer_gates()
        self.campagne.etape_ids.invalidate_recordset()

        self.campagne.with_user(facturiste).action_creer_factures()
        self.assertEqual(
            self._etape().demande_par_id, facturiste, "l'intention porte l'auteur du clic, pas l'exécutant du test"
        )
        self._vider()  # le cron réel tourne sous SON propre user_id (Administrator par défaut)

        self.assertEqual(len(self.souscription_base.facture_ids), 1)
        self.assertEqual(
            self.souscription_base.facture_ids.create_uid,
            facturiste,
            'le brouillon porte le·la demandeur·se, jamais le cron',
        )

    def test_notification_finale_arrive_chez_le_demandeur_via_bus(self):
        """AC #327 : une notification de fin arrive chez le·la demandeur·se
        avec le nombre de créées et d'échecs — via `bus.bus._sendone`
        (natif, même mécanique que l'émission #326)."""
        self.create_test_periode(self.souscription_base, date_debut=self.MOIS, date_fin=self.FIN_MOIS)
        self._preparer_gates()
        self.campagne.etape_ids.invalidate_recordset()

        with patch.object(type(self.env['bus.bus']), '_sendone') as mock_sendone:
            self._creer_et_vider()

        mock_sendone.assert_called_once()
        partner, notif_type, payload = mock_sendone.call_args[0]
        self.assertEqual(partner, self.env.user.partner_id)
        self.assertEqual(notif_type, 'simple_notification')
        self.assertIn('Créées : 1', payload['message'])
        self.assertEqual(payload['type'], 'success')
        self.assertFalse(payload['sticky'])

    # --- Isolation d'erreur par souscription (#327, même pattern que
    # l'isolation par facture #268/#326) : une souscription impossible à
    # facturer (régime Moulin sans Grille de prix DU TOUT — l'échec se
    # matérialise dès `_creer_facture()`, pas seulement à la re-génération
    # de l'émission) n'emporte pas les autres ; sa cause va à SON chatter,
    # pas à celui d'une facture qui n'existe pas encore à ce stade. ---

    def _souscription_sans_grille(self, ref):
        souscription = self.env['souscription.souscription'].create(
            {
                'partner_id': self.souscription_base.partner_id.id,
                'pdl': 'PDL_TEST_CREATION_KO',
                'puissance_souscrite': '6',
                'type_tarif': 'base',
                'regime_prix': 'moulin',
                'date_debut': self.MOIS,
                'provision_mensuelle_kwh': 300.0,
            }
        )
        souscription.with_context(rsc_automatisme=True).write({'ref_situation_contractuelle': ref})
        return souscription

    def _preparer_lot_avec_un_echec(self):
        souscription_ko = self._souscription_sans_grille('RSC-CAMPAGNE-CREATION-MOULIN-KO')
        self.create_test_periode(self.souscription_base, date_debut=self.MOIS, date_fin=self.FIN_MOIS)
        self.create_test_periode(souscription_ko, date_debut=self.MOIS, date_fin=self.FIN_MOIS)
        self._preparer_gates()
        self.campagne.etape_ids.invalidate_recordset()
        return souscription_ko

    def test_lot_partiel_isole_lechec_et_cree_le_reste(self):
        souscription_ko = self._preparer_lot_avec_un_echec()

        self._creer_et_vider()

        self.assertEqual(
            len(self.souscription_base.facture_ids), 1, 'la souscription saine est facturée malgré l’échec de l’autre'
        )
        self.assertEqual(len(souscription_ko.facture_ids), 0, 'la souscription en échec reste sans facture')

    def test_echec_laisse_la_cause_au_chatter_de_la_souscription(self):
        """AC #327 : la cause va dans le chatter de la SOUSCRIPTION, pas
        d'une facture — qui n'existe pas encore à ce stade."""
        souscription_ko = self._preparer_lot_avec_un_echec()

        self._creer_et_vider()

        self.assertTrue(
            any('Création de facture impossible' in (m.body or '') for m in souscription_ko.message_ids),
            'la cause est lisible dans le chatter de la souscription fautive',
        )

    def test_relancer_letape_apres_correction_est_idempotent(self):
        """AC #327 : relancer l'étape après avoir corrigé la cause de
        l'échec (création tardive de la Grille Moulin) crée la facture
        restée en échec — sans doublonner celle déjà créée."""
        souscription_ko = self._preparer_lot_avec_un_echec()
        self._creer_et_vider()
        self.assertEqual(len(self.souscription_base.facture_ids), 1)
        self.assertEqual(len(souscription_ko.facture_ids), 0)

        grille = self.env['grille.prix'].create(
            {
                'name': 'Grille Moulin Test Création',
                'date_debut': date(2024, 1, 1),
                'regime_prix': 'moulin',
                'active': True,
            }
        )
        build_grille_lignes(self.env, grille, prix_base=0.10, prix_hp=0.12, prix_hc=0.08)
        self.campagne.etape_ids.invalidate_recordset()

        self._creer_et_vider()

        self.assertEqual(len(souscription_ko.facture_ids), 1, "l'échec est retenté et réussit une fois corrigé")
        self.assertEqual(len(self.souscription_base.facture_ids), 1, 'déjà créée, pas de doublon')


@tagged('souscriptions', 'souscriptions_campagne', 'post_install', '-at_install')
class TestCampagneEtapeEmettreFactures(SouscriptionsTestCase):
    """#326, ADR 0035 : « émettre factures » s'exécute en tâche de fond —
    migration ASSUMÉE et VISIBLE des tests qui attendaient une émission
    synchrone (PRD #324). Deux seams, comme arrêté par #324 :

    - seam 1, `action_executer()`/`action_emettre_factures()` : la porte
      (gate), l'intention (`demande`) posée avec son auteur
      (`demande_par_id`) — ne fait PLUS le travail elle-même ;
    - seam 2, le cron RÉEL : `method_direct_trigger()` dans
      `self.enter_registry_test_mode()`, même idiome que
      `odoo/addons/account/tests/test_account_move_auto_post.py`.

    Aucun test ici ne s'accroche à la taille de paquet, au nombre de passes
    du cron, ni au contenu d'`ir.cron.progress` (#326) — `_vider()` boucle
    jusqu'à convergence (`etape.demande` retombée) sans présumer combien de
    passes ça prend."""

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
        # emettre_factures gagne gestes_commerciaux comme second prérequis
        # (#287) : pré-validé ici pour que cette classe continue à couvrir
        # exactement ce qu'elle testait (le gate creer_factures) — la porte
        # elle-même (blocage/déblocage) est testée dédiée,
        # TestCampagneEtapeGestesCommerciaux ci-dessous.
        self._valider('gestes_commerciaux')
        self.cron = self.env.ref('souscriptions_odoo.ir_cron_vidange_emettre_factures')

    def _valider(self, code):
        self.campagne.etape_ids.filtered(lambda e: e.code == code).write({'valide': True})

    def _etape(self, code='emettre_factures'):
        return self.campagne.etape_ids.filtered(lambda e: e.code == code)

    def _vider(self, max_passes=5):
        """Vidange réellement, via le second seam (#324) : le cron réel.
        Plusieurs passes tolérées — la règle « pas de progrès » (ADR 0035
        décision 3) ne retombe l'intention qu'à une passe qui n'a RIEN
        traité ; une passe mixte succès/échec ne conclut pas encore."""
        etape = self._etape()
        with self.enter_registry_test_mode():
            for _ in range(max_passes):
                self.cron.method_direct_trigger()
                etape.invalidate_recordset()
                if not etape.demande:
                    break

    def _emettre_et_vider(self):
        """Clic (pose l'intention, déclenche le cron) puis vidange réelle —
        remplace l'ancien appel synchrone unique à `action_emettre_factures()`."""
        self.campagne.action_emettre_factures()
        self._vider()

    def test_emettre_factures_bloque_si_creer_factures_pas_fait(self):
        """`creer_factures` n'est « fait » que si 0 souscription facturable
        reste « à facturer » (#157). Ici souscription_base a une période sans
        facture (« à facturer ») : creer_factures reste non fait, emettre
        reste bloquée (gestes_commerciaux, l'autre prérequis, est déjà
        validée par setUp — seul creer_factures manque ici). La porte du DAG
        est vérifiée AVANT toute pose d'intention (#326) : comportement
        inchangé."""
        self.create_test_periode(self.souscription_base, date_debut=self.MOIS, date_fin=self.FIN_MOIS)
        self.campagne.etape_ids.invalidate_recordset()
        with self.assertRaises(UserError):
            self.campagne.action_emettre_factures()
        self.assertFalse(self._etape().demande, "la porte a bloqué avant même de poser l'intention")

    def test_action_pose_lintention_marque_lauteur_et_ne_travaille_pas(self):
        """AC #326 : le clic (seam 1) rend la main immédiatement — pose
        l'intention et son auteur, mais AUCUNE facture n'est postée avant
        que le cron (seam 2) n'ait tourné."""
        periode = self.create_test_periode(self.souscription_base, date_debut=self.MOIS, date_fin=self.FIN_MOIS)
        facture = periode._creer_facture()
        self.campagne.etape_ids.invalidate_recordset()
        etape = self._etape()

        etape.action_executer()

        self.assertTrue(etape.demande, "l'intention est posée")
        self.assertEqual(etape.demande_par_id, self.env.user, "l'intention porte son auteur")
        self.assertEqual(facture.state, 'draft', 'le clic ne fait pas le travail lui-même')

    def test_reclic_sur_etape_deja_terminee_nemet_rien(self):
        """AC #326 : recliquer une étape déjà terminée ne trouve rien à
        faire — pas de double émission, pas de nouveau travail."""
        periode = self.create_test_periode(self.souscription_base, date_debut=self.MOIS, date_fin=self.FIN_MOIS)
        periode._creer_facture()
        self.campagne.etape_ids.invalidate_recordset()
        self._emettre_et_vider()
        self.assertEqual(periode.facture_id.state, 'posted')

        self._emettre_et_vider()  # reclic : l'étape est déjà faite

        self.assertEqual(periode.facture_id.state, 'posted', 'toujours postée, une seule fois')
        self.assertFalse(self._etape().demande, "l'intention ne reste jamais posée sans travail")

    def test_emettre_factures_poste_les_brouillons_du_mois(self):
        """AC : émettre pose les brouillons, gated sur créer factures —
        désormais en tâche de fond (#326) : le clic déclenche, le cron
        réel fait le travail."""
        periode = self.create_test_periode(self.souscription_base, date_debut=self.MOIS, date_fin=self.FIN_MOIS)
        periode._creer_facture()
        self.campagne.etape_ids.invalidate_recordset()

        self._emettre_et_vider()

        self.assertEqual(periode.facture_id.state, 'posted')

    def test_emettre_factures_idempotent(self):
        periode = self.create_test_periode(self.souscription_base, date_debut=self.MOIS, date_fin=self.FIN_MOIS)
        periode._creer_facture()
        self.campagne.etape_ids.invalidate_recordset()

        self._emettre_et_vider()
        self.campagne.etape_ids.invalidate_recordset()
        self._emettre_et_vider()  # 2e appel : plus rien en brouillon, no-op

        self.assertEqual(periode.facture_id.state, 'posted')

    def test_bouton_generique_dispatch_vers_emettre_factures(self):
        periode = self.create_test_periode(self.souscription_base, date_debut=self.MOIS, date_fin=self.FIN_MOIS)
        periode._creer_facture()
        self.campagne.etape_ids.invalidate_recordset()
        etape = self._etape()

        etape.action_executer()
        self._vider()

        self.assertEqual(periode.facture_id.state, 'posted')

    def test_emettre_factures_impute_les_cheques_energie_valides(self):
        """Couture campagne (#172, ADR 0026, tranche 1 du PRD #264, #265) : le
        brouillon créé par `creer_factures` reste sans imputation tant que
        l'étape « Émettre factures » ne l'a pas postée — c'est la vidange
        (donc `action_post`, donc `account.move._post()`) qui déclenche
        l'imputation FIFO, à la maille campagne comme à la maille facture
        individuelle."""
        cheque = self.env['souscription.cheque_energie'].create(
            {
                'numero': 'CHQ-CAMPAGNE-A',
                'partner_id': self.souscription_base.partner_id.id,
                'montant': 10.0,
                'date_reception': self.MOIS,
                'date_expiration': date(2026, 3, 31),
            }
        )
        cheque.action_valider()

        periode = self.create_test_periode(self.souscription_base, date_debut=self.MOIS, date_fin=self.FIN_MOIS)
        facture = periode._creer_facture()
        self.assertEqual(facture.state, 'draft', 'rien imputé avant émission')
        self.assertAlmostEqual(cheque.solde, cheque.montant, places=2)
        self.campagne.etape_ids.invalidate_recordset()

        self._emettre_et_vider()

        self.assertEqual(facture.state, 'posted')
        self.assertAlmostEqual(facture.amount_residual, facture.amount_total - 10.0, places=2)
        self.assertAlmostEqual(cheque.solde, 0.0, places=2)

    def test_travail_execute_sous_lidentite_du_demandeur_pas_du_cron(self):
        """AC #326 : les écritures comptables portent le·la Facturiste
        demandeur·se, jamais l'utilisateur technique du cron
        (`with_user(demande_par_id)`, ADR 0035 décision 5)."""
        facturiste = self.env['res.users'].create(
            {
                'name': 'Facturiste identité test',
                'login': 'facturiste-identite-emission',
                'email': 'facturiste-identite@souscriptions.test',
                # Corollaire assumé du with_user (#326) : les droits du·de la
                # demandeur·se s'appliquent à la vidange — il lui faut donc le
                # groupe Facturation natif pour poster une facture, en plus du
                # groupe métier du module.
                'group_ids': [
                    (
                        6,
                        0,
                        [
                            self.env.ref('souscriptions_odoo.group_souscriptions_manager').id,
                            self.env.ref('account.group_account_invoice').id,
                        ],
                    )
                ],
            }
        )
        periode = self.create_test_periode(self.souscription_base, date_debut=self.MOIS, date_fin=self.FIN_MOIS)
        periode._creer_facture()
        self.campagne.etape_ids.invalidate_recordset()

        self.campagne.with_user(facturiste).action_emettre_factures()
        self.assertEqual(
            self._etape().demande_par_id, facturiste, "l'intention porte l'auteur du clic, pas l'exécutant du test"
        )
        self._vider()  # le cron réel tourne sous SON propre user_id (Administrator par défaut)

        self.assertEqual(periode.facture_id.state, 'posted')
        self.assertEqual(
            periode.facture_id.write_uid,
            facturiste,
            "l'écriture comptable (state -> posted) porte le·la demandeur·se, jamais l'utilisateur du cron",
        )

    def test_notification_finale_arrive_chez_le_demandeur_via_bus(self):
        """AC #326 : une notification de fin arrive chez le·la demandeur·se
        avec le nombre d'émises et le nombre d'échecs — via `bus.bus._sendone`
        (natif, `simple_notification`), zéro JS."""
        periode = self.create_test_periode(self.souscription_base, date_debut=self.MOIS, date_fin=self.FIN_MOIS)
        periode._creer_facture()
        self.campagne.etape_ids.invalidate_recordset()

        with patch.object(type(self.env['bus.bus']), '_sendone') as mock_sendone:
            self._emettre_et_vider()

        mock_sendone.assert_called_once()
        partner, notif_type, payload = mock_sendone.call_args[0]
        self.assertEqual(partner, self.env.user.partner_id)
        self.assertEqual(notif_type, 'simple_notification')
        self.assertIn('Émises : 1', payload['message'])
        self.assertEqual(payload['type'], 'success')
        self.assertFalse(payload['sticky'])

    # --- Isolation d'erreur par facture (#268, tranche 4 du PRD #264) ---
    #
    # Scénario « grille incapable de prixer » : `_creer_facture()` résout
    # DÉJÀ la grille à la création (souscription_periode.py) — un régime
    # Moulin sans grille casserait donc dès « créer factures », pas à
    # l'émission. Le scénario réaliste d'un échec spécifique à l'ÉMISSION
    # est la fenêtre brouillon **vivante** (ADR 0032) : la grille Moulin
    # existe à la création du brouillon, puis disparaît (désactivée) avant
    # que l'étape « émettre » ne re-résolve la grille en re-générant les
    # lignes (`_recomposer_lignes_generees`, #266/#267) — `get_grille_active`
    # lève alors UserError (ADR 0029 : « échoue bruyamment »).

    def _creer_grille_moulin(self):
        grille = self.env['grille.prix'].create(
            {
                'name': 'Grille Moulin Test',
                'date_debut': date(2024, 1, 1),
                'regime_prix': 'moulin',
                'active': True,
            }
        )
        build_grille_lignes(self.env, grille, prix_base=0.10, prix_hp=0.12, prix_hc=0.08)
        return grille

    def _souscription_moulin(self, ref):
        souscription = self.env['souscription.souscription'].create(
            {
                'partner_id': self.souscription_base.partner_id.id,
                'pdl': 'PDL_TEST_MOULIN',
                'puissance_souscrite': '6',
                'type_tarif': 'base',
                'regime_prix': 'moulin',
                'date_debut': self.MOIS,
                'provision_mensuelle_kwh': 300.0,
            }
        )
        souscription.with_context(rsc_automatisme=True).write({'ref_situation_contractuelle': ref})
        return souscription

    def _preparer_lot_avec_un_echec(self):
        """Deux brouillons créés SAINS (les deux grilles existent encore) :
        `souscription_base` (régime standard) et `souscription_ko` (régime
        Moulin). La grille Moulin est ensuite désactivée — la fenêtre
        brouillon reste vivante, l'échec ne se matérialise qu'à la
        RE-génération que déclenche l'émission."""
        periode_ok = self.create_test_periode(self.souscription_base, date_debut=self.MOIS, date_fin=self.FIN_MOIS)
        facture_ok = periode_ok._creer_facture()

        grille_moulin = self._creer_grille_moulin()
        souscription_ko = self._souscription_moulin('RSC-CAMPAGNE-MOULIN-KO')
        periode_ko = self.create_test_periode(souscription_ko, date_debut=self.MOIS, date_fin=self.FIN_MOIS)
        facture_ko = periode_ko._creer_facture()
        self.assertEqual(facture_ko.state, 'draft', 'création saine : la grille Moulin existe encore ici')

        grille_moulin.active = False  # disparaît avant l'émission
        self.campagne.etape_ids.invalidate_recordset()
        return facture_ok, facture_ko, souscription_ko, grille_moulin

    def test_lot_partiel_isole_lechec_et_emet_le_reste(self):
        """AC #268/#326 : une facture en échec n'emporte plus le lot —
        reprend le pattern du cron natif `account.move._autopost_draft_entries`
        (lot sous savepoint, repli un par un). La facture saine s'émet,
        l'échec reste en brouillon — vidé via le cron réel (#326)."""
        facture_ok, facture_ko, _souscription_ko, _grille = self._preparer_lot_avec_un_echec()

        self._emettre_et_vider()

        self.assertEqual(facture_ok.state, 'posted', "la facture saine s'émet malgré l'échec de l'autre")
        self.assertEqual(facture_ko.state, 'draft', 'la facture en échec reste en brouillon, rejouable')

    def test_echec_laisse_la_cause_au_chatter_de_la_facture(self):
        """AC #326 : « le chatter de chaque facture fautive dit pourquoi » —
        le drill-down existant (action_drill_down) dit lesquelles, la
        notification finale ne porte plus le détail par échec (cf.
        test_notification_finale_arrive_chez_le_demandeur_via_bus)."""
        _facture_ok, facture_ko, _souscription_ko, _grille = self._preparer_lot_avec_un_echec()

        self._emettre_et_vider()

        self.assertTrue(
            any('Émission impossible' in (m.body or '') for m in facture_ko.message_ids),
            'la cause est lisible dans le chatter de la facture fautive',
        )

    def test_lot_partiel_reste_a_faire_reflete_letat_reel(self):
        """AC #268 : le reste-à-faire dérivé de « émettre factures » (#157)
        ne montre plus que la souscription en échec après un lot partiel —
        aucun champ de suivi ajouté, l'état découle des factures elles-mêmes.
        La porte du DAG reste fermée (étape pas « faite ») tant que l'échec
        subsiste (#326)."""
        _facture_ok, _facture_ko, souscription_ko, _grille = self._preparer_lot_avec_un_echec()

        self._emettre_et_vider()

        etape = self._etape()
        self.assertFalse(etape.fait, "l'étape n'est pas faite tant qu'un échec subsiste")
        self.assertEqual(etape.nb_reste_a_faire, 1)
        self.assertEqual(self.campagne._reste_a_faire('emettre_factures'), souscription_ko)

    def test_relancer_letape_apres_correction_est_idempotent(self):
        """AC #268/#326 : relancer l'étape après avoir corrigé la cause de
        l'échec (ici : la grille Moulin est réactivée) émet la facture
        restée en échec — sans re-poster celle déjà émise (idempotence :
        `state == 'draft'` l'exclut du lot de travail). Reclic = une
        nouvelle intention, qui ne reprend que les échecs (#326)."""
        facture_ok, facture_ko, _souscription_ko, grille_moulin = self._preparer_lot_avec_un_echec()

        self._emettre_et_vider()
        self.assertEqual(facture_ok.state, 'posted')
        self.assertEqual(facture_ko.state, 'draft')

        grille_moulin.active = True  # corrige la cause
        self.campagne.etape_ids.invalidate_recordset()

        self._emettre_et_vider()

        self.assertEqual(facture_ko.state, 'posted', "l'échec est retenté et réussit une fois corrigé")
        self.assertEqual(facture_ok.state, 'posted', 'la facture déjà émise le reste, sans double émission')

    def test_emission_individuelle_et_emission_en_masse_produisent_les_memes_effets(self):
        """AC #268 : l'émission individuelle (bouton produit, clôture, fil de
        l'eau) et l'émission en masse (étape de campagne) partagent
        EXACTEMENT le même point de couture (`account.move._post`, ADR 0032)
        — même tampon de provision, même imputation FIFO de chèque énergie,
        quel que soit le chemin emprunté."""
        partner_masse = self.env['res.partner'].create({'name': 'Souscripteur masse', 'is_company': False})
        souscription_masse = self.env['souscription.souscription'].create(
            {
                'partner_id': partner_masse.id,
                'pdl': 'PDL_TEST_EMISSION_MASSE',
                'puissance_souscrite': '6',
                'type_tarif': 'base',
                'date_debut': self.MOIS,
                'provision_mensuelle_kwh': 300.0,
            }
        )
        souscription_masse.with_context(rsc_automatisme=True).write(
            {'ref_situation_contractuelle': 'RSC-CAMPAGNE-EMISSION-MASSE'}
        )

        def _cheque_valide(partner, numero):
            cheque = self.env['souscription.cheque_energie'].create(
                {
                    'numero': numero,
                    'partner_id': partner.id,
                    'montant': 10.0,
                    'date_reception': self.MOIS,
                    'date_expiration': date(2026, 3, 31),
                }
            )
            cheque.action_valider()
            return cheque

        cheque_individuel = _cheque_valide(self.souscription_base.partner_id, 'CHQ-INDIVIDUEL')
        cheque_masse = _cheque_valide(partner_masse, 'CHQ-MASSE')

        periode_individuelle = self.create_test_periode(
            self.souscription_base, date_debut=self.MOIS, date_fin=self.FIN_MOIS, energie_base_kwh=280.0
        )
        facture_individuelle = periode_individuelle._creer_facture()
        periode_masse = self.create_test_periode(
            souscription_masse, date_debut=self.MOIS, date_fin=self.FIN_MOIS, energie_base_kwh=280.0
        )
        facture_masse = periode_masse._creer_facture()
        self.campagne.etape_ids.invalidate_recordset()

        facture_individuelle.action_post()  # émission individuelle : le bouton produit
        self._emettre_et_vider()  # émission en masse : l'étape de campagne, en tâche de fond (#326)

        for facture, periode, cheque in (
            (facture_individuelle, periode_individuelle, cheque_individuel),
            (facture_masse, periode_masse, cheque_masse),
        ):
            self.assertEqual(facture.state, 'posted')
            self.assertEqual(periode.provision_base_kwh, 280.0, 'même tampon de provision (ADR 0032), les deux voies')
            self.assertAlmostEqual(
                facture.amount_residual, facture.amount_total - 10.0, places=2, msg='même imputation FIFO'
            )
            self.assertAlmostEqual(cheque.solde, 0.0, places=2)


@tagged('souscriptions', 'souscriptions_campagne', 'post_install', '-at_install')
class TestCampagneStatutFacturationPeriodeOuverture(SouscriptionsTestCase):
    """#284 : une Période d'ouverture (`facture_legacy_ref`, #107) porte une
    facture déjà créée ET émise dans l'ancien système (Odoo 17) — statut
    terminal `émise`, jamais `à facturer`. `creer_factures()` le savait déjà
    (anti-doublon, #107) ; `_statut_facturation` doit converger au même
    endroit, sinon les deux compteurs dérivés (Créer, Émettre) restent
    bloqués à vie sur ces souscriptions."""

    MOIS = date(2024, 3, 1)
    FIN_MOIS = date(2024, 3, 31)

    def setUp(self):
        super().setUp()
        self.souscription_base.with_context(rsc_automatisme=True).write(
            {'ref_situation_contractuelle': 'RSC-CAMPAGNE-OUVERTURE'}
        )
        self.campagne = self.env['souscription.campagne.facturation'].create({'mois': self.MOIS})
        self.create_test_periode(
            self.souscription_base,
            date_debut=self.MOIS,
            date_fin=self.FIN_MOIS,
            facture_legacy_ref='FACT-PROD-2024-0099',
        )

    def test_periode_ouverture_classee_emise(self):
        self.assertEqual(self.campagne._statut_facturation(self.souscription_base), 'emise')

    def test_periode_ouverture_absente_du_reste_a_faire_creer_et_emettre(self):
        self.assertNotIn(self.souscription_base, self.campagne._reste_a_faire('creer_factures'))
        self.assertNotIn(self.souscription_base, self.campagne._reste_a_faire('emettre_factures'))


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
        """AC : dans le DAG, après « Émettre factures », gated dessus. Depuis
        #248 (ADR 0031 décision 4), `regulariser_clotures` s'intercale aussi
        après `emettre_factures` (les deux étapes partagent ce prérequis, DAG
        pas pipeline) : on vérifie l'ordre relatif plutôt que l'adjacence
        stricte."""
        codes = list(self.env['souscription.campagne.etape']._selection_code())
        codes_ordonnes = [c for c, _ in codes]
        self.assertEqual(codes_ordonnes[-1], 'preparer_prelevements')
        self.assertLess(codes_ordonnes.index('emettre_factures'), codes_ordonnes.index('preparer_prelevements'))

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


@tagged('souscriptions', 'souscriptions_campagne', 'post_install', '-at_install')
class TestCampagneEtapeGestesCommerciaux(SouscriptionsTestCase):
    """#287, ADR 0025 : porte manuelle entre Créer et Émettre — garde
    l'émission, même mécanique que Vérif périodes/Vérif refacturations
    (coche Validé + validé_par/validé_le, aucune action, aucun
    reste-à-faire)."""

    MOIS = date(2024, 3, 1)
    FIN_MOIS = date(2024, 3, 31)

    def setUp(self):
        super().setUp()
        self.souscription_base.with_context(rsc_automatisme=True).write(
            {'ref_situation_contractuelle': 'RSC-CAMPAGNE-GESTES'}
        )
        self.campagne = self.env['souscription.campagne.facturation'].create({'mois': self.MOIS})

    def _etape(self, code):
        return self.campagne.etape_ids.filtered(lambda e: e.code == code)

    def _facture_creee(self):
        periode = self.create_test_periode(self.souscription_base, date_debut=self.MOIS, date_fin=self.FIN_MOIS)
        return periode._creer_facture()

    def test_gestes_commerciaux_se_place_entre_creer_et_emettre(self):
        """AC : insérée entre creer_factures et emettre_factures dans l'ordre
        du catalogue (ordre topologique/d'affichage, ADR 0025 §1)."""
        codes = [code for code, _ in self.env['souscription.campagne.etape']._selection_code()]
        self.assertEqual(codes.index('gestes_commerciaux'), codes.index('creer_factures') + 1)
        self.assertEqual(codes.index('emettre_factures'), codes.index('gestes_commerciaux') + 1)

    def test_gestes_commerciaux_se_valide_comme_les_autres_portes(self):
        """Même mécanique que Vérif périodes/Vérif refacturations : coche +
        validé_par/validé_le estampillés au write, jamais saisis à la main."""
        etape = self._etape('gestes_commerciaux')
        self.assertEqual(etape.type_etape, 'porte')
        self.assertFalse(etape.fait)
        self.assertEqual(etape.nb_reste_a_faire, 0, 'une porte ne porte aucun reste-à-faire dérivé')

        etape.write({'valide': True})

        self.assertTrue(etape.fait)
        self.assertEqual(etape.valide_par_id, self.env.user)
        self.assertTrue(etape.valide_le)

    def test_emettre_factures_bloquee_tant_que_gestes_commerciaux_non_validee(self):
        """AC : Émettre factures reste bloquée tant que la porte n'est pas
        validée, même une fois Créer factures fait (facture déjà créée)."""
        self._facture_creee()
        self.campagne.etape_ids.invalidate_recordset()
        self.assertTrue(self._etape('creer_factures').fait, 'facture déjà créée : créer factures est faite')
        self.assertEqual(self._etape('emettre_factures').etat_prerequis, 'bloquee')

        with self.assertRaises(UserError):
            self.campagne.action_emettre_factures()

    def test_emettre_factures_debloquee_une_fois_gestes_commerciaux_validee(self):
        """AC : une fois la porte validée, Émettre factures tourne — c'est-à-
        dire, depuis #326 (tâche de fond), passe la porte et pose l'intention
        sans lever. Le POSTAGE effectif est couvert par le cron réel dans
        TestCampagneEtapeEmettreFactures ; ici seul le déblocage de la porte
        est le sujet."""
        facture = self._facture_creee()
        self._etape('gestes_commerciaux').write({'valide': True})
        self.campagne.etape_ids.invalidate_recordset()

        self.assertEqual(self._etape('emettre_factures').etat_prerequis, 'prete')
        self.campagne.action_emettre_factures()

        self.assertTrue(self._etape('emettre_factures').demande, "la porte ouverte, l'intention est posée")
        self.assertEqual(facture.state, 'draft', 'le clic ne poste plus lui-même (#326) — le cron le fera')


@tagged('souscriptions', 'souscriptions_campagne', 'post_install', '-at_install')
class TestCampagneEtapeMotDuMois(SouscriptionsTestCase):
    """#314, ADR 0034 amendée (« Le marketing gate la facturation,
    délibérément ») : porte manuelle, troisième racine du DAG — même
    mécanique que Vérif périodes/Vérif refacturations/Gestes commerciaux
    (coche Validé + validé_par/validé_le, aucune action, aucun reste-à-faire).
    """

    MOIS = date(2024, 3, 1)

    def setUp(self):
        super().setUp()
        self.campagne = self.env['souscription.campagne.facturation'].create({'mois': self.MOIS})

    def _etape(self, code):
        return self.campagne.etape_ids.filtered(lambda e: e.code == code)

    def test_mot_du_mois_est_une_racine_sans_prerequis(self):
        """AC : apparaît comme racine du DAG, aucun prérequis."""
        etape = self._etape('mot_du_mois')
        self.assertEqual(etape.type_etape, 'porte')
        self.assertEqual(etape.etat_prerequis, 'prete')
        self.assertFalse(etape.bloquee_par)

    def test_valider_avec_une_lettre_vide_est_accepte(self):
        """AC : valider la porte avec une lettre VIDE est accepté — « rien à
        dire ce mois-ci » est une décision légitime, jamais bloquée par le
        contenu du champ `lettre_mois`."""
        self.assertFalse(self.campagne.lettre_mois)
        etape = self._etape('mot_du_mois')

        etape.write({'valide': True})

        self.assertTrue(etape.fait)
        self.assertEqual(etape.valide_par_id, self.env.user)
        self.assertTrue(etape.valide_le)

    def test_envoyer_factures_a_pour_prerequis_emettre_et_mot_du_mois(self):
        """AC : `envoyer_factures` a pour prérequis `emettre_factures` ET
        `mot_du_mois`."""
        from odoo.addons.souscriptions_odoo.models.core import souscription_campagne as campagne_module

        prerequis = campagne_module.ETAPES_CAMPAGNE['envoyer_factures']['prerequis']
        self.assertEqual(set(prerequis), {'emettre_factures', 'mot_du_mois'})

    def test_non_validee_bloque_envoyer_factures(self):
        etape_envoyer = self._etape('envoyer_factures')
        self.assertEqual(etape_envoyer.etat_prerequis, 'bloquee')
        self.assertIn('Mot du mois', etape_envoyer.bloquee_par)


@tagged('souscriptions', 'souscriptions_campagne', 'post_install', '-at_install')
class TestCampagneEtapeEnvoyerFactures(SouscriptionsTestCase):
    """#314 : envoi gouverné — l'étape entre dans le DAG, gardée par
    `emettre_factures` ET la porte `mot_du_mois`. Délègue à la machinerie
    NATIVE d'envoi (`account.move.send._generate_and_send_invoices`) —
    jamais réimplémentée : les tests mockent cette frontière plutôt que de
    faire tourner un rendu PDF/e-mail réel (même convention que
    tests/test_mail_facture_energie.py, « jamais un envoi SMTP complet »)."""

    MOIS = date(2024, 3, 1)
    FIN_MOIS = date(2024, 3, 31)

    def setUp(self):
        super().setUp()
        self.souscription_base.with_context(rsc_automatisme=True).write(
            {'ref_situation_contractuelle': 'RSC-CAMPAGNE-ENVOYER'}
        )
        self.campagne = self.env['souscription.campagne.facturation'].create({'mois': self.MOIS})

    def _etape(self, code):
        return self.campagne.etape_ids.filtered(lambda e: e.code == code)

    def _valider(self, code):
        self._etape(code).write({'valide': True})

    def _facture_postee(self):
        periode = self.create_test_periode(self.souscription_base, date_debut=self.MOIS, date_fin=self.FIN_MOIS)
        facture = periode._creer_facture()
        facture.action_post()
        return facture

    def _periode_pour(self, souscription):
        return self.create_test_periode(souscription, date_debut=self.MOIS, date_fin=self.FIN_MOIS)

    def _mock_send(self):
        return patch.object(type(self.env['account.move.send']), '_generate_and_send_invoices')

    def test_envoyer_bloque_si_mot_du_mois_non_valide(self):
        """AC : tenter d'envoyer sans avoir validé la porte refuse, avec un
        message qui dit quoi faire — le libellé du prérequis manquant."""
        facture = self._facture_postee()
        self.campagne.etape_ids.invalidate_recordset()
        self.assertTrue(self._etape('emettre_factures').fait)
        self.assertEqual(self._etape('envoyer_factures').etat_prerequis, 'bloquee')

        with self.assertRaises(UserError) as cm:
            self.campagne.action_envoyer_factures()

        self.assertIn('Mot du mois', str(cm.exception))
        self.assertFalse(facture.is_move_sent)

    def test_envoyer_bloque_tant_que_emettre_factures_pas_fait(self):
        """AC : les brouillons ne sont jamais envoyés — `emettre_factures`
        gate aussi `envoyer_factures`."""
        periode = self.create_test_periode(self.souscription_base, date_debut=self.MOIS, date_fin=self.FIN_MOIS)
        periode._creer_facture()  # reste en brouillon
        self._valider('mot_du_mois')
        self.campagne.etape_ids.invalidate_recordset()

        self.assertEqual(self._etape('envoyer_factures').etat_prerequis, 'bloquee')
        with self.assertRaises(UserError):
            self.campagne.action_envoyer_factures()

    def test_envoyer_debloquee_une_fois_mot_du_mois_valide(self):
        facture = self._facture_postee()
        self._valider('mot_du_mois')
        self.campagne.etape_ids.invalidate_recordset()
        self.assertEqual(self._etape('envoyer_factures').etat_prerequis, 'prete')

        with self._mock_send() as mock_send:
            self.campagne.action_envoyer_factures()

        mock_send.assert_called_once()
        args, kwargs = mock_send.call_args
        self.assertEqual(set(args[0].ids), {facture.id})
        self.assertFalse(kwargs.get('allow_raising', True), 'remontée au chatter, jamais une levée (#314)')

    def test_bouton_generique_dispatch_vers_envoyer_factures(self):
        self._facture_postee()
        self._valider('mot_du_mois')
        self.campagne.etape_ids.invalidate_recordset()

        with self._mock_send() as mock_send:
            self._etape('envoyer_factures').action_executer()

        mock_send.assert_called_once()

    def test_reclic_ne_redeclenche_rien_quand_tout_est_deja_envoye(self):
        """AC : recliquer reprend exactement les factures non envoyées, sans
        doublon sur celles déjà parties — un reclic sans reste-à-faire
        n'appelle même pas la machinerie native."""
        facture = self._facture_postee()
        self._valider('mot_du_mois')
        self.campagne.etape_ids.invalidate_recordset()
        facture.is_move_sent = True

        with self._mock_send() as mock_send:
            self.campagne.action_envoyer_factures()

        mock_send.assert_not_called()

    def test_echec_denvoi_sur_une_facture_nempeche_pas_les_autres(self):
        """AC : un échec d'envoi sur une facture n'empêche pas les autres de
        partir ; l'échec est rapporté (ici, au chatter de la facture
        fautive — le point d'échec va toujours à l'enregistrement en
        cause, même convention que les vidanges #326/#327)."""
        p1 = self._periode_pour(self.souscription_base)
        p2 = self._periode_pour(self.souscription_hphc)
        f_ok = p1._creer_facture()
        f_ok.action_post()
        f_ko = p2._creer_facture()
        f_ko.action_post()
        self._valider('mot_du_mois')
        self.campagne.etape_ids.invalidate_recordset()

        def _envoi_partiel(model_self, moves, allow_raising=True, **kwargs):
            for move in moves:
                if move.id == f_ko.id:
                    move.message_post(body='Envoi impossible : erreur simulée')
                else:
                    move.is_move_sent = True

        with patch.object(type(self.env['account.move.send']), '_generate_and_send_invoices', _envoi_partiel):
            self.campagne.action_envoyer_factures()

        self.assertTrue(f_ok.is_move_sent)
        self.assertFalse(f_ko.is_move_sent)
        self.assertTrue(any('erreur simulée' in (m.body or '') for m in f_ko.message_ids))
        self.assertEqual(self.campagne._factures_a_envoyer_du_mois(), f_ko)


@tagged('souscriptions', 'souscriptions_migration', 'post_install', '-at_install')
class TestMigrationGestesCommerciaux(SouscriptionsTestCase):
    """Migration `19.0.1.17.0` (#287) : soigne les campagnes déjà ouvertes
    avant l'ajout de la porte « Gestes commerciaux » — `_seed_etapes` ne
    s'exécute qu'à la création, donc une campagne en vol n'a pas la ligne
    d'étape `gestes_commerciaux` ; `_compute_etat_prerequis` d'`emettre_factures`
    lit alors un prérequis absent (`freres.get('gestes_commerciaux')` -> None)
    -> bloquée à vie. Charge le script par chemin (`runpy.run_path`, même
    idiome que `test_migration_energie_facturee.py`/`test_facture_provenance.py`
    — le dossier de version n'est pas un identifiant Python importable)."""

    MOIS = date(2024, 3, 1)
    FIN_MOIS = date(2024, 3, 31)

    @staticmethod
    def _migrer(cr):
        chemin = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), 'migrations', '19.0.1.17.0', 'post-migrate.py'
        )
        module = runpy.run_path(chemin)
        module['migrate'](cr, None)

    def _campagne_en_vol(self):
        """Simule une campagne créée AVANT #287 : la ligne d'étape
        `gestes_commerciaux` existe (posée par `_seed_etapes`, le code est
        déjà déployé dans ce dépôt) puis on la supprime pour retrouver l'état
        pré-migration d'une campagne en vol."""
        campagne = self.env['souscription.campagne.facturation'].create({'mois': self.MOIS})
        campagne.etape_ids.filtered(lambda e: e.code == 'gestes_commerciaux').unlink()
        return campagne

    def test_migration_insere_la_ligne_manquante(self):
        campagne = self._campagne_en_vol()
        self.assertFalse(campagne.etape_ids.filtered(lambda e: e.code == 'gestes_commerciaux'))

        self._migrer(self.env.cr)
        campagne.invalidate_recordset()

        etape = campagne.etape_ids.filtered(lambda e: e.code == 'gestes_commerciaux')
        self.assertEqual(len(etape), 1)
        self.assertEqual(etape.sequence, 65, 'entre creer_factures=60 et emettre_factures=70 déjà tenus par le vol')
        self.assertEqual(etape.type_etape, 'porte')
        self.assertFalse(etape.valide)

    def test_migration_debloque_emettre_factures(self):
        """La ligne manquante bloquait `emettre_factures` à vie ; la
        migration lève le blocage — mais n'auto-valide rien : la porte
        insérée reste à valider par le·la facturiste."""
        campagne = self._campagne_en_vol()
        self.souscription_base.with_context(rsc_automatisme=True).write(
            {'ref_situation_contractuelle': 'RSC-MIGRATION-GESTES'}
        )
        periode = self.create_test_periode(self.souscription_base, date_debut=self.MOIS, date_fin=self.FIN_MOIS)
        periode._creer_facture()
        campagne.etape_ids.invalidate_recordset()

        etape_emettre = campagne.etape_ids.filtered(lambda e: e.code == 'emettre_factures')
        self.assertEqual(etape_emettre.etat_prerequis, 'bloquee', 'gestes_commerciaux absente : bloquée à vie')

        self._migrer(self.env.cr)
        campagne.invalidate_recordset()
        campagne.etape_ids.invalidate_recordset()

        etape_emettre = campagne.etape_ids.filtered(lambda e: e.code == 'emettre_factures')
        self.assertEqual(etape_emettre.etat_prerequis, 'bloquee', 'insérée mais pas encore validée : toujours bloquée')

        campagne.etape_ids.filtered(lambda e: e.code == 'gestes_commerciaux').write({'valide': True})
        campagne.invalidate_recordset()
        campagne.etape_ids.invalidate_recordset()

        etape_emettre = campagne.etape_ids.filtered(lambda e: e.code == 'emettre_factures')
        self.assertEqual(etape_emettre.etat_prerequis, 'prete', 'validée : le blocage à vie est levé')

    def test_migration_idempotente(self):
        campagne = self._campagne_en_vol()

        self._migrer(self.env.cr)
        self._migrer(self.env.cr)  # rejoué : no-op
        campagne.invalidate_recordset()

        etapes = campagne.etape_ids.filtered(lambda e: e.code == 'gestes_commerciaux')
        self.assertEqual(len(etapes), 1, 'idempotent : pas de doublon')
