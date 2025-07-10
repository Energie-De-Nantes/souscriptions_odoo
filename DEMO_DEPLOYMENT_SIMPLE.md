# Déploiement ultra-simple avec Docker Hub

## Pour la machine de démo (2 commandes!)

```bash
# 1. Télécharger le fichier de configuration
curl -O https://raw.githubusercontent.com/Energie-De-Nantes/souscriptions_odoo/refactor/minimal-version/docker-compose.demo.yml

# 2. Lancer la démo
docker-compose -f docker-compose.demo.yml up -d
```

C'est tout ! Accès sur http://localhost:8069 (admin/admin)

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