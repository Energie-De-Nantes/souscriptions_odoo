# Déploiement Docker - Module Souscriptions

Ce dossier contient les fichiers Docker du module Souscriptions.

> Pour lancer une instance de dev en une commande, voir `scripts/run-app.sh` à
> la racine du dépôt (démarre PostgreSQL + Odoo avec les données de démo).

## 📁 Structure des fichiers

```
docker/
├── Dockerfile                    # Image personnalisée avec le module
├── docker-entrypoint-init.sh     # Script d'auto-initialisation
├── docker-compose.yml            # Stack de développement (db + odoo)
├── config/
│   ├── odoo.conf                 # Configuration standard
│   └── odoo-prod.conf            # Configuration optimisée
└── README.md                     # Cette documentation
```

## 🔧 Usage pour développeurs

### Construction locale
```bash
# Depuis la racine du projet
docker build -f docker/Dockerfile -t souscriptions-local .
```

### Développement avec docker compose
```bash
cd docker/
docker compose up -d                      # service odoo (lecture seule, port 8069)
docker compose --profile dev up odoo-dev  # service odoo-dev (hot reload, port 8070)
```

## 🗄️ Données de démo

L'entrypoint (`docker-entrypoint-init.sh`) crée automatiquement la base
`souscriptions_demo` et installe le module avec les données de démo
(`demo/*.xml`) au premier lancement.

## 🛠️ Maintenance

### Arrêter la stack
```bash
cd docker/ && docker compose down
```

### Reset complet (repartir d'une base vierge)
```bash
cd docker/ && docker compose down -v
```

## 📝 Notes techniques

- **RAM requise** : ~2GB minimum
- **Ports utilisés** : 8069 (odoo), 8070 (odoo-dev)
- **Base de données** : `souscriptions_demo` créée automatiquement
