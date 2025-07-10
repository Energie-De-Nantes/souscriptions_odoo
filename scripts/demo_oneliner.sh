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

echo "✅ Démo lancée !"
echo "📌 Accès : http://localhost:8069"
echo "🔑 Login : admin / admin"
echo ""
echo "Pour arrêter : docker stop odoo-app odoo-db && docker rm odoo-app odoo-db"