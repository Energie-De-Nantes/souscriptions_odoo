# Prestation à refacturer : modèle indépendant, rassemblé sur la facture de la Période

Le fournisseur paie à Enedis des prestations ponctuelles (mise en service, déplacement,
changement de puissance, pénalité de coupure…) qu'il **refacture** au·à la *souscripteur·rice*
(voir le terme **Prestation (à refacturer)** dans `CONTEXT.md`). On introduit un modèle
`souscription.presta` dédié plutôt que de les porter sur la *Période* — la Période est déjà un
gros morceau (snapshot typé + verrou, [ADR-0006](0006-snapshot-periode-fait-autorite-facturation.md),
[ADR-0007](0007-snapshot-periode-type-verrou-facturation.md)) et une prestation n'est **pas** un
fait mensuel mais un **en-cours refacturable** à cadence Enedis.

**Décision.**

1. **Modèle indépendant de la Période.** `souscription.presta` porte `code_enedis`, `libelle`,
   `prix`, `quantite`, sa **nature** (`prestation` taxée / `indemnite` hors champ TVA, cf. §5),
   un `souscription_id` (M2o) et un `facture_id` (M2o). Aucun lien vers `souscription.periode`.

2. **Alimenté par electricore, dédupliqué par référence Enedis.** Les prestations sont
   **tirées en totalité** d'un endpoint electricore dédié (le volume est faible — ~une par PDL),
   puis **upsert** sur une **référence Enedis unique** (contrainte d'unicité). Pas de fenêtre
   temporelle : pull-tout-et-dédup est plus robuste qu'un curseur de date (les lignes F15
   arrivent en retard, datées dans le passé — un curseur les manquerait). Le PDL est résolu en
   *Souscription* au moment du sync ; les PDL **sans souscription active sont ignorés** (v1).

3. **Rassemblée sur la facture de la Période, orchestrée par la Souscription.** Une *Prestation*
   ne fabrique **pas** sa propre facture. Au moment de `souscription.creer_factures()`, après que
   la Période a composé sa facture ([ADR-0006](0006-snapshot-periode-fait-autorite-facturation.md)),
   la *Souscription* **ajoute les prestations en attente** comme lignes du brouillon de facture,
   avant qu'il ne sorte du pipeline de création, puis **pose `facture_id`** sur chaque presta.
   « Indépendante de la Période » vaut au niveau du **modèle** (table propre, cadence propre,
   référence la *Souscription* pas la *Période*), pas au niveau du **document**.

4. **Le lien `facture_id` est l'unique marqueur « facturé ».** Cohérent avec
   [ADR-0004](0004-lien-periode-facture-source-unique.md) (lien unique, sens naturel, côté
   « plusieurs ») : `facture_id IS NULL` **est** la file « à refacturer ». Pas de booléen à
   synchroniser (un éventuel `facturee` serait un `compute` non stocké). `ondelete='set null'` :
   supprimer une facture (échappatoire de correction de l'[ADR-0007](0007-snapshot-periode-type-verrou-facturation.md))
   **re-met les prestations dans la file**.

5. **Plomberie comptable minimale, la TVA suit le produit choisi par la nature** (amendée par
   #38, cf. ci-dessous). Deux **produits génériques** portent le compte de produits **et le régime
   de TVA** : `souscriptions_product_prestation_enedis` (prestation taxée) et
   `souscriptions_product_indemnite_enedis` (indemnité hors champ TVA — pénalité de coupure…). La
   `nature` de la presta choisit le produit ; la **ligne hérite de la TVA du produit** via le
   mécanisme Odoo standard (`_compute_tax_ids` + position fiscale), **sans override de `tax_ids`**.
   La ligne **surcharge** seulement name/price_unit/quantity depuis la presta. Pas de catalogue
   produit par code Enedis, pas de taux de TVA par presta.

6. **Refacturation à prix coûtant, une seule source de prix.** `prix` = prix de refacturation,
   par défaut le prix F15 (pass-through, marge nulle — « on n'est pas des voleurs »). **Pas** de
   champ `cout_enedis` distinct sur le modèle : si une marge devait un jour exister, elle se
   calcule à la demande en analytique en rejouant electricore
   ([ADR-0002](0002-deux-sources-de-verite-marge-en-analytique.md), « une seule source »).

Le montant peut être **négatif** (pénalité de coupure due par Enedis au bénéfice de l'usager·ère),
porté comme **ligne signée** qui se nette dans la facture mensuelle.

## Options écartées

- **Porter les prestations sur la Période** : surcharge un modèle déjà lourd et mélange deux
  cadences (mensuelle figée vs ponctuelle Enedis).
- **Facture autonome par prestation (Option B)** : casse les invariants actuels
  (`account.move.souscription_id` est un `related` de `periode_id` ; `is_facture_energie =
  periode_id and souscription_id` ; [ADR-0004](0004-lien-periode-facture-source-unique.md)
  « une facture naît d'une période ») et multiplie les petits documents. Une facture
  prestations-seules (souscription sans période ce mois-là, ex. après résiliation) reste un
  **follow-up** assumé, pas du v1.
- **Curseur temporel `[dernière facturée → maintenant]`** : fragile (prestations en retard datées
  avant le curseur → perdues ; relances → double-facturation). La dédup par référence Enedis
  supprime les deux risques.
- **Booléen `facturee`** au lieu du M2o : deux champs à désynchroniser, et perd le « où ».

## Hors périmètre (follow-up)

- **Facture prestations-seules** pour une souscription sans Période le mois donné (résiliation).
- **Avoir quand le total passe négatif** : si les crédits Enedis du mois (pénalités) dépassent
  les charges, la convention comptable veut un *avoir*, pas un `out_invoice` négatif. v1 pose des
  lignes signées qui se nettent ; le cas « facture qui passerait négative » est laissé au jugement
  du·de la *facturiste* dans l'instant. À retracker en issue dédiée.
- **PDL orphelins** (prestation pour un PDL sans souscription active) : ignorés au sync en v1 ;
  les rendre visibles « à rattacher » est une évolution.

## Amendement (#38) — la TVA suit le produit, par *nature* (pas un taux par presta)

La décision initiale (#8) prévoyait un **taux de TVA par presta, issu du F15**, appliqué en
surchargeant `tax_ids` sur la ligne. En préparant l'implémentation, deux problèmes :

1. **Impédance taux → enregistrement.** Le F15 donne un *taux* (un nombre) ; Odoo facture avec un
   `account.tax` *configuré par le·la comptable* (bons comptes de taxe, bonnes grilles CA3).
   Résoudre « 20 % » → « la bonne taxe » par le montant est fragile (plusieurs taxes au même taux).
2. **Court-circuit des positions fiscales.** Forcer `tax_ids` sur la ligne contourne
   `_compute_tax_ids → fiscal_position.map_tax` (clients exonérés / DOM-TOM / autoliquidation).

**Résolution.** La TVA n'est plus un champ de la presta : elle vient du **produit**, comme pour les
lignes d'énergie (qui ne posent déjà aucun `tax_ids`). Le sync ne résout plus un taux mais classe la
presta dans une **nature** (`prestation` / `indemnite`), qui choisit le produit ; chaque produit
porte la taxe que le·la comptable a configurée. Un produit unique ne suffit pas car les
**indemnités** (pénalités de coupure dues par Enedis) sont **hors champ TVA**, régime distinct des
prestations taxées — d'où deux produits. Le module les livre tous deux **sans taxe** (pass-through,
`taxes_id = []`) ; le·la comptable y rattache en prod la TVA réelle (p. ex. 20 % sur la prestation,
0 %/exonéré sur l'indemnité pour que la base atterrisse dans la bonne case CA3).

Bénéfices : plus de mapping taux→enregistrement, positions fiscales respectées, et la « TVA pas
depuis le défaut produit » d'origine devient « TVA *depuis* le bon produit, choisi par nature ».
