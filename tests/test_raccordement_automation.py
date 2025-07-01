"""
Tests pour l'automatisation IBAN du module raccordement.
"""

from odoo.tests.common import TransactionCase, tagged
from odoo.exceptions import UserError
from datetime import date, timedelta
from .common import SouscriptionsTestMixin


@tagged('souscriptions', 'souscriptions_raccordement_automation', 'post_install', '-at_install')
class TestRaccordementIbanAutomation(SouscriptionsTestMixin, TransactionCase):
    """Tests de l'automatisation IBAN"""
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.setUpSouscriptionsData()
        cls.setUpRaccordementStages()
    
    @classmethod
    def setUpRaccordementStages(cls):
        """Setup des étapes de raccordement pour les tests"""
        cls.stage_received = cls.env.ref('souscriptions.stage_demande_recue')
        cls.stage_iban_validated = cls.env.ref('souscriptions.stage_iban_valide')
        cls.stage_sge = cls.env.ref('souscriptions.stage_demande_sge')
    
    def create_demande_with_valid_iban(self, **kwargs):
        """Helper pour créer une demande avec IBAN valide"""
        defaults = {
            'pdl': 'TEST123456789',
            'date_debut_souhaitee': date.today() + timedelta(days=30),
            'puissance_souscrite': '6',
            'type_tarif': 'base',
            'provision_mensuelle_kwh': 250.0,
            'contact_nom': 'Test',
            'contact_prenom': 'User',
            'contact_email': 'test@example.com',
            'contact_telephone': '0123456789',
            'contact_street': 'Test Street',
            'contact_zip': '12345',
            'contact_city': 'Test City',
            'mode_paiement': 'prelevement',
            'bank_iban': 'FR7612345678901234567890123',  # IBAN valide
            'bank_bic': 'BNPAFRPP',
            'stage_id': self.stage_received.id,
        }
        defaults.update(kwargs)
        return self.env['raccordement.demande'].create(defaults)
    
    def test_auto_advance_on_iban_write(self):
        """Test que l'écriture d'un IBAN valide avance automatiquement l'étape"""
        # Créer une demande sans IBAN
        demande = self.env['raccordement.demande'].create({
            'pdl': 'TEST123456789',
            'date_debut_souhaitee': date.today() + timedelta(days=30),
            'puissance_souscrite': '6',
            'contact_nom': 'Test',
            'contact_email': 'test@example.com',
            'contact_street': 'Test Street',
            'contact_zip': '12345',
            'contact_city': 'Test City',
            'mode_paiement': 'prelevement',
            'stage_id': self.stage_received.id,
        })
        
        # Vérifier qu'elle est dans l'étape initiale
        self.assertEqual(demande.stage_id, self.stage_received)
        
        # Ajouter un IBAN valide
        demande.write({
            'bank_iban': 'FR7612345678901234567890123',
            'bank_bic': 'BNPAFRPP',
        })
        
        # Vérifier qu'elle a avancé automatiquement
        self.assertEqual(demande.stage_id, self.stage_iban_validated)
    
    def test_no_auto_advance_for_invalid_iban(self):
        """Test qu'un IBAN invalide n'avance pas automatiquement"""
        demande = self.env['raccordement.demande'].create({
            'pdl': 'TEST123456789',
            'date_debut_souhaitee': date.today() + timedelta(days=30),
            'puissance_souscrite': '6',
            'contact_nom': 'Test',
            'contact_email': 'test@example.com',
            'contact_street': 'Test Street',
            'contact_zip': '12345',
            'contact_city': 'Test City',
            'mode_paiement': 'prelevement',
            'stage_id': self.stage_received.id,
        })
        
        # Ajouter un IBAN invalide
        demande.write({
            'bank_iban': 'INVALID123',
        })
        
        # Vérifier qu'elle n'a pas avancé
        self.assertEqual(demande.stage_id, self.stage_received)
    
    def test_no_auto_advance_for_non_prelevement(self):
        """Test qu'une demande sans prélèvement n'avance pas automatiquement"""
        demande = self.env['raccordement.demande'].create({
            'pdl': 'TEST123456789',
            'date_debut_souhaitee': date.today() + timedelta(days=30),
            'puissance_souscrite': '6',
            'contact_nom': 'Test',
            'contact_email': 'test@example.com',
            'contact_street': 'Test Street',
            'contact_zip': '12345',
            'contact_city': 'Test City',
            'mode_paiement': 'virement',  # Pas de prélèvement
            'stage_id': self.stage_received.id,
        })
        
        # Ajouter un IBAN valide
        demande.write({
            'bank_iban': 'FR7612345678901234567890123',
        })
        
        # Vérifier qu'elle n'a pas avancé (pas de prélèvement)
        self.assertEqual(demande.stage_id, self.stage_received)
    
    def test_no_auto_advance_if_already_advanced(self):
        """Test qu'une demande déjà avancée ne recule pas"""
        demande = self.create_demande_with_valid_iban(
            stage_id=self.stage_sge.id  # Déjà dans une étape avancée
        )
        
        # Modifier l'IBAN
        demande.write({
            'bank_iban': 'FR7698765432109876543210987',  # Autre IBAN valide
        })
        
        # Vérifier qu'elle n'a pas reculé
        self.assertEqual(demande.stage_id, self.stage_sge)
    
    def test_action_verify_iban_batch_success(self):
        """Test de l'action de vérification IBAN en lot avec succès"""
        # Créer plusieurs demandes avec IBAN valide dans l'étape initiale
        demande1 = self.create_demande_with_valid_iban(pdl='PDL001')
        demande2 = self.create_demande_with_valid_iban(pdl='PDL002')
        
        # Créer une demande avec IBAN invalide (ne doit pas bouger)
        demande3 = self.create_demande_with_valid_iban(
            pdl='PDL003',
            bank_iban='INVALID123'
        )
        
        # Lancer l'action en lot
        result = self.env['raccordement.demande'].action_verify_iban_batch()
        
        # Vérifier que les demandes valides ont avancé
        self.assertEqual(demande1.stage_id, self.stage_iban_validated)
        self.assertEqual(demande2.stage_id, self.stage_iban_validated)
        
        # Vérifier que la demande invalide n'a pas bougé
        self.assertEqual(demande3.stage_id, self.stage_received)
        
        # Vérifier le retour de l'action
        self.assertEqual(result['type'], 'ir.actions.client')
        self.assertIn('2 demande(s)', result['params']['message'])
    
    def test_action_verify_iban_batch_no_candidates(self):
        """Test de l'action de vérification IBAN en lot sans candidats"""
        # Créer une demande déjà dans la bonne étape
        self.create_demande_with_valid_iban(stage_id=self.stage_iban_validated.id)
        
        # Lancer l'action en lot
        result = self.env['raccordement.demande'].action_verify_iban_batch()
        
        # Vérifier le message d'information
        self.assertEqual(result['type'], 'ir.actions.client')
        self.assertIn('Aucune demande', result['params']['message'])
    
    def test_action_force_verify_iban_success(self):
        """Test de l'action de force validation IBAN"""
        demande = self.create_demande_with_valid_iban()
        
        # Forcer la validation
        result = demande.action_force_verify_iban()
        
        # Vérifier que la demande a avancé
        self.assertEqual(demande.stage_id, self.stage_iban_validated)
        
        # Vérifier le retour de l'action
        self.assertEqual(result['type'], 'ir.actions.client')
        self.assertEqual(result['params']['type'], 'success')
    
    def test_action_force_verify_iban_no_iban(self):
        """Test de l'action de force validation sans IBAN"""
        demande = self.create_demande_with_valid_iban(bank_iban='')
        
        # Essayer de forcer la validation
        with self.assertRaises(UserError) as cm:
            demande.action_force_verify_iban()
        
        self.assertIn("Aucun IBAN renseigné", str(cm.exception))
    
    def test_action_force_verify_iban_invalid(self):
        """Test de l'action de force validation avec IBAN invalide"""
        demande = self.create_demande_with_valid_iban(bank_iban='INVALID123')
        
        # Essayer de forcer la validation
        with self.assertRaises(UserError) as cm:
            demande.action_force_verify_iban()
        
        self.assertIn("n'est pas valide", str(cm.exception))
    
    def test_action_force_verify_iban_non_prelevement(self):
        """Test de l'action de force validation pour non-prélèvement"""
        demande = self.create_demande_with_valid_iban(mode_paiement='virement')
        
        # Essayer de forcer la validation
        with self.assertRaises(UserError) as cm:
            demande.action_force_verify_iban()
        
        self.assertIn("prélèvement automatique", str(cm.exception))
    
    def test_action_force_verify_iban_already_advanced(self):
        """Test de l'action de force validation sur demande déjà avancée"""
        demande = self.create_demande_with_valid_iban(stage_id=self.stage_sge.id)
        
        # Essayer de forcer la validation
        with self.assertRaises(UserError) as cm:
            demande.action_force_verify_iban()
        
        self.assertIn("étape avancée", str(cm.exception))
    
    def test_cron_auto_verify_iban(self):
        """Test du cron job de vérification automatique"""
        # Créer des demandes test
        demande1 = self.create_demande_with_valid_iban(pdl='PDL001')
        demande2 = self.create_demande_with_valid_iban(pdl='PDL002')
        demande3 = self.create_demande_with_valid_iban(
            pdl='PDL003',
            bank_iban='INVALID123'
        )
        
        # Lancer le cron
        self.env['raccordement.demande'].cron_auto_verify_iban()
        
        # Vérifier les résultats
        self.assertEqual(demande1.stage_id, self.stage_iban_validated)
        self.assertEqual(demande2.stage_id, self.stage_iban_validated)
        self.assertEqual(demande3.stage_id, self.stage_received)
    
    def test_message_post_on_auto_advance(self):
        """Test que les messages sont bien postés lors de l'avancement automatique"""
        demande = self.create_demande_with_valid_iban()
        
        # Compter les messages avant
        messages_before = len(demande.message_ids)
        
        # Déclencher l'avancement automatique en modifiant l'IBAN
        demande.write({'bank_iban': 'FR7698765432109876543210987'})
        
        # Vérifier qu'un message a été ajouté
        messages_after = len(demande.message_ids)
        self.assertGreater(messages_after, messages_before)
        
        # Vérifier le contenu du message
        last_message = demande.message_ids[0]
        self.assertIn("IBAN vérifié automatiquement", last_message.body)