#!/bin/bash
# Script de mise à jour rapide pour la démo Odoo
# Conserve la base de données et met à jour uniquement le code

set -e

echo "🔄 Mise à jour rapide du module Souscriptions..."
echo ""

# Vérifier que nous sommes dans le bon répertoire
if [ ! -f "docker-compose.yml" ]; then
    echo "❌ Erreur: Ce script doit être exécuté depuis le répertoire racine du projet"
    exit 1
fi

# Pull les dernières modifications
echo "📥 Récupération des dernières modifications..."
git pull

# Rebuild l'image Docker avec le nouveau code
echo "🔨 Reconstruction de l'image Docker..."
docker-compose build odoo

# Redémarrer uniquement le conteneur Odoo
echo "🔄 Redémarrage du conteneur Odoo..."
docker-compose restart odoo

# Mettre à jour le module dans Odoo
echo "📦 Mise à jour du module dans Odoo..."
docker-compose exec -T odoo odoo \
    --db_host=db \
    --db_user=odoo \
    --db_password=odoo \
    --database=souscriptions_demo \
    --update=souscriptions \
    --stop-after-init

# Redémarrer Odoo en mode normal
echo "🚀 Redémarrage d'Odoo..."
docker-compose restart odoo

echo ""
echo "✅ Mise à jour terminée!"
echo "📌 Accès: http://localhost:8069"
echo "🔑 Login: admin / admin"