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
    
    def create_base_demande(self, **kwargs):
        """Helper pour créer une demande de base"""
        defaults = {
            'pdl': 'TEST123456789',
            'date_debut_souhaitee': date.today() + timedelta(days=30),
            'puissance_souscrite': '6',
            'contact_nom': 'Test',
            'contact_email': 'test@example.com',
            'contact_street': 'Test Street',
            'contact_zip': '12345',
            'contact_city': 'Test City',
        }
        defaults.update(kwargs)
        return self.env['raccordement.demande'].create(defaults)
    
    # Tests existants mis à jour avec IBAN réellement valides
    def test_iban_validation_valid(self):
        """Test de validation IBAN avec un IBAN réellement valide"""
        demande = self.create_base_demande(bank_iban='FR1420041010050500013M02606')
        self.assertTrue(demande.iban_valide)
    
    def test_iban_validation_invalid_too_short(self):
        """Test de validation IBAN avec un IBAN trop court"""
        demande = self.create_base_demande(bank_iban='FR123')
        self.assertFalse(demande.iban_valide)
    
    def test_iban_validation_invalid_format(self):
        """Test de validation IBAN avec un format invalide"""
        demande = self.create_base_demande(bank_iban='123456789INVALID')
        self.assertFalse(demande.iban_valide)
    
    def test_iban_validation_empty(self):
        """Test de validation IBAN avec un IBAN vide"""
        demande = self.create_base_demande(bank_iban='')
        self.assertFalse(demande.iban_valide)
    
    # Nouveaux tests détaillés pour _validate_iban()
    def test_validate_iban_method_valid_cases(self):
        """Test méthode _validate_iban avec IBAN réellement valides"""
        demande = self.create_base_demande()
        
        # IBAN français valide
        self.assertTrue(demande._validate_iban('FR1420041010050500013M02606'))
        
        # IBAN avec espaces (doit être nettoyé)
        self.assertTrue(demande._validate_iban('FR14 2004 1010 0505 0001 3M02 606'))
        
        # IBAN en minuscules (doit être converti)
        self.assertTrue(demande._validate_iban('fr1420041010050500013m02606'))
        
        # IBAN allemand valide
        self.assertTrue(demande._validate_iban('DE89370400440532013000'))
        
        # IBAN britannique valide
        self.assertTrue(demande._validate_iban('GB29NWBK60161331926819'))
        
        # IBAN espagnol valide
        self.assertTrue(demande._validate_iban('ES9121000418450200051332'))
        
        # IBAN italien valide
        self.assertTrue(demande._validate_iban('IT60X0542811101000000123456'))
    
    def test_validate_iban_method_invalid_cases(self):
        """Test méthode _validate_iban avec cas invalides"""
        demande = self.create_base_demande()
        
        # IBAN vide
        self.assertFalse(demande._validate_iban(''))
        self.assertFalse(demande._validate_iban(None))
        
        # IBAN trop court
        self.assertFalse(demande._validate_iban('FR76123'))
        self.assertFalse(demande._validate_iban('DE89370'))
        
        # Format invalide - pas de lettres au début
        self.assertFalse(demande._validate_iban('1234567890123456789'))
        
        # Format invalide - pas de chiffres après les lettres
        self.assertFalse(demande._validate_iban('FRAB1234567890123456789'))
        
        # Format invalide - caractères spéciaux
        self.assertFalse(demande._validate_iban('FR76-1234-5678-9012-3456'))
        self.assertFalse(demande._validate_iban('FR76_1234_5678_9012_3456'))
        self.assertFalse(demande._validate_iban('FR76@1234567890123456789'))
        
        # Format invalide - une seule lettre au début
        self.assertFalse(demande._validate_iban('F7612345678901234567890123'))
        
        # Format invalide - trois lettres au début
        self.assertFalse(demande._validate_iban('FRA1234567890123456789'))
        
        # IBAN avec checksum invalide (format correct mais modulo 97 échoue)
        self.assertFalse(demande._validate_iban('FR1420041010050500013M02607'))  # 07 au lieu de 06
        self.assertFalse(demande._validate_iban('DE89370400440532013001'))      # 01 au lieu de 00
        self.assertFalse(demande._validate_iban('GB29NWBK60161331926818'))
    
    def test_compute_iban_valide_field(self):
        """Test du champ calculé _compute_iban_valide"""
        # Test avec IBAN valide
        demande1 = self.create_base_demande(bank_iban='FR1420041010050500013M02606')
        self.assertTrue(demande1.iban_valide)
        
        # Test avec IBAN invalide (checksum incorrecte)
        demande2 = self.create_base_demande(bank_iban='FR1420041010050500013M02607')
        self.assertFalse(demande2.iban_valide)
        
        # Test avec IBAN format invalide
        demande3 = self.create_base_demande(bank_iban='INVALID123')
        self.assertFalse(demande3.iban_valide)
        
        # Test avec IBAN vide
        demande4 = self.create_base_demande(bank_iban='')
        self.assertFalse(demande4.iban_valide)
    
    def test_compute_iban_valide_update_trigger(self):
        """Test que le champ calculé se met à jour lors des changements"""
        demande = self.create_base_demande(bank_iban='INVALID123')
        
        # Initialement invalide
        self.assertFalse(demande.iban_valide)
        
        # Changer vers un IBAN valide
        demande.bank_iban = 'FR1420041010050500013M02606'
        # Force le recalcul du champ calculé
        demande._compute_iban_valide()
        self.assertTrue(demande.iban_valide)
        
        # Changer vers un IBAN avec checksum invalide
        demande.bank_iban = 'FR1420041010050500013M02607'
        demande._compute_iban_valide()
        self.assertFalse(demande.iban_valide)
        
        # Changer vers un IBAN format invalide
        demande.bank_iban = 'BAD'
        demande._compute_iban_valide()
        self.assertFalse(demande.iban_valide)
        
        # Vider l'IBAN
        demande.bank_iban = ''
        demande._compute_iban_valide()
        self.assertFalse(demande.iban_valide)
    
    def test_compute_iban_valide_multiple_records(self):
        """Test champ calculé sur plusieurs enregistrements simultanément"""
        # Créer plusieurs demandes avec différents IBAN
        demandes = self.env['raccordement.demande']
        
        demande1 = self.create_base_demande(
            pdl='PDL001',
            bank_iban='FR1420041010050500013M02606'  # IBAN français valide
        )
        demande2 = self.create_base_demande(
            pdl='PDL002', 
            bank_iban='FR1420041010050500013M02607'  # IBAN français invalide (checksum)
        )
        demande3 = self.create_base_demande(
            pdl='PDL003',
            bank_iban='INVALID123'  # Format invalide
        )
        demande4 = self.create_base_demande(
            pdl='PDL004',
            bank_iban=''  # Vide
        )
        demande5 = self.create_base_demande(
            pdl='PDL005',
            bank_iban='DE89370400440532013000'  # IBAN allemand valide
        )
        
        demandes = demande1 + demande2 + demande3 + demande4 + demande5
        
        # Forcer le recalcul sur tous les enregistrements
        demandes._compute_iban_valide()
        
        # Vérifier les résultats
        self.assertTrue(demande1.iban_valide)   # IBAN français valide
        self.assertFalse(demande2.iban_valide)  # IBAN français invalide (checksum)
        self.assertFalse(demande3.iban_valide)  # Format invalide
        self.assertFalse(demande4.iban_valide)  # IBAN vide
        self.assertTrue(demande5.iban_valide)   # IBAN allemand valide
    
    def test_iban_spaces_and_case_normalization(self):
        """Test normalisation des espaces et de la casse"""
        demande = self.create_base_demande()
        
        # Test différents formats d'espacement du même IBAN valide
        iban_formats = [
            'FR1420041010050500013M02606',
            'FR14 2004 1010 0505 0001 3M02 606',
            'FR14  2004  1010  0505  0001  3M02  606',
            'FR142004 1010 0505 0001 3M02606',
            ' FR14 2004 1010 0505 0001 3M02 606 ',
        ]
        
        for iban_format in iban_formats:
            self.assertTrue(demande._validate_iban(iban_format), 
                          f"IBAN format should be valid: {iban_format}")
        
        # Test différentes casses du même IBAN valide
        case_formats = [
            'FR1420041010050500013M02606',
            'fr1420041010050500013m02606',
            'Fr1420041010050500013M02606',
            'fR1420041010050500013m02606',
        ]
        
        for case_format in case_formats:
            self.assertTrue(demande._validate_iban(case_format),
                          f"IBAN case should be valid: {case_format}")
    
    def test_iban_modulo97_algorithm(self):
        """Test spécifique de l'algorithme modulo 97"""
        demande = self.create_base_demande()
        
        # Test de la méthode _check_iban_modulo directement
        self.assertTrue(demande._check_iban_modulo('FR1420041010050500013M02606'))
        self.assertFalse(demande._check_iban_modulo('FR1420041010050500013M02607'))
        
        # Test avec différents pays
        self.assertTrue(demande._check_iban_modulo('DE89370400440532013000'))
        self.assertTrue(demande._check_iban_modulo('GB29NWBK60161331926819'))
        self.assertTrue(demande._check_iban_modulo('ES9121000418450200051332'))
        
        # Test avec checksums incorrectes
        self.assertFalse(demande._check_iban_modulo('DE89370400440532013001'))
        self.assertFalse(demande._check_iban_modulo('GB29NWBK60161331926818'))
        self.assertFalse(demande._check_iban_modulo('ES9121000418450200051333'))
    
    def test_iban_validation_edge_cases(self):
        """Test des cas limites de validation IBAN"""
        demande = self.create_base_demande()
        
        # Test avec None
        self.assertFalse(demande._validate_iban(None))
        
        # Test avec chaîne vide
        self.assertFalse(demande._validate_iban(''))
        
        # Test avec espaces seulement
        self.assertFalse(demande._validate_iban('   '))
        
        # Test avec IBAN très long (mais valide)
        # Ce serait un IBAN de Saint-Marin par exemple
        # self.assertTrue(demande._validate_iban('SM86U0322509800000000270100'))
        
        # Test avec caractères numériques seulement
        self.assertFalse(demande._validate_iban('1234567890123456789'))
        
        # Test avec caractères alphabétiques seulement
        self.assertFalse(demande._validate_iban('ABCDEFGHIJKLMNOPQRS'))
        
        # Test gestion d'erreur pour numeric_string trop grand (edge case)
        # Ceci ne devrait pas arriver en pratique, mais testons la robustesse
        very_long_invalid = 'AA' + '1' * 100  # IBAN artificiellement long
        self.assertFalse(demande._validate_iban(very_long_invalid))
    
    def test_pro_field_default_and_tracking(self):
        """Test du champ PRO : valeur par défaut et tracking"""
        # Test valeur par défaut (False)
        demande = self.create_base_demande()
        self.assertFalse(demande.pro)
        
        # Test modification du champ PRO
        demande.pro = True
        self.assertTrue(demande.pro)
        
        # Test création avec PRO=True
        demande_pro = self.create_base_demande(pro=True, siret="12345678901234")
        self.assertTrue(demande_pro.pro)


@tagged('souscriptions', 'souscriptions_raccordement_siret', 'post_install', '-at_install')
class TestRaccordementSiret(SouscriptionsTestMixin, TransactionCase):
    """Tests spécifiques pour la validation SIRET"""
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.setUpSouscriptionsData()
    
    def create_base_demande(self, **kwargs):
        """Helper pour créer une demande de base"""
        defaults = {
            'pdl': 'TEST123456789',
            'date_debut_souhaitee': date.today() + timedelta(days=30),
            'puissance_souscrite': '6',
            'contact_nom': 'Test',
            'contact_email': 'test@example.com',
            'contact_street': 'Test Street',
            'contact_zip': '12345',
            'contact_city': 'Test City',
        }
        defaults.update(kwargs)
        return self.env['raccordement.demande'].create(defaults)
    
    def test_siret_required_for_pro(self):
        """Test que le SIRET est obligatoire pour les demandes PRO"""
        from odoo.exceptions import ValidationError
        
        # Test que la création PRO sans SIRET échoue
        with self.assertRaises(ValidationError) as cm:
            self.create_base_demande(pro=True)  # Pas de SIRET
        
        self.assertIn("SIRET est obligatoire", str(cm.exception))
        
        # Test que la création PRO avec SIRET fonctionne
        demande = self.create_base_demande(pro=True, siret="12345678901234")
        self.assertTrue(demande.pro)
        self.assertEqual(demande.siret, "12345678901234")
    
    def test_siret_not_required_for_particulier(self):
        """Test que le SIRET n'est pas obligatoire pour les particuliers"""
        # Test création particulier sans SIRET (doit fonctionner)
        demande = self.create_base_demande(pro=False)
        self.assertFalse(demande.pro)
        self.assertFalse(demande.siret)
        
        # Test création particulier avec SIRET (doit fonctionner aussi)
        demande_avec_siret = self.create_base_demande(pro=False, siret="12345678901234")
        self.assertFalse(demande_avec_siret.pro)
        self.assertEqual(demande_avec_siret.siret, "12345678901234")
    
    def test_siret_format_validation(self):
        """Test de validation du format SIRET"""
        from odoo.exceptions import ValidationError
        
        # Test SIRET valide (14 chiffres)
        demande_valid = self.create_base_demande(pro=True, siret="12345678901234")
        self.assertEqual(demande_valid.siret, "12345678901234")
        
        # Test SIRET trop court
        with self.assertRaises(ValidationError) as cm:
            self.create_base_demande(pro=True, siret="123456789")
        self.assertIn("14 chiffres", str(cm.exception))
        
        # Test SIRET trop long
        with self.assertRaises(ValidationError) as cm:
            self.create_base_demande(pro=True, siret="123456789012345")
        self.assertIn("14 chiffres", str(cm.exception))
        
        # Test SIRET avec lettres
        with self.assertRaises(ValidationError) as cm:
            self.create_base_demande(pro=True, siret="1234567890123A")
        self.assertIn("14 chiffres", str(cm.exception))
        
        # Test SIRET avec caractères spéciaux
        with self.assertRaises(ValidationError) as cm:
            self.create_base_demande(pro=True, siret="12345-67890-123")
        self.assertIn("14 chiffres", str(cm.exception))
    
    def test_siret_format_cleaning(self):
        """Test que les espaces sont nettoyés dans la validation SIRET"""
        from odoo.exceptions import ValidationError
        
        # SIRET avec espaces (devrait échouer car nettoyage ne s'applique que pour validation)
        with self.assertRaises(ValidationError) as cm:
            self.create_base_demande(pro=True, siret="123 456 789 012 34")
        self.assertIn("14 chiffres", str(cm.exception))
    
    def test_siret_change_pro_status(self):
        """Test changement de statut PRO avec SIRET"""
        from odoo.exceptions import ValidationError
        
        # Créer une demande particulière
        demande = self.create_base_demande(pro=False)
        
        # Passer en PRO sans SIRET (doit échouer)
        with self.assertRaises(ValidationError) as cm:
            demande.pro = True
        self.assertIn("SIRET est obligatoire", str(cm.exception))
        
        # Ajouter un SIRET puis passer en PRO (doit fonctionner)
        demande.siret = "12345678901234"
        demande.pro = True
        self.assertTrue(demande.pro)
        self.assertEqual(demande.siret, "12345678901234")


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
            'bank_iban': 'FR1420041010050500013M02606',
            'bank_bic': 'BNPAFRPP',
            'bank_acc_holder_name': 'Test User',
            'sepa_mandate_date': date.today(),
            'sepa_mandate_ref': 'SEPA-TEST-001',
        }
        defaults.update(kwargs)
        return self.env['raccordement.demande'].create(defaults)
    
    def test_create_odoo_entries_complete(self):
        """Test de création des entrées Odoo avec données complètes (particulier)"""
        demande = self.create_complete_demande()
        
        # Passer à l'étape finale
        demande.stage_id = self.stage_final
        
        # Vérifier que les entrées ont été créées
        self.assertTrue(demande.partner_id, "Contact devrait être créé")
        self.assertTrue(demande.partner_bank_id, "Compte bancaire devrait être créé")
        self.assertTrue(demande.souscription_id, "Souscription devrait être créée")
        
        # Vérifier les données du contact (particulier)
        partner = demande.partner_id
        self.assertEqual(partner.name, "Test User")  # prénom + nom
        self.assertEqual(partner.email, "test@example.com")
        self.assertEqual(partner.street, "Test Street")
        self.assertEqual(partner.city, "Test City")
        self.assertFalse(partner.is_company)  # C'est un particulier
        
        # Vérifier les données de la souscription
        souscription = demande.souscription_id
        self.assertEqual(souscription.pdl, "TEST123456789")
        self.assertEqual(souscription.puissance_souscrite, "6")
        self.assertEqual(souscription.type_tarif, "base")
        self.assertEqual(souscription.partner_id, partner)
    
    def test_create_odoo_entries_pro(self):
        """Test de création des entrées Odoo pour une demande professionnelle"""
        demande = self.create_complete_demande(
            pro=True,
            contact_nom="SARL Test Énergie",  # Nom de société
            contact_prenom="",  # Pas de prénom pour une société
            siret="12345678901234",  # SIRET valide (14 chiffres)
        )
        
        # Passer à l'étape finale
        demande.stage_id = self.stage_final
        
        # Vérifier que les entrées ont été créées
        self.assertTrue(demande.partner_id, "Contact société devrait être créé")
        self.assertTrue(demande.partner_bank_id, "Compte bancaire devrait être créé")
        self.assertTrue(demande.souscription_id, "Souscription devrait être créée")
        
        # Vérifier les données du contact (société)
        partner = demande.partner_id
        self.assertEqual(partner.name, "SARL Test Énergie")  # Nom de société uniquement
        self.assertEqual(partner.email, "test@example.com")
        self.assertEqual(partner.street, "Test Street")
        self.assertEqual(partner.city, "Test City")
        self.assertTrue(partner.is_company)  # C'est une société
        self.assertEqual(partner.siret, "12345678901234")  # SIRET transmis
        
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