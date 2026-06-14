# Granularité de l'énergie pilotée par le calendrier de comptage, orthogonale au type de tarif

La *Période* historise l'énergie **par cadran**. Deux axes de cadrans, **orthogonaux**, s'y
croisent : les cadrans **mesurés** (propriété du *compteur* — *Configuration Enedis*, source
electricore) et les cadrans **facturés** (formule fournisseur, `type_tarif`). Le `type_tarif`
n'a que deux valeurs (`base`, `hphc`) et **ne peut pas** distinguer un compteur **2 registres
HP/HC** d'un compteur **4 cadrans saisonniers** : les deux sont `hphc`. Piloter la saisie de
l'énergie sur le seul `type_tarif` est donc structurellement insuffisant.

## Décision

Introduire **`config_cadrans`** (`base` / `hp_hc` / `4_cadrans`) — le *calendrier de comptage*
du compteur, issu de la *Configuration Enedis* (electricore ; saisi à la main tant que le contrat
d'intégration n'existe pas, cf. #12). Porté par la *Souscription* (live) et **copié/historisé**
sur la *Période* (gel à la création, comme les autres champs `_periode`).

- `config_cadrans` pilote le **niveau de saisie** de l'énergie :
  `4_cadrans` → HPH/HPB/HCH/HCB ; `hp_hc` → HP, HC ; `base` → BASE.
- `type_tarif` pilote le **regroupement facturé** affiché (`base` → BASE ; `hphc` → HP, HC).
  Contrainte : `type_tarif` ≤ granularité du compteur.

L'énergie est modélisée en **cascade dérivée-mais-surchargeable**
(`HPH/HPB/HCH/HCB → HP/HC → BASE`) : chaque niveau est `compute store readonly=False`, le
calcul étant **config-aware** (il ne dérive un niveau que s'il est au-dessus du niveau de saisie,
pour ne jamais écraser une valeur saisie à la main). Un PDL facturé Base sur compteur 4 cadrans
est ainsi `config_cadrans=4_cadrans` + `type_tarif=base` : saisie des 4 cadrans, BASE en
roll-up lecture seule.

## Conséquences

- `energie_hp_kwh`, `energie_hc_kwh`, `energie_base_kwh` passent de **calculés purs** à
  **calculés + stockés + surchargeables** ; commenter clairement leur double nature.
- Nouveau champ `config_cadrans` (souscription + copie historisée période) ; migration.
- TURPE variable reste saisi à la main pour l'instant ; son recalcul par electricore depuis les
  cadrans dépend du contrat d'intégration (#12).
- Ce travail est une **tranche de #14** (refonte du modèle période : champs typés, historisation
  propre). Le glossaire (*Configuration Enedis* → calendrier de comptage) est dans `CONTEXT.md`.

## Raison

Justesse non négociable (sans `config_cadrans`, impossible de distinguer 2-registres et 4-cadrans),
tenue dans un périmètre **KISS borné** : un jeu **fini de 3 configurations** plutôt qu'un modèle
de lignes de cadrans dynamiques. Couvre le process principal (Base, HP/HC, 4 cadrans) ; Tempo/EJP
explicitement hors périmètre.

## Options écartées

- **Piloter par `type_tarif`** : insuffisant (ne sépare pas 2-registres / 4-cadrans).
- **Lignes de cadrans dynamiques** (`periode.cadran`) : surdimensionné pour 3 configs finies.
- **Garder HP/HC/BASE purement calculés** : empêche la saisie directe d'un Base mono-index ou
  d'un HP/HC 2 registres quand le flux Enedis manque.
