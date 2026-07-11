# Colonnes du justificatif des relevés : union des familles réellement relevées, pas `config_cadrans`

[ADR-0015](0015-releves-index-enfant-fige-periode-projete-facture.md) fixait : « les colonnes
affichées suivent `config_cadrans` » ([ADR-0005](0005-granularite-energie-calendrier-comptage.md)).
En pratique, un changement de compteur **en cours de période** fait cohabiter deux familles de
cadrans dans les mêmes `releve_ids` (l'ancien compteur relève une famille, le nouveau une autre) —
`config_cadrans`, valeur **unique** figée à la création de la Période, ne peut en représenter
qu'une seule. Suivre `config_cadrans` produit alors soit une colonne **parasite** à zéro (famille
déclarée mais jamais relevée), soit une famille **manquante** (relevée mais pas déclarée) — dans
les deux cas le justificatif légal ne montre pas fidèlement « tous les index qu'electricore a
utilisés ». Cet ADR amende ADR-0015 sur ce seul point (le reste — enfant figé, cardinalité
variable, rendu par projection — est inchangé).

## Décision

1. **`releve_colonnes()` lit les relevés, pas `config_cadrans`.** Nouvelle méthode
   `_familles_relevees()` : pour chaque famille de `_FAMILLES = ['base', 'hp_hc', '4_cadrans']`
   (ordre **superficiel → profond**), retient celles dont au moins un `releve_ids` porte un index
   non nul. `releve_colonnes()` concatène les colonnes (`_RELEVE_COLONNES`, dict inchangé) des
   familles retenues, dans cet ordre.
2. **Une famille présente → cette famille seule.** Plus de colonne parasite à zéro pour une
   famille déclarée mais jamais relevée.
3. **Deux familles présentes → l'union ordonnée.** Le changement de compteur en cours de période
   (~2–4 relevés, cf. ADR-0015) donne un **diff visuel** naturel : chaque relevé ne remplit que les
   registres de son propre compteur, les autres colonnes restent à 0 sur sa ligne.
4. **Repli sur `config_cadrans` déclaré si aucun relevé ne porte le moindre index** — `releve_ids`
   vide, ou relevés présents mais sans aucun index renseigné. Préserve la saisie manuelle (#12) :
   le·la facturiste doit garder des colonnes où écrire avant d'avoir des données à afficher.
5. **`column_invisible` ne peut pas appeler de méthode**, et l'union peut rendre **plusieurs**
   familles vraies simultanément — irreprésentable par la Selection `config_cadrans` seule. Le
   formulaire backend expose trois booléens **calculés** sur la Période — `releve_show_base`,
   `releve_show_hphc`, `releve_show_4cadrans` — lisant `_familles_relevees()`, que le sous-formulaire
   `releve_ids` référence en `parent.releve_show_*`.
6. **Source unique inchangée** : PDF, portail et formulaire backend appellent tous
   `periode.releve_colonnes()` (PDF/portail) ou les booléens dérivés de la même méthode (backend) —
   aucune des trois surfaces ne relit `config_cadrans` pour décider des colonnes.

## Conséquences

- `souscription.periode` gagne `_FAMILLES`, `_famille_non_vide()`, `_familles_relevees()` et trois
  champs `Boolean` calculés non stockés (`releve_show_*`). `_RELEVE_COLONNES` (le mapping
  cadran→colonne) et la signature de `releve_colonnes()` sont inchangés — seule la clé qui pilote
  la sélection change (familles relevées, plus `config_cadrans` directement).
- La vue formulaire (`views/core/souscriptions_periode_views.xml`) remplace
  `column_invisible="parent.config_cadrans != '…'"` par `column_invisible="not parent.releve_show_…"`
  sur les 7 colonnes d'index de `releve_ids`.
- `config_cadrans` garde son rôle de **repli** (aucun index relevé) et continue de piloter la
  saisie de l'énergie (ADR 0005, inchangé) : cet amendement ne concerne que l'affichage du
  justificatif des relevés.
- Non-régression démo : la période « Juin 2026 » (Base facturée, compteur remplacé en cours de
  mois) illustre le cas à deux familles — le justificatif affiche Base **et** HPH/HPB/HCH/HCB.

## Raison

L'obligation légale (ADR-0015) est d'afficher **tous** les index utilisés, pas ceux qu'un champ de
configuration figé au premier jour de la période *prévoyait*. Un changement de compteur est
exactement le cas où le·la souscripteur·rice a le plus besoin de vérifier — le diff visuel entre
deux familles rend la transition lisible plutôt que de la masquer derrière une colonne unique.
L'inférence depuis les données réelles (`releve_ids`) est strictement plus fidèle qu'une
déclaration a priori, tout en gardant un repli sûr pour la saisie manuelle tant que #12 n'est pas
comblé.

## Options écartées

- **Ajouter une valeur « mixte » à `config_cadrans`** : quelle famille afficher en premier ? dans
  quel ordre ? Le champ redeviendrait un fourre-tout recalculé, alors que l'information vit déjà,
  précisément, dans `releve_ids`.
- **Un champ `config_cadrans` par relevé plutôt que par Période** : existe déjà (`releve.config_cadrans`,
  related, ADR 0015) mais ne résout pas l'agrégation — il faudrait quand même une méthode d'union
  côté Période pour piloter l'affichage.
- **Consommer directement le `calendrier distributeur` electricore** (identifiant autoritatif du
  calendrier de comptage, cf. `CONTEXT.md`) plutôt que d'inférer depuis les relevés : dépend d'un
  pull non encore construit (#12) ; l'inférence est une étape intermédiaire correcte, à remplacer
  le jour où ce pull existe — pas avant.
