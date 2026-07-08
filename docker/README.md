# Déploiement Docker - Module Souscriptions

Ce dossier contient les fichiers Docker du module Souscriptions.

> Pour lancer une instance de dev en une commande, voir `scripts/dev.sh` à la
> racine du dépôt (démarre PostgreSQL + Odoo, image construite, hot reload).

## 📁 Structure des fichiers

```
docker/
├── Dockerfile                    # Image personnalisée avec le module
├── docker-entrypoint-init.sh     # Script d'auto-initialisation (DB/LOAD_DEMO)
├── docker-compose.yml            # Stack de développement (db + odoo, un seul service app)
└── README.md                     # Cette documentation
```

## 🔧 Usage pour développeurs

Toujours passer par `scripts/dev.sh` (voir racine du dépôt) : c'est l'unique
point d'entrée, il pilote `docker compose` sans dupliquer aucune config —
tout le paramétrage conteneur vit dans `docker-compose.yml`.

```bash
../scripts/dev.sh                  # mode demo (défaut) : souscriptions_demo + données de démo
../scripts/dev.sh --data=prod      # souscriptions_prodlocal, module installé sans démo
../scripts/dev.sh --reset          # repart d'une base vierge (mode courant uniquement)
```

Le service `odoo` unique tourne sur l'image **construite** (`docker/Dockerfile`,
`electricore-client` inclus), montage rw, hot reload (`--dev=reload,xml,qweb`),
servi sur le port 8069.

### Construction locale (sans dev.sh)
```bash
# Depuis la racine du projet
docker build -f docker/Dockerfile -t souscriptions-local .
```

## 🗄️ Données de démo

L'entrypoint (`docker-entrypoint-init.sh`) crée automatiquement la base `$DB`
(défaut `souscriptions_demo`) et installe le module, avec les données de démo
(`demo/*.xml`) tant que `LOAD_DEMO` n'est pas vide (défaut). `scripts/dev.sh`
pilote ces deux variables selon `--data=demo|prod`.

## 🛠️ Maintenance

### Arrêter la stack
```bash
cd docker/ && docker compose down
```

### Reset complet (repartir d'une base vierge)
Préférer `../scripts/dev.sh --reset` (ne supprime que la base du mode courant ;
les deux bases `souscriptions_demo` / `souscriptions_prodlocal` coexistent dans
le même volume PostgreSQL). `docker compose down -v` reste possible pour tout
réinitialiser (volume PG + filestore).

## 📝 Notes techniques

- **RAM requise** : ~2GB minimum
- **Port utilisé** : 8069
- **Bases de données** : `souscriptions_demo` (défaut) ou `souscriptions_prodlocal`,
  un mode à la fois, choisi par `scripts/dev.sh --data=`
