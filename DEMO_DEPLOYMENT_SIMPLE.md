# Déploiement ultra-simple avec Docker Hub

## Option 1 : Une seule commande (vraiment !)

```bash
curl -sSL https://raw.githubusercontent.com/Energie-De-Nantes/souscriptions_odoo/refactor/minimal-version/scripts/demo_oneliner.sh | bash
```

C'est tout ! Cette commande va :
- Télécharger et lancer PostgreSQL
- Télécharger et lancer Odoo avec le module pré-configuré
- Créer automatiquement les données de démo

Accès sur http://localhost:8069 (admin/admin)

## Option 2 : Avec docker-compose (si vous préférez)

```bash
# Télécharger le fichier de configuration
curl -O https://raw.githubusercontent.com/Energie-De-Nantes/souscriptions_odoo/refactor/minimal-version/docker-compose.demo.yml

# Lancer la démo
docker-compose -f docker-compose.demo.yml up -d
```

## Pour mettre à jour

```bash
# Récupérer la dernière version
docker-compose -f docker-compose.demo.yml pull

# Redémarrer
docker-compose -f docker-compose.demo.yml up -d
```

## Workflow développeur

1. **Chez vous** : Développer et tester
2. **Build & Push** :
   ```bash
   ./scripts/build_and_push.sh
   ```
3. **Sur la machine démo** :
   ```bash
   docker-compose -f docker-compose.demo.yml pull
   docker-compose -f docker-compose.demo.yml up -d
   ```

## Avantages

- ✅ Pas besoin de Git sur la machine démo
- ✅ Pas de build Docker sur place (économie de ressources)
- ✅ Image pré-configurée avec toutes les dépendances
- ✅ Mise à jour en 2 commandes
- ✅ Données de démo incluses