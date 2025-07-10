#!/bin/bash
# Script pour construire et pousser l'image sur Docker Hub
# À exécuter depuis votre machine de développement

set -e

echo "🔨 Construction de l'image Docker pour la démo..."

# S'assurer qu'on est dans le bon répertoire
if [ ! -f "docker/docker-compose.yml" ]; then
    echo "❌ Erreur: Ce script doit être exécuté depuis le répertoire racine du projet"
    exit 1
fi

# Tag de l'image (utiliser la date pour versionner)
TAG="virgile42d/odoo-souscription-demo:$(date +%Y%m%d)"
LATEST="virgile42d/odoo-souscription-demo:latest"

# Construire l'image
echo "📦 Construction de l'image $TAG..."
docker build -f docker/Dockerfile -t $TAG -t $LATEST .

# Se connecter à Docker Hub (demande identifiants si pas déjà connecté)
echo "🔐 Connexion à Docker Hub..."
docker login

# Pousser l'image
echo "📤 Push de l'image vers Docker Hub..."
docker push $TAG
docker push $LATEST

echo ""
echo "✅ Image poussée avec succès!"
echo ""
echo "📋 Pour déployer sur la machine de démo:"
echo "   1. docker pull $LATEST"
echo "   2. docker-compose -f docker-compose.demo.yml up -d"
echo ""
echo "Ou directement:"
echo "   curl -O https://raw.githubusercontent.com/Energie-De-Nantes/souscriptions_odoo/refactor/minimal-version/docker/docker-compose.demo.yml"
echo "   docker-compose -f docker-compose.demo.yml up -d"