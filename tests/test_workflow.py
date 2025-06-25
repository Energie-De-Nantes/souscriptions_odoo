"""
Tests de workflow complets avec SavepointCase.
Tests de scénarios complexes nécessitant des savepoints.
"""

from odoo.tests.common import SavepointCase, tagged
from odoo.exceptions import UserError, ValidationError
from datetime import date, timedelta

from .common import SouscriptionsTestMixin


@tagged('souscriptions', 'souscriptions_workflow', 'post_install', '-at_install')
class TestWorkflow(SouscriptionsTestMixin, SavepointCase):
    """
    Tests de workflow complets avec gestion des savepoints.
    
    SavepointCase est utilisée ici car nous testons des scénarios complexes
    qui peuvent nécessiter des rollbacks partiels ou des tests de performance
    avec commit/rollback.
    """
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.setUpSouscriptionsData()
    
    def test_workflow_creation_souscription_complete(self):
        """Test du workflow complet de création d'une souscription avec périodes."""
        # Phase 1: Création de la souscription
        souscription = self.env['souscription.souscription'].create({
            'partner_id': self.partner_test.id,
            'pdl': 'PDL_WORKFLOW_001',
            'puissance_souscrite': '6',
            'type_tarif': 'base',
            'etat_facturation_id': self.etat_facturation.id,
            'date_debut': date(2024, 1, 1),
            'provision_mensuelle_kwh': 250.0,
            'ref_compteur': 'COMP_WORKFLOW_001',
        })
        
        # Savepoint après création souscription
        self.env.cr.savepoint()
        
        # Phase 2: Création de plusieurs périodes
        periodes = []
        for mois in range(1, 4):  # Jan, Fév, Mars 2024
            periode = self.create_test_periode(
                souscription,
                date_debut=date(2024, mois, 1),
                date_fin=date(2024, mois + 1, 1) - timedelta(days=1) if mois < 3 else date(2024, 3, 31),
                base_kwh=250.0 + (mois * 10)  # Variation saisonnière
            )
            periodes.append(periode)
        
        # Vérifications après création des périodes
        self.assertEqual(len(periodes), 3)
        self.assertEqual(souscription.periode_ids.ids, [p.id for p in periodes])
        
        # Phase 3: Génération des factures
        factures = []
        for periode in periodes:
            facture = souscription._creer_facture_periode(periode)
            factures.append(facture)
            
            # Vérifier que la période est liée à la facture
            self.assertEqual(periode.facture_id, facture)
            self.assert_invoice_structure(facture)
        
        # Vérifications finales
        self.assertEqual(len(factures), 3)
        
        # Toutes les périodes devraient être facturées
        periodes_non_facturees = souscription.periode_ids.filtered(lambda p: not p.facture_id)
        self.assertEqual(len(periodes_non_facturees), 0)
        
        # Montants cohérents
        total_facture = sum(f.amount_total for f in factures)
        self.assertGreater(total_facture, 0)
    
    def test_workflow_migration_tarif(self):
        """Test du changement de tarif d'une souscription existante."""
        # Créer souscription Base
        souscription = self.env['souscription.souscription'].create({
            'partner_id': self.partner_test.id,
            'pdl': 'PDL_MIGRATION_001',
            'puissance_souscrite': '6',
            'type_tarif': 'base',
            'etat_facturation_id': self.etat_facturation.id,
            'date_debut': date(2024, 1, 1),
            'provision_mensuelle_kwh': 280.0,
        })
        
        # Créer période et facture en Base
        periode_base = self.create_test_periode(
            souscription,
            date_debut=date(2024, 1, 1),
            date_fin=date(2024, 1, 31)
        )
        facture_base = souscription._creer_facture_periode(periode_base)
        
        # Savepoint avant migration
        self.env.cr.savepoint()
        
        # Migration vers HP/HC
        souscription.write({
            'type_tarif': 'hphc',
            'provision_hp_kwh': 180.0,
            'provision_hc_kwh': 100.0,
            'provision_mensuelle_kwh': 0.0,  # Reset
        })
        
        # Créer période HP/HC après migration
        periode_hphc = self.create_test_periode(
            souscription,
            date_debut=date(2024, 2, 1),
            date_fin=date(2024, 2, 29),
            hp_kwh=180.0,
            hc_kwh=100.0
        )
        facture_hphc = souscription._creer_facture_periode(periode_hphc)
        
        # Vérifications
        self.assertEqual(souscription.type_tarif, 'hphc')
        
        # Facture Base toujours valide
        self.assertTrue(facture_base.is_facture_energie)
        base_lines = facture_base.invoice_line_ids.filtered(lambda l: not l.display_type)
        base_energy_lines = [l for l in base_lines if 'Base' in l.name]
        self.assertTrue(len(base_energy_lines) > 0)
        
        # Facture HP/HC correcte
        self.assertTrue(facture_hphc.is_facture_energie)
        hphc_lines = facture_hphc.invoice_line_ids.filtered(lambda l: not l.display_type)
        hp_lines = [l for l in hphc_lines if 'HP' in l.name]
        hc_lines = [l for l in hphc_lines if 'HC' in l.name]
        self.assertTrue(len(hp_lines) > 0)
        self.assertTrue(len(hc_lines) > 0)
    
    def test_workflow_regularisation_lissage(self):
        """Test du workflow de régularisation pour contrat lissé."""
        # Créer souscription lissée
        souscription = self.env['souscription.souscription'].create({
            'partner_id': self.partner_test.id,
            'pdl': 'PDL_LISSAGE_001',
            'puissance_souscrite': '6',
            'type_tarif': 'base',
            'etat_facturation_id': self.etat_facturation.id,
            'date_debut': date(2024, 1, 1),
            'lisse': True,
            'provision_mensuelle_kwh': 300.0,
        })
        
        # Créer plusieurs périodes avec variations
        consommations = [280, 320, 290, 350, 270, 310]  # Variation autour de 300
        periodes = []
        
        for i, conso in enumerate(consommations):
            mois = i + 1
            periode = self.create_test_periode(
                souscription,
                date_debut=date(2024, mois, 1),
                date_fin=date(2024, mois + 1, 1) - timedelta(days=1) if mois < 6 else date(2024, 6, 30),
                base_kwh=conso
            )
            periodes.append(periode)
        
        # Facturer toutes les périodes
        factures = []
        for periode in periodes:
            facture = souscription._creer_facture_periode(periode)
            factures.append(facture)
        
        # Savepoint avant régularisation
        self.env.cr.savepoint()
        
        # Simulation de régularisation (logique à implémenter)
        total_provision = souscription.provision_mensuelle_kwh * 6  # 6 mois
        total_reel = sum(consommations)
        difference = total_reel - total_provision
        
        # Vérifications
        self.assertEqual(len(factures), 6)
        self.assertNotEqual(difference, 0)  # Il devrait y avoir une différence
        
        # Pour un contrat lissé, les factures devraient être cohérentes
        # même si la consommation varie
        for facture in factures:
            self.assertTrue(facture.is_facture_energie)
            self.assertGreater(facture.amount_total, 0)
    
    def test_workflow_erreurs_et_rollback(self):
        """Test de gestion d'erreurs avec rollback."""
        souscription = self.env['souscription.souscription'].create({
            'partner_id': self.partner_test.id,
            'pdl': 'PDL_ERROR_001',
            'puissance_souscrite': '6',
            'type_tarif': 'base',
            'etat_facturation_id': self.etat_facturation.id,
            'date_debut': date(2024, 1, 1),
        })
        
        periode = self.create_test_periode(souscription)
        facture = souscription._creer_facture_periode(periode)
        
        # Savepoint avant tentative d'erreur
        sp = self.env.cr.savepoint()
        
        try:
            # Tentative de refacturation (devrait échouer)
            souscription._creer_facture_periode(periode)
            self.fail("Devrait lever une UserError")
        except UserError:
            # Rollback vers le savepoint
            sp.rollback()
        
        # Vérifier que l'état est cohérent après rollback
        self.assertEqual(periode.facture_id, facture)
        self.assertTrue(facture.exists())
    
    def test_workflow_performance_batch(self):
        """Test de performance pour facturation en batch."""
        # Créer plusieurs souscriptions
        souscriptions = []
        for i in range(5):
            souscription = self.env['souscription.souscription'].create({
                'partner_id': self.partner_test.id,
                'pdl': f'PDL_BATCH_{i:03d}',
                'puissance_souscrite': '6',
                'type_tarif': 'base',
                'etat_facturation_id': self.etat_facturation.id,
                'date_debut': date(2024, 1, 1),
                'provision_mensuelle_kwh': 280.0,
            })
            souscriptions.append(souscription)
        
        # Créer périodes pour toutes
        periodes = []
        for souscription in souscriptions:
            periode = self.create_test_periode(souscription)
            periodes.append(periode)
        
        # Facturation en batch avec gestion des erreurs
        factures_creees = []
        erreurs = []
        
        for i, (souscription, periode) in enumerate(zip(souscriptions, periodes)):
            try:
                # Savepoint pour chaque facturation
                sp = self.env.cr.savepoint()
                facture = souscription._creer_facture_periode(periode)
                factures_creees.append(facture)
                sp.release()
            except Exception as e:
                sp.rollback()
                erreurs.append((i, str(e)))
        
        # Vérifications
        self.assertEqual(len(factures_creees), 5)
        self.assertEqual(len(erreurs), 0)
        
        # Toutes les factures sont valides
        for facture in factures_creees:
            self.assertTrue(facture.is_facture_energie)
            self.assertGreater(facture.amount_total, 0)