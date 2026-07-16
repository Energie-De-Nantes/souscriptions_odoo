# Scripts de démo - Module Souscriptions Odoo

## Configuration requise
- Docker + Docker Compose
- Odoo 19

## Scripts disponibles

### `./scripts/dev.sh`
Point d'entrée UNIQUE pour lancer le module en local (image construite avec
electricore-client, hot reload). Voir l'en-tête du script pour les modes
disponibles (`--data=demo` par défaut, `--data=prod`, `--reset`, `--light`).
```bash
./scripts/dev.sh
```

## Données de démo

Les fichiers XML dans ce dossier contiennent les données de démonstration :
- `souscriptions_demo.xml` : Clients et contrats de souscription
- `raccordement_demo.xml` : Demandes de raccordement

## Accès
- URL : http://localhost:8069
- Login : admin / admin
