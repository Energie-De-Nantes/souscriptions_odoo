"""Tests de l'amorçage automatique à la création (#343, ADR 0036 décisions
2-8, PRD #339).

La création reste instantanée et sans réseau (garde « mois révolu » +
`_trigger()` qui ne fait que planifier) ; le vrai travail est piloté ici par
déclenchement direct du cron dédié (`ir_cron_amorcage_campagne`), même idiome
que les deux crons de vidange (`enter_registry_test_mode()` +
`method_direct_trigger()`, cf. test_campagne_etapes_actions.py) — registry
test mode, client electricore factice, aucune couture réseau réelle.

Dates dans la couverture de la grille de prix fixture (2024, tests/common.py).
"""

from datetime import date
from unittest.mock import MagicMock, patch

from dateutil.relativedelta import relativedelta
from odoo.addons.souscriptions_odoo.models.core import electricore_client_fabrique
from odoo.addons.souscriptions_odoo.models.core import souscription_pull_meta_periodes_service as service_module
from odoo.addons.souscriptions_odoo.models.core import souscription_refacturation as refacturation_module
from odoo.exceptions import UserError
from odoo.tests.common import tagged

from .common import (
    SouscriptionsTestCase,
    client_flux_factice,
    flux_electricore,
    patcher_client_fabrique,
    patcher_transport,
)
from .common import periode_meta as _periode_meta_partage


def _meta(**kwargs):
    """Overrides locaux (RSC/PDL/mois de mars 2024) par-dessus le stub
    partagé (`periode_meta`, tests/common.py, #356)."""
    overrides = dict(
        ref_situation_contractuelle='RSC-AMORCAGE-BASE',
        pdl='14000000000099',
        mois_annee='2024-03',
        debut='2024-03-01',
        fin='2024-04-01',
        source_hash='hash-amorcage',
    )
    overrides.update(kwargs)
    return _periode_meta_partage(**overrides)


def _client_amorcage(*, sorties_leve=None, meta_items=(), meta_leve=None):
    """Client electricore factice unique, couvrant à la fois `sorties` (RPC)
    et `meta_periodes` (flux) — la fabrique est patchée globalement (ADR
    0024 §6), les trois pulls de l'amorçage y puisent le même client au fil
    de la passe."""
    client = MagicMock()
    if sorties_leve is not None:
        client.sorties.side_effect = sorties_leve
    else:
        client.sorties.return_value = []
    if meta_leve is not None:
        client.meta_periodes.side_effect = meta_leve
    else:
        client.meta_periodes.side_effect = lambda *a, **kw: flux_electricore(list(meta_items))
    return client


@tagged('souscriptions', 'souscriptions_campagne', 'post_install', '-at_install')
class TestCampagneCreationMoisRevolu(SouscriptionsTestCase):
    """AC #343 : garde « mois révolu » — la création refuse un mois qui
    n'est pas strictement antérieur au mois courant."""

    def _premier_mois_courant(self):
        return date.today().replace(day=1)

    def test_creation_mois_courant_leve_userror(self):
        with self.assertRaises(UserError):
            self.env['souscription.campagne.facturation'].create({'mois': self._premier_mois_courant()})

    def test_creation_mois_futur_leve_userror(self):
        mois_futur = self._premier_mois_courant() + relativedelta(months=1)
        with self.assertRaises(UserError):
            self.env['souscription.campagne.facturation'].create({'mois': mois_futur})

    def test_creation_mois_revolu_reussit_instantanement(self):
        mois_revolu = self._premier_mois_courant() - relativedelta(months=1)
        campagne = self.env['souscription.campagne.facturation'].create({'mois': mois_revolu})
        self.assertTrue(campagne)
        self.assertEqual(campagne.mois, mois_revolu)

    def test_creation_mois_revolu_naboutit_a_aucun_appel_reseau(self):
        """AC #343 : la création rend la main sans jamais parler
        electricore — la fabrique n'est même pas sollicitée."""
        with patch.object(
            electricore_client_fabrique.SouscriptionElectricoreClient,
            'client',
            side_effect=AssertionError('appel réseau pendant la création de la campagne'),
        ):
            campagne = self.env['souscription.campagne.facturation'].create({'mois': date(2024, 3, 1)})
        self.assertTrue(campagne)

    def test_creation_mois_revolu_planifie_le_cron_damorcage(self):
        cron = self.env.ref('souscriptions_odoo.ir_cron_amorcage_campagne')
        avant = self.env['ir.cron.trigger'].search_count([('cron_id', '=', cron.id)])

        self.env['souscription.campagne.facturation'].create({'mois': date(2024, 3, 1)})

        apres = self.env['ir.cron.trigger'].search_count([('cron_id', '=', cron.id)])
        self.assertGreater(apres, avant, "la création déclenche le cron d'amorçage dédié")


@tagged('souscriptions', 'souscriptions_campagne', 'post_install', '-at_install')
class TestCampagneAmorcagePasseComplete(SouscriptionsTestCase):
    """AC #343 : après passage du cron, les trois pulls tournent, la Période
    du mois est créée, `demande` est posée sur les pulls réussis."""

    MOIS = date(2024, 3, 1)

    def setUp(self):
        super().setUp()
        self.souscription_base.with_context(rsc_automatisme=True).write(
            {'ref_situation_contractuelle': 'RSC-AMORCAGE-BASE'}
        )
        self.campagne = self.env['souscription.campagne.facturation'].create({'mois': self.MOIS})
        self.cron = self.env.ref('souscriptions_odoo.ir_cron_amorcage_campagne')

    def _etapes(self):
        self.campagne.etape_ids.invalidate_recordset()
        return {e.code: e for e in self.campagne.etape_ids}

    def _declencher(self, client):
        with (
            patcher_client_fabrique(client),
            patcher_transport(refacturation_module.SouscriptionRefacturation, '_tirer_prestations', return_value=[]),
            self.enter_registry_test_mode(),
        ):
            self.cron.method_direct_trigger()

    def test_cron_amorce_les_trois_pulls_et_pose_demande(self):
        self._declencher(_client_amorcage(meta_items=[_meta()]))

        etapes = self._etapes()
        self.assertTrue(etapes['pull_sorties_c15'].demande)
        self.assertTrue(etapes['pull_meta_periodes'].demande)
        self.assertTrue(etapes['pull_meta_periodes'].fait)
        self.assertTrue(etapes['sync_f15'].demande)

        periode = self.env['souscription.periode'].search(
            [('souscription_id', '=', self.souscription_base.id), ('mois', '=', self.MOIS)]
        )
        self.assertEqual(len(periode), 1, 'la Période du mois est créée par le pull méta amorcé')

    def test_les_portes_de_verif_restent_strictement_humaines(self):
        """AC #343 : l'automate s'arrête net aux portes — même après une
        passe complète, `verif_periodes`/`verif_refacturations` restent des
        portes non validées, jamais franchies par le cron."""
        self._declencher(_client_amorcage(meta_items=[_meta()]))

        etapes = self._etapes()
        self.assertFalse(etapes['verif_periodes'].valide)
        self.assertFalse(etapes['verif_periodes'].fait)
        self.assertFalse(etapes['verif_refacturations'].valide)
        self.assertFalse(etapes['verif_refacturations'].fait)
        self.assertFalse(etapes['creer_factures'].demande)
        self.assertFalse(etapes['emettre_factures'].demande)


@tagged('souscriptions', 'souscriptions_campagne', 'post_install', '-at_install')
class TestCampagneAmorcageOrdreDependances(SouscriptionsTestCase):
    """AC #343 : conséquence voulue de la condition « prête » — si le pull
    des sorties C15 échoue, le pull méta n'est jamais tenté ; la sync F15,
    indépendante, l'est quand même (ADR 0036 décision 5)."""

    MOIS = date(2024, 3, 1)

    def setUp(self):
        super().setUp()
        self.souscription_base.with_context(rsc_automatisme=True).write(
            {'ref_situation_contractuelle': 'RSC-AMORCAGE-ORDRE'}
        )
        self.campagne = self.env['souscription.campagne.facturation'].create({'mois': self.MOIS})
        self.cron = self.env.ref('souscriptions_odoo.ir_cron_amorcage_campagne')

    def test_echec_sorties_c15_bloque_pull_meta_mais_pas_sync_f15(self):
        client = _client_amorcage(sorties_leve=service_module.IngestionEnCours('verrou'))
        # Si le pull méta était (à tort) tenté, il appellerait ce mock —
        # jamais configuré avec un flux valide : lever prouve l'appel.
        client.meta_periodes.side_effect = AssertionError('pull méta ne doit jamais être tenté ici')

        with (
            patcher_client_fabrique(client),
            patcher_transport(refacturation_module.SouscriptionRefacturation, '_tirer_prestations', return_value=[]),
            self.enter_registry_test_mode(),
        ):
            self.cron.method_direct_trigger()

        self.campagne.etape_ids.invalidate_recordset()
        etapes = {e.code: e for e in self.campagne.etape_ids}
        self.assertFalse(etapes['pull_sorties_c15'].demande, 'sorties C15 reste « à lancer »')
        self.assertFalse(etapes['pull_sorties_c15'].fait)
        self.assertFalse(etapes['pull_meta_periodes'].fait, 'méta jamais tenté, donc jamais fait')
        self.assertEqual(etapes['pull_meta_periodes'].etat_prerequis, 'bloquee')
        self.assertTrue(etapes['sync_f15'].demande, 'F15 indépendant, quand même tenté')
        self.assertTrue(etapes['sync_f15'].fait)


@tagged('souscriptions', 'souscriptions_campagne', 'post_install', '-at_install')
class TestCampagneAmorcageEchecTransport(SouscriptionsTestCase):
    """AC #343 : un échec transport laisse l'étape « à lancer » et notifie
    le créateur par bus — jamais un échec silencieux."""

    MOIS = date(2024, 3, 1)

    def setUp(self):
        super().setUp()
        self.souscription_base.with_context(rsc_automatisme=True).write(
            {'ref_situation_contractuelle': 'RSC-AMORCAGE-ECHEC'}
        )
        self.campagne = self.env['souscription.campagne.facturation'].create({'mois': self.MOIS})
        self.cron = self.env.ref('souscriptions_odoo.ir_cron_amorcage_campagne')

    def test_echec_transport_notifie_bus_et_etape_reste_a_lancer(self):
        client = _client_amorcage(sorties_leve=service_module.IngestionEnCours('verrou'))

        with (
            patcher_client_fabrique(client),
            patcher_transport(refacturation_module.SouscriptionRefacturation, '_tirer_prestations', return_value=[]),
            self.enter_registry_test_mode(),
            patch.object(type(self.env['bus.bus']), '_sendone') as mock_sendone,
        ):
            self.cron.method_direct_trigger()

        mock_sendone.assert_called_once()
        partner, notif_type, payload = mock_sendone.call_args[0]
        self.assertEqual(partner, self.env.user.partner_id)
        self.assertEqual(notif_type, 'simple_notification')
        self.assertIn('Pull sorties C15', payload['message'])
        self.assertIn('échec transport', payload['message'])
        self.assertIn('verrou', payload['message'])
        self.assertEqual(payload['type'], 'warning')
        self.assertTrue(payload['sticky'])

        self.campagne.etape_ids.invalidate_recordset()
        etape = self.campagne.etape_ids.filtered(lambda e: e.code == 'pull_sorties_c15')
        self.assertFalse(etape.demande)
        self.assertFalse(etape.fait)


@tagged('souscriptions', 'souscriptions_campagne', 'post_install', '-at_install')
class TestCampagneAmorcageNotificationRecap(SouscriptionsTestCase):
    """AC #343 : notification bus récapitulative de fin de passe — comptes
    et durée par étape (instrumentation qui solde la réserve « pull méta à
    froid » d'ADR 0035)."""

    MOIS = date(2024, 3, 1)

    def setUp(self):
        super().setUp()
        self.souscription_base.with_context(rsc_automatisme=True).write(
            {'ref_situation_contractuelle': 'RSC-AMORCAGE-RECAP'}
        )
        self.campagne = self.env['souscription.campagne.facturation'].create({'mois': self.MOIS})
        self.cron = self.env.ref('souscriptions_odoo.ir_cron_amorcage_campagne')

    def test_notification_recapitulative_porte_comptes_et_durees_par_etape(self):
        client = _client_amorcage(meta_items=[_meta(ref_situation_contractuelle='RSC-AMORCAGE-RECAP')])

        with (
            patcher_client_fabrique(client),
            patcher_transport(refacturation_module.SouscriptionRefacturation, '_tirer_prestations', return_value=[]),
            self.enter_registry_test_mode(),
            patch.object(type(self.env['bus.bus']), '_sendone') as mock_sendone,
        ):
            self.cron.method_direct_trigger()

        mock_sendone.assert_called_once()
        _partner, _notif_type, payload = mock_sendone.call_args[0]
        message = payload['message']
        for label in ('Pull sorties C15', 'Pull méta-périodes', 'Sync F15'):
            self.assertIn(label, message, f'{label} absent du récapitulatif')
        self.assertRegex(message, r'\d+ traité\(s\)', 'compte par étape absent')
        self.assertRegex(message, r'\(\d+\.\ds\)', 'durée par étape absente')
        self.assertEqual(payload['type'], 'success')
        self.assertFalse(payload['sticky'])

    def test_les_erreurs_ne_comptent_pas_dans_les_traites(self):
        """Grill 19/07 : « traité » = ligne aboutie — une erreur par
        souscription (skip-and-report) apparaît au compteur d'erreurs, jamais
        dans le total traité (pas de double comptage)."""
        meta_invalide = _meta(ref_situation_contractuelle='RSC-AMORCAGE-RECAP', debut=None)

        with (
            patcher_client_fabrique(_client_amorcage(meta_items=[meta_invalide])),
            patcher_transport(refacturation_module.SouscriptionRefacturation, '_tirer_prestations', return_value=[]),
            self.enter_registry_test_mode(),
            patch.object(type(self.env['bus.bus']), '_sendone') as mock_sendone,
        ):
            self.cron.method_direct_trigger()

        mock_sendone.assert_called_once()
        _partner, _notif_type, payload = mock_sendone.call_args[0]
        self.assertIn('Pull méta-périodes : 0 traité(s), 1 en erreur', payload['message'])
        self.assertEqual(payload['type'], 'warning')
        self.assertTrue(payload['sticky'])


@tagged('souscriptions', 'souscriptions_campagne', 'post_install', '-at_install')
class TestCampagneAmorcageIdentite(SouscriptionsTestCase):
    """AC #343 : les écritures produites par l'amorçage portent le créateur
    de la campagne, jamais l'utilisateur technique du cron (ADR 0036
    décision 7)."""

    MOIS = date(2024, 3, 1)

    def test_ecritures_amorcees_portent_le_createur_pas_le_cron(self):
        facturiste = self.env['res.users'].create(
            {
                'name': 'Facturiste amorçage',
                'login': 'facturiste-amorcage',
                'email': 'facturiste-amorcage@souscriptions.test',
                'group_ids': [(6, 0, [self.env.ref('souscriptions_odoo.group_souscriptions_manager').id])],
            }
        )
        self.souscription_base.with_context(rsc_automatisme=True).write(
            {'ref_situation_contractuelle': 'RSC-AMORCAGE-IDENTITE'}
        )
        campagne = self.env['souscription.campagne.facturation'].with_user(facturiste).create({'mois': self.MOIS})
        cron = self.env.ref('souscriptions_odoo.ir_cron_amorcage_campagne')
        client = _client_amorcage(meta_items=[_meta(ref_situation_contractuelle='RSC-AMORCAGE-IDENTITE')])

        with (
            patcher_client_fabrique(client),
            patcher_transport(refacturation_module.SouscriptionRefacturation, '_tirer_prestations', return_value=[]),
            self.enter_registry_test_mode(),
        ):
            # Le job cron tourne sous l'utilisateur par défaut du test
            # (jamais `facturiste`) — seule `with_user(create_uid)` dans
            # `_cron_amorcer` doit faire porter les écritures par elle.
            cron.method_direct_trigger()

        self.assertNotEqual(self.env.user, facturiste, 'le job tourne sous un autre utilisateur que le créateur')
        periode = self.env['souscription.periode'].search(
            [('souscription_id', '=', self.souscription_base.id), ('mois', '=', self.MOIS)]
        )
        self.assertEqual(len(periode), 1)
        self.assertEqual(
            periode.create_uid,
            facturiste,
            "la Période créée par l'amorçage porte le créateur de la campagne, jamais l'utilisateur du cron",
        )
        self.assertEqual(campagne.create_uid, facturiste)


@tagged('souscriptions', 'souscriptions_campagne', 'post_install', '-at_install')
class TestCampagneAmorcageIdempotence(SouscriptionsTestCase):
    """AC #343 : un re-clic manuel sur un pull après amorçage reste un
    non-événement — idempotence inchangée."""

    MOIS = date(2024, 3, 1)

    def test_reclic_manuel_apres_amorcage_est_un_non_evenement(self):
        self.souscription_base.with_context(rsc_automatisme=True).write(
            {'ref_situation_contractuelle': 'RSC-AMORCAGE-RECLIC'}
        )
        campagne = self.env['souscription.campagne.facturation'].create({'mois': self.MOIS})
        cron = self.env.ref('souscriptions_odoo.ir_cron_amorcage_campagne')
        meta = _meta(ref_situation_contractuelle='RSC-AMORCAGE-RECLIC')

        with (
            patcher_client_fabrique(_client_amorcage(meta_items=[meta])),
            patcher_transport(refacturation_module.SouscriptionRefacturation, '_tirer_prestations', return_value=[]),
            self.enter_registry_test_mode(),
        ):
            cron.method_direct_trigger()

        nb_avant = self.env['souscription.periode'].search_count(
            [('souscription_id', '=', self.souscription_base.id), ('mois', '=', self.MOIS)]
        )
        self.assertEqual(nb_avant, 1)

        with patcher_client_fabrique(client_flux_factice('meta_periodes', [meta])):
            campagne.action_pull_meta_periodes()

        nb_apres = self.env['souscription.periode'].search_count(
            [('souscription_id', '=', self.souscription_base.id), ('mois', '=', self.MOIS)]
        )
        self.assertEqual(nb_apres, 1, 'idempotent : un re-clic manuel après amorçage ne double rien')
