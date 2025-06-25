#!/usr/bin/env python3
"""
Script pour exécuter tous les tests du portal avec le framework de tests Odoo.
"""

import sys
import os
import subprocess
from pathlib import Path

def run_odoo_tests():
    """Exécute les tests Odoo du module souscriptions."""
    
    print("🧪 Exécution des tests portal avec le framework Odoo")
    print("=" * 60)
    
    # Chemin vers le module
    module_path = Path(__file__).parent
    
    # Commande de test Odoo
    test_cmd = [
        'odoo',
        '--test-enable',
        '--test-tags', 'portal,portal_integration',
        '--stop-after-init',
        '--addons-path', str(module_path.parent),
        '-d', 'test_souscriptions_portal',
        '-i', 'souscriptions',
        '--log-level=test',
    ]
    
    print(f"📋 Commande : {' '.join(test_cmd)}")
    print()
    
    try:
        # Exécuter les tests
        result = subprocess.run(test_cmd, capture_output=True, text=True, timeout=300)
        
        # Afficher les résultats
        print("📊 STDOUT:")
        print(result.stdout)
        
        if result.stderr:
            print("⚠️  STDERR:")
            print(result.stderr)
        
        if result.returncode == 0:
            print("✅ Tous les tests portal sont passés !")
            
            # Compter les tests
            stdout = result.stdout
            if 'ran' in stdout and 'test' in stdout:
                print(f"📈 Résumé trouvé dans la sortie")
            
        else:
            print(f"❌ Tests échoués (code: {result.returncode})")
            
        return result.returncode == 0
        
    except subprocess.TimeoutExpired:
        print("⏰ Timeout - les tests prennent trop de temps")
        return False
    except FileNotFoundError:
        print("❌ Commande 'odoo' non trouvée")
        print("💡 Vérifiez que Odoo est installé et accessible")
        return False
    except Exception as e:
        print(f"❌ Erreur inattendue: {e}")
        return False

def run_specific_portal_tests():
    """Exécute uniquement les tests portal spécifiques."""
    
    print("\n🎯 Tests portal spécifiques")
    print("=" * 30)
    
    # Test d'accessibilité basique
    try:
        from odoo.addons.souscriptions.tests.test_portal import PortalCompatibilityTests
        
        print("📋 Test d'accessibilité portal...")
        if PortalCompatibilityTests.test_portal_accessibility():
            print("✅ Portal accessible")
        else:
            print("❌ Portal non accessible")
            
        print("📋 Test de la route des périodes...")
        if PortalCompatibilityTests.test_periods_route_exists():
            print("✅ Route des périodes existe")
        else:
            print("❌ Route des périodes non trouvée")
            
    except ImportError:
        print("⚠️  Tests de compatibilité non disponibles (Odoo non chargé)")
    except Exception as e:
        print(f"❌ Erreur dans les tests spécifiques: {e}")

def print_test_summary():
    """Affiche un résumé des tests disponibles."""
    
    print("\n📚 Tests portal intégrés")
    print("=" * 30)
    print("🔧 Tests unitaires (unittest + Odoo):")
    print("   • test_portal_access_redirect_unauthenticated")
    print("   • test_portal_souscriptions_list_authenticated")
    print("   • test_portal_souscription_detail_authenticated")
    print("   • test_portal_periods_view_authenticated")
    print("   • test_portal_security_other_user_data")
    print("   • test_portal_invoice_links")
    print("   • test_portal_responsive_display_base_vs_hphc")
    print("   • test_portal_data_completeness")
    print("   • test_portal_breadcrumb_navigation")
    print("   • test_portal_calculations_accuracy")
    print("   • test_portal_empty_data_handling")
    
    print("\n🔗 Tests d'intégration:")
    print("   • test_portal_menu_integration")
    print("   • test_portal_with_real_invoice_data")
    print("   • test_portal_permissions_consistency")
    
    print("\n🎯 Fonctionnalités testées:")
    print("   ✅ Authentification et sécurité")
    print("   ✅ Navigation et interface")
    print("   ✅ Affichage des données")
    print("   ✅ Calculs et totaux")
    print("   ✅ Gestion des cas limites")
    print("   ✅ Intégration avec Odoo")

def main():
    """Point d'entrée principal."""
    
    print("🧪 Tests Portal - Module Souscriptions")
    print("=" * 50)
    
    # Check for command line arguments
    if len(sys.argv) > 1:
        if '--help' in sys.argv or '-h' in sys.argv:
            print_test_summary()
            print("\n📖 Usage:")
            print("  python3 run_portal_tests.py [--auto] [--summary] [--compat]")
            print("  --auto    : Exécuter tous les tests automatiquement")
            print("  --summary : Afficher seulement le résumé")
            print("  --compat  : Tests de compatibilité uniquement")
            return 0
        
        if '--auto' in sys.argv:
            choice = "1"
        elif '--summary' in sys.argv:
            choice = "3"
        elif '--compat' in sys.argv:
            choice = "2"
        else:
            choice = "1"
    else:
        # Afficher le résumé
        print_test_summary()
        
        # Choix utilisateur
        print("\n🎯 Options d'exécution:")
        print("1. Exécuter tous les tests Odoo (recommandé)")
        print("2. Tests de compatibilité uniquement")
        print("3. Afficher seulement le résumé")
        
        try:
            choice = input("\nVotre choix (1-3) [1]: ").strip() or "1"
        except (EOFError, KeyboardInterrupt):
            print("\n\n✅ Mode automatique - Exécution de tous les tests")
            choice = "1"
    
    if choice == "1":
        success = run_odoo_tests()
        run_specific_portal_tests()
        
        if success:
            print("\n🎉 Tous les tests portal intégrés sont fonctionnels !")
            print("📍 Le portal client est prêt pour la production.")
        else:
            print("\n⚠️  Certains tests ont échoué - vérifiez les logs ci-dessus.")
            
    elif choice == "2":
        run_specific_portal_tests()
        
    elif choice == "3":
        print("\n✅ Résumé affiché. Tests disponibles via:")
        print("   python3 run_portal_tests.py")
        print("   ou")
        print("   odoo --test-enable --test-tags portal -i souscriptions")
        
    else:
        print("❌ Choix invalide")
        return 1
        
    return 0

if __name__ == "__main__":
    sys.exit(main())