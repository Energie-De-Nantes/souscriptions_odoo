# Architecture Modulaire - Module Souscriptions

## Vue d'ensemble

Le module `souscriptions` utilise une architecture modulaire qui permet un déploiement progressif :
- **Phase 1** : Module Core uniquement (gestion des souscriptions)
- **Phase 2** : Module Core + Métier (intégration données Enedis)

## Structure

```
souscriptions/
├── models/
│   ├── core/              # Phase 1 - Modèles principaux
│   │   ├── souscription.py
│   │   ├── souscription_periode.py
│   │   ├── grille_prix.py
│   │   └── account_move.py
│   └── metier/            # Phase 2 - Données métier
│       ├── models/        # Modèles de données Enedis
│       ├── importers/     # Import depuis fichiers Parquet
│       └── mixins/        # Extension du modèle souscription
├── views/
│   ├── core/              # Vues Phase 1
│   └── metier/            # Vues Phase 2
└── toggle_metier.sh       # Script d'activation/désactivation
```

## Utilisation

### Phase 1 : Installation Core uniquement
```bash
# État par défaut - Métier désactivé
odoo-bin -d votre_base -i souscriptions
```

### Phase 2 : Activation du module Métier
```bash
# Activer le module métier
./toggle_metier.sh enable

# Redémarrer Odoo et mettre à jour
odoo-bin -d votre_base -u souscriptions
```

### Vérifier le statut
```bash
./toggle_metier.sh status
```

### Désactiver le module Métier
```bash
./toggle_metier.sh disable
odoo-bin -d votre_base -u souscriptions
```

## Avantages

1. **Déploiement progressif** : Permet de mettre en production le core avant le métier
2. **Un seul module** : Simplicité de maintenance et de déploiement
3. **Séparation claire** : Code organisé par domaine fonctionnel
4. **Performance** : Chargement uniquement des composants nécessaires

## Notes importantes

- Les données métier restent dans la base même si le module est désactivé
- L'activation/désactivation nécessite un redémarrage d'Odoo
- Les tests sont organisés pour fonctionner dans les deux modes