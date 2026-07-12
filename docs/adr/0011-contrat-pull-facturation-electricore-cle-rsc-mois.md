# Contrat de facturation electricore → Odoo : *pull* facturiste, clé `(RSC, mois)`, payload physique

*Note (juillet 2026) : le payload décrit en §4/§5 a été rattrapé par le contrat **réel**
d'electricore — `PeriodeMeta` **v3**, qui fait foi
([ADR-0020](0020-alignement-contrat-meta-periodes-v3.md)). Écarts : l'accise arrive en
**taux** (`taux_accise_eur_mwh`, l'assiette restant côté Odoo) et non en montant + assiette ;
`data_complete` n'existe plus (verdicts jumeaux `qualite`/`statut_communication`) ;
`puissance_moyenne_kva` — grandeur **physique** C15, pas le paramètre contractuel — traverse
le fil pour prixer l'abonnement (#78) ; les énergies arrivent **déjà regroupées** base/HP/HC
(plus de grain `config_cadrans` sur le fil), le détail par registre survivant dans la trace
d'index `releves_utilises`. La direction, la clé `(RSC, mois)`, le déclencheur facturiste et
la clé de **création** create-missing sont inchangés — la politique de **réécriture**, elle,
change (cf. note ci-dessous).*

*Note (juillet 2026, #235) : le §3 amendé —
[ADR-0030](0030-facture-gele-mesure-vivant-regularisation-modele-propre-solde-tampon.md)
décision 1 **unifie** le pull. Le create-missing-only **strict** meurt : un `(RSC, mois)` déjà
amorcé n'est plus systématiquement ignoré, il est désormais évalué par l'**empreinte**
(`source_hash`) — inchangée → rien ne bouge (la protection des corrections manuelles du·de la
facturiste survit, dans le même esprit) ; nouvelle + verdict `réelle`/`estimée` → le mesuré
(l'atterrissage v3) est rafraîchi **en bloc**, y compris sur une Période **facturée** (exemption
chirurgicale du verrou #14, jamais la provision) ; `incalculable`/mois absent du flux → conservé,
signalé. « L'énergie arrivée en retard se reprend par une re-récupération explicite » (fin du §3)
est donc caduc : la reprise est désormais automatique, gardée par l'empreinte. Portée par
`souscription.pull.meta.periodes.service`, deux scopes : `pull` (un mois, crée les manquantes) et
`refresh` (plage de mois, ne crée rien — pour la Régularisation, tranche 4 du PRD #231).*

[ADR-0001](0001-odoo-systeme-ecriture-electricore-api-read-only.md) a tranché la **direction**
(Odoo *tire*, electricore *calcule-et-renvoie*, n'écrit jamais le nouveau module). Cet ADR fixe
le **contrat concret** : endpoints, clé d'idempotence, format du payload, déclencheur,
authentification, erreurs. Il répond au livrable de l'**issue #12** (« format exact des données
de période ») et à l'**issue #4** (accise).

## Décision

1. **Clé d'idempotence `(RSC, mois calendaire)`.** Une *Période* par mois et par RSC ;
   `date_debut`/`date_fin` **tronqués au MES/RES** dans les mois de bornes (d'où `jours` réels,
   abonnement au **prorata**). Pas de découpe infra-mensuelle : la RSC distingue déjà les
   *souscripteur·rice·s* d'un même PDL (passation en cours de mois → deux RSC, deux clés
   distinctes).

2. **Endpoints calcule-et-renvoie (Odoo → electricore).**
   - **GET méta-périodes en masse** : Odoo passe la liste des `(RSC, mois)` **facturables**,
     electricore renvoie les quantités physiques.
   - **POST recompute TURPE ciblé** : prend les **cadrans courants** de la *Période* (parfois
     saisis à la main) **en entrée** et ne renvoie **que** `turpe_fixe`/`turpe_variable` ; il
     **ne touche jamais l'énergie**.
   - (La résolution `id_Affaire → RSC` vit dans
     [ADR-0010](0010-identite-souscription-rsc-cle-id-affaire-amorce.md).)

3. **Déclencheur 100 % facturiste, pas de cron.** Une action « récupérer les périodes du mois »
   lancée à la demande ; elle **ignore silencieusement** les *Souscriptions* non facturables
   (raccordement non effectué / RSC non résolue) — aucune pression sur les raccordements
   inachevés. **Upsert create-missing-only** : un `(RSC, mois)` déjà amorcé n'est **jamais
   réécrit** automatiquement (protège les corrections du·de la *facturiste*). Une *Période*
   **facturée** est gelée
   ([ADR-0007](0007-snapshot-periode-type-verrou-facturation.md)) : toute correction passe par
   une **régularisation**. L'énergie arrivée en retard se reprend par une **re-récupération
   explicite** (écrasement assumé), jamais par le flux automatique.

4. **Payload = physique/réseau uniquement.** Énergie par cadran au grain `config_cadrans`
   ([ADR-0005](0005-granularite-energie-calendrier-comptage.md)), montants **TURPE**
   ([ADR-0002](0002-deux-sources-de-verite-marge-en-analytique.md)), **accise/CTA en montant +
   assiette**, bornes tronquées + `jours`, `config_cadrans`, drapeau `data_complete`. Les
   paramètres **contractuels** (`puissance`, `type_tarif`, `lisse`, `provision_*`,
   `tarif_solidaire`) **ne traversent jamais le fil** : ils sont le *snapshot* d'Odoo
   (« référencer, pas recopier »,
   [ADR-0002](0002-deux-sources-de-verite-marge-en-analytique.md)). electricore lit la puissance
   dans le C15 pour **son** calcul TURPE, sans la renvoyer.

5. **Authentification & erreurs.** API electricore protégée par **`X-API-Key`**, stockée comme
   **secret** Odoo (`ir.config_parameter`), URL configurable. Pull facturiste =
   **skip-and-report par élément** (un `(RSC, mois)` en échec n'avorte pas le lot) ; aucune
   écriture partielle (amorçage transactionnel). **Énergie absente = `null` +
   `data_complete=false`** — distinct de `0` (une vraie mesure) et d'une **erreur de service**.
   Suppression des méthodes d'écriture entrante `create_billing_period` /
   `update_consumption_data` (vestiges Option A,
   [ADR-0001](0001-odoo-systeme-ecriture-electricore-api-read-only.md), AUDIT §5) ;
   `get_souscriptions_by_pdl` re-clé sur la RSC.

## Conséquences

- Retire le cron aveugle `ajouter_periodes_mensuelles` (AUDIT §6) : la troncature vient du C15
  (electricore), pas d'une supposition calendaire.
- electricore expose les deux endpoints ci-dessus (+ la résolution RSC d'[ADR-0010](0010-identite-souscription-rsc-cle-id-affaire-amorce.md)) —
  donnée qu'il calcule déjà (`ContexteMensuel.facturation_mensuelle`).
- **Issue #4** tranchée : l'accise (montant + assiette, par catégorie) est dans le payload,
  calculée par electricore ; Odoo n'en maintient **aucun taux**
  ([ADR-0002](0002-deux-sources-de-verite-marge-en-analytique.md)).
- Le **lecteur analytique** (electricore lisant `souscription.*` en read-only pour la marge) est
  **hors périmètre** de cet ADR — issue dédiée ultérieure.

## Options écartées

- **electricore *upsert* les Périodes (Option A de l'audit)** : déjà écartée par
  [ADR-0001](0001-odoo-systeme-ecriture-electricore-api-read-only.md) (read-only-vers-Odoo).
- **Cron de pull automatique** : réécrirait les brouillons corrigés à la main et mettrait la
  pression sur les raccordements inachevés.
- **Recompute complet sur le bouton** : écraserait les cadrans saisis par le·la *facturiste* —
  d'où le recompute **TURPE seul**.
- **Périodes calées sur le mois plein** (partiels renvoyés par electricore) : casse le prorata et
  la passation de PDL — la **troncature MES/RES au grain mois** est retenue.
- **Envoyer les paramètres contractuels dans le payload** : viole la frontière de propriété
  d'[ADR-0002](0002-deux-sources-de-verite-marge-en-analytique.md).

## Raison

Le·la *facturiste* possède le brouillon (`CONTEXT.md`), electricore possède le calcul physique.
**Create-missing-only** et **recompute TURPE seul** protègent par défaut la saisie manuelle des
cadrans ; `(RSC, mois)` est la clé idempotente naturelle ; le déclenchement manuel colle au
process réel — on facture quand on est prêt, pas quand un cron l'impose.
