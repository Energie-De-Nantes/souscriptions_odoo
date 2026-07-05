# Alignement sur le contrat méta-périodes v3 : noms du contrat, `mois` canonique, atterrissage des verdicts et montants, provenance des relevés

*Note (juillet 2026) : le §1 s'étend des **noms** aux **valeurs** du contrat. Le fil sert les
verdicts avec les termes du glossaire electricore — `qualite ∈ {réelle, estimée, incalculable}`,
**accentués** (son ADR-0033) — et les clés de sélection Odoo les reprennent **telles quelles** ;
les clés désaccentuées (`reelle`, `estimee`) du premier atterrissage étaient une traduction
involontaire, révélée en prod par le rejet du pull S0001 (`Wrong value ... 'réelle'`). Même
raison que pour les noms : toute couche de traduction est une classe de bugs. Une valeur de fil
hors sélection reste un **échec bruyant** skip-and-report (savepoint, ADR-0011) — pas de repli
silencieux : hors bump de `contract_version`, c'est une violation de contrat qui doit se voir.*

[ADR-0011](0011-contrat-pull-facturation-electricore-cle-rsc-mois.md) a fixé le pull
facturiste sur un payload *supposé* ; depuis, electricore a versionné son contrat **réel** :
`PeriodeMeta` **v3** (`electricore_client.models.meta_periodes`, servi en `response_model`,
[ADR-0019](0019-consommation-electricore-client-fin-contrat-type-versionne.md)), qui **fait
foi**. Cet ADR fixe comment `souscription.*` s'y aligne — quels noms, quels sens, où
atterrissent les champs — pour que #76 (champs), #77 (pull) et #78 (abonnement sur puissance
moyenne) construisent sur un vocabulaire arrêté. Les écarts avec l'ADR-0011 sont notés
là-bas ; ici on acte la cible.

## Décision

1. **Les noms du contrat, sauf collision.** Les champs v3 atterrissent sur la *Période*
   **sous le nom du contrat** : `qualite`, `statut_communication`, `has_changement`,
   `source_hash`, `cta_eur`, `taux_accise_eur_mwh`, `puissance_moyenne_kva`. Le contrat typé
   étant single-source ([ADR-0019](0019-consommation-electricore-client-fin-contrat-type-versionne.md)),
   partager les noms supprime toute couche de traduction au mapping. **Une** collision,
   tranchée en faveur de l'existant Odoo : le contrat nomme `mois_annee` sa clé « YYYY-MM » ;
   côté Odoo, `mois_annee` est déjà le **libellé d'affichage** français (« juillet 2025 »)
   et le reste — la clé canonique est un champ **`mois`** distinct.

2. **`mois` canonique.** `Date` au **1er du mois**, **dérivé stocké** de `date_debut` —
   support local de la clé d'idempotence `(RSC, mois)` du pull
   ([ADR-0011](0011-contrat-pull-facturation-electricore-cle-rsc-mois.md)). Unicité
   **`(souscription, mois)` scopée aux périodes mensuelles** : les
   régularisations/ajustements restent libres (plusieurs par mois possibles).

3. **Identité : la *Période* snapshotte la RSC.** `ref_situation_contractuelle` est recopiée
   de la *Souscription* à la création — même logique que le snapshot des paramètres
   contractuels ([ADR-0006](0006-snapshot-periode-fait-autorite-facturation.md)). La
   *Souscription* porte RSC + `id_affaire`
   ([ADR-0010](0010-identite-souscription-rsc-cle-id-affaire-amorce.md)), saisissables à la
   main tant que le raccordement ne les peuple pas (acquisition RSC : #79).

4. **Sens des champs d'atterrissage.**
   - `qualite` (réelle / estimée / incalculable) et `statut_communication` (communicante /
     non communicante) : les **verdicts jumeaux** d'electricore — ils remplacent le drapeau
     `data_complete` d'ADR-0011. Une période `incalculable` est créée quand même : le
     brouillon facturable reste la règle (`CONTEXT.md`, *Période*).
   - `taux_accise_eur_mwh` est un **taux** : l'assiette est l'énergie **facturée** par Odoo
     (la provision si le contrat est lissé,
     [ADR-0008](0008-quantite-facturee-mesure-ou-provision-selon-lissage.md)) ; le montant
     se calcule côté Odoo. `cta_eur` est un **montant**, servi tel quel.
   - `puissance_moyenne_kva` : moyenne pondérée **physique** (C15) sur la période — une
     grandeur réseau, pas le paramètre contractuel. C'est **elle** qui prixe l'abonnement
     affine quand elle est présente (#78,
     [ADR-0018](0018-abonnement-affine-base-3kva-plus-coefficient-kva.md)) ; la puissance
     **souscrite** reste le paramètre contractuel snapshotté, affiché aux *conditions
     particulières*.

5. **Énergies pré-pliées, cascade préservée.** electricore sert `energie_base/hp/hc_kwh`
   **déjà regroupées** depuis les 4 cadrans saisonniers (HP = HPH+HPB, HC = HCH+HCB) — ce
   pliage lui appartient. La cascade locale (4 cadrans → HP/HC → Base) ne sert plus qu'à la
   **saisie manuelle** et ne doit **jamais écraser** des valeurs fournies à la création
   (test verrouillant, #76). Seul le regroupement final vers le cadran **facturé**
   (HP/HC → Base si la formule fournisseur est Base) reste côté Odoo. Le détail par
   **registre réel** ne survit que dans la trace d'index `releves_utilises`.

6. **Provenance des relevés.** Le *Relevé* porte `releve_externe_id` (← `releve_id` du
   contrat) et `origine` (← `origine_releve`, précisé par `evenement` pour les relevés
   d'événement C15) : identifiant du justificatif côté electricore, support de la **dédup au
   re-pull**. La nature réel/estimé se mappe depuis `nature_index`.

7. **Verrouillage et exposition.** Tous ces champs sont **figés après facturation**
   ([ADR-0007](0007-snapshot-periode-type-verrou-facturation.md)) et visibles du·de la
   *facturiste* sur le formulaire Période.

## Conséquences

- Nouveaux champs sur *Souscription*, *Période* et *Relevé* (#76) ; le wizard de pull (#77)
  mappe `PeriodeMeta → create()` sans table de traduction (hors `mois`, dérivé).
- La garde de version du client
  ([ADR-0019](0019-consommation-electricore-client-fin-contrat-type-versionne.md)) attend
  `contract_version = 3` sur l'endpoint méta-périodes.
- `CONTEXT.md` corrigé : le regroupement en HP/HC appartient à electricore, l'axe des
  *Relevés* (registres réels) diverge de celui des énergies servies (cadrans regroupés).
- Notes de dérive apposées sur
  [ADR-0010](0010-identite-souscription-rsc-cle-id-affaire-amorce.md) et
  [ADR-0011](0011-contrat-pull-facturation-electricore-cle-rsc-mois.md).

## Options écartées

- **Renommer le libellé Odoo pour suivre le contrat (`mois_annee` = clé)** : casse vues,
  rapports et habitudes pour un bénéfice nul — la collision porte sur un *nom*, pas un sens.
- **Clé `mois` en `Char` « YYYY-MM » (copie du fil)** : une `Date` au 1er trie, groupe et se
  contraint nativement (ORM + SQL) ; la forme fil se dérive trivialement.
- **Table de correspondance nom-fil → nom-Odoo** : une couche de traduction à maintenir,
  que l'alignement des noms rend inutile.
- **Unicité `(souscription, mois)` globale** : bloquerait régularisations et ajustements —
  d'où le scope aux seules périodes mensuelles.
- **Renvoyer la puissance souscrite dans le payload** : reste exclu — la frontière
  d'[ADR-0002](0002-deux-sources-de-verite-marge-en-analytique.md)/0011 sur les paramètres
  contractuels tient ; seule la grandeur *physique* (moyenne C15) traverse le fil.

## Raison

Le contrat typé est single-source et versionné
([ADR-0019](0019-consommation-electricore-client-fin-contrat-type-versionne.md)) : s'aligner
sur ses noms et son sens supprime la classe entière des bugs de traduction, et la seule
collision (`mois_annee`) se résout en préservant l'existant. Fixer ces décisions *avant*
#76/#77/#78 donne aux trois tranches un vocabulaire commun au lieu de trois interprétations
du même fil.
