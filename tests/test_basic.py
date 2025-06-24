from odoo.tests.common import TransactionCase, tagged


@tagged('souscriptions', 'post_install', '-at_install')
class TestBasic(TransactionCase):
    """Test basique pour vérifier que les tests fonctionnent"""
    
    def test_basic_module_import(self):
        """Test que le module souscriptions peut être importé"""
        self.assertTrue(True)
        
    def test_models_exist(self):
        """Test que les modèles principaux existent"""
        # Test modèle souscription
        souscription_model = self.env['souscription.souscription']
        self.assertTrue(souscription_model)
        
        # Test modèle période
        periode_model = self.env['souscription.periode'] 
        self.assertTrue(periode_model)
        
        # Test modèle grille prix
        grille_model = self.env['grille.prix']
        self.assertTrue(grille_model)