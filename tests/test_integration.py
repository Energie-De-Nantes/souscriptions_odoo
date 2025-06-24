from odoo.tests.common import TransactionCase, tagged
from odoo.exceptions import UserError
from datetime import date


@tagged('souscriptions', 'post_install', '-at_install')
class TestIntegration(TransactionCase):
    """Tests d'intégration bout-en-bout : souscription -> période -> facture"""
    
    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({
            'name': 'Client Intégration',
            'is_company': False,
        })
        
        self.etat_actif = self.env['souscription.etat'].create({
            'name': 'Actif',
            'sequence': 1,
        })
        
        # Grille de prix complète pour les tests
        self.grille = self.env['grille.prix'].create({
            'name': 'Grille Intégration',
            'date_debut': date(2024, 1, 1),
            'date_fin': date(2024, 12, 31),
            'active': True,
            'prix_abonnement_6kva': 94.2,  # Prix annuel TTC
            'prix_abonnement_9kva': 118.8,
            'coefficient_pro': 1.15,
            'reduction_solidaire': 0.10,
        })
        
        # Prix énergies
        produits = {
            'base': self.env.ref('souscriptions.souscriptions_product_energie_base'),
            'hp': self.env.ref('souscriptions.souscriptions_product_energie_hp'),
            'hc': self.env.ref('souscriptions.souscriptions_product_energie_hc'),
        }
        
        prix_energie = {'base': 0.2276, 'hp': 0.2516, 'hc': 0.2032}
        
        for type_energie, produit in produits.items():
            self.env['grille.prix.ligne'].create({
                'grille_id': self.grille.id,
                'product_id': produit.id,
                'prix_interne': prix_energie[type_energie],
            })
    
    def test_workflow_complet_base(self):
        """Test workflow complet : souscription BASE -> période -> facture"""
        # 1. Créer souscription BASE
        souscription = self.env['souscription.souscription'].create({
            'partner_id': self.partner.id,
            'pdl': 'PDL_INTEG_BASE',
            'puissance_souscrite': '6',
            'type_tarif': 'base',
            'etat_facturation_id': self.etat_actif.id,
            'date_debut': date(2024, 1, 1),
            'coeff_pro': 0.0,  # Particulier
        })
        
        # 2. Créer période de facturation
        periode = self.env['souscription.periode'].create({
            'souscription_id': souscription.id,
            'date_debut': date(2024, 1, 1),
            'date_fin': date(2024, 1, 31),
            'type_periode': 'mensuelle',
            'provision_base_kwh': 280.0,
            'turpe_fixe': 8.50,
            'turpe_variable': 12.30,
        })
        
        # 3. Générer facture
        souscription.creer_factures()
        
        # 4. Vérifications
        self.assertTrue(periode.facture_id)
        facture = periode.facture_id
        
        # Vérifier la facture
        self.assertEqual(facture.partner_id, self.partner)
        self.assertEqual(facture.move_type, 'out_invoice')
        
        # Vérifier les lignes de facture
        lignes = facture.invoice_line_ids
        self.assertGreater(len(lignes), 0)
        
        # Ligne abonnement
        ligne_abo = lignes.filtered(lambda l: 'Abonnement' in l.name)
        self.assertEqual(len(ligne_abo), 1)
        self.assertEqual(ligne_abo.quantity, 31)  # Jours du mois
        
        # Ligne énergie BASE
        ligne_energie = lignes.filtered(lambda l: 'Énergie Base' in l.name)
        self.assertEqual(len(ligne_energie), 1)
        self.assertEqual(ligne_energie.quantity, 280.0)
        
        # Lignes TURPE
        lignes_turpe = lignes.filtered(lambda l: 'TURPE' in l.name)
        self.assertEqual(len(lignes_turpe), 2)
    
    def test_workflow_complet_hphc(self):
        """Test workflow complet : souscription HP/HC -> période -> facture"""
        # 1. Créer souscription HP/HC
        souscription = self.env['souscription.souscription'].create({
            'partner_id': self.partner.id,
            'pdl': 'PDL_INTEG_HPHC',
            'puissance_souscrite': '9',
            'type_tarif': 'hphc',
            'etat_facturation_id': self.etat_actif.id,
            'date_debut': date(2024, 2, 1),
            'coeff_pro': 15.0,  # PRO +15%
        })
        
        # 2. Créer période HP/HC
        periode = self.env['souscription.periode'].create({
            'souscription_id': souscription.id,
            'date_debut': date(2024, 2, 1),
            'date_fin': date(2024, 2, 29),
            'type_periode': 'mensuelle',
            'provision_hp_kwh': 180.0,
            'provision_hc_kwh': 120.0,
        })
        
        # 3. Générer facture
        souscription.creer_factures()
        
        # 4. Vérifications HP/HC
        facture = periode.facture_id
        lignes = facture.invoice_line_ids
        
        # Ligne abonnement avec majoration PRO
        ligne_abo = lignes.filtered(lambda l: 'Abonnement' in l.name and 'PRO' in l.name)
        self.assertEqual(len(ligne_abo), 1)
        
        # Lignes énergie HP et HC
        ligne_hp = lignes.filtered(lambda l: 'Énergie HP' in l.name)
        ligne_hc = lignes.filtered(lambda l: 'Énergie HC' in l.name)
        
        self.assertEqual(len(ligne_hp), 1)
        self.assertEqual(len(ligne_hc), 1)
        self.assertEqual(ligne_hp.quantity, 180.0)
        self.assertEqual(ligne_hc.quantity, 120.0)
    
    def test_workflow_solidaire(self):
        """Test workflow tarif solidaire"""
        souscription = self.env['souscription.souscription'].create({
            'partner_id': self.partner.id,
            'pdl': 'PDL_SOLIDAIRE',
            'puissance_souscrite': '6',
            'type_tarif': 'base',
            'etat_facturation_id': self.etat_actif.id,
            'tarif_solidaire': True,
        })
        
        periode = self.env['souscription.periode'].create({
            'souscription_id': souscription.id,
            'date_debut': date(2024, 3, 1),
            'date_fin': date(2024, 3, 31),
            'type_periode': 'mensuelle',
            'provision_base_kwh': 200.0,
        })
        
        souscription.creer_factures()
        
        # Vérifier produit solidaire utilisé
        facture = periode.facture_id
        ligne_abo = facture.invoice_line_ids.filtered(lambda l: 'Abonnement' in l.name)
        
        # Le prix doit être réduit (solidaire)
        prix_journalier_attendu = (94.2 / 365) * 0.90  # -10%
        self.assertAlmostEqual(ligne_abo.price_unit, prix_journalier_attendu, places=4)
    
    def test_facturation_multiple_souscriptions(self):
        """Test facturation simultanée de plusieurs souscriptions"""
        # Créer 3 souscriptions différentes
        souscriptions = []
        for i in range(3):
            partner = self.env['res.partner'].create({
                'name': f'Client Multi {i+1}',
            })
            
            sous = self.env['souscription.souscription'].create({
                'partner_id': partner.id,
                'pdl': f'PDL_MULTI_{i+1}',
                'puissance_souscrite': '6',
                'type_tarif': 'base',
                'etat_facturation_id': self.etat_actif.id,
            })
            souscriptions.append(sous)
            
            # Période pour chaque souscription
            self.env['souscription.periode'].create({
                'souscription_id': sous.id,
                'date_debut': date(2024, 4, 1),
                'date_fin': date(2024, 4, 30),
                'type_periode': 'mensuelle',
                'provision_base_kwh': 250.0,
            })
        
        # Facturation groupée
        souscriptions_recordset = self.env['souscription.souscription'].browse([s.id for s in souscriptions])
        souscriptions_recordset.creer_factures()
        
        # Vérifier que toutes les factures sont créées
        for sous in souscriptions:
            periode = sous.periode_ids[0]
            self.assertTrue(periode.facture_id)
            self.assertEqual(periode.facture_id.partner_id, sous.partner_id)
    
    def test_erreur_grille_manquante(self):
        """Test gestion erreur : pas de grille de prix active"""
        # Désactiver la grille
        self.grille.active = False
        
        souscription = self.env['souscription.souscription'].create({
            'partner_id': self.partner.id,
            'pdl': 'PDL_ERREUR',
            'puissance_souscrite': '6',
            'type_tarif': 'base',
            'etat_facturation_id': self.etat_actif.id,
        })
        
        periode = self.env['souscription.periode'].create({
            'souscription_id': souscription.id,
            'date_debut': date(2024, 5, 1),
            'date_fin': date(2024, 5, 31),
            'type_periode': 'mensuelle',
            'provision_base_kwh': 100.0,
        })
        
        # Doit lever une erreur
        with self.assertRaises(UserError):
            souscription.creer_factures()