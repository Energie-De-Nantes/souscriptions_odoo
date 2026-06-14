# Scripts de démo - Module Souscriptions Odoo

## Configuration requise
- uv installé (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- PostgreSQL actif
- Odoo 18+ installé sur le système

## Scripts disponibles

### 🚀 `launch_demo_uv.sh`
Réinitialise complètement la base de données et installe le module avec les données de démo.
```bash
./demo/launch_demo_uv.sh
```
- Supprime et recrée la base `souscriptions_demo`
- Installe le module `souscriptions_odoo`
- Charge les données de démo
- Lance le serveur en mode développement

### 🔧 `launch_dev_uv.sh`
Lance Odoo en mode développement avec rechargement automatique.
```bash
./demo/launch_dev_uv.sh [nom_base]  # Par défaut: souscriptions_demo
```
- Utilise une base existante ou en crée une nouvelle
- Active le rechargement automatique (Python, XML, QWeb)
- Mode debug activé

## Données de démo

Les fichiers XML dans ce dossier contiennent les données de démonstration :
- `souscriptions_demo.xml` : Clients et contrats de souscription
- `raccordement_demo.xml` : Demandes de raccordement

## Accès
- URL : http://localhost:8069
- Login : admin / admin