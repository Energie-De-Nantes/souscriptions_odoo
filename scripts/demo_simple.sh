#!/bin/bash
# Script ultra-simple pour lancer la démo
# L'image contient déjà tout le nécessaire pour s'auto-initialiser

echo "🚀 Lancement de la démo Odoo Souscriptions..."

# Créer un réseau Docker
docker network create odoo-demo 2>/dev/null || true

# Lancer PostgreSQL
docker run -d \
  --name odoo-db \
  --network odoo-demo \
  -e POSTGRES_USER=odoo \
  -e POSTGRES_PASSWORD=odoo \
  -e POSTGRES_DB=postgres \
  postgres:15

# Attendre PostgreSQL
echo "⏳ Attente de PostgreSQL..."
sleep 5

# Lancer Odoo avec l'image qui s'auto-initialise
docker run -d \
  --name odoo-app \
  --network odoo-demo \
  -p 8069:8069 \
  -e HOST=odoo-db \
  -e USER=odoo \
  -e PASSWORD=odoo \
  virgile42d/odoo-souscription-demo:latest

echo ""
echo "✅ Démo lancée!"
echo "⏳ L'initialisation automatique peut prendre 1-2 minutes au premier lancement"
echo ""
echo "📌 Accès : http://localhost:8069"
echo "🗄️ Base : souscriptions_demo (créée automatiquement)"
echo "🔑 Login : admin / admin"
echo ""
echo "Pour arrêter : docker stop odoo-app odoo-db && docker rm odoo-app odoo-db"