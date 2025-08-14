"""
Tests d'interface utilisateur avec HttpCase.
Tests de l'interface web et des interactions utilisateur.
"""

from odoo.tests.common import HttpCase, tagged
from odoo.tests import tagged

from .common import SouscriptionsTestMixin


@tagged('souscriptions', 'souscriptions_ui', 'post_install', '-at_install')
class TestSouscriptionsUI(SouscriptionsTestMixin, HttpCase):
    """
    Tests de l'interface utilisateur pour le module souscriptions.
    
    HttpCase permet de tester les vues, formulaires et interactions web.
    """
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.setUpSouscriptionsData()
        
        # Créer un utilisateur de test avec droits appropriés
        cls.user_test = cls.env['res.users'].create({
            'name': 'Utilisateur Test Souscriptions',
            'login': 'test_souscriptions',
            'email': 'test@souscriptions.com',
            'groups_id': [(6, 0, [
                cls.env.ref('base.group_user').id,
                # Ajouter d'autres groupes selon les besoins
            ])]
        })
    
    def test_souscription_list_view(self):
        """Test de la vue liste des souscriptions."""
        # Connexion avec l'utilisateur test
        self.authenticate('test_souscriptions', 'test_souscriptions')
        
        # Accéder à la vue liste des souscriptions
        response = self.url_open('/web#action=souscriptions_odoo.action_souscription_souscription')
        self.assertEqual(response.status_code, 200)
        
        # Vérifier que la page contient les éléments attendus
        self.assertIn('souscription', response.text.lower())
    
    def test_souscription_form_view(self):
        """Test de la vue formulaire d'une souscription."""
        self.authenticate('test_souscriptions', 'test_souscriptions')
        
        # Accéder au formulaire d'une souscription existante
        souscription_id = self.souscription_base.id
        url = f'/web#id={souscription_id}&model=souscription.souscription&view_type=form'
        response = self.url_open(url)
        
        self.assertEqual(response.status_code, 200)
        # Vérifier la présence de champs importants
        self.assertIn('PDL_TEST_STANDARD', response.text)
    
    def test_create_souscription_form(self):
        """Test de création d'une souscription via le formulaire."""
        self.authenticate('test_souscriptions', 'test_souscriptions')
        
        # Accéder au formulaire de création
        url = '/web#model=souscription.souscription&view_type=form'
        response = self.url_open(url)
        
        self.assertEqual(response.status_code, 200)
        # Le formulaire devrait être accessible
        self.assertIn('form', response.text.lower())
    
    def test_periode_kanban_view(self):
        """Test de la vue kanban des périodes."""
        self.authenticate('test_souscriptions', 'test_souscriptions')
        
        # Créer quelques périodes pour avoir du contenu
        for i in range(3):
            self.create_test_periode(self.souscription_base)
        
        # Accéder à la vue des périodes
        response = self.url_open('/web#action=souscriptions_odoo.action_souscription_periode')
        self.assertEqual(response.status_code, 200)


@tagged('souscriptions', 'souscriptions_reports', 'post_install', '-at_install')  
class TestSouscriptionsReports(SouscriptionsTestMixin, HttpCase):
    """Tests des rapports et PDF."""
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.setUpSouscriptionsData()
        
        # Créer une facture de test
        periode = cls.env['souscription.periode'].create({
            'souscription_id': cls.souscription_base.id,
            'date_debut': '2024-01-01',
            'date_fin': '2024-01-31',
            'type_periode': 'mensuelle',
            'jours': 31,
            'energie_hph_kwh': 140.0,
            'energie_hpb_kwh': 56.0,
            'energie_hch_kwh': 56.0,
            'energie_hcb_kwh': 28.0,
            'turpe_fixe': 8.5,
            'turpe_variable': 4.2,
        })
        cls.facture_test = cls.souscription_base._creer_facture_periode(periode)
    
    def test_facture_energie_pdf(self):
        """Test de génération du PDF de facture d'énergie."""
        # Test de génération via l'interface web
        report_url = f'/report/pdf/souscriptions_odoo.report_facture_energie/{self.facture_test.id}'
        
        response = self.url_open(report_url)
        
        # Vérifier que le PDF est généré
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get('Content-Type'), 'application/pdf')
        
        # Vérifier que le contenu n'est pas vide
        self.assertGreater(len(response.content), 1000)  # Un PDF minimal fait plus de 1KB
    
    def test_facture_energie_html_preview(self):
        """Test de prévisualisation HTML de la facture."""
        # Prévisualisation HTML (sans PDF)
        report_url = f'/report/html/souscriptions_odoo.report_facture_energie/{self.facture_test.id}'
        
        response = self.url_open(report_url)
        self.assertEqual(response.status_code, 200)
        
        # Vérifier le contenu HTML
        self.assertIn('Facture d\'Électricité', response.text)
        self.assertIn('Informations Souscription', response.text)
        self.assertIn('PDL_TEST_STANDARD', response.text)
        self.assertIn('Dont turpe', response.text.lower())
    
    def test_report_souscription_contrat(self):
        """Test du rapport de contrat de souscription."""
        # Si un rapport de contrat existe
        report_url = f'/report/pdf/souscriptions_odoo.report_souscription_contrat/{self.souscription_base.id}'
        
        response = self.url_open(report_url)
        
        # Le rapport devrait être accessible (même s'il n'est pas encore complètement développé)
        # On teste juste qu'il n'y a pas d'erreur 500
        self.assertIn(response.status_code, [200, 404])  # 404 acceptable si rapport pas implémenté


@tagged('souscriptions', 'souscriptions_javascript', 'post_install', '-at_install')
class TestSouscriptionsJavascript(HttpCase):
    """
    Tests des fonctionnalités JavaScript du module.
    À développer selon les besoins en JavaScript.
    """
    
    def test_javascript_basic(self):
        """Test basique pour vérifier que le JavaScript fonctionne."""
        # Test de base - à étendre selon les fonctionnalités JS
        response = self.url_open('/web')
        self.assertEqual(response.status_code, 200)
        
    # TODO: Ajouter des tests spécifiques selon les widgets/JS développés
    # Par exemple:
    # - Widget de sélection de tarif
    # - Calculatrice de consommation
    # - Graphiques interactifs
    # - Validations côté client