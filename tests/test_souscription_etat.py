"""Tests #87 — identité & état de la Souscription (ADR 0021 §1-2, ADR 0010
amendé) : capture de l'id_Affaire côté raccordement (avec sa date de saisie),
recopie à la création, correction possible, RSC restreinte au groupe
gestionnaire, état de cycle de vie calculé.
"""

from datetime import date, timedelta

from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, tagged

from .common import SouscriptionsTestMixin


@tagged('souscriptions', 'souscriptions_etat', 'post_install', '-at_install')
class TestIdAffaireRaccordement(SouscriptionsTestMixin, TransactionCase):
    """Capture et recopie de l'id_Affaire (demande -> Souscription)."""

    def create_complete_demande(self, **kwargs):
        defaults = {
            'pdl': 'TEST123456789',
            'date_debut_souhaitee': date.today() + timedelta(days=30),
            'puissance_souscrite': '6',
            'type_tarif': 'base',
            'provision_mensuelle_kwh': 250.0,
            'contact_nom': 'Test',
            'contact_email': 'test-etat@example.com',
            'contact_street': 'Test Street',
            'contact_zip': '12345',
            'contact_city': 'Test City',
        }
        defaults.update(kwargs)
        return self.env['raccordement.demande'].create(defaults)

    def test_date_de_saisie_enregistree_a_la_saisie_de_lid_affaire(self):
        """Écrire id_affaire sur une demande sans id_affaire_date_saisie
        explicite stampe la date du jour."""
        demande = self.create_complete_demande()
        self.assertFalse(demande.id_affaire_date_saisie)
        demande.id_affaire = '38233180'
        self.assertEqual(demande.id_affaire_date_saisie, date.today())

    def test_date_de_saisie_antidatable_pour_les_tests(self):
        """La date de saisie reste explicitement pilotable (grâce du poll #89,
        testée en antidatant)."""
        demande = self.create_complete_demande()
        hier = date.today() - timedelta(days=10)
        demande.write({'id_affaire': '38233180', 'id_affaire_date_saisie': hier})
        self.assertEqual(demande.id_affaire_date_saisie, hier)

    def test_id_affaire_et_date_recopies_sur_la_souscription_a_la_creation(self):
        """AC1 : id_affaire (et sa date de saisie) recopiés sur la
        Souscription engendrée par le raccordement."""
        demande = self.create_complete_demande()
        hier = date.today() - timedelta(days=2)
        demande.write({'id_affaire': '38233180', 'id_affaire_date_saisie': hier})

        stage_final = self.env.ref('souscriptions_odoo.stage_souscrit')
        demande.stage_id = stage_final

        souscription = demande.souscription_id
        self.assertTrue(souscription, 'La souscription devrait être créée')
        self.assertEqual(souscription.id_affaire, '38233180')
        self.assertEqual(souscription.id_affaire_date_saisie, hier)

    def test_id_affaire_corrigeable_sur_la_souscription_apres_creation(self):
        """AC2 : rattrapage de typo sur la Souscription — id_affaire n'est
        pas restreint (seule la RSC l'est)."""
        self.souscription_base.id_affaire = '38233180'
        self.assertEqual(self.souscription_base.id_affaire, '38233180')
        # Correction : la date de saisie est ré-amorcée (nouvelle tentative).
        self.souscription_base.id_affaire = '38233181'
        self.assertEqual(self.souscription_base.id_affaire, '38233181')
        self.assertEqual(self.souscription_base.id_affaire_date_saisie, date.today())


@tagged('souscriptions', 'souscriptions_etat', 'post_install', '-at_install')
class TestRscRestreinte(SouscriptionsTestMixin, TransactionCase):
    """AC3 : écriture de la RSC réservée au groupe gestionnaire, tracée."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.setUpSouscriptionsData()
        cls.user = cls.env['res.users'].create(
            {
                'name': 'Accueilliste',
                'login': 'accueilliste_etat',
                'email': 'accueilliste@souscriptions.test',
                'group_ids': [(6, 0, [cls.env.ref('souscriptions_odoo.group_souscriptions_user').id])],
            }
        )
        cls.manager = cls.env['res.users'].create(
            {
                'name': 'Gestionnaire',
                'login': 'gestionnaire_etat',
                'email': 'gestionnaire@souscriptions.test',
                'group_ids': [(6, 0, [cls.env.ref('souscriptions_odoo.group_souscriptions_manager').id])],
            }
        )

    def test_utilisateur_standard_ne_peut_pas_ecrire_la_rsc(self):
        with self.assertRaises(AccessError):
            self.souscription_base.with_user(self.user).write({'ref_situation_contractuelle': 'RSC-1'})

    def test_gestionnaire_peut_ecrire_la_rsc(self):
        self.souscription_base.with_user(self.manager).write({'ref_situation_contractuelle': 'RSC-1'})
        self.assertEqual(self.souscription_base.ref_situation_contractuelle, 'RSC-1')

    def test_ecriture_rsc_tracee_au_chatter(self):
        self.souscription_base.with_user(self.manager).write({'ref_situation_contractuelle': 'RSC-1'})
        tracking_messages = self.souscription_base.message_ids.filtered(lambda m: m.tracking_value_ids)
        self.assertTrue(tracking_messages, 'Le changement de RSC devrait être tracé au chatter')

    def test_automatisme_peut_ecrire_la_rsc_sans_le_groupe(self):
        """Le contournement de contexte réservé aux automatismes (#88/#89) :
        la RSC vient d'electricore, pas d'une saisie manuelle."""
        self.souscription_base.with_user(self.user).with_context(rsc_automatisme=True).write(
            {'ref_situation_contractuelle': 'RSC-1'}
        )
        self.assertEqual(self.souscription_base.ref_situation_contractuelle, 'RSC-1')


@tagged('souscriptions', 'souscriptions_etat', 'post_install', '-at_install')
class TestEtatCalcule(SouscriptionsTestMixin, TransactionCase):
    """AC4 : état de cycle de vie calculé, jamais saisi."""

    def test_en_instance_sans_rsc(self):
        self.assertFalse(self.souscription_base.ref_situation_contractuelle)
        self.assertEqual(self.souscription_base.etat, 'en_instance')

    def test_bascule_en_service_a_lecriture_de_la_rsc(self):
        self.souscription_base.write({'ref_situation_contractuelle': 'RSC-1'})
        self.assertEqual(self.souscription_base.etat, 'en_service')

    def test_resiliee_si_date_fin_passee(self):
        self.souscription_base.write(
            {'ref_situation_contractuelle': 'RSC-1', 'date_fin': date.today() - timedelta(days=1)}
        )
        self.assertEqual(self.souscription_base.etat, 'resiliee')

    def test_pas_de_vocabulaire_brouillon_dans_la_selection(self):
        """Vocabulaire du glossaire (CONTEXT.md) : jamais « brouillon », jamais
        « active » pour le cycle de vie."""
        libelles = dict(self.env['souscription.souscription']._fields['etat'].selection)
        self.assertNotIn('brouillon', ' '.join(libelles.values()).lower())
        self.assertNotIn('active', ' '.join(libelles.values()).lower())


@tagged('souscriptions', 'souscriptions_etat', 'post_install', '-at_install')
class TestFiltresEtat(SouscriptionsTestMixin, TransactionCase):
    """AC5 : filtres/recherche par état, RSC, id_Affaire — filtre « en
    instance sans id_Affaire »."""

    def test_filtre_en_instance_sans_id_affaire(self):
        self.souscription_base.id_affaire = False
        self.souscription_hphc.write({'id_affaire': '38233180'})

        Souscription = self.env['souscription.souscription']
        domaine = [('etat', '=', 'en_instance'), ('id_affaire', '=', False)]
        resultat = Souscription.search(domaine)

        self.assertIn(self.souscription_base, resultat)
        self.assertNotIn(self.souscription_hphc, resultat)

    def test_recherche_par_rsc_et_id_affaire(self):
        self.souscription_base.with_context(rsc_automatisme=True).write(
            {'ref_situation_contractuelle': 'RSC-UNIQUE-001'}
        )
        self.souscription_hphc.id_affaire = 'AFFAIRE-UNIQUE-002'

        Souscription = self.env['souscription.souscription']
        par_rsc = Souscription.search([('ref_situation_contractuelle', '=', 'RSC-UNIQUE-001')])
        par_affaire = Souscription.search([('id_affaire', '=', 'AFFAIRE-UNIQUE-002')])

        self.assertEqual(par_rsc, self.souscription_base)
        self.assertEqual(par_affaire, self.souscription_hphc)
