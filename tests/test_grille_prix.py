from odoo.tests.common import TransactionCase, tagged
from odoo.exceptions import UserError
from datetime import date


@tagged('souscriptions', 'post_install', '-at_install')
class TestGrillePrix(TransactionCase):
    
    def setUp(self):
        super().setUp()
        # Désactiver les grilles existantes
        self.env['grille.prix'].search([('is_current', '=', True)]).write({'is_current': False})
        
        # Créer grille avec nouvelle structure
        self.grille = self.env['grille.prix'].create({
            'name': 'Grille Test 2024',
            'date_debut': date(2024, 1, 1),
            'date_fin': date(2024, 12, 31),
            'active': True,
            'is_current': True,
        })
        
        # Récupérer les produits
        produit_base = self.env.ref('souscriptions.souscriptions_product_energie_base')
        produit_hp = self.env.ref('souscriptions.souscriptions_product_energie_hp')
        produit_hc = self.env.ref('souscriptions.souscriptions_product_energie_hc')
        produit_abo_standard = self.env.ref('souscriptions.souscriptions_product_abonnement_standard')
        produit_abo_solidaire = self.env.ref('souscriptions.souscriptions_product_abonnement_solidaire')
        
        # Créer les lignes de prix
        self.env['grille.prix.ligne'].create([
            # Lignes abonnement
            {
                'grille_id': self.grille.id,
                'product_id': produit_abo_standard.id,
                'type_produit': 'abonnement',
                'prix_base_3kva': 10.50,  # €/mois pour 3kVA
            },
            {
                'grille_id': self.grille.id,
                'product_id': produit_abo_solidaire.id,
                'type_produit': 'abonnement',
                'prix_base_3kva': 9.45,  # €/mois pour 3kVA solidaire (-10%)
            },
            # Lignes énergie
            {
                'grille_id': self.grille.id,
                'product_id': produit_base.id,
                'type_produit': 'energie',
                'prix_unitaire': 0.2276,
            },
            {
                'grille_id': self.grille.id,
                'product_id': produit_hp.id,
                'type_produit': 'energie',
                'prix_unitaire': 0.2516,
            },
            {
                'grille_id': self.grille.id,
                'product_id': produit_hc.id,
                'type_produit': 'energie',
                'prix_unitaire': 0.2032,
            }
        ])
    
    def test_grille_creation(self):
        """Test création grille de prix"""
        self.assertEqual(self.grille.name, 'Grille Test 2024')
        self.assertTrue(self.grille.active)
        self.assertEqual(len(self.grille.ligne_ids), 5)  # 2 abonnements + 3 énergies
    
    def test_get_grille_active(self):
        """Test récupération grille active"""
        grille_active = self.env['grille.prix'].get_grille_active(date(2024, 6, 15))
        self.assertEqual(grille_active, self.grille)
        
        # Test sans grille active
        self.grille.is_current = False
        with self.assertRaises(UserError):
            self.env['grille.prix'].get_grille_active(date(2024, 6, 15))
    
    def test_get_prix_dict(self):
        """Test récupération dictionnaire des prix"""
        prix_dict = self.grille.get_prix_dict()
        
        produit_base = self.env.ref('souscriptions.souscriptions_product_energie_base')
        produit_hp = self.env.ref('souscriptions.souscriptions_product_energie_hp')
        produit_hc = self.env.ref('souscriptions.souscriptions_product_energie_hc')
        
        # Vérifier que les prix énergie sont présents
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
        # Nouvelle logique : 6kVA = 2 * 3kVA, donc 2 * 10.50€/mois / 30 jours
        prix_attendu = (10.50 * 2) / 30  # €/jour
        self.assertAlmostEqual(prix_journalier, prix_attendu, places=4)
    
    def test_calcul_prix_abonnement_pro(self):
        """Test calcul prix abonnement PRO avec majoration"""
        # 9 kVA PRO (15% majoration)
        prix_journalier = self.grille.get_prix_abonnement(
            puissance_kva=9.0,
            coeff_pro=15.0,
            is_solidaire=False
        )
        # 9kVA = 3 * 3kVA, donc 3 * 10.50€/mois * 1.15 / 30 jours
        prix_base = (10.50 * 3) / 30
        prix_attendu = prix_base * 1.15  # +15%
        self.assertAlmostEqual(prix_journalier, prix_attendu, places=4)
    
    def test_calcul_prix_abonnement_solidaire(self):
        """Test calcul prix abonnement solidaire"""
        # 3 kVA solidaire (utilise prix spécifique solidaire)
        prix_journalier = self.grille.get_prix_abonnement(
            puissance_kva=3.0,
            coeff_pro=0.0,
            is_solidaire=True
        )
        # 3kVA solidaire : 9.45€/mois / 30 jours
        prix_attendu = 9.45 / 30  # €/jour
        self.assertAlmostEqual(prix_journalier, prix_attendu, places=4)
    
    def test_calcul_prix_puissance_non_standard(self):
        """Test calcul avec puissance non-standard (fractionnaire)"""
        # La nouvelle logique permet toutes les puissances en se basant sur 3kVA
        # 7.5 kVA = 2.5 * 3kVA
        prix_journalier = self.grille.get_prix_abonnement(
            puissance_kva=7.5,
            coeff_pro=0.0,
            is_solidaire=False
        )
        prix_attendu = (10.50 * 2.5) / 30  # 2.5 * prix_base_3kva / 30 jours
        self.assertAlmostEqual(prix_journalier, prix_attendu, places=4)
    
    def test_grilles_multiples_chevauchement(self):
        """Test gestion de grilles multiples avec is_current"""
        # Tester la contrainte d'unicité pour is_current
        with self.assertRaises(UserError):
            # Essayer de créer une seconde grille avec is_current=True devrait échouer
            grille2 = self.env['grille.prix'].create({
                'name': 'Grille 2024 Bis',
                'date_debut': date(2024, 6, 1),
                'date_fin': date(2024, 12, 31),
                'active': True,
                'is_current': True,  # Cela devrait échouer à cause de la contrainte
            })
        
        # Vérifier que la grille originale est toujours active
        self.assertTrue(self.grille.is_current)