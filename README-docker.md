# Guide Docker pour Odoo Souscriptions

Ce guide explique comment utiliser Docker pour faire tourner le module Souscriptions.

## Prérequis

- Docker et Docker Compose installés
- Port 8069 disponible (8070 pour le mode dev)

## Démarrage rapide

### 1. Lancer la démo avec données de test

```bash
./docker-demo.sh
```

Ce script va :
- Construire l'image Docker avec toutes les dépendances
- Démarrer PostgreSQL et Odoo
- Créer une base de données `souscriptions_demo`
- Installer le module souscriptions
- Créer des données de démonstration

### 2. Accéder à Odoo

- URL: http://localhost:8069
- Base de données: `souscriptions_demo`
- Login: `admin`
- Mot de passe: `admin`

## Commandes utiles

### Mode production (lecture seule du code)
```bash
docker-compose up
```

### Mode développement (avec auto-reload)
```bash
docker-compose --profile dev up odoo-dev
```
Accessible sur http://localhost:8070

### Arrêter les conteneurs
```bash
docker-compose down
```

### Nettoyer complètement (supprime les données)
```bash
docker-compose down -v
```

### Accéder au shell Odoo
```bash
docker-compose exec odoo odoo shell -d souscriptions_demo
```

### Voir les logs
```bash
docker-compose logs -f odoo
```

## Structure Docker

- **Dockerfile** : Image personnalisée basée sur odoo:18.0 avec pandas, fastparquet et watchdog
- **docker-compose.yml** : Orchestration avec PostgreSQL et deux profils (prod/dev)
- **docker-demo.sh** : Script automatisé pour la démo

## Données de démo

Le script crée automatiquement :
- 4 clients (2 particuliers, 2 professionnels)
- 4 souscriptions avec différentes configurations
- 1 grille de prix active pour 2025

## Personnalisation

### Modifier la configuration Odoo
Éditer `config/odoo.conf`

### Ajouter des dépendances Python
Modifier le `Dockerfile` et reconstruire :
```bash
docker-compose build
```

### Changer les ports
Modifier les ports dans `docker-compose.yml`

## Dépannage

### "Address already in use"
Un autre service utilise le port 8069. Changez le port dans docker-compose.yml :
```yaml
ports:
  - "8080:8069"  # Utilise le port 8080 à la place
```

### Problèmes de permissions
Les volumes Docker peuvent avoir des problèmes de permissions. Assurez-vous que l'utilisateur odoo (UID 101) a accès aux fichiers.

### Base de données corrompue
Nettoyer et recommencer :
```bash
docker-compose down -v
./docker-demo.sh
```