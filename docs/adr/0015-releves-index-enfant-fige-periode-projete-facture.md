# Relevés d'index : enfant figé de la Période, projeté sur la facture (pas de bundle)

La facture d'énergie doit **afficher tous les index qu'electricore a utilisés** pour son calcul :
c'est une **obligation légale** et le support de **vérification** par le·la *souscripteur·rice*
(re-jouer le calcul de conso). Aujourd'hui le module ne porte **aucun** index : la *Période*
n'historise que l'énergie en kWh **par cadran** (`energie_*`). L'index — le relevé cumulé d'un
registre de compteur — est un **nouveau** concept.

## Décision

Introduire **`souscription.releve`**, modèle **enfant de la _Période_** (One2many `periode_id`),
et non de la *Souscription*.

- **Forme large, par cadran réseau.** Un record = un **relevé daté** portant un index par
  **registre** du compteur — même axe *mesuré* que `energie_hph/hpb/hch/hcb` (ou HP/HC, ou Base),
  jamais par cadran **facturé** (un compteur 4-cadrans facturé Base n'a pas d'`index_base`
  physique). Les colonnes affichées suivent `config_cadrans` ([ADR-0005](0005-granularite-energie-calendrier-comptage.md)).
- **Cardinalité variable.** ~2 relevés par Période normale (début / fin), 3–4 lors d'un
  **changement de compteur** ou d'un relevé réel intermédiaire — représentés fidèlement, sans
  branche spéciale (un `index_fin − index_debut` naïf serait *faux* à travers un changement de
  compteur, d'où le refus d'une paire fixe).
- **Nature `reel` / `estime`** par relevé (mesure Enedis vs estimation electricore/facturiste),
  étiquetée sur la facture — exigence légale d'affichage de l'index estimé, et honnêteté de la
  vérification.
- **Figé avec le snapshot de la Période** ([ADR-0006](0006-snapshot-periode-fait-autorite-facturation.md)).
  Le **verrou de facturation** (#14 / [ADR-0014](0014-pas-de-verrou-lignes-facture-confiance-facturiste.md))
  **s'étend à l'enfant** : `create` / `write` / `unlink` sur `souscription.releve` sont rejetés
  dès que `periode.facture_id` existe. Sans cela, le figement fuit.
- **Relevé frontière dupliqué** entre deux Périodes consécutives (`fin` de mars = `début` d'avril) :
  assumé. Chaque facture est **auto-portante** (obligation légale : imprimer son propre début et sa
  propre fin), et le cas « réel arrivé en retard » se résout naturellement — mars garde son `fin`
  *estimé* figé, le réel devient le `début` d'avril, l'écart est soldé en *régularisation*.
- **Source.** Saisie à la main par le·la *facturiste* tant que l'intégration manque (#12), comme
  l'énergie aujourd'hui ; peuplé plus tard par le **pull electricore**
  ([ADR-0011](0011-contrat-pull-facturation-electricore-cle-rsc-mois.md)) au moment du snapshot.
- **Rendu par projection, pas par lignes de facture.** Le relevé n'est **jamais** matérialisé en
  `account.move.line`. Un **bloc QWeb « Justificatif de calcul — relevés utilisés »** itère
  `o.periode_id.releve_ids`, sur la facture **PDF** *et* dans le détail souscription du **portail**.
  Le `move` reste purement financier ([ADR-0014](0014-pas-de-verrou-lignes-facture-confiance-facturiste.md),
  facture = projection de la Période).
- **Pas de modèle « bundle » intermédiaire.** Le jeu de relevés d'une Période **est** la Période :
  celle-ci est déjà le conteneur figé 1:1. La métadonnée propre au *set* — le **`source_hash`**
  (qui permet, en re-pullant le même mois, de détecter de nouvelles données) et, plus tard,
  `calc_ref` / `pulled_at` / `source` — est portée en **champs sur la Période**, pas dans une table
  dédiée — `source_hash` étant peuplé par le pull à venir, pas pendant la saisie manuelle.

## Conséquences

- Nouveau modèle `souscription.releve` (+ vues, sécurité) ; champ `source_hash` sur
  `souscription.periode`. Migration : aucune donnée existante à reprendre (concept neuf).
- Le verrou #14 doit couvrir un **troisième** point (move, Période, **relevé**) : implémenter le
  blocage sur `create`/`write`/`unlink` de `souscription.releve` quand la Période est facturée.
- **Re-pull avant facturation** = **remplacement en bloc** de `releve_ids`
  (`[(5, 0, 0), (0, 0, …)]`) + mise à jour de `source_hash`. Pas de FK à échanger, pas de bundle.
- La **conso** par cadran reste portée par `energie_*` (la ligne de facture) ; le bloc justificatif
  **liste les relevés bruts** plutôt que de recalculer une conso (à travers un changement de
  compteur, le brut *est* la piste d'audit). En **lissé**, le bloc est informatif et visiblement
  séparé de la provision facturée ; la *régularisation* solde l'écart.
- Deux surfaces à maintenir (PDF + portail) lisent la même source `releve_ids`.

## Options écartées

- **Relevés enfants de la _Souscription_** (timeline PDL partagée) : une correction de relevé
  réagirait sur les factures passées — casse la reproductibilité d'[ADR-0006](0006-snapshot-periode-fait-autorite-facturation.md).
  La duplication frontière est le prix assumé de l'auto-portance.
- **Modèle « bundle » intermédiaire** (Période → bundle → relevés) : wrapper **1:1** avec la
  Période, sans identité ni cycle de vie propres — *middle-man*. Les deux justifications réelles
  d'un agrégat (jeu **partagé**, jeu **pluriel/versionné**) ont été **écartées par conception**
  (copie figée par période ; correction = régularisation, [ADR-0006](0006-snapshot-periode-fait-autorite-facturation.md)).
  La troisième (métadonnée propre au set) est absorbée par le parent 1:1 (`source_hash`).
  **Tripwire** : promouvoir le jeu en modèle propre **le jour où il faut retenir ≥ 2 jeux
  simultanés par Période** (vrai versioning) — et seulement ce jour-là. Un `source_hash` qui change
  au re-pull n'est *pas* cette condition tant que la politique reste « non facturée → remplacer ;
  facturée → régularisation ».
- **Relevés en `account.move.line`** (notes/sections, comme le TURPE) : pollue le move de lignes
  non financières (quantités/prix factices), dédouble la source (move *et* Période).
- **Paire `index_debut` / `index_fin` fixe par cadran** (champs sur la Période) : simple, mais
  incapable de représenter fidèlement un changement de compteur — exactement un cas où l'usager·ère
  voudrait vérifier.
- **Payload opaque d'electricore** (JSON brut stocké tel quel) : fidélité maximale mais non
  requêtable / non agrégeable et fragile au format amont.

## Raison

« Tous les index utilisés » est une **contrainte légale** doublée d'un **droit de vérification** :
la facture doit exposer, fidèlement, la matière première du calcul d'electricore. Loger ce jeu sur
la **Période** — l'unité de snapshot déjà figée et déjà autoritaire à la facturation
([ADR-0006](0006-snapshot-periode-fait-autorite-facturation.md)) — donne la reproductibilité sans
nouvelle frontière, et le rendre **par projection** garde le move purement comptable
([ADR-0014](0014-pas-de-verrou-lignes-facture-confiance-facturiste.md)). Refuser le bundle, c'est
appliquer YAGNI avec un **déclencheur nommé** : on n'abstrait le jeu qu'à l'apparition du deuxième
exemplaire, pas avant.
