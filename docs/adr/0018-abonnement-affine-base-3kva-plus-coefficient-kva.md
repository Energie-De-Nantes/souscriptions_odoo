# Tarif d'abonnement affine (base 3 kVA + coefficient par kVA) au lieu d'un prix par palier

La *Grille de prix* tarifait l'abonnement par un **prix indépendant par palier de puissance**
(9 valeurs/univers, invariant verrouillé par `test_prix_independant_par_puissance`). On le remplace
par un **tarif affine** : `prix_base_3kva + coef_kva × (puissance − 3)`, soit **2 paramètres** par
univers. Cet ADR **renverse** cet ancien invariant et fixe la forme de la grille qui en découle.

## Décision

L'abonnement journalier se calcule par une fonction affine de la puissance souscrite :

```
abo_jour_ht = (prix_base_3kva + coef_kva × (puissance_kva − 3)) / 365
              × (1 + coeff_pro / 100)          ← majoration PRO, cf. plus bas
```

La puissance **cesse d'être une dimension de la grille** : elle n'est plus qu'une **entrée** de la
formule, portée par la *Souscription* (`puissance_souscrite`). La grille ne énumère plus les paliers.

**Forme de la grille** — l'univers (standard / solidaire) reste **porté par le produit**, jamais
ré-encodé dans la grille (ADR 0013 : le catalogue est l'**unique** endroit qui résout l'univers).
L'abonnement est donc **une ligne par univers**, dont le `product_id` (issu du catalogue) porte
l'univers et qui ne stocke que `prix_base_3kva` + `coef_kva` :

```
grille.prix.ligne :
  product_id      ← produit du catalogue = porte l'univers (std/sol) ET le rôle
  type_produit    ← abonnement | energie          (le rôle ; 'autre' supprimé)
  · abonnement →  prix_base_3kva (€/an @3 kVA) + coef_kva (€/an par kVA supplémentaire)
  · energie    →  prix_unitaire (€/kWh)
```

→ **8 lignes** par grille (2 abonnement + 6 énergie), contre 24 auparavant. Les lignes énergie sont
inchangées.

**Majoration PRO** : `coeff_pro` reste **propre à chaque souscription** (négocié au cas par cas, pas
dans la grille) et s'applique désormais à **toutes les lignes de fourniture** (abonnement **et**
énergie), **jamais** à la *Refacturation* (pur transit de coût Enedis).

## Raison

La non-linéarité historique du prix d'abonnement n'existait que pour **épouser les paliers du TURPE**.
Or le TURPE est **externalisé** (electricore) et **absorbé** dans un prix fournisseur tout-compris,
jamais refacturé ligne à ligne (ADR 0002). La justification du prix par palier disparaît donc avec lui.

Une fois le TURPE sorti, l'affine est la forme **naturelle d'un prix final maîtrisé** : pour stabiliser
le prix payé quand le TURPE bouge, on tient **2 boutons** (`base`, `coef`) au lieu de re-justifier
9 valeurs. La contrepartie — une **marge par palier variable** (affine − TURPE non-linéaire, parfois
mince voire négative) — est **assumée** : c'est précisément « encaisser la différence dans la marge »,
surveillée dans la couche analytique (ADR 0002).

## Conséquences

- Suppression de l'invariant inverse et de son test (`test_prix_independant_par_puissance`), du champ
  `puissance` et de `prix_abonnement_annuel` sur la ligne, et de la branche `type_produit='autre'`
  (jamais utilisée).
- La marge par palier n'est plus uniforme — voulu, surveillé hors transactionnel (ADR 0002).
- Nettoyage corrélé (même refonte) : suppression de `is_current` et de son action (la grille est
  sélectionnée **par date**, jamais par un drapeau « grille actuelle »).

## Options écartées

- **Affine avec dérogations par palier** (formule + quelques prix épinglés) : machinerie pour une
  déviation qu'on ne sait pas nommer aujourd'hui (YAGNI). Si un palier doit casser la droite un jour,
  ce sera un changement de grille.
- **Paramètres d'abonnement en champs d'en-tête** (`prix_abo_base_std/_sol`…) : ré-encoderait l'axe
  solidaire dans des **noms de champs**, en doublon du catalogue — viole le principe d'unicité de
  l'univers (ADR 0013). D'où la ligne-par-univers retenue.
