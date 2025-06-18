from odoo.tests.common import TransactionCase, tagged
from odoo.exceptions import UserError
from datetime import date, timedelta


@tagged('souscriptions', 'post_install', '-at_install')
class TestFacturation(TransactionCase):
    
    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({
            'name': 'Test Client Facturation',
            'is_company': False,
        })
        
        self.etat_actif = self.env['souscription.etat'].create({
            'name': 'Actif',
            'sequence': 1,
        })
        
        # Créer une grille de prix basique pour les tests
        self.grille_prix = self.env['grille.prix'].create({
            'name': 'Grille Test',
            'date_debut': date(2024, 1, 1),
            'date_fin': date(2024, 12, 31),
            'active': True,
        })
        
        self.souscription = self.env['souscription'].create({
            'partner_id': self.partner.id,
            'pdl': 'PDL_TEST_001',
            'puissance_souscrite': '6',
            'type_tarif': 'base',
            'etat_facturation_id': self.etat_actif.id,
            'date_debut': date(2024, 1, 1),
            'provision_mensuelle_kwh': 300.0,
        })
    
    def test_creation_periode_mensuelle(self):
        """Test création d'une période de facturation"""
        periode = self.env['souscription.periode'].create({
            'souscription_id': self.souscription.id,
            'date_debut': date(2024, 1, 1),
            'date_fin': date(2024, 1, 31),
            'type_periode': 'mensuelle',
            'provision_base_kwh': 280.0,
        })
        
        self.assertEqual(periode.souscription_id, self.souscription)
        self.assertEqual(periode.provision_base_kwh, 280.0)
        self.assertEqual(periode.jours, 31)
    
    def test_creation_periode_hphc(self):
        """Test création période HP/HC"""
        souscription_hphc = self.env['souscription'].create({
            'partner_id': self.partner.id,
            'pdl': 'PDL_HPHC_001',
            'puissance_souscrite': '9',
            'type_tarif': 'hphc',
            'etat_facturation_id': self.etat_actif.id,
        })
        
        periode = self.env['souscription.periode'].create({
            'souscription_id': souscription_hphc.id,
            'date_debut': date(2024, 2, 1),
            'date_fin': date(2024, 2, 29),
            'type_periode': 'mensuelle',
            'provision_hp_kwh': 150.0,
            'provision_hc_kwh': 120.0,
        })
        
        self.assertEqual(periode.provision_hp_kwh, 150.0)
        self.assertEqual(periode.provision_hc_kwh, 120.0)
    
    def test_get_produit_abonnement(self):
        """Test récupération produits abonnement"""
        produit_standard = self.souscription._get_produit_abonnement(False)
        self.assertEqual(produit_standard.name, 'Abonnement')
        
        produit_solidaire = self.souscription._get_produit_abonnement(True)
        self.assertEqual(produit_solidaire.name, 'Abonnement solidaire')
    
    def test_get_produit_energie(self):
        """Test récupération produits énergie"""
        produit_base = self.souscription._get_produit_energie('base')
        self.assertEqual(produit_base.name, 'Énergie Base')
        
        produit_hp = self.souscription._get_produit_energie('hp')
        self.assertEqual(produit_hp.name, 'Énergie HP')
        
        produit_hc = self.souscription._get_produit_energie('hc')
        self.assertEqual(produit_hc.name, 'Énergie HC')
        
        with self.assertRaises(UserError):
            self.souscription._get_produit_energie('inexistant')
    
    def test_ajouter_periodes_mensuelles(self):
        """Test création automatique des périodes mensuelles"""
        # Marquer la souscription comme active
        self.souscription.active = True
        
        count_before = len(self.souscription.periode_ids)
        
        # Appeler la méthode de création des périodes
        self.env['souscription'].ajouter_periodes_mensuelles()
        
        # Vérifier qu'une période a été créée
        count_after = len(self.souscription.periode_ids)
        self.assertGreater(count_after, count_before)
    
    def test_api_externe_get_souscriptions_by_pdl(self):
        """Test API pour pont externe - recherche par PDL"""
        result = self.env['souscription'].get_souscriptions_by_pdl(['PDL_TEST_001'])
        
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['pdl'], 'PDL_TEST_001')
        self.assertEqual(result[0]['puissance_souscrite'], '6')
    
    def test_api_externe_get_billing_periods(self):
        """Test API récupération périodes de facturation"""
        # Créer une période pour le test
        periode = self.env['souscription.periode'].create({
            'souscription_id': self.souscription.id,
            'date_debut': date(2024, 3, 1),
            'date_fin': date(2024, 3, 31),
            'type_periode': 'mensuelle',
            'provision_base_kwh': 250.0,
        })
        
        periods = self.souscription.get_billing_periods(
            date_start=date(2024, 3, 1),
            date_end=date(2024, 3, 31)
        )
        
        self.assertEqual(len(periods), 1)
        self.assertEqual(periods[0]['date_debut'], date(2024, 3, 1))
        self.assertEqual(periods[0]['date_fin'], date(2024, 3, 31))