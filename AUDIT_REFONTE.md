# Audit — Refonte du module souscriptions sur Odoo 19

*Audit réalisé le 13 juin 2026, en vue d'une version solide s'appuyant sur
[electricore](https://github.com/Energie-De-Nantes/electricore) (v2.1.1, API REST déployée sur VPS)
pour tout le savoir métier, Odoo ne gardant que la comptabilité légale et les prix.*

## 1. Contexte et cible

Le prototype actuel a été écrit sans connaissance préalable d'Odoo, en phase exploratoire.
Depuis, electricore a atteint la maturité : pipelines Polars (périmètre, abonnements,
énergies, TURPE, accise), API FastAPI sécurisée par clé (`X-API-Key`), connecteur Odoo
(`OdooReader`/`OdooWriter`), 15 releases, CI.

**Philosophie cible** (déjà actée dans l'issue #4) :

| Responsabilité | Système |
|---|---|
| Ingestion flux Enedis (C15, R151, F15…) | electricore |
| Calculs métier : périmètre, énergies par cadran, TURPE, accise | electricore |
| Archivage des données métier raffinées (périodes) | Odoo |
| Règles tarifaires (grilles de prix) | Odoo |
| Facturation, taxes, comptabilité légale, paiements | Odoo |
| Portail usager·ère | Odoo |

**Version Odoo cible : 19** (stable depuis octobre 2025). Les vues utilisent déjà `<list>`
(syntaxe 18+), pas d'`attrs` ; la migration est donc surtout du nettoyage, pas une réécriture.

## 2. Ce qui est conceptuellement bon (à garder)

- **`souscription.periode` comme pivot** : la couche intermédiaire « données métier →
  période → facture » correspond exactement à ce que produit le pipeline `facturation`
  d'electricore (périodes avec cadrans + TURPE). C'est la bonne frontière.
- **Historisation des paramètres contractuels par période** (puissance, type tarif,
  solidaire, coeff PRO au moment T) : indispensable pour l'audit comptable et les
  régularisations. Le principe est bon, l'implémentation (copies en `Char`) est à revoir.
- **Grilles de prix datées** avec fermeture automatique de la précédente.
- **Pipeline raccordement** (kanban → création partner/banque/souscription) : workflow
  natif Odoo, pertinent.
- **Portail** en lecture seule avec `ir.rule` par partenaire.
- **Suite de tests** : ~2 800 lignes existent (contrairement à ce que dit CLAUDE.md,
  obsolète sur ce point). À remettre au vert et brancher en CI.

## 3. Problèmes bloquants

### 3.1 Double héritage `account.move` (cassera sur Odoo 19)
`models/__init__.py` charge **à la fois** `models/core/account_move.py` et
`models/account_move.py`, qui définissent chacun `periode_id` et `souscription_id`
(avec des définitions divergentes). Odoo 19 valide strictement les conflits de champs
sur `_inherit`. À fusionner en un seul fichier.

### 3.2 Désaccord de contrat avec electricore
Le `CONTEXT.md` du module `integrations/odoo` d'electricore cible aujourd'hui
**`sale.order` + champs custom `x_pdl`, `x_ref_situation_contractuelle`, `x_lisse`,
`x_invoicing_state`, `x_date_cfne`** — pas les modèles `souscription.*` de cet addon.
Il faut trancher le contrat d'intégration et l'écrire **dans un seul endroit** :

- Option A (recommandée) : electricore adapte son writer aux modèles `souscription.*`,
  l'addon expose un contrat stable (upsert idempotent de périodes, clé
  `ref_situation_contractuelle` + bornes de dates).
- Option B : refonder l'addon sur `sale.order` (perd la modélisation métier propre,
  non recommandé vu les besoins spécifiques élec).

### 3.3 Identifiant : RSC au lieu du PDL seul (issue #5)
Tout est clé sur `pdl`, qui n'est pas un identifiant de contrat (plusieurs
souscripteurices successif·ves sur un même PDL). electricore travaille en
`ref_situation_contractuelle`. Ajouter le RSC sur souscription et période, garder le PDL
comme attribut d'affichage/recherche.

### 3.4 Module métier redondant → à supprimer
`models/metier/` (miroirs readonly des données Enedis + importeurs Parquet
pandas/fastparquet) duplique l'ingestion d'electricore. Le supprimer retire les
dépendances pandas/fastparquet/pyarrow du runtime Odoo, le `toggle_metier.sh`, et
la moitié de la surface de code. Si on veut afficher l'historique périmètre dans une
fiche souscription, on interroge l'API electricore (`GET /flux/c15?prm=…`) à la volée.

## 4. Problèmes majeurs (facturation et comptabilité légale)

Odoo devant porter « la comptabilité légale et les prix », c'est paradoxalement la
partie la plus faible du prototype :

1. **Taxes énergie absentes** : ni accise sur l'électricité, ni CTA, ni gestion de la
   TVA différenciée (5,5 % abonnement+CTA / 20 % consommation+accise). Le TURPE
   n'apparaît que comme note informative (« Dont turpe fixe… ») et non comme ligne
   comptabilisée. C'est le cœur d'une facture d'électricité conforme.
2. **`get_grille_active(date)` ignore la date** : retourne la grille flaguée
   `is_current`, donc une régularisation sur une période passée serait facturée au
   prix courant. La sélection doit se faire par plage `date_debut`/`date_fin`.
3. **Formule d'abonnement codée en dur** : `prix_3kVA × (kVA/3) / 30` — linéarité en
   kVA non garantie par la réalité tarifaire, mois forfaitaire à 30 jours faux pour
   un prorata (28–31 jours). Les prix d'abonnement doivent être des données
   (prix par puissance, en €/jour ou €/an), pas une formule.
4. **Historisation par chaînes** : `puissance_souscrite_periode = "6 kVA"` (Char),
   reparsé par regex au moment de facturer. Stocker des valeurs typées.
5. **Régularisation non implémentée** : `type_periode='regularisation'` existe mais
   aucun calcul d'écart conso réelle vs provisions, aucune génération d'avoir.
   C'est la raison d'être du module (contrats lissés).
6. **Génération de périodes naïve** : `ajouter_periodes_mensuelles` crée une période
   calendaire pour toute souscription active, sans tenir compte de `date_debut`/
   `date_fin` du contrat (résiliations, emménagements — issue #7). Dans la cible,
   c'est **electricore qui connaît les bornes réelles** (C15) : les périodes doivent
   être créées/upsertées par electricore, pas par un cron Odoo aveugle.
7. **Paiements** : IBAN/BIC/mandat SEPA capturés comme simples Char sur le
   raccordement ; aucun lien avec `account.payment`, pas de génération de
   prélèvements SEPA (le bouton existant est un stub). Utiliser les modules
   standard (`account_sepa_direct_debit` / OCA `account_banking_sepa_direct_debit`).

## 5. Problèmes de qualité / sécurité

- **Droits** : tout utilisateur interne (`base.group_user`) a CRUD complet (y compris
  unlink) sur souscriptions, périodes, grilles. Créer des groupes
  `souscriptions_user` / `souscriptions_manager`, verrouiller les périodes facturées
  (readonly après liaison facture), retirer l'unlink par défaut.
- **API « pont externe » non sécurisée par conception** : `update_consumption_data`
  écrit n'importe quel champ de n'importe quelle période sans validation ni contrôle
  d'état (période déjà facturée ?). À remplacer par un upsert validé et idempotent.
- **`.env` versionné** (pas de secret dedans aujourd'hui, mais mauvaise habitude).
- **`grille_prix_demo.xml` chargé en `data`** (production) au lieu de `demo`.
- **Odoo 19** : `odoo.osv.expression` déprécié (→ `odoo.fields.Domain`),
  `_sql_constraints` → `models.Constraint()`, manifeste sans `version: "19.0.x.y.z"`.
- **Docs contradictoires** : plan.md décrit une architecture 3 modules jamais réalisée,
  README_ARCHITECTURE décrit le toggle métier, CLAUDE.md nie l'existence des tests.
  Une seule source de vérité à réécrire après refonte.
- **Pas de CI** : la suite de tests n'est exécutée nulle part.

## 6. Architecture cible proposée

```
electricore (VPS, FastAPI + OdooWriter XML-RPC)
   │  calcule : périmètre, énergies/cadrans, TURPE, accise (quantités)
   │  upsert idempotent ──────────────────────────┐
   ▼                                              ▼
souscription.souscription ──1:n── souscription.periode ──1:0..1── account.move
(contrat : partner, RSC+PDL,      (données raffinées,             (facture : grille de
 puissance, tarif, lissage,        verrouillée une fois            prix datée, taxes
 mode paiement, mandat SEPA)       facturée)                       CTA/accise/TVA,
                                                                   prélèvement SEPA)
```

- Un seul addon Odoo 19 (`souscriptions_odoo`), sans pandas, sans module métier.
- Périodes **écrites par electricore** (writer existant à adapter au contrat), clé
  d'idempotence `(ref_situation_contractuelle, date_debut, date_fin)`.
- Grilles de prix datées, prix d'abonnement par puissance en données, taxes énergie
  configurées en `account.tax` + positions fiscales.
- Régularisation des lissés implémentée comme période spéciale → facture/avoir.
- Raccordement et portail conservés, consolidés.

## 7. Découpage proposé

Voir les issues GitHub créées à partir de cet audit (milestone « Refonte Odoo 19 »).
Ordre de dépendance recommandé :

1. Assainissement : fusion `account.move`, suppression métier, manifeste 19, CI verte.
2. Contrat d'intégration electricore ↔ Odoo (décision A/B + doc + RSC).
3. Refonte périodes (champs typés, verrouillage, upsert idempotent).
4. Refonte grilles de prix (sélection par date, prix par puissance en données).
5. Facture légale complète (TURPE en lignes, CTA, accise, TVA différenciée).
6. Régularisation des lissés.
7. SEPA / paiements.
8. Sécurité (groupes, règles), portail, raccordement consolidé.
