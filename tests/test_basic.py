from odoo.tests.common import TransactionCase, tagged


@tagged('souscriptions', 'souscriptions_basic', 'post_install', '-at_install')
class TestBasic(TransactionCase):
    """Test basique pour vérifier que les tests fonctionnent"""
    
    def test_basic_module_import(self):
        """Test que le module souscriptions peut être importé"""
        self.assertTrue(True)
        
    def test_models_exist(self):
        """Test que les modèles principaux existent"""
        # Test modèle souscription
        self.assertIn('souscription.souscription', self.env)
        
        # Test modèle période
        self.assertIn('souscription.periode', self.env)
        
        # Test modèle grille prix
        self.assertIn('grille.prix', self.env)
        
        # Test modèle état
        self.assertIn('souscription.etat', self.env)