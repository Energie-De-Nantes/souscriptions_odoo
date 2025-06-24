#!/bin/bash

# Script de test des factures - génère et affiche une facture de test
DB_NAME="souscriptions_demo"

echo "🧾 Test de génération de factures..."

odoo shell -d $DB_NAME --addons-path=/home/virgile/addons_odoo << 'EOF'

print("=== Test de génération de factures ===")

# Récupérer une souscription avec des périodes
sous = env["souscription.souscription"].search([], limit=1)
if not sous:
    print("❌ Aucune souscription trouvée")
    exit()

print(f"Souscription trouvée: {sous.name} - {sous.partner_id.name}")

# Récupérer les périodes sans facture
periodes_sans_facture = sous.periode_ids.filtered(lambda p: not p.facture_id)
print(f"Périodes sans facture: {len(periodes_sans_facture)}")

if periodes_sans_facture:
    # Générer les factures
    try:
        sous.creer_factures()
        print("✅ Factures générées avec succès")
        
        # Afficher le détail de la première facture
        if sous.facture_ids:
            facture = sous.facture_ids[0]
            print(f"\n=== Détail facture {facture.name} ===")
            for line in facture.invoice_line_ids:
                if line.display_type == 'line_section':
                    print(f"\n📋 SECTION: {line.name}")
                elif line.display_type == 'line_note':
                    print(f"   💬 Note: {line.name}")
                else:
                    print(f"   • {line.name}: {line.quantity} x {line.price_unit}€ = {line.price_subtotal}€")
                    
            print(f"\n💰 Total: {facture.amount_total}€")
        
    except Exception as e:
        print(f"❌ Erreur: {e}")
else:
    print("Toutes les périodes ont déjà une facture")
    if sous.facture_ids:
        facture = sous.facture_ids[0]
        print(f"\n=== Détail facture existante {facture.name} ===")
        for line in facture.invoice_line_ids:
            if line.display_type == 'line_section':
                print(f"\n📋 SECTION: {line.name}")
            elif line.display_type == 'line_note':
                print(f"   💬 Note: {line.name}")
            else:
                print(f"   • {line.name}: {line.quantity} x {line.price_unit}€ = {line.price_subtotal}€")

env.cr.commit()

EOF