# Portal Client - Module Souscriptions

## Vue d'ensemble

Le portal client utilise le framework Portal standard d'Odoo pour permettre aux usager·ères de consulter leurs souscriptions électriques. Cette approche suit les bonnes pratiques d'Odoo 18 et s'intègre naturellement avec les autres modules.

## Accès

- URL : `/my/home` (portail principal Odoo)
- Section Souscriptions : `/my/souscriptions`
- Authentification : Via le système de login standard d'Odoo

## Fonctionnalités

### Page d'accueil du portail
- Tuile "Souscriptions" avec compteur
- Intégration avec les autres documents (factures, etc.)

### Liste des souscriptions (`/my/souscriptions`)
- Tableau des souscriptions actives
- Informations clés : PDL, puissance, type de tarif
- Pagination automatique
- Accès sécurisé par partner_id

### Détail d'une souscription (`/my/souscription/<id>`)
- Informations complètes du contrat
- État de facturation
- Historique des 10 dernières factures
- Liens vers les PDF de factures
- Informations de dépannage

## Architecture technique

### Contrôleur Portal (`controllers/portal.py`)
- Hérite de `CustomerPortal` 
- Surcharge `_prepare_home_portal_values` pour le compteur
- Routes sécurisées avec vérification partner_id
- Support de la pagination

### Templates (`views/portal_templates.xml`)
- `portal_my_home_souscriptions` : tuile sur la page d'accueil
- `portal_my_souscriptions` : liste des souscriptions
- `portal_souscription_page` : détail d'une souscription

### Sécurité (`security/ir.model.access.csv`)
- Groupe `base.group_portal` : lecture seule sur les modèles
- Filtrage automatique par partner_id dans le contrôleur

## Avantages de l'approche Portal

1. **Intégration native** : S'intègre avec le portail Odoo existant
2. **Cohérence UX** : Même interface que les autres documents
3. **Sécurité** : Utilise le système de droits d'Odoo
4. **Responsive** : Templates Bootstrap intégrés
5. **Maintenance** : Suit les mises à jour d'Odoo

## Différences avec l'ancienne approche

L'approche Portal remplace l'espace client autonome en :
- Utilisant les templates standards au lieu de HTML custom
- S'intégrant au module website (quand il fonctionne)
- Réutilisant les composants Odoo (pagination, breadcrumbs, etc.)
- Suivant les conventions de routes (`/my/...`)

## Configuration requise

- Module `portal` installé (dépendance automatique)
- Module `website` pour le rendu complet
- Utilisateurs avec accès portal configuré

## Évolution future

- Ajout de graphiques de consommation
- Export des données en CSV/PDF
- Notifications par email
- Paiement en ligne (quand website_payment sera résolu)