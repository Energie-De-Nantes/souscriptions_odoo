"""Tests #90 — kanban de raccordement piloté par les faits (ADR 0021 §5) :
auto-move à la saisie de l'id_Affaire et à l'acquisition de la RSC, drag-in
manuel interdit sur ces deux étapes factuelles, pas de recul, non-régression
de la création à « Souscrit »."""

from datetime import date, timedelta

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged

from .common import SouscriptionsTestMixin


@tagged('souscriptions', 'souscriptions_raccordement_faits', 'post_install', '-at_install')
class TestKanbanPiloteParLesFaits(SouscriptionsTestMixin, TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.setUpSouscriptionsData()
        cls.stage_recue = cls.env.ref('souscriptions_odoo.stage_demande_recue')
        cls.stage_iban = cls.env.ref('souscriptions_odoo.stage_iban_valide')
        cls.stage_demande_sge = cls.env.ref('souscriptions_odoo.stage_demande_sge')
        cls.stage_souscrit = cls.env.ref('souscriptions_odoo.stage_souscrit')
        cls.stage_en_service = cls.env.ref('souscriptions_odoo.stage_en_service')

    def create_demande(self, email, **kwargs):
        defaults = {
            'pdl': 'PDL_FAITS_' + email,
            'date_debut_souhaitee': date.today() + timedelta(days=30),
            'puissance_souscrite': '6',
            'type_tarif': 'base',
            'provision_mensuelle_kwh': 250.0,
            'contact_nom': 'Test',
            'contact_email': email,
            'contact_street': 'Test Street',
            'contact_zip': '12345',
            'contact_city': 'Test City',
        }
        defaults.update(kwargs)
        return self.env['raccordement.demande'].create(defaults)

    # --- Stage « En service » : nouvelle étape ---

    def test_stage_en_service_finale_repliee_sans_role_de_creation(self):
        self.assertGreater(self.stage_en_service.sequence, self.stage_souscrit.sequence)
        self.assertTrue(self.stage_en_service.fold)
        self.assertFalse(self.stage_en_service.is_close)
        self.assertTrue(self.stage_en_service.entree_factuelle)
        self.assertTrue(self.stage_demande_sge.entree_factuelle)

    # --- Auto-move : id_Affaire -> Demande SGE faite ---

    def test_auto_move_a_la_saisie_id_affaire(self):
        demande = self.create_demande('faits1@example.com')
        self.assertEqual(demande.stage_id, self.stage_recue)

        demande.id_affaire = '38233180'

        self.assertEqual(demande.stage_id, self.stage_demande_sge)

    def test_auto_move_id_affaire_ne_recule_pas(self):
        """Une demande déjà en aval (Souscrit) ne recule jamais vers
        « Demande SGE faite » quand l'id_Affaire est (re)saisi."""
        demande = self.create_demande(
            'faits2@example.com',
            mode_paiement='virement',
        )
        demande.stage_id = self.stage_souscrit
        self.assertEqual(demande.stage_id, self.stage_souscrit)

        demande.id_affaire = '38233181'

        self.assertEqual(demande.stage_id, self.stage_souscrit)

    # --- Drag-in manuel interdit ---

    def test_drag_in_manuel_refuse_vers_demande_sge(self):
        demande = self.create_demande('faits3@example.com')
        with self.assertRaises(UserError) as cm:
            demande.stage_id = self.stage_demande_sge
        self.assertIn('pilotée par un fait', str(cm.exception))
        self.assertEqual(demande.stage_id, self.stage_recue)

    def test_drag_in_manuel_refuse_vers_en_service(self):
        demande = self.create_demande('faits4@example.com', mode_paiement='virement')
        demande.stage_id = self.stage_souscrit
        with self.assertRaises(UserError) as cm:
            demande.stage_id = self.stage_en_service
        self.assertIn('pilotée par un fait', str(cm.exception))
        self.assertEqual(demande.stage_id, self.stage_souscrit)

    def test_drag_in_manuel_autorise_vers_etape_non_factuelle(self):
        """Les étapes non pilotées par un fait restent librement draggables."""
        demande = self.create_demande('faits5@example.com')
        demande.stage_id = self.stage_iban
        self.assertEqual(demande.stage_id, self.stage_iban)

    def test_contournement_de_contexte_reserve_aux_automatismes(self):
        demande = self.create_demande('faits6@example.com')
        demande.with_context(raccordement_automove=True).stage_id = self.stage_demande_sge
        self.assertEqual(demande.stage_id, self.stage_demande_sge)

    # --- Auto-move : RSC acquise -> En service ---

    def test_auto_move_en_service_a_la_rsc_manuelle(self):
        demande = self.create_demande('faits7@example.com', mode_paiement='virement', id_affaire='38233182')
        demande.stage_id = self.stage_souscrit
        souscription = demande.souscription_id
        self.assertTrue(souscription)
        self.assertEqual(souscription.id_affaire, '38233182')

        souscription.write({'ref_situation_contractuelle': 'RSC-9001'})  # gestionnaire (superuser en test)

        self.assertEqual(demande.stage_id, self.stage_en_service)
        messages = demande.message_ids.mapped('body')
        self.assertTrue(any('En service' in body for body in messages))

    def test_auto_move_en_service_a_la_rsc_du_poll(self):
        """L'automatisme s'accroche au fait, pas au canal : une RSC écrite
        via le contournement `rsc_automatisme` (poll #89) avance la carte
        exactement comme une écriture manuelle."""
        demande = self.create_demande('faits8@example.com', mode_paiement='virement', id_affaire='38233183')
        demande.stage_id = self.stage_souscrit
        souscription = demande.souscription_id

        souscription.with_context(rsc_automatisme=True).write({'ref_situation_contractuelle': 'RSC-9002'})

        self.assertEqual(demande.stage_id, self.stage_en_service)

    def test_auto_move_en_service_ne_recule_jamais(self):
        """Une nouvelle résolution RSC (re-résolution) sur une demande déjà
        « En service » ne provoque ni erreur ni recul."""
        demande = self.create_demande('faits9@example.com', mode_paiement='virement', id_affaire='38233184')
        demande.stage_id = self.stage_souscrit
        souscription = demande.souscription_id
        souscription.write({'ref_situation_contractuelle': 'RSC-9003'})
        self.assertEqual(demande.stage_id, self.stage_en_service)

        # Ré-écriture (même valeur) : no-op côté auto-move (pas de nouvelle
        # trace, la demande reste en service).
        souscription.write({'ref_situation_contractuelle': 'RSC-9003'})
        self.assertEqual(demande.stage_id, self.stage_en_service)

    def test_souscription_sans_demande_liee_ne_leve_pas_derreur(self):
        """Une Souscription sans demande (saisie manuelle) : la RSC s'écrit
        normalement, sans erreur d'auto-move (rien à avancer)."""
        souscription = self.env['souscription.souscription'].create(
            {
                'partner_id': self.partner_test.id,
                'pdl': 'PDL_MANUEL',
                'puissance_souscrite': '6',
                'type_tarif': 'base',
                'etat_facturation_id': self.etat_facturation.id,
            }
        )
        souscription.write({'ref_situation_contractuelle': 'RSC-MANUEL'})
        self.assertEqual(souscription.etat, 'en_service')

    # --- Non-régression : « Souscrit » garde son rôle de création ---

    def test_souscrit_garde_son_role_de_creation(self):
        demande = self.create_demande('faits10@example.com', mode_paiement='virement')
        demande.stage_id = self.stage_souscrit
        self.assertTrue(demande.souscription_id)
        self.assertTrue(demande.partner_id)
