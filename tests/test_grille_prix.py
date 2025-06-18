from odoo.tests.common import TransactionCase, tagged
from odoo.exceptions import UserError
from datetime import date


@tagged('souscriptions', 'post_install', '-at_install')
class TestGrillePrix(TransactionCase):
    
    def setUp(self):
        super().setUp()
        self.grille = self.env['grille.prix'].create({
            'name': 'Grille Test 2024',
            'date_debut': date(2024, 1, 1),
            'date_fin': date(2024, 12, 31),
            'active': True,
            'prix_abonnement_3kva': 10.50,
            'prix_abonnement_6kva': 15.75,
            'prix_abonnement_9kva': 20.25,
            'prix_abonnement_12kva': 25.50,
            'coefficient_pro': 1.15,
            'reduction_solidaire': 0.10,
        })
        
        # Créer des lignes de prix énergie
        produit_base = self.env.ref('souscriptions.souscriptions_product_energie_base')
        produit_hp = self.env.ref('souscriptions.souscriptions_product_energie_hp')
        produit_hc = self.env.ref('souscriptions.souscriptions_product_energie_hc')
        
        self.env['grille.prix.ligne'].create([
            {
                'grille_id': self.grille.id,
                'product_id': produit_base.id,
                'prix_interne': 0.2276,
            },
            {
                'grille_id': self.grille.id,
                'product_id': produit_hp.id,
                'prix_interne': 0.2516,
            },
            {
                'grille_id': self.grille.id,
                'product_id': produit_hc.id,
                'prix_interne': 0.2032,
            }
        ])
    
    def test_grille_creation(self):
        """Test création grille de prix"""
        self.assertEqual(self.grille.name, 'Grille Test 2024')
        self.assertTrue(self.grille.active)
        self.assertEqual(len(self.grille.ligne_ids), 3)
    
    def test_get_grille_active(self):
        """Test récupération grille active"""
        grille_active = self.env['grille.prix'].get_grille_active(date(2024, 6, 15))
        self.assertEqual(grille_active, self.grille)
        
        # Test avec date hors période
        with self.assertRaises(UserError):
            self.env['grille.prix'].get_grille_active(date(2025, 6, 15))
    
    def test_get_prix_dict(self):
        """Test récupération dictionnaire des prix"""
        prix_dict = self.grille.get_prix_dict()
        
        produit_base = self.env.ref('souscriptions.souscriptions_product_energie_base')
        produit_hp = self.env.ref('souscriptions.souscriptions_product_energie_hp')
        produit_hc = self.env.ref('souscriptions.souscriptions_product_energie_hc')
        
        self.assertEqual(prix_dict[produit_base.id], 0.2276)
        self.assertEqual(prix_dict[produit_hp.id], 0.2516)
        self.assertEqual(prix_dict[produit_hc.id], 0.2032)
    
    def test_calcul_prix_abonnement_particulier(self):
        """Test calcul prix abonnement particulier"""
        # 6 kVA particulier
        prix_journalier = self.grille.get_prix_abonnement(
            puissance_kva=6.0,
            coeff_pro=0.0,
            is_solidaire=False
        )
        prix_attendu = 15.75 / 365  # Prix annuel / 365 jours
        self.assertAlmostEqual(prix_journalier, prix_attendu, places=4)
    
    def test_calcul_prix_abonnement_pro(self):
        """Test calcul prix abonnement PRO avec majoration"""
        # 9 kVA PRO (15% majoration)
        prix_journalier = self.grille.get_prix_abonnement(
            puissance_kva=9.0,
            coeff_pro=15.0,
            is_solidaire=False
        )
        prix_base = 20.25 / 365
        prix_attendu = prix_base * 1.15  # +15%
        self.assertAlmostEqual(prix_journalier, prix_attendu, places=4)
    
    def test_calcul_prix_abonnement_solidaire(self):
        """Test calcul prix abonnement solidaire"""
        # 3 kVA solidaire (-10%)
        prix_journalier = self.grille.get_prix_abonnement(
            puissance_kva=3.0,
            coeff_pro=0.0,
            is_solidaire=True
        )
        prix_base = 10.50 / 365
        prix_attendu = prix_base * 0.90  # -10%
        self.assertAlmostEqual(prix_journalier, prix_attendu, places=4)
    
    def test_calcul_prix_puissance_non_standard(self):
        """Test calcul avec puissance non-standard"""
        with self.assertRaises(UserError):
            self.grille.get_prix_abonnement(
                puissance_kva=7.0,  # Puissance non définie
                coeff_pro=0.0,
                is_solidaire=False
            )
    
    def test_grilles_multiples_chevauchement(self):
        """Test gestion de grilles avec périodes qui se chevauchent"""
        # Créer une seconde grille qui chevauche
        grille2 = self.env['grille.prix'].create({
            'name': 'Grille 2024 Bis',
            'date_debut': date(2024, 6, 1),
            'date_fin': date(2024, 12, 31),
            'active': True,
            'prix_abonnement_6kva': 16.00,
        })
        
        # La première grille doit devenir inactive
        self.grille._check_chevauchement()
        self.assertFalse(self.grille.active)
        self.assertTrue(grille2.active)