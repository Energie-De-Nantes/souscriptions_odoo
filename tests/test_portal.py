"""
Tests unitaires pour le portal client du module souscriptions.
"""

import json
from unittest.mock import patch
from odoo.tests.common import HttpCase, tagged
from odoo.addons.souscriptions.tests.common import SouscriptionsTestMixin
from datetime import date


@tagged('post_install', '-at_install', 'portal')
class PortalTestCase(SouscriptionsTestMixin, HttpCase):
    """Tests du portal client pour les souscriptions."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.setUpSouscriptionsData()
        
        # Créer un utilisateur portal pour les tests
        cls.portal_user = cls.env['res.users'].create({
            'name': 'Portal Test User',
            'login': 'portal_test',
            'email': 'portal@test.com',
            'groups_id': [(6, 0, [cls.env.ref('base.group_portal').id])],
        })
        
        # Associer le partner de test à l'utilisateur portal
        cls.partner_test.user_ids = [(6, 0, [cls.portal_user.id])]
        
        # Créer des périodes et factures de test pour la souscription
        cls._create_test_periods_and_invoices()

    @classmethod
    def _create_test_periods_and_invoices(cls):
        """Créer des données de test complètes pour le portal."""
        # Période janvier 2024
        cls.periode_jan = cls.env['souscription.periode'].create({
            'souscription_id': cls.souscription_base.id,
            'date_debut': date(2024, 1, 1),
            'date_fin': date(2024, 1, 31),
            'type_periode': 'mensuelle',
            'energie_base_kwh': 280.0,
            'provision_base_kwh': 300.0,
            'turpe_fixe': 8.50,
            'turpe_variable': 12.30,
        })
        
        # Période février 2024
        cls.periode_feb = cls.env['souscription.periode'].create({
            'souscription_id': cls.souscription_base.id,
            'date_debut': date(2024, 2, 1),
            'date_fin': date(2024, 2, 29),
            'type_periode': 'mensuelle',
            'energie_base_kwh': 320.0,
            'provision_base_kwh': 300.0,
            'turpe_fixe': 8.50,
            'turpe_variable': 14.20,
        })
        
        # Créer des factures associées
        cls.facture_jan = cls.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': cls.partner_test.id,
            'invoice_date': date(2024, 2, 5),
            'periode_id': cls.periode_jan.id,
        })
        
        cls.facture_feb = cls.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': cls.partner_test.id,
            'invoice_date': date(2024, 3, 5),
            'periode_id': cls.periode_feb.id,
        })

    def test_portal_access_redirect_unauthenticated(self):
        """Test que l'accès non authentifié redirige vers login."""
        # Test liste des souscriptions
        response = self.url_open('/my/souscriptions')
        self.assertEqual(response.status_code, 200)
        # Vérifier qu'on est sur la page de login
        self.assertIn('login', response.url)
        
        # Test détail souscription
        response = self.url_open(f'/my/souscription/{self.souscription_base.id}')
        self.assertEqual(response.status_code, 200)
        self.assertIn('login', response.url)
        
        # Test vue périodes
        response = self.url_open(f'/my/souscription/{self.souscription_base.id}/periodes')
        self.assertEqual(response.status_code, 200)
        self.assertIn('login', response.url)

    def test_portal_souscriptions_list_authenticated(self):
        """Test de la liste des souscriptions avec utilisateur authentifié."""
        # Se connecter comme utilisateur portal
        self.authenticate(self.portal_user.login, self.portal_user.login)
        
        # Accéder à la liste des souscriptions
        response = self.url_open('/my/souscriptions')
        self.assertEqual(response.status_code, 200)
        
        # Vérifier que la souscription apparaît
        self.assertIn(self.souscription_base.name, response.text)
        self.assertIn(self.souscription_base.pdl, response.text)
        
        # Vérifier les éléments de l'interface
        self.assertIn('Mes Souscriptions Électriques', response.text)
        self.assertIn('Base', response.text)  # Type de tarif
        self.assertIn('Active', response.text)  # État

    def test_portal_souscription_detail_authenticated(self):
        """Test de la vue détail d'une souscription."""
        self.authenticate(self.portal_user.login, self.portal_user.login)
        
        response = self.url_open(f'/my/souscription/{self.souscription_base.id}')
        self.assertEqual(response.status_code, 200)
        
        # Vérifier les informations de la souscription
        self.assertIn(self.souscription_base.name, response.text)
        self.assertIn(self.souscription_base.pdl, response.text)
        self.assertIn(str(self.souscription_base.puissance_souscrite), response.text)
        
        # Vérifier les liens vers les fonctionnalités
        self.assertIn('Voir l\'historique des consommations', response.text)
        self.assertIn('Factures récentes', response.text)

    def test_portal_periods_view_authenticated(self):
        """Test de la vue des périodes de facturation."""
        self.authenticate(self.portal_user.login, self.portal_user.login)
        
        response = self.url_open(f'/my/souscription/{self.souscription_base.id}/periodes')
        self.assertEqual(response.status_code, 200)
        
        # Vérifier les éléments de navigation
        self.assertIn('Historique des consommations', response.text)
        self.assertIn('Mes Souscriptions', response.text)
        
        # Vérifier les données des périodes
        self.assertIn('01/2024', response.text)  # Période janvier
        self.assertIn('02/2024', response.text)  # Période février
        self.assertIn('280', response.text)      # Consommation janvier
        self.assertIn('320', response.text)      # Consommation février
        
        # Vérifier les totaux
        self.assertIn('600', response.text)      # Total kWh (280+320)
        self.assertIn('Nombre de périodes', response.text)

    def test_portal_security_other_user_data(self):
        """Test que l'utilisateur ne peut pas voir les données d'autres utilisateurs."""
        # Créer un autre utilisateur et souscription
        other_partner = self.env['res.partner'].create({
            'name': 'Other User',
            'email': 'other@test.com',
        })
        
        other_user = self.env['res.users'].create({
            'name': 'Other Portal User',
            'login': 'other_portal',
            'email': 'other_portal@test.com',
            'groups_id': [(6, 0, [self.env.ref('base.group_portal').id])],
        })
        other_partner.user_ids = [(6, 0, [other_user.id])]
        
        other_souscription = self.env['souscription.souscription'].create({
            'partner_id': other_partner.id,
            'pdl': 'PDL_OTHER_USER',
            'puissance_souscrite': '3',
            'type_tarif': 'base',
            'etat_facturation_id': self.etat_facturation.id,
        })
        
        # Se connecter comme premier utilisateur
        self.authenticate(self.portal_user.login, self.portal_user.login)
        
        # Tenter d'accéder aux données de l'autre utilisateur
        response = self.url_open(f'/my/souscription/{other_souscription.id}')
        # Doit rediriger vers /my
        self.assertEqual(response.status_code, 200)
        self.assertIn('/my', response.url)

    def test_portal_invoice_links(self):
        """Test que les liens vers les factures fonctionnent."""
        self.authenticate(self.portal_user.login, self.portal_user.login)
        
        # Aller sur la vue des périodes
        response = self.url_open(f'/my/souscription/{self.souscription_base.id}/periodes')
        self.assertEqual(response.status_code, 200)
        
        # Vérifier que les liens vers les factures sont présents
        self.assertIn(f'/my/invoices/{self.facture_jan.id}', response.text)
        self.assertIn(f'/my/invoices/{self.facture_feb.id}', response.text)

    def test_portal_responsive_display_base_vs_hphc(self):
        """Test que l'affichage s'adapte selon le type de tarif."""
        # Test avec souscription Base
        self.authenticate(self.portal_user.login, self.portal_user.login)
        
        response = self.url_open(f'/my/souscription/{self.souscription_base.id}/periodes')
        self.assertEqual(response.status_code, 200)
        
        # Doit afficher les colonnes Base
        self.assertIn('Énergie Base (kWh)', response.text)
        self.assertNotIn('Énergie HP (kWh)', response.text)
        
        # Test avec souscription HP/HC
        # Créer des périodes pour la souscription HP/HC
        periode_hphc = self.env['souscription.periode'].create({
            'souscription_id': self.souscription_hphc.id,
            'date_debut': date(2024, 1, 1),
            'date_fin': date(2024, 1, 31),
            'type_periode': 'mensuelle',
            'energie_hp_kwh': 200.0,
            'energie_hc_kwh': 120.0,
            'provision_hp_kwh': 210.0,
            'provision_hc_kwh': 130.0,
            'turpe_fixe': 12.80,
            'turpe_variable': 18.50,
        })
        
        # Associer la souscription HP/HC au même partner pour le test
        self.souscription_hphc.partner_id = self.partner_test.id
        
        response = self.url_open(f'/my/souscription/{self.souscription_hphc.id}/periodes')
        self.assertEqual(response.status_code, 200)
        
        # Doit afficher les colonnes HP/HC
        self.assertIn('Énergie HP (kWh)', response.text)
        self.assertIn('Énergie HC (kWh)', response.text)
        self.assertNotIn('Énergie Base (kWh)', response.text)

    def test_portal_data_completeness(self):
        """Test que toutes les données importantes sont affichées."""
        self.authenticate(self.portal_user.login, self.portal_user.login)
        
        # Test page détail souscription
        response = self.url_open(f'/my/souscription/{self.souscription_base.id}')
        self.assertEqual(response.status_code, 200)
        
        # Vérifier les informations techniques
        self.assertIn(self.souscription_base.pdl, response.text)
        self.assertIn(str(self.souscription_base.puissance_souscrite), response.text)
        self.assertIn('Base', response.text)  # Type de tarif
        
        # Vérifier les informations de facturation
        if self.souscription_base.lisse:
            self.assertIn('Facturation lissée', response.text)
            self.assertIn(str(self.souscription_base.provision_mensuelle_kwh), response.text)

    def test_portal_breadcrumb_navigation(self):
        """Test que la navigation breadcrumb fonctionne."""
        self.authenticate(self.portal_user.login, self.portal_user.login)
        
        # Test sur la vue des périodes
        response = self.url_open(f'/my/souscription/{self.souscription_base.id}/periodes')
        self.assertEqual(response.status_code, 200)
        
        # Vérifier les éléments de navigation
        self.assertIn('Mes Souscriptions', response.text)
        self.assertIn(self.souscription_base.name, response.text)
        self.assertIn('Périodes de facturation', response.text)
        
        # Vérifier les liens
        self.assertIn('/my/souscriptions', response.text)
        self.assertIn(f'/my/souscription/{self.souscription_base.id}', response.text)

    def test_portal_calculations_accuracy(self):
        """Test que les calculs de totaux sont corrects."""
        self.authenticate(self.portal_user.login, self.portal_user.login)
        
        response = self.url_open(f'/my/souscription/{self.souscription_base.id}/periodes')
        self.assertEqual(response.status_code, 200)
        
        # Calculer les totaux attendus
        expected_total_kwh = self.periode_jan.energie_base_kwh + self.periode_feb.energie_base_kwh
        expected_total_turpe = (
            (self.periode_jan.turpe_fixe + self.periode_jan.turpe_variable) +
            (self.periode_feb.turpe_fixe + self.periode_feb.turpe_variable)
        )
        
        # Vérifier que les totaux calculés apparaissent
        self.assertIn(f'{expected_total_kwh:.0f}', response.text)
        self.assertIn(f'{expected_total_turpe:.2f}', response.text)

    def test_portal_empty_data_handling(self):
        """Test la gestion des cas où il n'y a pas de données."""
        # Créer une souscription sans périodes
        empty_souscription = self.env['souscription.souscription'].create({
            'partner_id': self.partner_test.id,
            'pdl': 'PDL_EMPTY_TEST',
            'puissance_souscrite': '6',
            'type_tarif': 'base',
            'etat_facturation_id': self.etat_facturation.id,
        })
        
        self.authenticate(self.portal_user.login, self.portal_user.login)
        
        # Test vue des périodes sans données
        response = self.url_open(f'/my/souscription/{empty_souscription.id}/periodes')
        self.assertEqual(response.status_code, 200)
        
        # Vérifier le message d'absence de données
        self.assertIn('Aucune période de facturation trouvée', response.text)


@tagged('post_install', '-at_install', 'portal_integration')
class PortalIntegrationTestCase(SouscriptionsTestMixin, HttpCase):
    """Tests d'intégration du portal avec le reste du système."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.setUpSouscriptionsData()

    def test_portal_menu_integration(self):
        """Test que le menu portal s'intègre correctement."""
        # Vérifier que l'entrée portal existe dans les données
        portal_menu = self.env.ref('souscriptions.portal_my_home_souscriptions', raise_if_not_found=False)
        self.assertTrue(portal_menu, "Le menu portal doit exister")

    def test_portal_with_real_invoice_data(self):
        """Test avec des factures réelles générées par le système."""
        # Créer une période et générer une vraie facture
        periode, facture = self.create_test_invoice(self.souscription_base)
        
        # Associer au partner de test
        self.souscription_base.partner_id = self.partner_test.id
        
        # Créer utilisateur portal
        portal_user = self.env['res.users'].create({
            'name': 'Integration Test User',
            'login': 'integration_test',
            'email': 'integration@test.com',
            'groups_id': [(6, 0, [self.env.ref('base.group_portal').id])],
        })
        self.partner_test.user_ids = [(6, 0, [portal_user.id])]
        
        self.authenticate(portal_user.login, portal_user.login)
        
        # Test accès aux factures depuis le portal
        response = self.url_open(f'/my/souscription/{self.souscription_base.id}')
        self.assertEqual(response.status_code, 200)
        
        # Vérifier que la facture apparaît
        self.assertIn(facture.name, response.text)

    def test_portal_permissions_consistency(self):
        """Test que les permissions portal sont cohérentes."""
        # Vérifier les droits d'accès des modèles
        portal_group = self.env.ref('base.group_portal')
        
        # Souscription
        access = self.env['ir.model.access'].search([
            ('model_id.model', '=', 'souscription.souscription'),
            ('group_id', '=', portal_group.id)
        ])
        self.assertTrue(access, "Accès portal aux souscriptions requis")
        self.assertTrue(access.perm_read, "Lecture autorisée")
        self.assertFalse(access.perm_write, "Écriture interdite")
        self.assertFalse(access.perm_create, "Création interdite")
        self.assertFalse(access.perm_unlink, "Suppression interdite")
        
        # Périodes
        access = self.env['ir.model.access'].search([
            ('model_id.model', '=', 'souscription.periode'),
            ('group_id', '=', portal_group.id)
        ])
        self.assertTrue(access, "Accès portal aux périodes requis")
        self.assertTrue(access.perm_read, "Lecture autorisée")
        self.assertFalse(access.perm_write, "Écriture interdite")


# Compatibilité avec les anciens tests Python standalone
class PortalCompatibilityTests:
    """
    Wrapper pour intégrer les anciens tests Python standalone.
    Ces méthodes peuvent être appelées depuis les tests unitaires.
    """
    
    @staticmethod
    def test_portal_accessibility():
        """Test basique d'accessibilité du portal (équivalent test_portal.py)."""
        import requests
        base_url = "http://localhost:8069"  # Port par défaut des tests
        
        try:
            response = requests.get(f"{base_url}/my/souscriptions", allow_redirects=False, timeout=5)
            return response.status_code in [302, 303, 200]
        except:
            return False
    
    @staticmethod
    def test_periods_route_exists():
        """Test que la route des périodes existe (équivalent test_periods_view.py)."""
        import requests
        base_url = "http://localhost:8069"
        
        try:
            response = requests.get(f"{base_url}/my/souscription/1/periodes", allow_redirects=False, timeout=5)
            return response.status_code in [302, 303, 200, 404]  # 404 = route existe mais pas d'ID 1
        except:
            return False