# Déploiement Docker - Module Souscriptions

Ce dossier contient tous les fichiers nécessaires pour le déploiement Docker du module Souscriptions.

## 🚀 Déploiement en une commande

**Sur la machine de démo :**
```bash
curl -sSL https://raw.githubusercontent.com/Energie-De-Nantes/souscriptions_odoo/refactor/minimal-version/docker/scripts/demo_simple.sh | bash
```

Cette commande va :
- Télécharger et lancer PostgreSQL
- Télécharger l'image Odoo pré-configurée depuis Docker Hub
- Créer automatiquement la base de données et les données de démo
- Démarrer Odoo sur http://localhost:8069

**Connexion :** admin / admin

## 📁 Structure des fichiers

```
docker/
├── Dockerfile                    # Image personnalisée avec le module
├── docker-entrypoint-init.sh     # Script d'auto-initialisation
├── docker-compose.yml            # Version développement
├── docker-compose.demo.yml       # Version pour Docker Hub
├── docker-compose.prod.yml       # Version optimisée
├── config/
│   ├── odoo.conf                 # Configuration standard
│   └── odoo-prod.conf           # Configuration optimisée
├── scripts/
│   ├── build_and_push.sh        # Construction et publication
│   └── demo_simple.sh           # Démo one-liner
└── README.md                     # Cette documentation
```

## 🔧 Usage pour développeurs

### Construction locale
```bash
# Depuis la racine du projet
docker build -f docker/Dockerfile -t souscriptions-local .
```

### Développement avec docker-compose
```bash
cd docker/
docker-compose up -d                    # Version production
docker-compose --profile dev up odoo-dev # Version développement
```

### Publication sur Docker Hub
```bash
# Depuis la racine du projet
./docker/scripts/build_and_push.sh
```

## 🗄️ Données de démo

L'image crée automatiquement :
- 4 clients (2 particuliers, 2 professionnels)
- 4 souscriptions avec différents profils (Base, HP/HC)
- 1 grille de prix active pour 2025
- États de facturation pré-configurés

## 🛠️ Maintenance

### Arrêter la démo
```bash
docker stop odoo-app odoo-db && docker rm odoo-app odoo-db
```

### Mise à jour
```bash
# La même commande que pour l'installation
curl -sSL [...]/demo_simple.sh | bash
```

### Reset complet
```bash
docker stop odoo-app odoo-db && docker rm odoo-app odoo-db
docker volume prune -f
# Puis relancer la démo
```

## 📝 Notes techniques

- **Taille de l'image** : ~1.5GB (incluant Odoo + PostgreSQL + dépendances Python)
- **RAM requise** : ~2GB minimum
- **Ports utilisés** : 8069 (Odoo)
- **Base de données** : `souscriptions_demo` créée automatiquement