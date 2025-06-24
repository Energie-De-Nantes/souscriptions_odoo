#!/bin/bash

echo "🔍 Test du modèle souscription.etat..."

odoo shell -d souscriptions_demo --addons-path=/home/virgile/addons_odoo << 'EOF'

print("=== Test du modèle souscription.etat ===")

# Test 1: Vérifier que le modèle existe
SouscriptionEtat = env['souscription.etat']
print(f"✅ Modèle 'souscription.etat' trouvé")

# Test 2: Compter les enregistrements
count = SouscriptionEtat.search_count([])
print(f"✅ Nombre d'états : {count}")

# Test 3: Lister les états
etats = SouscriptionEtat.search([])
print("\nÉtats disponibles :")
for etat in etats:
    print(f"  - {etat.name} (ID: {etat.id}, séquence: {etat.sequence})")

# Test 4: Vérifier que les souscriptions utilisent bien ces états
souscriptions = env['souscription.souscription'].search([])
print(f"\n✅ {len(souscriptions)} souscriptions trouvées")
for sous in souscriptions:
    print(f"  - {sous.name} : état = {sous.etat_facturation_id.name if sous.etat_facturation_id else 'AUCUN'}")

exit()
EOF

echo "✅ Test terminé !"