from odoo.tests.common import TransactionCase, tagged
from odoo.exceptions import UserError
from datetime import date, timedelta


@tagged('souscriptions', 'souscriptions_facturation', 'post_install', '-at_install')
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
        
        self.souscription = self.env['souscription.souscription'].create({
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
        souscription_hphc = self.env['souscription.souscription'].create({
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
        self.env['souscription.souscription'].ajouter_periodes_mensuelles()
        
        # Vérifier qu'une période a été créée
        count_after = len(self.souscription.periode_ids)
        self.assertGreater(count_after, count_before)
    
    def test_api_externe_get_souscriptions_by_pdl(self):
        """Test API pour pont externe - recherche par PDL"""
        result = self.env['souscription.souscription'].get_souscriptions_by_pdl(['PDL_TEST_001'])
        
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
    
    def test_generation_facture_complete(self):
        """Test complet de génération de facture avec TURPE"""
        # Créer une période avec consommation
        periode = self.env['souscription.periode'].create({
            'souscription_id': self.souscription.id,
            'date_debut': date(2024, 4, 1),
            'date_fin': date(2024, 4, 30),
            'type_periode': 'mensuelle',
            'energie_hph_kwh': 150.0,
            'energie_hpb_kwh': 60.0,
            'energie_hch_kwh': 60.0,
            'energie_hcb_kwh': 30.0,
            'turpe_fixe': 8.5,
            'turpe_variable': 4.5,
        })
        
        # Générer la facture
        facture = self.souscription._creer_facture_periode(periode)
        
        # Vérifications
        self.assertTrue(facture.is_facture_energie)
        self.assertEqual(facture.periode_id, periode)
        self.assertEqual(facture.souscription_id, self.souscription)
        self.assertEqual(facture.partner_id, self.partner)
        
        # Vérifier les lignes de facture
        lines = facture.invoice_line_ids
        self.assertTrue(len(lines) > 0)
        
        # Vérifier les sections
        sections = lines.filtered(lambda l: l.display_type == 'line_section')
        section_names = [s.name for s in sections]
        self.assertIn('Abonnement', section_names)
        self.assertIn('Énergie', section_names)
        
        # Vérifier les notes TURPE
        notes = lines.filtered(lambda l: l.display_type == 'line_note')
        note_names = [n.name for n in notes]
        turpe_notes = [n for n in note_names if 'turpe' in n.lower()]
        self.assertTrue(len(turpe_notes) >= 2)
        
        # Vérifier que la période est marquée comme facturée
        self.assertEqual(periode.facture_id, facture)
    
    def test_generation_facture_hp_hc(self):
        """Test génération facture pour souscription HP/HC"""
        # Créer souscription HP/HC
        souscription_hphc = self.env['souscription.souscription'].create({
            'partner_id': self.partner.id,
            'pdl': 'PDL_HPHC_TEST',
            'puissance_souscrite': '9',
            'type_tarif': 'hphc',
            'etat_facturation_id': self.etat_actif.id,
            'date_debut': date(2024, 1, 1),
            'provision_hp_kwh': 200.0,
            'provision_hc_kwh': 120.0,
        })
        
        # Créer période HP/HC
        periode_hphc = self.env['souscription.periode'].create({
            'souscription_id': souscription_hphc.id,
            'date_debut': date(2024, 5, 1),
            'date_fin': date(2024, 5, 31),
            'type_periode': 'mensuelle',
            'energie_hph_kwh': 120.0,
            'energie_hpb_kwh': 80.0,
            'energie_hch_kwh': 72.0,
            'energie_hcb_kwh': 48.0,
            'turpe_fixe': 12.8,
            'turpe_variable': 5.76,
        })
        
        # Générer facture
        facture_hphc = souscription_hphc._creer_facture_periode(periode_hphc)
        
        # Vérifications spécifiques HP/HC
        self.assertTrue(facture_hphc.is_facture_energie)
        self.assertEqual(facture_hphc.souscription_id.type_tarif, 'hphc')
        
        # Vérifier les lignes HP et HC
        product_lines = facture_hphc.invoice_line_ids.filtered(lambda l: not l.display_type)
        line_names = [line.name for line in product_lines]
        
        # Doit contenir des lignes HP et HC
        hp_lines = [name for name in line_names if 'HP' in name]
        hc_lines = [name for name in line_names if 'HC' in name]
        self.assertTrue(len(hp_lines) > 0)
        self.assertTrue(len(hc_lines) > 0)
    
    def test_calcul_montants_turpe(self):
        """Test du calcul des montants TURPE"""
        periode = self.env['souscription.periode'].create({
            'souscription_id': self.souscription.id,
            'date_debut': date(2024, 6, 1),
            'date_fin': date(2024, 6, 30),
            'type_periode': 'mensuelle',
            'energie_hph_kwh': 100.0,
            'energie_hpb_kwh': 50.0,
            'energie_hch_kwh': 40.0,
            'energie_hcb_kwh': 20.0,
            'turpe_fixe': 10.0,
            'turpe_variable': 3.15,  # 210 kWh * 0.015
        })
        
        facture = self.souscription._creer_facture_periode(periode)
        
        # Vérifier que les montants TURPE apparaissent dans les notes
        notes = facture.invoice_line_ids.filtered(lambda l: l.display_type == 'line_note')
        note_texts = [note.name for note in notes]
        
        # Chercher les notes TURPE
        turpe_fixe_found = False
        turpe_variable_found = False
        
        for note in note_texts:
            if 'turpe fixe: 10.00€' in note:
                turpe_fixe_found = True
            elif 'turpe variable: 3.15€' in note:
                turpe_variable_found = True
        
        self.assertTrue(turpe_fixe_found, "Note TURPE fixe non trouvée")
        self.assertTrue(turpe_variable_found, "Note TURPE variable non trouvée")
    
    def test_erreur_periode_deja_facturee(self):
        """Test qu'on ne peut pas refacturer une période déjà facturée"""
        periode = self.env['souscription.periode'].create({
            'souscription_id': self.souscription.id,
            'date_debut': date(2024, 7, 1),
            'date_fin': date(2024, 7, 31),
            'type_periode': 'mensuelle',
            'provision_base_kwh': 250.0,
        })
        
        # Première facturation
        facture1 = self.souscription._creer_facture_periode(periode)
        self.assertTrue(facture1)
        
        # Tentative de refacturation
        with self.assertRaises(UserError):
            self.souscription._creer_facture_periode(periode)
    
    def test_filename_facture_energie(self):
        """Test du nom de fichier personnalisé pour factures d'énergie"""
        periode = self.env['souscription.periode'].create({
            'souscription_id': self.souscription.id,
            'date_debut': date(2024, 8, 1),
            'date_fin': date(2024, 8, 31),
            'type_periode': 'mensuelle',
            'provision_base_kwh': 220.0,
        })
        
        facture = self.souscription._creer_facture_periode(periode)
        filename = facture._get_report_base_filename()
        
        # Vérifier le format du nom de fichier
        self.assertIn('Facture_Energie', filename)
        self.assertIn(self.souscription.name, filename)
    
    def test_champs_computed_facture_energie(self):
        """Test des champs computed de account.move pour l'énergie"""
        # Créer une facture normale (non-énergie)
        facture_normale = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
        })
        self.assertFalse(facture_normale.is_facture_energie)
        
        # Créer une facture d'énergie
        periode = self.env['souscription.periode'].create({
            'souscription_id': self.souscription.id,
            'date_debut': date(2024, 9, 1),
            'date_fin': date(2024, 9, 30),
            'type_periode': 'mensuelle',
            'provision_base_kwh': 200.0,
        })
        
        facture_energie = self.souscription._creer_facture_periode(periode)
        
        # Vérifier les champs computed
        self.assertTrue(facture_energie.is_facture_energie)
        self.assertEqual(facture_energie.souscription_id, self.souscription)
        self.assertEqual(facture_energie.periode_id, periode)