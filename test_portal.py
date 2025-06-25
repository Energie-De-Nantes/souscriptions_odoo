#!/usr/bin/env python3
"""
Script de test pour vérifier que le portal fonctionne correctement
"""
import requests
import sys

def test_portal_access():
    base_url = "http://localhost:8071"
    
    # Test 1: Accès au portal sans authentification (doit rediriger)
    print("🔍 Test 1: Accès sans authentification")
    response = requests.get(f"{base_url}/my/souscriptions", allow_redirects=False)
    if response.status_code in [303, 302]:
        print("✅ Redirection correcte vers la page de login")
    else:
        print(f"❌ Code de réponse inattendu: {response.status_code}")
        return False
    
    # Test 2: Vérifier que l'interface web principale fonctionne
    print("\n🔍 Test 2: Interface web principale")
    response = requests.get(f"{base_url}/web", allow_redirects=False)
    if response.status_code in [200, 303, 302]:
        print("✅ Interface web accessible")
    else:
        print(f"❌ Interface web non accessible: {response.status_code}")
        return False
    
    # Test 3: Vérifier que la page de login existe
    print("\n🔍 Test 3: Page de login")
    response = requests.get(f"{base_url}/web/login")
    if response.status_code == 200:
        print("✅ Page de login accessible")
    else:
        print(f"❌ Page de login non accessible: {response.status_code}")
        return False
    
    print("\n🎉 Tous les tests de base passent ! Le portal standard Odoo fonctionne.")
    print("\nPour tester complètement:")
    print(f"1. Connectez-vous à {base_url}/web avec admin/admin")  
    print(f"2. Accédez au portal via {base_url}/my/souscriptions")
    print("3. Vérifiez que les souscriptions s'affichent correctement")
    
    return True

if __name__ == "__main__":
    if test_portal_access():
        sys.exit(0)
    else:
        sys.exit(1)