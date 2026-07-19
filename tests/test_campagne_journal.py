"""Journal de campagne (#366) : chatter + récapitulatif de passe à chaque fin
d'étape — CONTEXT.md « Campagne de facturation » : « le point d'échec va au
chatter de l'enregistrement fautif ; le récapitulatif de passe (comptes,
lignes d'erreur liées, durées) va au journal de la Campagne (chatter) — le
toast/bus reste le retour immédiat, jamais la trace. »

Cinq seams couverts, chacun exercé au moins une fois : les trois pulls (avec
liens HTML sur les erreurs), régulariser les clôtures (comptes seuls), les
deux vidanges (réussites/échecs) et l'amorçage à la création (#343). Le
toast/bus reste inchangé partout — non ré-exercé exhaustivement ici (déjà
couvert par test_campagne_etapes_actions.py / test_campagne_amorcage.py),
seulement repris ponctuellement pour prouver la non-régression.
"""

from datetime import date
from unittest.mock import MagicMock, patch

from odoo.addons.souscriptions_odoo.models.core import souscription_refacturation as refacturation_module
from odoo.tests.common import tagged

from .common import (
    SouscriptionsTestCase,
    client_flux_factice,
    client_sorties_factice,
    flux_electricore,
    ligne_sortie,
    patcher_client_fabrique,
    patcher_transport,
)
from .common import periode_meta as _periode_meta_partage


def _periode_meta(**kwargs):
    overrides = dict(
        ref_situation_contractuelle='RSC-JOURNAL-BASE',
        pdl='14000000000099',
        mois_annee='2024-03',
        debut='2024-03-01',
        fin='2024-04-01',
        source_hash='hash-journal',
    )
    overrides.update(kwargs)
    return _periode_meta_partage(**overrides)


def _ligne_f15(**overrides):
    base = dict(
        reference='ref-journal-0001',
        pdl='PDL_TEST_STANDARD',
        ref_situation_contractuelle='RSC-JOURNAL-F15',
        id_ev='F180B',
        libelle_ev='Mise en service',
        taux_tva_applicable='20.00',
        prix_unitaire=30.37,
        quantite=1.0,
    )
    base.update(overrides)
    return base


@tagged('souscriptions', 'souscriptions_campagne', 'post_install', '-at_install')
class TestCampagneChatter(SouscriptionsTestCase):
    """AC #366 : la Campagne porte le chatter (`mail.thread` seul, pas
    `mail.activity.mixin`) ; les notes de campagne (#159) restent intactes."""

    def test_campagne_est_mail_thread_pas_activity_mixin(self):
        Campagne = self.env['souscription.campagne.facturation']
        self.assertIn('message_ids', Campagne._fields, 'mail.thread présent')
        self.assertIn('message_follower_ids', Campagne._fields, 'mail.thread présent')
        self.assertNotIn('activity_ids', Campagne._fields, 'pas mail.activity.mixin (spec explicite #366)')

    def test_notes_de_campagne_restent_le_modele_dedie(self):
        """Le chatter n'absorbe rien des notes reportables/chaînées (#159)."""
        campagne = self.env['souscription.campagne.facturation'].create({'mois': date(2024, 3, 1)})
        note = self.env['souscription.campagne.note'].create({'campagne_id': campagne.id, 'texte': 'Une note.'})
        self.assertIn(note, campagne.note_ids)
        self.assertEqual(campagne.note_ids.texte, 'Une note.')


@tagged('souscriptions', 'souscriptions_campagne', 'post_install', '-at_install')
class TestCampagneJournalPullMetaPeriodes(SouscriptionsTestCase):
    MOIS = date(2024, 3, 1)

    def setUp(self):
        super().setUp()
        self.souscription_base.with_context(rsc_automatisme=True).write(
            {'ref_situation_contractuelle': 'RSC-JOURNAL-BASE'}
        )
        self.campagne = self.env['souscription.campagne.facturation'].create({'mois': self.MOIS})

    def test_pull_reussi_poste_les_comptes_au_journal(self):
        client = client_flux_factice('meta_periodes', [_periode_meta()])
        with patcher_client_fabrique(client):
            action = self.campagne.action_pull_meta_periodes()

        messages = self.campagne.message_ids.mapped('body')
        self.assertTrue(any('Créées : 1' in m for m in messages), 'compte au journal')
        self.assertTrue(any('Erreurs : 0' in m for m in messages))
        # AC #366 : le toast reste inchangé.
        self.assertEqual(action['tag'], 'display_notification')
        self.assertIn('Créées : 1', action['params']['message'])

    def test_erreur_poste_un_lien_html_vers_la_souscription_fautive(self):
        meta_invalide = _periode_meta(debut=None)  # déclenche une erreur de mapping
        client = client_flux_factice('meta_periodes', [meta_invalide])
        with patcher_client_fabrique(client):
            self.campagne.action_pull_meta_periodes()

        messages = self.campagne.message_ids.mapped('body')
        message = next((m for m in messages if 'data-oe-model' in m), None)
        self.assertIsNotNone(message, 'un lien HTML vers la souscription fautive figure au journal')
        self.assertIn('data-oe-model="souscription.souscription"', message)
        self.assertIn(f'data-oe-id="{self.souscription_base.id}"', message)

        # ADR 0036 décision 8a : le point d'échec reste AUSSI au chatter de
        # la souscription fautive — le journal complète, ne remplace pas.
        souscription_messages = self.souscription_base.message_ids.mapped('body')
        self.assertTrue(any('Pull méta-périodes' in m for m in souscription_messages))

    def test_posts_sont_des_notes_internes_signees_par_le_demandeur(self):
        facturiste = self.env['res.users'].create(
            {
                'name': 'Facturiste journal pull méta',
                'login': 'facturiste-journal-pull-meta',
                'email': 'facturiste-journal-pull-meta@souscriptions.test',
                'group_ids': [(6, 0, [self.env.ref('souscriptions_odoo.group_souscriptions_manager').id])],
            }
        )
        client = client_flux_factice('meta_periodes', [_periode_meta()])
        with patcher_client_fabrique(client):
            self.campagne.with_user(facturiste).action_pull_meta_periodes()

        message = self.campagne.message_ids.filtered(lambda m: 'Créées' in (m.body or ''))
        self.assertTrue(message)
        self.assertEqual(message[:1].author_id, facturiste.partner_id, 'signé par le·la demandeur·se, pas le cron')
        self.assertEqual(message[:1].subtype_id, self.env.ref('mail.mt_note'), 'note interne (défaut message_post)')


@tagged('souscriptions', 'souscriptions_campagne', 'post_install', '-at_install')
class TestCampagneJournalPullSortiesC15(SouscriptionsTestCase):
    MOIS = date(2024, 3, 1)

    def setUp(self):
        super().setUp()
        self.souscription_base.with_context(rsc_automatisme=True).write(
            {'ref_situation_contractuelle': 'RSC-JOURNAL-SORTIES'}
        )
        self.campagne = self.env['souscription.campagne.facturation'].create({'mois': self.MOIS})

    def test_pull_reussi_poste_les_comptes_au_journal_et_toast_inchange(self):
        client = client_sorties_factice([ligne_sortie('RSC-JOURNAL-SORTIES', date(2024, 3, 12))])
        with patcher_client_fabrique(client):
            action = self.campagne.action_pull_sorties_c15()

        messages = self.campagne.message_ids.mapped('body')
        self.assertTrue(any('Écrites : 1' in m for m in messages))
        self.assertEqual(action['type'], 'ir.actions.client')
        self.assertIn('1', action['params']['message'])

    def test_erreur_poste_un_lien_html_vers_la_souscription_fautive(self):
        client = client_sorties_factice([ligne_sortie('RSC-JOURNAL-SORTIES', None)])  # date_sortie invalide
        with patcher_client_fabrique(client):
            self.campagne.action_pull_sorties_c15()

        messages = self.campagne.message_ids.mapped('body')
        message = next((m for m in messages if 'data-oe-model' in m), None)
        self.assertIsNotNone(message)
        self.assertIn(f'data-oe-id="{self.souscription_base.id}"', message)


@tagged('souscriptions', 'souscriptions_campagne', 'post_install', '-at_install')
class TestCampagneJournalSyncF15(SouscriptionsTestCase):
    MOIS = date(2024, 3, 1)

    def setUp(self):
        super().setUp()
        # `_synchroniser_depuis_electricore_donnees` acquiert un client
        # AVANT d'appeler `_tirer_prestations` (patché par test ci-dessous) —
        # la fabrique doit donc aussi être patchée (même paire que
        # test_sync_prestations.py/TestCampagneEtapeSyncF15).
        self.fake_client = MagicMock(url='https://electricore.example.test', api_key='fake-api-key')
        patcher = patcher_client_fabrique(self.fake_client)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.souscription_base.with_context(rsc_automatisme=True).write(
            {'ref_situation_contractuelle': 'RSC-JOURNAL-F15'}
        )
        self.campagne = self.env['souscription.campagne.facturation'].create({'mois': self.MOIS})

    def test_sync_reussie_poste_les_comptes_au_journal_et_toast_inchange(self):
        with patcher_transport(
            refacturation_module.SouscriptionRefacturation, '_tirer_prestations', return_value=[_ligne_f15()]
        ):
            action = self.campagne.action_sync_f15()

        messages = self.campagne.message_ids.mapped('body')
        self.assertTrue(any('Créées : 1' in m for m in messages))
        self.assertEqual(action['type'], 'ir.actions.client')
        self.assertIn('1 créée', action['params']['message'])

    def test_erreur_poste_un_lien_html_vers_la_souscription_fautive(self):
        """Contrainte UNIQUE violée par une référence dupliquée dans le même
        lot (ADR 0011, skip-and-report) — même déclencheur que
        test_sync_prestations.py::test_erreur_par_ligne_ne_bloque_pas_le_lot."""
        with patcher_transport(
            refacturation_module.SouscriptionRefacturation,
            '_tirer_prestations',
            return_value=[_ligne_f15(reference='ref-journal-dup'), _ligne_f15(reference='ref-journal-dup')],
        ):
            self.campagne.action_sync_f15()

        messages = self.campagne.message_ids.mapped('body')
        message = next((m for m in messages if 'data-oe-model' in m), None)
        self.assertIsNotNone(message)
        self.assertIn(f'data-oe-id="{self.souscription_base.id}"', message)


@tagged('souscriptions', 'souscriptions_cloture_campagne', 'post_install', '-at_install')
class TestCampagneJournalRegulariserClotures(SouscriptionsTestCase):
    """Pas de lien HTML ici (#366) : le drill-down (file `en_attente_cloture`,
    auto-cicatrisante) suffit déjà — seuls les comptes du toast sont repris."""

    def test_regulariser_poste_les_comptes_au_journal_sans_lien(self):
        campagne = self.env['souscription.campagne.facturation'].create({'mois': date(2024, 3, 1)})
        with patcher_client_fabrique(client_flux_factice('meta_periodes', [])):
            action = campagne.action_regulariser_clotures()

        messages = campagne.message_ids.mapped('body')
        message = next((m for m in messages if 'Émises' in m), None)
        self.assertIsNotNone(message, 'récap au journal (aucune clôture en attente ici : comptes à 0)')
        self.assertNotIn('data-oe-model', message, 'pas de lien — les erreurs restent des libellés simples ici')
        self.assertIn('Émises : 0', action['params']['message'])


@tagged('souscriptions', 'souscriptions_campagne', 'post_install', '-at_install')
class TestCampagneJournalVidangeCreerFactures(SouscriptionsTestCase):
    MOIS = date(2024, 3, 1)
    FIN_MOIS = date(2024, 3, 31)

    def setUp(self):
        super().setUp()
        self.souscription_base.with_context(rsc_automatisme=True).write(
            {'ref_situation_contractuelle': 'RSC-JOURNAL-CREER'}
        )
        self.campagne = self.env['souscription.campagne.facturation'].create({'mois': self.MOIS})
        self.cron = self.env.ref('souscriptions_odoo.ir_cron_vidange_creer_factures')

    def _valider(self, code):
        self.campagne.etape_ids.filtered(lambda e: e.code == code).write({'valide': True})

    def _etape(self, code='creer_factures'):
        return self.campagne.etape_ids.filtered(lambda e: e.code == code)

    def _vider(self, max_passes=5):
        etape = self._etape()
        with self.enter_registry_test_mode():
            for _ in range(max_passes):
                self.cron.method_direct_trigger()
                etape.invalidate_recordset()
                if not etape.demande:
                    break

    def test_fin_de_vidange_poste_reussites_echecs_au_journal_bus_inchange(self):
        self.create_test_periode(self.souscription_base, date_debut=self.MOIS, date_fin=self.FIN_MOIS)
        self._valider('verif_periodes')
        self._valider('verif_refacturations')
        self.campagne.etape_ids.invalidate_recordset()

        with patch.object(type(self.env['bus.bus']), '_sendone') as mock_sendone:
            self.campagne.action_creer_factures()
            self._vider()

        messages = self.campagne.message_ids.mapped('body')
        self.assertTrue(any('Créées : 1' in m for m in messages), 'récap de vidange au journal')
        self.assertTrue(any('Échecs : 0' in m for m in messages))
        # AC #366 : la notification bus reste inchangée (même contenu qu'avant).
        mock_sendone.assert_called_once()
        _partner, _notif_type, payload = mock_sendone.call_args[0]
        self.assertIn('Créées : 1', payload['message'])


@tagged('souscriptions', 'souscriptions_campagne', 'post_install', '-at_install')
class TestCampagneJournalVidangeEmettreFactures(SouscriptionsTestCase):
    MOIS = date(2024, 3, 1)
    FIN_MOIS = date(2024, 3, 31)

    def setUp(self):
        super().setUp()
        self.souscription_base.with_context(rsc_automatisme=True).write(
            {'ref_situation_contractuelle': 'RSC-JOURNAL-EMETTRE'}
        )
        self.campagne = self.env['souscription.campagne.facturation'].create({'mois': self.MOIS})
        self.campagne.etape_ids.filtered(lambda e: e.code == 'gestes_commerciaux').write({'valide': True})
        self.cron = self.env.ref('souscriptions_odoo.ir_cron_vidange_emettre_factures')

    def _etape(self):
        return self.campagne.etape_ids.filtered(lambda e: e.code == 'emettre_factures')

    def _vider(self, max_passes=5):
        etape = self._etape()
        with self.enter_registry_test_mode():
            for _ in range(max_passes):
                self.cron.method_direct_trigger()
                etape.invalidate_recordset()
                if not etape.demande:
                    break

    def test_fin_de_vidange_poste_reussites_echecs_au_journal(self):
        periode = self.create_test_periode(self.souscription_base, date_debut=self.MOIS, date_fin=self.FIN_MOIS)
        periode._creer_facture()
        self.campagne.etape_ids.invalidate_recordset()

        self.campagne.action_emettre_factures()
        self._vider()

        messages = self.campagne.message_ids.mapped('body')
        self.assertTrue(any('Émises : 1' in m for m in messages), 'récap de vidange au journal')
        self.assertTrue(any('Échecs : 0' in m for m in messages))


@tagged('souscriptions', 'souscriptions_campagne', 'post_install', '-at_install')
class TestCampagneJournalAmorcage(SouscriptionsTestCase):
    MOIS = date(2024, 3, 1)

    def setUp(self):
        super().setUp()
        self.souscription_base.with_context(rsc_automatisme=True).write(
            {'ref_situation_contractuelle': 'RSC-JOURNAL-AMORCAGE'}
        )
        self.campagne = self.env['souscription.campagne.facturation'].create({'mois': self.MOIS})
        self.cron = self.env.ref('souscriptions_odoo.ir_cron_amorcage_campagne')

    def _client(self, meta_items=()):
        client = MagicMock()
        client.sorties.return_value = []
        client.meta_periodes.side_effect = lambda *a, **kw: flux_electricore(list(meta_items))
        return client

    def test_fin_de_passe_amorcage_poste_le_recap_au_journal_bus_inchange(self):
        client = self._client(meta_items=[_periode_meta(ref_situation_contractuelle='RSC-JOURNAL-AMORCAGE')])

        with (
            patcher_client_fabrique(client),
            patcher_transport(refacturation_module.SouscriptionRefacturation, '_tirer_prestations', return_value=[]),
            self.enter_registry_test_mode(),
            patch.object(type(self.env['bus.bus']), '_sendone') as mock_sendone,
        ):
            self.cron.method_direct_trigger()

        messages = self.campagne.message_ids.mapped('body')
        message = next((m for m in messages if 'Pull méta-périodes' in m), None)
        self.assertIsNotNone(message, "récap d'amorçage posté au journal")
        self.assertIn('Pull sorties C15', message)
        self.assertIn('Sync F15', message)
        # AC #366 : la notification bus reste inchangée.
        mock_sendone.assert_called_once()


@tagged('souscriptions', 'souscriptions_campagne', 'post_install', '-at_install')
class TestCampagneJournalAmorcageIdentite(SouscriptionsTestCase):
    """Aucune campagne pré-existante dans ce setUp (contrairement aux classes
    ci-dessus) : `_cron_amorcer` (limit=1) doit trouver SANS ambiguïté la
    campagne créée dans le test — même garde que
    test_campagne_amorcage.py::TestCampagneAmorcageIdentite."""

    MOIS = date(2024, 3, 1)

    def test_recap_amorcage_signe_par_le_createur_pas_le_cron(self):
        facturiste = self.env['res.users'].create(
            {
                'name': 'Facturiste journal amorçage',
                'login': 'facturiste-journal-amorcage',
                'email': 'facturiste-journal-amorcage@souscriptions.test',
                'group_ids': [(6, 0, [self.env.ref('souscriptions_odoo.group_souscriptions_manager').id])],
            }
        )
        self.souscription_base.with_context(rsc_automatisme=True).write(
            {'ref_situation_contractuelle': 'RSC-JOURNAL-AMORCAGE-IDENTITE'}
        )
        campagne = self.env['souscription.campagne.facturation'].with_user(facturiste).create({'mois': self.MOIS})
        cron = self.env.ref('souscriptions_odoo.ir_cron_amorcage_campagne')
        client = MagicMock()
        client.sorties.return_value = []
        client.meta_periodes.side_effect = lambda *a, **kw: flux_electricore(
            [_periode_meta(ref_situation_contractuelle='RSC-JOURNAL-AMORCAGE-IDENTITE')]
        )

        with (
            patcher_client_fabrique(client),
            patcher_transport(refacturation_module.SouscriptionRefacturation, '_tirer_prestations', return_value=[]),
            self.enter_registry_test_mode(),
        ):
            # Le job cron tourne sous l'utilisateur par défaut du test
            # (jamais `facturiste`) — seule `with_user(create_uid)` dans
            # `_cron_amorcer` doit faire porter le post au journal par elle.
            cron.method_direct_trigger()

        self.assertNotEqual(self.env.user, facturiste, 'le job tourne sous un autre utilisateur que le créateur')
        message = campagne.message_ids.filtered(lambda m: 'Pull méta-périodes' in (m.body or ''))
        self.assertTrue(message, 'récap posté au journal de la bonne campagne')
        self.assertEqual(
            message[:1].author_id,
            facturiste.partner_id,
            "le post au journal porte le créateur de la campagne, jamais l'utilisateur du cron",
        )
