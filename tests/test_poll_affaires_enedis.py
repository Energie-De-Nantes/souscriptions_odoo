"""Tests #89 — poll quotidien des affaires Enedis : ciblage, mapping des
motifs, grâce de 3 jours, alertes sans spam, résolution en cours de vie,
échec réseau silencieux (ADR 0021 §3-4).

Réutilise la couture de #88 : on patche `_appeler`, la méthode transport du
service RSC, avec des réponses en boîte. La grâce est testée en antidatant
`id_affaire_date_saisie` — pas de mock du temps.
"""

from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from odoo.addons.souscriptions_odoo.models.core import electricore_rsc_service as service_module
from odoo.tests.common import tagged

from .common import SouscriptionsTestCase

_SERVICE = service_module.SouscriptionRscService

_MOTIF_SANS_C15 = (
    'Affaire connue (X12) sans situation contractuelle C15 (précurseur en cours ou affaire non contractuelle).'
)


def _resultat(id_affaire, rsc=None, error=None):
    return SimpleNamespace(id_affaire=id_affaire, ref_situation_contractuelle=rsc, error=error)


@tagged('souscriptions', 'souscriptions_poll_rsc', 'post_install', '-at_install')
class TestPollAffairesEnedis(SouscriptionsTestCase):
    def setUp(self):
        super().setUp()
        # Le paquet peut être absent du sandbox d'exécution des tests : forcé
        # disponible (même garde que le wizard #84 et le service #88).
        patcher = patch.object(service_module, 'ELECTRICORE_CLIENT_DISPONIBLE', True)
        patcher.start()
        self.addCleanup(patcher.stop)
        ICP = self.env['ir.config_parameter'].sudo()
        ICP.set_param('souscriptions.electricore_url', 'https://electricore.example.test')
        ICP.set_param('souscriptions.electricore_api_key', 'fake-api-key')

    def _patch_appeler(self, return_value=None, side_effect=None):
        return patch.object(_SERVICE, '_appeler', return_value=return_value, side_effect=side_effect)

    def create_demande_avec_souscription(self, id_affaire=None, email='poll-rsc@example.com'):
        """Demande complète menée jusqu'à « Souscrit » : Souscription créée,
        liée à sa demande via souscription_id."""
        demande = self.env['raccordement.demande'].create(
            {
                'pdl': 'PDL_POLL_' + email,
                'date_debut_souhaitee': date.today() + timedelta(days=30),
                'puissance_souscrite': '6',
                'type_tarif': 'base',
                'provision_mensuelle_kwh': 250.0,
                'contact_nom': 'Test',
                'contact_email': email,
                'contact_street': 'Test Street',
                'contact_zip': '12345',
                'contact_city': 'Test City',
                'id_affaire': id_affaire,
            }
        )
        demande.stage_id = self.env.ref('souscriptions_odoo.stage_souscrit')
        return demande

    # --- Ciblage du lot ---

    def test_cible_en_instance_id_affaire_actif_seulement(self):
        """AC1 : cible en instance + id_Affaire renseigné + non archivée,
        indépendamment de l'existence d'une demande — un seul appel batch."""
        cible_1 = self.souscription_base
        cible_1.id_affaire = 'AFF-CIBLE-1'  # souscription saisie à la main, sans demande

        sans_affaire = self.souscription_hphc
        self.assertFalse(sans_affaire.id_affaire)

        self.create_demande_avec_souscription(id_affaire='AFF-CIBLE-2')

        deja_en_service = self.env['souscription.souscription'].create(
            {
                'partner_id': self.partner_test.id,
                'pdl': 'PDL_DEJA_SERVICE',
                'puissance_souscrite': '6',
                'type_tarif': 'base',
                'etat_facturation_id': self.etat_facturation.id,
                'id_affaire': 'AFF-DEJA-SERVICE',
            }
        )
        deja_en_service.with_context(rsc_automatisme=True).write({'ref_situation_contractuelle': 'RSC-X'})

        archivee = self.env['souscription.souscription'].create(
            {
                'partner_id': self.partner_test.id,
                'pdl': 'PDL_ARCHIVEE',
                'puissance_souscrite': '6',
                'type_tarif': 'base',
                'etat_facturation_id': self.etat_facturation.id,
                'id_affaire': 'AFF-ARCHIVEE',
                'active': False,
            }
        )

        with self._patch_appeler(
            return_value=[
                _resultat('AFF-CIBLE-1', error=_MOTIF_SANS_C15),
                _resultat('AFF-CIBLE-2', error=_MOTIF_SANS_C15),
            ]
        ) as mock_appeler:
            self.env['souscription.souscription']._cron_poll_affaires_enedis()

        mock_appeler.assert_called_once()
        lot_envoye = set(mock_appeler.call_args.args[0])
        self.assertEqual(lot_envoye, {'AFF-CIBLE-1', 'AFF-CIBLE-2'})
        self.assertNotIn(sans_affaire.id_affaire, lot_envoye)
        self.assertNotIn(deja_en_service.id_affaire, lot_envoye)
        self.assertNotIn(archivee.id_affaire, lot_envoye)

    def test_lot_vide_naboutit_pas_a_un_appel(self):
        self.assertFalse(self.souscription_base.id_affaire)
        self.assertFalse(self.souscription_hphc.id_affaire)
        with self._patch_appeler() as mock_appeler:
            self.env['souscription.souscription']._cron_poll_affaires_enedis()
        mock_appeler.assert_not_called()

    # --- Mapping des motifs ---

    def test_connue_sans_c15_attente_silencieuse(self):
        """AC2 : ni activité, ni blocage — motif/date rafraîchis."""
        demande = self.create_demande_avec_souscription(id_affaire='AFF-SILENCE')
        souscription = demande.souscription_id

        with self._patch_appeler(return_value=[_resultat('AFF-SILENCE', error=_MOTIF_SANS_C15)]):
            self.env['souscription.souscription']._cron_poll_affaires_enedis()

        self.assertEqual(souscription.motif_resolution_rsc, _MOTIF_SANS_C15)
        self.assertEqual(souscription.date_derniere_resolution_rsc, date.today())
        self.assertEqual(demande.kanban_state, 'normal')
        self.assertFalse(demande.activity_ids)

    def test_ambigue_alerte_immediate(self):
        """AC3 : résolution ambiguë alerte immédiatement, même à J+0."""
        demande = self.create_demande_avec_souscription(id_affaire='AFF-AMBIGUE')
        motif = "Résolution ambiguë : 2 situations contractuelles pour l'affaire AFF-AMBIGUE (X, Y)."

        with self._patch_appeler(return_value=[_resultat('AFF-AMBIGUE', error=motif)]):
            self.env['souscription.souscription']._cron_poll_affaires_enedis()

        self.assertEqual(demande.kanban_state, 'blocked')
        self.assertEqual(len(demande.activity_ids), 1)

    def test_inconnue_toleree_dans_le_delai_de_grace(self):
        """AC3 : à J+3 (borne incluse), pas d'alerte."""
        demande = self.create_demande_avec_souscription(id_affaire='AFF-GRACE')
        souscription = demande.souscription_id
        souscription.write({'id_affaire_date_saisie': date.today() - timedelta(days=3)})

        with self._patch_appeler(return_value=[_resultat('AFF-GRACE', error='Affaire inconnue : AFF-GRACE')]):
            self.env['souscription.souscription']._cron_poll_affaires_enedis()

        self.assertEqual(demande.kanban_state, 'normal')
        self.assertFalse(demande.activity_ids)

    def test_inconnue_alerte_passe_le_delai_de_grace(self):
        """AC3 : à J+4, alerte (typo probable)."""
        demande = self.create_demande_avec_souscription(id_affaire='AFF-GRACE-EXPIREE')
        souscription = demande.souscription_id
        souscription.write({'id_affaire_date_saisie': date.today() - timedelta(days=4)})

        with self._patch_appeler(
            return_value=[_resultat('AFF-GRACE-EXPIREE', error='Affaire inconnue : AFF-GRACE-EXPIREE')]
        ):
            self.env['souscription.souscription']._cron_poll_affaires_enedis()

        self.assertEqual(demande.kanban_state, 'blocked')
        self.assertEqual(len(demande.activity_ids), 1)

    # --- Alertes sans spam / résolution en cours de vie ---

    def test_deux_polls_en_erreur_consecutifs_une_seule_activite(self):
        demande = self.create_demande_avec_souscription(id_affaire='AFF-SPAM')
        motif = "Résolution ambiguë : 2 situations contractuelles pour l'affaire AFF-SPAM (X, Y)."

        with self._patch_appeler(return_value=[_resultat('AFF-SPAM', error=motif)]):
            self.env['souscription.souscription']._cron_poll_affaires_enedis()
            self.env['souscription.souscription']._cron_poll_affaires_enedis()

        self.assertEqual(len(demande.activity_ids), 1)

    def test_resolution_leve_lalerte(self):
        """AC5 : la carte se débloque et l'activité disparaît dès que le
        motif disparaît (RSC résolue au poll suivant)."""
        demande = self.create_demande_avec_souscription(id_affaire='AFF-RESOUT')
        souscription = demande.souscription_id
        motif = "Résolution ambiguë : 2 situations contractuelles pour l'affaire AFF-RESOUT (X, Y)."

        with self._patch_appeler(return_value=[_resultat('AFF-RESOUT', error=motif)]):
            self.env['souscription.souscription']._cron_poll_affaires_enedis()
        self.assertEqual(demande.kanban_state, 'blocked')
        self.assertEqual(len(demande.activity_ids), 1)

        with self._patch_appeler(return_value=[_resultat('AFF-RESOUT', rsc='RSC-RESOLUE')]):
            self.env['souscription.souscription']._cron_poll_affaires_enedis()

        self.assertEqual(souscription.ref_situation_contractuelle, 'RSC-RESOLUE')
        self.assertEqual(demande.kanban_state, 'normal')
        self.assertFalse(demande.activity_ids)

    def test_souscription_sans_demande_liee_alerte_portee_par_elle_meme(self):
        souscription = self.env['souscription.souscription'].create(
            {
                'partner_id': self.partner_test.id,
                'pdl': 'PDL_SANS_DEMANDE',
                'puissance_souscrite': '6',
                'type_tarif': 'base',
                'etat_facturation_id': self.etat_facturation.id,
                'id_affaire': 'AFF-SANS-DEMANDE',
            }
        )
        motif = "Résolution ambiguë : 2 situations contractuelles pour l'affaire AFF-SANS-DEMANDE (X, Y)."

        with self._patch_appeler(return_value=[_resultat('AFF-SANS-DEMANDE', error=motif)]):
            self.env['souscription.souscription']._cron_poll_affaires_enedis()

        self.assertEqual(len(souscription.activity_ids), 1)

    # --- Échec réseau/service ---

    def test_echec_reseau_skip_silencieux_sans_effet(self):
        demande = self.create_demande_avec_souscription(id_affaire='AFF-RESEAU')
        souscription = demande.souscription_id

        with self._patch_appeler(side_effect=ConnectionError('timeout')):
            self.env['souscription.souscription']._cron_poll_affaires_enedis()

        self.assertEqual(souscription.etat, 'en_instance')
        self.assertFalse(souscription.motif_resolution_rsc)
        self.assertFalse(souscription.date_derniere_resolution_rsc)
        self.assertEqual(demande.kanban_state, 'normal')
        self.assertFalse(demande.activity_ids)
