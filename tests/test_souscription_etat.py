"""Tests #87 — identité & état de la Souscription (ADR 0021 §1-2, ADR 0010
amendé) : capture de l'id_Affaire côté raccordement (avec sa date de saisie),
recopie à la création, correction possible, RSC restreinte au groupe
gestionnaire, état de cycle de vie calculé.
"""

from datetime import date, timedelta

from odoo.exceptions import AccessError
from odoo.tests.common import tagged
from odoo.tools import mute_logger
from psycopg2 import IntegrityError

from .common import SouscriptionsTestCase


@tagged('souscriptions', 'souscriptions_etat', 'post_install', '-at_install')
class TestIdAffaireRaccordement(SouscriptionsTestCase):
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
            # Hors sujet de ces tests (capture/recopie de l'id_Affaire) :
            # situation d'entrée posée (#100, requise à la saisie de
            # l'id_Affaire) et mode virement (#101, pas de garde IBAN à
            # contourner).
            'situation_entree': 'mes',
            'mode_paiement': 'virement',
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

        stage_final = self.env.ref('souscriptions_odoo.stage_accepte_iban_verifie')
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
class TestRscRestreinte(SouscriptionsTestCase):
    """AC3 : écriture de la RSC réservée au groupe gestionnaire, tracée."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
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
        # Le tracking est différé au precommit — le forcer pour l'observer.
        self.env.flush_all()
        self.env.cr.precommit.run()
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
class TestEtatCalcule(SouscriptionsTestCase):
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
class TestFiltresEtat(SouscriptionsTestCase):
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


@tagged('souscriptions', 'souscriptions_etat', 'post_install', '-at_install')
class TestRscUnique(SouscriptionsTestCase):
    """#15 : deux souscriptions successives sur le même PDL sont distinguables
    sans ambiguïté — l'identité est portée par la RSC, unique par contrat."""

    def _souscription(self, pdl, rsc):
        return (
            self.env['souscription.souscription']
            .with_context(rsc_automatisme=True)
            .create(
                {
                    'partner_id': self.partner_test.id,
                    'pdl': pdl,
                    'puissance_souscrite': '6',
                    'type_tarif': 'base',
                    'etat_facturation_id': self.etat_facturation.id,
                    'date_debut': date(2024, 1, 1),
                    'ref_situation_contractuelle': rsc,
                }
            )
        )

    def test_deux_souscriptions_successives_meme_pdl_distinguables(self):
        premiere = self._souscription('PDL_PARTAGE', 'RSC-OCCUPANT-1')
        seconde = self._souscription('PDL_PARTAGE', 'RSC-OCCUPANT-2')

        Souscription = self.env['souscription.souscription']
        self.assertEqual(len(Souscription.search([('pdl', '=', 'PDL_PARTAGE')])), 2)
        self.assertEqual(Souscription.search([('ref_situation_contractuelle', '=', 'RSC-OCCUPANT-1')]), premiere)
        self.assertEqual(Souscription.search([('ref_situation_contractuelle', '=', 'RSC-OCCUPANT-2')]), seconde)

    def test_rsc_dupliquee_refusee(self):
        self._souscription('PDL_PARTAGE', 'RSC-DOUBLON')
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'), self.cr.savepoint():
            self._souscription('PDL_AUTRE', 'RSC-DOUBLON')
            self.env.flush_all()

    def test_rsc_absente_ne_bloque_pas_les_en_instance(self):
        """Les souscriptions en instance (RSC NULL) cohabitent librement —
        sémantique UNIQUE de Postgres, les NULL ne se gênent pas."""
        self._souscription('PDL_A', False)
        self._souscription('PDL_B', False)
        self.env.flush_all()
