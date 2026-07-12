# Le facturé gelé, le mesuré vivant : Régularisation en modèle propre, soldée par tampon de l'énergie facturée

Instruit le chantier régularisation des lissés (#20) — la raison d'être du module — grillé en
session le 2026-07-12. Point de départ : les briques existent (grilles historisées #16, écarts par
cadran, snapshot contractuel, unicité mensuelle scopée), mais le pull est create-missing-only
(ADR-0011) et le verrou de facturation (#14) fige `energie_*` — le « réel » stocké sur une
mensuelle facturée est la photo du pull d'origine, systématiquement périmée dès qu'Enedis raffine.
ADR-0015 avait déjà posé la politique « non facturée → remplacer ; facturée → régularisation » :
le présent ADR réalise la seconde moitié. #19 (facture légale complète) est décroché : la régul
projette le même moteur de composition que la mensuelle et héritera de ses enrichissements.

**Décisions.**

1. **Deux natures de champs sur la Période — le facturé gelé, le mesuré vivant.** Le *facturé*
   (provisions, jours, snapshot contractuel, relevés-justificatifs) reste verrouillé. Le *mesuré*
   — **l'atterrissage réseau v3 complet** : énergies par cadran, verdicts (`qualite`, statut de
   communication), TURPE fixe/variable, CTA, taux d'accise, puissance moyenne, empreinte — devient
   réécrivable **après facturation** (exemption ciblée du verrou), rafraîchi **en bloc** par pull
   frais (jamais d'énergie fraîche sur TURPE périmé), les énergies restant corrigeables à la main
   par le·la facturiste (bouche-trou pendant une régul compris) — electricore fait foi. Règle d'écrasement, **gardée par l'empreinte** : `source_hash` inchangé →
   ne rien toucher (les corrections manuelles survivent à la relecture de données inchangées) ;
   empreinte nouvelle + verdict `réelle`/`estimée` → écraser (y compris une estimation manuelle —
   la meilleure donnée gagne) ; `incalculable` ou mois absent du flux ne réécrit jamais (« je ne
   sais pas » n'écrase pas « je savais ») — la valeur conservée est signalée.

2. **Énergie facturée universelle.** `provision_*` = le facturé, pour tout contrat. Lissé : fixée
   à la création de la Période (provision contractuelle, inchangé). Non lissé : **tamponnée
   `provision := energie` à la création de la facture** — la branche lissé/non-lissé de
   `_quantite_facturee` meurt, on facture toujours la provision. Migration one-shot : backfill
   `provision := energie` sur les non-lissées facturées existantes (sûr : le pull
   create-missing-only ne les a jamais réécrites).

3. **La Régularisation est un modèle propre, pas une Période.** `souscription.regularisation`
   (en-tête : souscription, dates couvertes informatives, relevés frais en justificatif) +
   **lignes typées** (une par grille × cadran : sous-période, Σ écart kWh, prix) dont la facture
   est la **projection** (notes par mois sous chaque ligne). Même motif que la Refacturation
   (ADR-0009) : modèle indépendant rassemblé sur une Facture. Le formulaire en brouillon est la
   surface de review du·de la facturiste (pas de wizard). La Période redevient **purement
   mensuelle** : `type_periode` perd `regularisation`/`ajustement` (jamais portés par une donnée),
   l'index d'unicité partiel (ADR-0020 §2) peut perdre sa clause `WHERE`.

4. **Solde par tampon, pas par fenêtre.** Candidats d'une régul : **tous les mois facturés à
   écart non nul dont le mesuré est connu** (verdict `réelle`/`estimée`) **et non soldés en
   legacy** (état « régularisée » posé par la migration, PRD #207/#208) — aucune fenêtre stockée,
   aucun ancrage. À l'**émission** de la facture de régul (jamais au brouillon) : chaque mensuelle
   couverte reçoit `provision_* += écart facturé` et la trace `regularisation_id`. **Invariant :
   la provision n'évolue que par l'émission d'une facture qui la porte** (création pour le lissé,
   facturation pour le non-lissé, émission d'une régul) — la Période reste la somme exacte de ce
   que ses factures ont porté (historisation raffinée, toujours opposable). Conséquences
   structurelles : idempotence (relancer aussitôt = zéro candidat), re-régul gratuite (un mesuré
   qui bouge fait renaître l'écart), « régul des réels » émergente (une non-lissée rééditée par
   Enedis produit un écart, même circuit), régul enjambante de la migration sans code spécial —
   articulée avec le PRD #207 (qui renverse ADR-0023 §3) : les mois soldés en prod portent l'état
   « régularisée » migré et sont exclus ; les Périodes historiques deviennent candidates dès
   qu'un mesuré est connu (capté à la migration #213, ou rafraîchi ensuite). Chaque écart mensuel est valorisé à la grille de **son** mois
   (sélection par date, ADR-0029) ; lignes de facture groupées par grille × cadran. Net négatif →
   avoir. **v1 scopée aux compteurs communicants** ; les ~25 non-communicants relèvent d'un autre
   processus (l'heuristique prod « prix le moins cher » meurt avec la ventilation aux prix réels).

5. **Liens : deux m2o concrets, pas de référence polymorphe.** `account.move.regularisation_id`
   parallèle à `periode_id` (contrainte : jamais les deux) — amende ADR-0004 en « toute facture
   d'énergie référence sa source : une Période *ou* une Régularisation ». `souscription.releve.periode_id`
   devient optionnel, second parent `regularisation_id` (contrainte : exactement un). Une
   `fields.Reference` n'aurait ni FK ni inverse `one2many` — or `facture_id` et le justificatif
   QWeb reposent sur ces inverses.

## Options écartées

- **Sommer les `ecart_*` stockés** : périmés par construction (verrou + create-missing-only).
- **Versionner les mesures / dupliquer les périodes** : tripwire d'ADR-0015 non atteint — les
  relevés frais vivent sur la Régularisation, jamais deux jeux simultanés par Période.
- **Fenêtres chaînées `[début, fin]`** : ancrage requis pour 823 contrats migrés sans régul
  antérieure ; un mesuré raffiné après solde resterait à jamais non soldable.
- **Période de régularisation** : porte-énergie → double comptage avec le tampon (Σ provisions
  compterait chaque écart deux fois) ; porte-document → champs mensuels morts affichés parmi les
  mensuelles.
- **N périodes de régul (une par fenêtre de grille)** : ADR-0004 imposerait N factures au
  souscripteur pour une seule régul.
- **Référence polymorphe `source_type`/`source_id` sur le move** : pas de FK, pas d'inverse,
  abstraction pour deux cas.
- **Blocage dur sur mois `incalculable` dans les candidats** : l'humain décide (ADR-0014) ; la
  régul part « au mieux du connu », mois conservés signalés.

## Conséquences

- Verrou #14 amendé (ADR-0006/0007) : exemption `energie_*`/`qualite` ; la provision reste
  verrouillée contre pull et édition, mue par le seul tampon d'émission.
- Le pull est **unifié** (amende ADR-0011, dont le create-missing-only strict meurt) : une seule
  mécanique gardée par l'empreinte (cf. décision 1), portée par le **propriétaire durable du
  pull** — service extrait du wizard transient (carte de la revue d'architecture du 2026-07-12,
  jamais tirée), prérequis du chantier. Deux scopes sur le même service : pull de facturation
  (un mois, crée les Périodes manquantes) et refresh de régularisation (tous les mois de la
  souscription, ne crée rien). Sur une Période **non facturée**, l'empreinte nouvelle remplace
  aussi les relevés en bloc — le re-pull promis par ADR-0015 est enfin réalisé, la dette
  s'éteint. Aucun canal n'écrit jamais la provision. Le wizard peut se dissoudre en action mince.
- L'estimation des provisions au raccordement est une **lecture** electricore (ADR-0001 : Odoo ne
  pousse rien) — aucune friction avec les pulls unifiés. Suivi humain à ouvrir séparément :
  réviser la mensualité d'un lissé après une grosse régul (philosophie partagée par l'épique
  electricore #191 : « adapter les provisions plutôt que subir la régularisation »).
- **Articulation electricore** : l'épique amont #191 (régularisation) fixe la même frontière —
  electricore livre des **quantités**, la valorisation aux prix fournisseur est déférée à l'ERP —
  et attend précisément la modélisation Odoo du « déjà-régularisé » que cet ADR fournit (tampon +
  trace + modèle Régularisation ; après tampon, la provision d'un mois **est** le facturé total du
  mois, ce que sa future « lecture Odoo du facturé » consommera tel quel). Convergence possible
  plus tard vers son contrat de solde ventilé sans changer le modèle Odoo. Le calculateur sans
  état `POST /facturation/turpe-variable` (electricore #247, livré) permet de re-dériver le TURPE
  variable d'énergies corrigées — utile pour la marge et #19, non requis pour facturer la régul.
  La correction d'**assiette accise** des trimestres soldés (périmètre #191) se suit avec #19.
- Portail : les factures de régul émises doivent remonter (le chemin actuel ne liste que les
  Périodes) — dans le périmètre du chantier.
- UX notée pour plus tard : restituer la temporalité mensuelles/réguls côté facturiste et portail
  (piste : `group_by regularisation_id` sur la liste des périodes). L'en-tête de groupe doit être
  **customisable** — texte parlant + référence de la facture de régul. Levier paresseux : l'en-tête
  d'un group_by affiche le `display_name` du m2o → un `_compute_display_name` sur la Régularisation
  (dates couvertes + référence facture) fait l'essentiel ; le **lien cliquable** dans l'en-tête
  n'est pas natif en vue liste Odoo, à vérifier au moment de l'UI (widget ou bouton de ligne en
  repli).
- Tests : `test_periode_mois` s'ajuste (unicité totale) ; scénarios d'acceptation de #20 couverts
  par le nouveau modèle.
- Communication souscripteur·rices : premières réguls potentiellement grosses (ADR-0023, plusieurs
  mois d'écarts).
- CONTEXT.md : entrées *Période* (facturé/mesuré), *Énergie facturée* et *Régularisation (solde)*
  mises à jour en session.
