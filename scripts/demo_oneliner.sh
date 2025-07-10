#!/bin/bash
# Script one-liner pour lancer la démo sans rien cloner

echo "🚀 Lancement de la démo Odoo Souscriptions..."

# Créer un réseau Docker pour la communication
docker network create odoo-demo 2>/dev/null || true

# Lancer PostgreSQL
docker run -d \
  --name odoo-db \
  --network odoo-demo \
  -e POSTGRES_USER=odoo \
  -e POSTGRES_PASSWORD=odoo \
  -e POSTGRES_DB=postgres \
  postgres:15

# Attendre que PostgreSQL soit prêt
echo "⏳ Attente de PostgreSQL..."
sleep 5

# Lancer Odoo avec l'image pré-construite
docker run -d \
  --name odoo-app \
  --network odoo-demo \
  -p 8069:8069 \
  -e HOST=odoo-db \
  -e USER=odoo \
  -e PASSWORD=odoo \
  virgile42d/odoo-souscription-demo:latest

echo "⏳ Attente du démarrage d'Odoo..."
sleep 10

# Créer la base de données et installer le module
echo "🗄️ Création de la base de données..."
docker exec odoo-app odoo \
  --db_host=odoo-db \
  --db_user=odoo \
  --db_password=odoo \
  --database=souscriptions_demo \
  --init=souscriptions \
  --load-language=fr_FR \
  --stop-after-init

# Créer les données de démo
echo "📊 Création des données de démo..."
docker exec odoo-app bash -c 'odoo shell --db_host=odoo-db --db_user=odoo --db_password=odoo -d souscriptions_demo <<EOF
# Créer des partenaires de test
partners = []
for i, (name, is_pro) in enumerate([
    ("Jean Dupont", False),
    ("Marie Martin", False),
    ("Boulangerie Artisanale SARL", True),
    ("Restaurant Le Gourmet", True)
]):
    partner = env["res.partner"].create({
        "name": name,
        "is_company": is_pro,
        "street": f"{i+1} rue de la Demo",
        "city": "Paris",
        "zip": f"7500{i+1}",
        "country_id": env.ref("base.fr").id,
        "phone": f"01 23 45 67 8{i}",
        "email": f"{name.lower().replace(\" \", \".\")}@demo.fr"
    })
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
print("✅ Données de démo créées avec succès!")
EOF'

# Redémarrer Odoo en mode normal
echo "🔄 Redémarrage d'Odoo..."
docker restart odoo-app

echo ""
echo "✅ Démo lancée et configurée !"
echo "📌 Accès : http://localhost:8069"
echo "🗄️ Base de données : souscriptions_demo"
echo "🔑 Login : admin / admin"
echo ""
echo "Pour arrêter : docker stop odoo-app odoo-db && docker rm odoo-app odoo-db"