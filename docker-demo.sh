#!/bin/bash

# Script de démo Docker pour le module Souscriptions
set -e

echo "🐳 Démarrage de la démo Odoo Souscriptions avec Docker..."
echo ""

# Fonction pour attendre qu'Odoo soit prêt
wait_for_odoo() {
    echo "⏳ Attente du démarrage d'Odoo..."
    until curl -s http://localhost:8069/web/database/selector > /dev/null 2>&1; do
        echo -n "."
        sleep 2
    done
    echo ""
    echo "✅ Odoo est prêt!"
}

# Arrêter et nettoyer les conteneurs existants
echo "🧹 Nettoyage des conteneurs existants..."
docker-compose down -v 2>/dev/null || true

# Construire l'image
echo "🔨 Construction de l'image Docker..."
docker-compose build

# Démarrer les services
echo "🚀 Démarrage des services..."
docker-compose up -d

# Attendre qu'Odoo soit prêt
wait_for_odoo

# Créer la base de données de démo
echo "🗄️  Création de la base de données de démo..."
docker-compose exec -T odoo odoo \
    --db_host=db \
    --db_user=odoo \
    --db_password=odoo \
    --init=souscriptions \
    --database=souscriptions_demo \
    --load-language=fr_FR \
    --stop-after-init

# Créer les données de démo via shell Odoo
echo "📊 Création des données de démo..."
docker-compose exec -T odoo bash -c '
odoo shell --db_host=db --db_user=odoo --db_password=odoo -d souscriptions_demo <<EOF
# Créer des partenaires de test
partners = []
for i, (name, is_pro, siret) in enumerate([
    ("Jean Dupont", False, None),
    ("Marie Martin", False, None),
    ("Boulangerie Artisanale SARL", True, "12345678901234"),
    ("Restaurant Le Gourmet", True, "98765432109876")
]):
    partner_vals = {
        "name": name,
        "is_company": is_pro,
        "street": f"{i+1} rue de la Demo",
        "city": "Paris",
        "zip": f"7500{i+1}",
        "country_id": env.ref("base.fr").id,
        "phone": f"01 23 45 67 8{i}",
        "email": f"{name.lower().replace(' ', '.')}@demo.fr"
    }
    # Ajouter le SIRET si l10n_fr est installé et si c'est une entreprise
    if is_pro and siret and hasattr(env["res.partner"], "siret"):
        partner_vals["siret"] = siret
    
    partner = env["res.partner"].create(partner_vals)
    partners.append(partner)
    print(f"✅ Partenaire créé: {partner.name}")

# Créer une grille de prix
grille = env["grille.prix"].create({
    "name": "Grille démo 2025",
    "date_debut": "2025-01-01",
    "active": True
})

# Ajouter les prix des produits
products = {
    "souscriptions_product_energie_base": 0.25,
    "souscriptions_product_energie_hp": 0.30,
    "souscriptions_product_energie_hc": 0.20
}

for xml_id, prix in products.items():
    product = env.ref(f"souscriptions.{xml_id}")
    env["grille.prix.ligne"].create({
        "grille_id": grille.id,
        "product_id": product.id,
        "prix_interne": prix
    })

print("✅ Grille de prix créée")

# Créer des souscriptions
souscriptions_data = [
    (partners[0], "6", "base", False, 100, 0, 0),
    (partners[1], "9", "hphc", True, 0, 120, 80),
    (partners[2], "12", "base", True, 300, 0, 0),
    (partners[3], "18", "hphc", False, 0, 250, 150)
]

for i, (partner, puissance, tarif, lisse, base_kwh, hp_kwh, hc_kwh) in enumerate(souscriptions_data):
    sous = env["souscription.souscription"].create({
        "partner_id": partner.id,
        "date_debut": "2025-01-01",
        "puissance_souscrite": puissance,
        "type_tarif": tarif,
        "lisse": lisse,
        "provision_mensuelle_kwh": base_kwh,
        "provision_hp_kwh": hp_kwh,
        "provision_hc_kwh": hc_kwh,
        "pdl": f"0000000000{i+1}",
        "mode_paiement": "prelevement" if i % 2 == 0 else "virement",
        "coeff_pro": 10.0 if partner.is_company else 0.0,
        "ref_compteur": f"COMP{i+1:04d}",
        "numero_depannage": "09 726 750 01"
    })
    print(f"✅ Souscription créée: {sous.name} pour {partner.name}")

env.cr.commit()
print("\n✅ Données de démo créées avec succès!")
EOF
'

echo ""
echo "🎉 Démo prête!"
echo ""
echo "📌 Informations de connexion:"
echo "   URL: http://localhost:8069"
echo "   Base de données: souscriptions_demo"
echo "   Login: admin"
echo "   Mot de passe: admin"
echo ""
echo "📊 Données de démo disponibles:"
echo "   - 4 clients (2 particuliers, 2 professionnels)"
echo "   - 4 souscriptions avec différents profils"
echo "   - 1 grille de prix active"
echo ""
echo "🛑 Pour arrêter: docker-compose down"
echo "🧹 Pour nettoyer: docker-compose down -v"
echo "🔄 Pour le mode dev: docker-compose --profile dev up odoo-dev"