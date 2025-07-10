#!/bin/bash
set -e

# Script d'entrée qui initialise automatiquement la démo au premier lancement

# Fonction pour attendre PostgreSQL
wait_for_postgres() {
    echo "Attente de PostgreSQL..."
    until PGPASSWORD=$PASSWORD psql -h "$HOST" -U "$USER" -c '\q' 2>/dev/null; do
        echo -n "."
        sleep 1
    done
    echo " PostgreSQL prêt!"
}

# Attendre que PostgreSQL soit prêt
wait_for_postgres

# Vérifier si la base de données existe déjà
if PGPASSWORD=$PASSWORD psql -h "$HOST" -U "$USER" -lqt | cut -d \| -f 1 | grep -qw souscriptions_demo; then
    echo "✅ Base de données déjà initialisée"
else
    echo "🗄️ Initialisation de la base de données..."
    
    # Créer la base
    PGPASSWORD=$PASSWORD createdb -h "$HOST" -U "$USER" souscriptions_demo
    
    # Initialiser Odoo avec le module
    odoo --db_host="$HOST" --db_user="$USER" --db_password="$PASSWORD" \
         --database=souscriptions_demo --init=souscriptions \
         --load-language=fr_FR --stop-after-init
    
    # Créer les données de démo
    echo "📊 Création des données de démo..."
    odoo shell --db_host="$HOST" --db_user="$USER" --db_password="$PASSWORD" -d souscriptions_demo <<'EOF'
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
        "email": f"{name.lower().replace(' ', '.')}@demo.fr"
    })
    partners.append(partner)

# Créer une grille de prix
grille = env["grille.prix"].create({
    "name": "Grille démo 2025",
    "date_debut": "2025-01-01",
    "active": True
})

# Prix des produits
for xml_id, prix in [
    ("souscriptions_product_energie_base", 0.25),
    ("souscriptions_product_energie_hp", 0.30),
    ("souscriptions_product_energie_hc", 0.20)
]:
    product = env.ref(f"souscriptions.{xml_id}")
    env["grille.prix.ligne"].create({
        "grille_id": grille.id,
        "product_id": product.id,
        "prix_interne": prix
    })

# Créer des souscriptions
souscriptions_data = [
    (partners[0], "6", "base", False, 100, 0, 0),
    (partners[1], "9", "hphc", True, 0, 120, 80),
    (partners[2], "12", "base", True, 300, 0, 0),
    (partners[3], "18", "hphc", False, 0, 250, 150)
]

for i, (partner, puissance, tarif, lisse, base_kwh, hp_kwh, hc_kwh) in enumerate(souscriptions_data):
    env["souscription.souscription"].create({
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

env.cr.commit()
print("✅ Données de démo créées avec succès!")
EOF
    
    echo "✅ Base de données initialisée!"
fi

# Lancer Odoo normalement avec la base de données par défaut
exec odoo --db_host="$HOST" --db_user="$USER" --db_password="$PASSWORD" \
          --database=souscriptions_demo --db-filter=souscriptions_demo "$@"