"""Tests #90/#100 — kanban de raccordement piloté par les faits (ADR 0021 §5,
ADR 0022 §1/§4) : routage à la création (PRO/particulier), situation d'entrée
requise à la saisie de l'id_Affaire, auto-move vers la branche ⏳ désignée,
re-routage latéral d'une branche à l'autre à la correction de la situation
d'entrée, reciblage de l'auto-move RSC vers « Validé sur SGE », drag-in manuel
interdit sur les étapes factuelles, pas de recul, non-régression de la
création à « Abonnement Validé »."""

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
        cls.stage_nouveau = cls.env.ref('souscriptions_odoo.stage_nouveau')
        cls.stage_pro_a_valider = cls.env.ref('souscriptions_odoo.stage_pro_a_valider')
        cls.stage_accepte_iban_verifie = cls.env.ref('souscriptions_odoo.stage_accepte_iban_verifie')
        cls.stage_f120_mes = cls.env.ref('souscriptions_odoo.stage_f120_mes')
        cls.stage_f130_cfne = cls.env.ref('souscriptions_odoo.stage_f130_cfne')
        cls.stage_valide_sge = cls.env.ref('souscriptions_odoo.stage_valide_sge')
        cls.stage_calcul_mensualites = cls.env.ref('souscriptions_odoo.stage_calcul_mensualites')
        cls.stage_abonnement_valide = cls.env.ref('souscriptions_odoo.stage_abonnement_valide')

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

    # --- Routage à la création (#100, ADR 0022 §1) ---

    def test_routage_creation_particulier_vers_nouveau(self):
        demande = self.create_demande('routage1@example.com')
        self.assertEqual(demande.stage_id, self.stage_nouveau)

    def test_routage_creation_pro_vers_pro_a_valider(self):
        demande = self.create_demande('routage2@example.com', pro=True, siret='12345678901234')
        self.assertEqual(demande.stage_id, self.stage_pro_a_valider)

    # --- Nature des étapes ---

    def test_branches_sge_et_valide_sge_sont_factuelles(self):
        self.assertTrue(self.stage_f120_mes.entree_factuelle)
        self.assertTrue(self.stage_f130_cfne.entree_factuelle)
        self.assertTrue(self.stage_valide_sge.entree_factuelle)

    def test_stage_abonnement_valide_finale_repliee(self):
        self.assertGreater(self.stage_abonnement_valide.sequence, self.stage_valide_sge.sequence)
        self.assertTrue(self.stage_abonnement_valide.fold)
        self.assertTrue(self.stage_abonnement_valide.is_close)
        self.assertFalse(self.stage_abonnement_valide.entree_factuelle)

    # --- Situation d'entrée requise à la saisie de l'id_Affaire ---

    def test_id_affaire_sans_situation_entree_refuse_a_la_creation(self):
        with self.assertRaises(UserError) as cm:
            self.create_demande('faits_refus1@example.com', id_affaire='38233180')
        self.assertIn("situation d'entrée", str(cm.exception).lower())

    def test_id_affaire_sans_situation_entree_refuse_en_ecriture(self):
        demande = self.create_demande('faits_refus2@example.com')
        with self.assertRaises(UserError) as cm:
            demande.id_affaire = '38233180'
        self.assertIn("situation d'entrée", str(cm.exception).lower())

    # --- Auto-move : id_Affaire + situation_entree -> branche ⏳ ---

    def test_auto_move_vers_f120_mes(self):
        demande = self.create_demande('faits1@example.com')
        self.assertEqual(demande.stage_id, self.stage_nouveau)

        demande.write({'situation_entree': 'mes', 'id_affaire': '38233180'})

        self.assertEqual(demande.stage_id, self.stage_f120_mes)

    def test_auto_move_vers_f130_cfne(self):
        demande = self.create_demande('faits1b@example.com')

        demande.write({'situation_entree': 'cfne', 'id_affaire': '38233181'})

        self.assertEqual(demande.stage_id, self.stage_f130_cfne)

    def test_auto_move_id_affaire_ne_recule_pas(self):
        """Une demande déjà en aval (Abonnement Validé) ne recule jamais vers
        une branche ⏳ quand l'id_Affaire est (re)saisi."""
        demande = self.create_demande(
            'faits2@example.com',
            mode_paiement='virement',
        )
        demande.stage_id = self.stage_abonnement_valide
        self.assertEqual(demande.stage_id, self.stage_abonnement_valide)

        demande.write({'situation_entree': 'mes', 'id_affaire': '38233182'})

        self.assertEqual(demande.stage_id, self.stage_abonnement_valide)

    # --- Drag-in manuel interdit ---

    def test_drag_in_manuel_refuse_vers_f120_mes(self):
        demande = self.create_demande('faits3@example.com')
        with self.assertRaises(UserError) as cm:
            demande.stage_id = self.stage_f120_mes
        self.assertIn('pilotée par un fait', str(cm.exception))
        self.assertEqual(demande.stage_id, self.stage_nouveau)

    def test_drag_in_manuel_refuse_vers_valide_sge(self):
        demande = self.create_demande('faits4@example.com', mode_paiement='virement')
        demande.stage_id = self.stage_calcul_mensualites
        with self.assertRaises(UserError) as cm:
            demande.stage_id = self.stage_valide_sge
        self.assertIn('pilotée par un fait', str(cm.exception))
        self.assertEqual(demande.stage_id, self.stage_calcul_mensualites)

    def test_drag_in_manuel_autorise_vers_etape_non_factuelle(self):
        """Les étapes non pilotées par un fait restent librement draggables."""
        demande = self.create_demande('faits5@example.com')
        demande.stage_id = self.stage_accepte_iban_verifie
        self.assertEqual(demande.stage_id, self.stage_accepte_iban_verifie)

    def test_contournement_de_contexte_reserve_aux_automatismes(self):
        demande = self.create_demande('faits6@example.com')
        demande.with_context(raccordement_automove=True).stage_id = self.stage_f120_mes
        self.assertEqual(demande.stage_id, self.stage_f120_mes)

    # --- Re-routage latéral F120 <-> F130 (correction de situation_entree) ---

    def test_correction_situation_entree_reroute_de_f120_vers_f130(self):
        demande = self.create_demande('faits_reroute1@example.com', situation_entree='mes', id_affaire='38233190')
        self.assertEqual(demande.stage_id, self.stage_f120_mes)

        demande.situation_entree = 'cfne'

        self.assertEqual(demande.stage_id, self.stage_f130_cfne)

    def test_correction_situation_entree_reroute_de_f130_vers_f120(self):
        demande = self.create_demande('faits_reroute2@example.com', situation_entree='cfne', id_affaire='38233191')
        self.assertEqual(demande.stage_id, self.stage_f130_cfne)

        demande.situation_entree = 'mes'

        self.assertEqual(demande.stage_id, self.stage_f120_mes)

    def test_correction_situation_entree_ne_fait_jamais_reculer_une_carte_en_aval(self):
        demande = self.create_demande(
            'faits_reroute3@example.com', mode_paiement='virement', situation_entree='mes', id_affaire='38233192'
        )
        self.assertEqual(demande.stage_id, self.stage_f120_mes)
        # Simule l'avancement à « Validé sur SGE » (poll RSC déjà couvert
        # plus bas) : contournement de contexte réservé aux automatismes,
        # étape factuelle.
        demande.with_context(raccordement_automove=True).stage_id = self.stage_valide_sge

        demande.situation_entree = 'cfne'

        self.assertEqual(demande.stage_id, self.stage_valide_sge)

    # --- Auto-move : RSC acquise -> Validé sur SGE (reciblage #100) ---

    # Ces trois tests exercent l'automove RSC -> Validé sur SGE isolément :
    # les entrées Odoo sont créées directement (`_create_odoo_entries`, déjà
    # couvert par les tests de création plus haut) pour lier la Souscription
    # à sa demande sans déplacer la carte — la demande reste en amont de
    # « Validé sur SGE » (état intérimaire #100 : la naissance normale
    # n'intervient qu'à la toute dernière étape, cf. #101).

    def test_auto_move_valide_sge_a_la_rsc_manuelle(self):
        demande = self.create_demande(
            'faits7@example.com', mode_paiement='virement', situation_entree='mes', id_affaire='38233182'
        )
        self.assertEqual(demande.stage_id, self.stage_f120_mes)
        demande._create_odoo_entries()
        souscription = demande.souscription_id
        self.assertTrue(souscription)
        self.assertEqual(souscription.id_affaire, '38233182')

        souscription.write({'ref_situation_contractuelle': 'RSC-9001'})  # gestionnaire (superuser en test)

        self.assertEqual(demande.stage_id, self.stage_valide_sge)
        messages = demande.message_ids.mapped('body')
        self.assertTrue(any('Validé sur SGE' in body for body in messages))

    def test_auto_move_valide_sge_a_la_rsc_du_poll(self):
        """L'automatisme s'accroche au fait, pas au canal : une RSC écrite
        via le contournement `rsc_automatisme` (poll #89) avance la carte
        exactement comme une écriture manuelle."""
        demande = self.create_demande(
            'faits8@example.com', mode_paiement='virement', situation_entree='mes', id_affaire='38233183'
        )
        demande._create_odoo_entries()
        souscription = demande.souscription_id

        souscription.with_context(rsc_automatisme=True).write({'ref_situation_contractuelle': 'RSC-9002'})

        self.assertEqual(demande.stage_id, self.stage_valide_sge)

    def test_auto_move_valide_sge_ne_recule_jamais(self):
        """Une nouvelle résolution RSC (re-résolution) sur une demande déjà
        « Validé sur SGE » ne provoque ni erreur ni recul."""
        demande = self.create_demande(
            'faits9@example.com', mode_paiement='virement', situation_entree='mes', id_affaire='38233184'
        )
        demande._create_odoo_entries()
        souscription = demande.souscription_id
        souscription.write({'ref_situation_contractuelle': 'RSC-9003'})
        self.assertEqual(demande.stage_id, self.stage_valide_sge)

        # Ré-écriture (même valeur) : no-op côté auto-move (pas de nouvelle
        # trace, la demande reste à Validé sur SGE).
        souscription.write({'ref_situation_contractuelle': 'RSC-9003'})
        self.assertEqual(demande.stage_id, self.stage_valide_sge)

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

    # --- Non-régression : « Abonnement Validé » garde son rôle de création ---
    # (état intérimaire #100 — le déplacement vers « Accepté et IBAN vérifié »
    # est la tranche #101.)

    def test_abonnement_valide_garde_son_role_de_creation(self):
        demande = self.create_demande('faits10@example.com', mode_paiement='virement')
        demande.stage_id = self.stage_abonnement_valide
        self.assertTrue(demande.souscription_id)
        self.assertTrue(demande.partner_id)
