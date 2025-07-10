# Guide de déploiement pour démo Odoo Souscriptions

Ce guide explique comment déployer et maintenir le module Souscriptions pour les démonstrations.

## 🚀 Déploiement initial (sur la machine de démo)

### Prérequis
- Ubuntu 20.04+ ou similaire
- Docker et Docker Compose installés
- Connexion internet
- ~4GB de RAM minimum

### Installation en 3 étapes

1. **Cloner le repository**
```bash
git clone https://github.com/Energie-De-Nantes/souscriptions_odoo.git
cd souscriptions_odoo
git checkout refactor/minimal-version
```

2. **Lancer la démo**
```bash
./docker-demo.sh
```

Ce script va automatiquement :
- Construire l'image Docker avec Odoo 18 et toutes les dépendances
- Créer une base PostgreSQL
- Installer le module souscriptions
- Créer des données de démonstration (clients, souscriptions, grilles de prix)

3. **Accéder à Odoo**
- URL : http://localhost:8069
- Base de données : souscriptions_demo
- Login : admin
- Mot de passe : admin

## 🔄 Mises à jour du module

### Mise à jour rapide (conserve les données)

Après avoir développé des nouvelles fonctionnalités depuis chez vous :

1. **Sur votre machine de développement**
```bash
git add .
git commit -m "Description des changements"
git push origin refactor/minimal-version
```

2. **Sur la machine de démo**
```bash
cd souscriptions_odoo
./scripts/quick_update.sh
```

Ce script va :
- Récupérer les dernières modifications (git pull)
- Reconstruire l'image Docker si nécessaire
- Mettre à jour le module dans Odoo
- Redémarrer les services

### Réinitialisation complète

Si vous voulez repartir de zéro avec des données fraîches :

```bash
./scripts/reset_demo.sh
```

⚠️ **Attention** : Ceci supprime toutes les données !

## 🛠️ Scripts utilitaires

### `docker-demo.sh`
Script principal pour l'installation initiale. Crée la base de données et les données de démo.

### `scripts/quick_update.sh`
Met à jour le code du module sans toucher aux données. Idéal pour les itérations rapides.

### `scripts/reset_demo.sh`
Réinitialise complètement l'environnement. Utile pour repartir sur une base propre.

## 🎯 Configuration optimisée pour machines peu puissantes

Si la machine de démo a des ressources limitées, utilisez la configuration de production :

```bash
docker-compose -f docker-compose.prod.yml up -d
```

Cette configuration :
- Limite l'utilisation mémoire à 1.5GB
- Désactive les logs verbeux
- Optimise PostgreSQL pour les petites machines

## 📊 Données de démonstration

Le script crée automatiquement :
- 4 clients (2 particuliers, 2 professionnels)
- 4 souscriptions avec différentes configurations
- 1 grille de prix active pour 2025
- Différents types de tarification (Base, HP/HC)

## 🐛 Dépannage

### Les conteneurs ne démarrent pas
```bash
docker-compose logs
```

### Port 8069 déjà utilisé
Modifier le port dans docker-compose.yml :
```yaml
ports:
  - "8080:8069"  # Utilise le port 8080 à la place
```

### Problème de performances
1. Utiliser docker-compose.prod.yml
2. Vérifier la mémoire disponible : `free -h`
3. Fermer les autres applications

### Réinitialiser complètement
```bash
docker-compose down -v
docker system prune -a
./docker-demo.sh
```

## 📝 Notes importantes

- Les mises à jour via `quick_update.sh` sont non-destructives
- Les données persistent dans des volumes Docker
- Pour sauvegarder la base : `docker-compose exec db pg_dump -U odoo souscriptions_demo > backup.sql`
- Pour restaurer : `docker-compose exec -T db psql -U odoo souscriptions_demo < backup.sql`

## 🔗 Workflow typique

1. **Matin** : Développement de nouvelles fonctionnalités chez vous
2. **Commit et push** sur GitHub
3. **Sur place** : `./scripts/quick_update.sh` pour appliquer les changements
4. **Démo** avec les nouvelles fonctionnalités
5. **Feedback** et notes pour les prochaines améliorations
6. **Retour chez vous** : Implémenter les changements demandés
7. **Répéter** le cycle