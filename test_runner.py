#!/usr/bin/env python3
"""
Test runner simplifié pour le module souscriptions.
Utilise les standards Python unittest et les commandes Odoo officielles.
"""

import sys
import subprocess
import argparse
from pathlib import Path


class OdooTestRunner:
    """Runner de tests simplifié pour Odoo utilisant les standards Python."""
    
    def __init__(self):
        self.odoo_cmd = "odoo"
        self.addons_path = "/home/virgile/addons_odoo"
        self.default_db = "souscriptions_test"
        
        # Mapping des tags selon les standards Odoo
        self.test_tags = {
            'all': 'souscriptions',
            'basic': 'souscriptions_basic',
            'facturation': 'souscriptions_facturation', 
            'template': 'souscriptions_template',
            'workflow': 'souscriptions_workflow',
            'ui': 'souscriptions_ui',
            'reports': 'souscriptions_reports',
        }
    
    def build_command(self, test_type='all', db_name=None, verbose=False, install=False):
        """Construit la commande Odoo selon les standards officiels."""
        db = db_name or self.default_db
        tag = self.test_tags.get(test_type, 'souscriptions')
        
        cmd = [
            self.odoo_cmd,
            '-d', db,
            '--test-enable',
            '--test-tags', tag,
            '--stop-after-init',
            '--addons-path', self.addons_path
        ]
        
        if install:
            cmd.extend(['-i', 'souscriptions'])
        
        if verbose:
            cmd.extend(['--log-level', 'info'])
            
        return cmd
    
    def run_tests(self, test_type='all', db_name=None, verbose=False, install=False):
        """Lance les tests avec la commande Odoo standard."""
        cmd = self.build_command(test_type, db_name, verbose, install)
        
        print(f"🧪 Lancement des tests {test_type}")
        print(f"📊 Base de données: {db_name or self.default_db}")
        print(f"🏷️  Tag: {self.test_tags.get(test_type, 'souscriptions')}")
        print(f"💻 Commande: {' '.join(cmd)}")
        print("-" * 50)
        
        try:
            result = subprocess.run(cmd, check=False)
            
            if result.returncode == 0:
                print("✅ Tests réussis!")
                return True
            else:
                print("❌ Certains tests ont échoué")
                return False
                
        except FileNotFoundError:
            print(f"❌ Erreur: {self.odoo_cmd} non trouvé dans le PATH")
            print("💡 Vérifiez votre installation Odoo")
            return False
        except KeyboardInterrupt:
            print("\n⚠️ Tests interrompus par l'utilisateur")
            return False
    
    def discover_tests(self):
        """Utilise unittest discovery pour lister les tests disponibles."""
        print("🔍 Découverte des tests avec unittest...")
        
        test_dir = Path(__file__).parent / "tests"
        
        try:
            # Utilise unittest discovery standard
            cmd = [
                sys.executable, '-m', 'unittest', 'discover',
                '-s', str(test_dir),
                '-p', 'test_*.py',
                '-v'
            ]
            
            print(f"Commande: {' '.join(cmd)}")
            subprocess.run(cmd, check=True)
            
        except subprocess.CalledProcessError:
            print("❌ Erreur lors de la découverte des tests")
        except FileNotFoundError:
            print("❌ Tests directory non trouvé")
    
    def list_available_tags(self):
        """Liste les tags de test disponibles."""
        print("🏷️ Tags de test disponibles:")
        for name, tag in self.test_tags.items():
            print(f"  {name:12} -> {tag}")
    
    def quick_test(self, test_type='basic'):
        """Lance des tests rapides pour développement."""
        print(f"⚡ Tests rapides: {test_type}")
        return self.run_tests(test_type, verbose=False, install=False)


def main():
    """Point d'entrée principal avec CLI simple."""
    parser = argparse.ArgumentParser(
        description="Test runner pour le module Odoo souscriptions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples d'utilisation:
  python test_runner.py                    # Tous les tests
  python test_runner.py basic              # Tests basiques
  python test_runner.py template --verbose # Tests template avec logs
  python test_runner.py --install          # Avec installation du module
  python test_runner.py --discover         # Découverte unittest
  python test_runner.py --list-tags        # Liste des tags
        """
    )
    
    parser.add_argument(
        'test_type', 
        nargs='?', 
        default='all',
        choices=['all', 'basic', 'facturation', 'template', 'workflow', 'ui', 'reports'],
        help='Type de test à lancer (défaut: all)'
    )
    
    parser.add_argument(
        '--db', 
        default=None,
        help='Nom de la base de données (défaut: souscriptions_test)'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Mode verbeux avec logs détaillés'
    )
    
    parser.add_argument(
        '--install',
        action='store_true', 
        help='Installer le module avant les tests'
    )
    
    parser.add_argument(
        '--discover',
        action='store_true',
        help='Utiliser unittest discover pour lister les tests'
    )
    
    parser.add_argument(
        '--list-tags',
        action='store_true',
        help='Lister les tags de test disponibles'
    )
    
    parser.add_argument(
        '--quick',
        action='store_true',
        help='Tests rapides (équivalent à basic sans install)'
    )
    
    args = parser.parse_args()
    
    runner = OdooTestRunner()
    
    # Actions spéciales
    if args.list_tags:
        runner.list_available_tags()
        return
        
    if args.discover:
        runner.discover_tests()
        return
        
    if args.quick:
        success = runner.quick_test(args.test_type)
    else:
        success = runner.run_tests(
            test_type=args.test_type,
            db_name=args.db,
            verbose=args.verbose,
            install=args.install
        )
    
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()