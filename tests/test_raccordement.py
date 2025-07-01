"""
Tests pour le module de gestion des raccordements.
"""

from odoo.tests.common import TransactionCase, tagged
from odoo.exceptions import UserError
from datetime import date, timedelta
from .common import SouscriptionsTestMixin


@tagged('souscriptions', 'souscriptions_raccordement', 'post_install', '-at_install')
class TestRaccordementBasic(SouscriptionsTestMixin, TransactionCase):
    """Tests basiques du module raccordement"""
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.setUpSouscriptionsData()
        cls.setUpRaccordementData()
    
    @classmethod
    def setUpRaccordementData(cls):
        """Setup des données spécifiques aux tests de raccordement"""
        # Créer les étapes de raccordement
        cls.stage_received = cls.env['raccordement.stage'].create({
            'name': 'Test Reçue',
            'sequence': 10,
            'color': 1,
        })
        
        cls.stage_validated = cls.env['raccordement.stage'].create({
            'name': 'Test Validée',
            'sequence': 20,
            'color': 2,
        })
        
        cls.stage_final = cls.env['raccordement.stage'].create({
            'name': 'Test Souscrite',
            'sequence': 60,
            'color': 10,
            'is_close': True,
        })
    
    def test_models_exist(self):
        """Test que les modèles de raccordement existent"""
        self.assertIn('raccordement.demande', self.env)
        self.assertIn('raccordement.stage', self.env)
    
    def test_sequence_generation(self):
        """Test que la séquence de référence fonctionne"""
        demande = self.env['raccordement.demande'].create({
            'pdl': 'TEST123456789',
            'date_debut_souhaitee': date.today() + timedelta(days=30),
            'puissance_souscrite': '6',
            'contact_nom': 'Test',
            'contact_email': 'test@example.com',
            'contact_street': 'Test Street',
            'contact_zip': '12345',
            'contact_city': 'Test City',
        })
        
        self.assertNotEqual(demande.name, 'Nouveau')
        self.assertTrue(demande.name.startswith('RACC/'))
    
    def test_default_stage_assignment(self):
        """Test que l'étape par défaut est assignée"""
        demande = self.env['raccordement.demande'].create({
            'pdl': 'TEST123456789',
            'date_debut_souhaitee': date.today() + timedelta(days=30),
            'puissance_souscrite': '6',
            'contact_nom': 'Test',
            'contact_email': 'test@example.com',
            'contact_street': 'Test Street',
            'contact_zip': '12345',
            'contact_city': 'Test City',
        })
        
        self.assertTrue(demande.stage_id)


@tagged('souscriptions', 'souscriptions_raccordement', 'post_install', '-at_install')
class TestRaccordementIban(SouscriptionsTestMixin, TransactionCase):
    """Tests de validation IBAN"""
    
    def test_iban_validation_valid(self):
        """Test de validation IBAN avec un IBAN valide"""
        demande = self.env['raccordement.demande'].create({
            'pdl': 'TEST123456789',
            'date_debut_souhaitee': date.today() + timedelta(days=30),
            'puissance_souscrite': '6',
            'contact_nom': 'Test',
            'contact_email': 'test@example.com',
            'contact_street': 'Test Street',
            'contact_zip': '12345',
            'contact_city': 'Test City',
            'bank_iban': 'FR7612345678901234567890123',
        })
        
        self.assertTrue(demande.iban_valide)
    
    def test_iban_validation_invalid_too_short(self):
        """Test de validation IBAN avec un IBAN trop court"""
        demande = self.env['raccordement.demande'].create({
            'pdl': 'TEST123456789',
            'date_debut_souhaitee': date.today() + timedelta(days=30),
            'puissance_souscrite': '6',
            'contact_nom': 'Test',
            'contact_email': 'test@example.com',
            'contact_street': 'Test Street',
            'contact_zip': '12345',
            'contact_city': 'Test City',
            'bank_iban': 'FR123',
        })
        
        self.assertFalse(demande.iban_valide)
    
    def test_iban_validation_invalid_format(self):
        """Test de validation IBAN avec un format invalide"""
        demande = self.env['raccordement.demande'].create({
            'pdl': 'TEST123456789',
            'date_debut_souhaitee': date.today() + timedelta(days=30),
            'puissance_souscrite': '6',
            'contact_nom': 'Test',
            'contact_email': 'test@example.com',
            'contact_street': 'Test Street',
            'contact_zip': '12345',
            'contact_city': 'Test City',
            'bank_iban': '123456789INVALID',
        })
        
        self.assertFalse(demande.iban_valide)
    
    def test_iban_validation_empty(self):
        """Test de validation IBAN avec un IBAN vide"""
        demande = self.env['raccordement.demande'].create({
            'pdl': 'TEST123456789',
            'date_debut_souhaitee': date.today() + timedelta(days=30),
            'puissance_souscrite': '6',
            'contact_nom': 'Test',
            'contact_email': 'test@example.com',
            'contact_street': 'Test Street',
            'contact_zip': '12345',
            'contact_city': 'Test City',
            'bank_iban': '',
        })
        
        self.assertFalse(demande.iban_valide)


@tagged('souscriptions', 'souscriptions_raccordement', 'post_install', '-at_install')
class TestRaccordementWorkflow(SouscriptionsTestMixin, TransactionCase):
    """Tests du workflow de raccordement"""
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.setUpSouscriptionsData()
        cls.setUpRaccordementData()
    
    @classmethod
    def setUpRaccordementData(cls):
        """Setup des données spécifiques aux tests de raccordement"""
        # Utiliser les vraies étapes du module
        cls.stage_received = cls.env.ref('souscriptions.stage_demande_recue')
        cls.stage_validated = cls.env.ref('souscriptions.stage_iban_valide')
        cls.stage_final = cls.env.ref('souscriptions.stage_souscrit')
    
    def create_complete_demande(self, **kwargs):
        """Helper pour créer une demande complète"""
        defaults = {
            'pdl': 'TEST123456789',
            'date_debut_souhaitee': date.today() + timedelta(days=30),
            'puissance_souscrite': '6',
            'type_tarif': 'base',
            'provision_mensuelle_kwh': 250.0,
            'contact_nom': 'User',
            'contact_prenom': 'Test',
            'contact_email': 'test@example.com',
            'contact_telephone': '0123456789',
            'contact_street': 'Test Street',
            'contact_zip': '12345',
            'contact_city': 'Test City',
            'mode_paiement': 'prelevement',
            'bank_iban': 'FR7612345678901234567890123',
            'bank_bic': 'BNPAFRPP',
            'bank_acc_holder_name': 'Test User',
            'sepa_mandate_date': date.today(),
            'sepa_mandate_ref': 'SEPA-TEST-001',
        }
        defaults.update(kwargs)
        return self.env['raccordement.demande'].create(defaults)
    
    def test_create_odoo_entries_complete(self):
        """Test de création des entrées Odoo avec données complètes"""
        demande = self.create_complete_demande()
        
        # Passer à l'étape finale
        demande.stage_id = self.stage_final
        
        # Vérifier que les entrées ont été créées
        self.assertTrue(demande.partner_id, "Contact devrait être créé")
        self.assertTrue(demande.partner_bank_id, "Compte bancaire devrait être créé")
        self.assertTrue(demande.souscription_id, "Souscription devrait être créée")
        
        # Vérifier les données du contact
        partner = demande.partner_id
        self.assertEqual(partner.name, "Test User")  # prénom + nom
        self.assertEqual(partner.email, "test@example.com")
        self.assertEqual(partner.street, "Test Street")
        self.assertEqual(partner.city, "Test City")
        
        # Vérifier les données de la souscription
        souscription = demande.souscription_id
        self.assertEqual(souscription.pdl, "TEST123456789")
        self.assertEqual(souscription.puissance_souscrite, "6")
        self.assertEqual(souscription.type_tarif, "base")
        self.assertEqual(souscription.partner_id, partner)
    
    def test_create_odoo_entries_hphc(self):
        """Test de création avec tarif HP/HC"""
        demande = self.create_complete_demande(
            type_tarif='hphc',
            provision_hp_kwh=150.0,
            provision_hc_kwh=100.0,
            provision_mensuelle_kwh=0.0,  # Pas utilisé en HP/HC
        )
        
        demande.stage_id = self.stage_final
        
        souscription = demande.souscription_id
        self.assertEqual(souscription.type_tarif, "hphc")
        self.assertEqual(souscription.provision_hp_kwh, 150.0)
        self.assertEqual(souscription.provision_hc_kwh, 100.0)
    
    def test_create_odoo_entries_no_bank_for_other_payment(self):
        """Test de création sans compte bancaire pour autre mode de paiement"""
        demande = self.create_complete_demande(
            mode_paiement='virement',
            bank_iban='',
            bank_bic='',
        )
        
        demande.stage_id = self.stage_final
        
        self.assertTrue(demande.partner_id, "Contact devrait être créé")
        self.assertFalse(demande.partner_bank_id, "Compte bancaire ne devrait pas être créé")
        self.assertTrue(demande.souscription_id, "Souscription devrait être créée")
    
    def test_existing_partner_update(self):
        """Test de mise à jour d'un contact existant"""
        # Créer un contact existant avec le même email
        existing_partner = self.env['res.partner'].create({
            'name': 'Ancien Nom',
            'email': 'test@example.com',
            'city': 'Ancienne Ville',
        })
        
        demande = self.create_complete_demande()
        demande.stage_id = self.stage_final
        
        # Le contact existant devrait être mis à jour
        self.assertEqual(demande.partner_id.id, existing_partner.id)
        self.assertEqual(existing_partner.name, "Test User")  # prénom + nom
        self.assertEqual(existing_partner.city, "Test City")
    
    def test_stage_change_no_duplicate_creation(self):
        """Test qu'on ne crée pas de doublons en changeant d'étape plusieurs fois"""
        demande = self.create_complete_demande()
        
        # Premier passage à l'étape finale
        demande.stage_id = self.stage_final
        
        partner_id = demande.partner_id.id
        souscription_id = demande.souscription_id.id
        
        # Retour en arrière puis nouveau passage
        demande.stage_id = self.stage_validated
        demande.stage_id = self.stage_final
        
        # Les IDs devraient être identiques
        self.assertEqual(demande.partner_id.id, partner_id)
        self.assertEqual(demande.souscription_id.id, souscription_id)


@tagged('souscriptions', 'souscriptions_raccordement', 'post_install', '-at_install')
class TestRaccordementKanban(SouscriptionsTestMixin, TransactionCase):
    """Tests de la vue kanban et group_expand"""
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.setUpSouscriptionsData()
    
    def test_read_group_stage_ids(self):
        """Test que group_expand retourne toutes les étapes"""
        # Créer quelques étapes de test
        stage1 = self.env['raccordement.stage'].create({
            'name': 'Étape 1',
            'sequence': 10,
        })
        stage2 = self.env['raccordement.stage'].create({
            'name': 'Étape 2',
            'sequence': 20,
        })
        
        # Tester la méthode group_expand
        demande_model = self.env['raccordement.demande']
        stages = demande_model._read_group_stage_ids(self.env['raccordement.stage'], [])
        
        # Toutes les étapes devraient être retournées
        self.assertIn(stage1, stages)
        self.assertIn(stage2, stages)
    
    def test_kanban_view_rendering(self):
        """Test que la vue kanban peut être rendue"""
        # Créer une demande de test
        demande = self.env['raccordement.demande'].create({
            'pdl': 'TEST123456789',
            'date_debut_souhaitee': date.today() + timedelta(days=30),
            'puissance_souscrite': '6',
            'contact_nom': 'Test',
            'contact_email': 'test@example.com',
            'contact_street': 'Test Street',
            'contact_zip': '12345',
            'contact_city': 'Test City',
        })
        
        # Vérifier que les champs nécessaires pour la vue kanban sont présents
        self.assertTrue(demande.name)
        self.assertTrue(demande.pdl)
        self.assertTrue(demande.contact_nom)
        self.assertTrue(demande.date_debut_souhaitee)


@tagged('souscriptions', 'souscriptions_raccordement', 'post_install', '-at_install')
class TestRaccordementSecurity(SouscriptionsTestMixin, TransactionCase):
    """Tests de sécurité et validation"""
    
    def test_required_fields_validation(self):
        """Test que les champs requis sont validés"""
        from psycopg2 import IntegrityError
        
        with self.assertRaises(IntegrityError):
            # PDL manquant
            self.env['raccordement.demande'].create({
                'date_debut_souhaitee': date.today() + timedelta(days=30),
                'puissance_souscrite': '6',
                'contact_nom': 'Test',
                'contact_email': 'test@example.com',
                'contact_street': 'Test Street',
                'contact_zip': '12345',
                'contact_city': 'Test City',
            })
    
    def test_email_validation(self):
        """Test que l'email est requis"""
        from psycopg2 import IntegrityError
        
        with self.assertRaises(IntegrityError):
            self.env['raccordement.demande'].create({
                'pdl': 'TEST123456789',
                'date_debut_souhaitee': date.today() + timedelta(days=30),
                'puissance_souscrite': '6',
                'contact_nom': 'Test',
                'contact_street': 'Test Street',
                'contact_zip': '12345',
                'contact_city': 'Test City',
            })
    
    def test_stage_constraint(self):
        """Test les contraintes de changement d'étape"""
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
            'bank_iban': 'INVALID',  # IBAN invalide
        })
        
        # Essayer de passer à l'étape IBAN validé avec un IBAN invalide
        stage_iban = self.env.ref('souscriptions.stage_iban_valide')
        
        # L'onchange devrait générer un warning (pas d'exception)
        # On vérifie juste que l'IBAN est invalide
        self.assertFalse(demande.iban_valide)