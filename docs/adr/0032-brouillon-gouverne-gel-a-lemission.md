# Le brouillon gouverne : pré-facture rejetée, l'émission est l'unique événement de gel

Instruit le chantier « Brouillon gouverné, gel à l'émission » (PRD #264, grillé le
2026-07-13), tranche 3 (#267) — pivot du chantier ouvert par la tranche 1 (#265,
imputation du chèque énergie déplacée à l'émission) et la tranche 2 (#266, provenance des
lignes générées + re-génération préservante à l'émission). Ces deux tranches avaient déjà
déplacé des effets vers l'émission sans re-trancher la question de fond : **où vit l'espace
d'édition du·de la facturiste avant que la facture ne devienne définitive ?**

## Le détour envisagé : une pré-facture

Avant cette tranche, l'hypothèse de travail — jamais actée, mais latente dans le vocabulaire
du PRD #264 (« brouillon gouverné ») — était qu'il fallait peut-être un **objet intermédiaire
propre**, distinct de l'`account.move` : une « pré-facture » `souscription.*` qui porterait
les lignes candidates, resterait éditable sans contrainte comptable, et ne se transformerait
en `account.move` qu'au moment de la facturation réelle. Motivation apparente : garder
`account.move`/`account.move.line` — la table la plus chaude d'Odoo, cf.
[ADR-0014](0014-pas-de-verrou-lignes-facture-confiance-facturiste.md) — à l'écart de toute
mécanique métier tant que rien n'est sûr.

Cette hypothèse a été **instruite puis rejetée**, sur deux fronts.

**1. Le brouillon `account.move` EST déjà l'espace intermédiaire — Odoo ne distingue pas
« facture candidate » de « facture ».** Le cycle de vie natif d'`account.move`
(`draft → posted → cancel`) porte *par construction* la sémantique voulue : un document en
`draft` n'a **aucune valeur comptable** (pas d'écriture générée, pas de numéro de séquence
définitif, librement éditable — lignes, montants, partenaire) ; il ne devient opposable qu'à
`action_post()`. C'est l'idiome que ce module utilise déjà **ailleurs**, sans jamais
l'avoir nommé : `souscription.periode._creer_facture()` crée le move en **brouillon**
délibérément — son docstring le rapproche explicitement de `sale.order._create_invoices`,
qui produit lui aussi des factures en brouillon destinées à être **revues avant validation**
(idiome standard du module Ventes : une commande confirmée crée une facture brouillon,
jamais postée automatiquement). Le module Abonnements standard qu'on remplace
(`CLAUDE.md` : « Why Replace Odoo's Subscription Module ») suit le même schéma récurrent :
génération périodique de factures **brouillon**, review humaine, validation en lot. Aucun de
ces flux ne connaît de « pré-facture » : le brouillon `account.move` **est** la pré-facture.
Chercher un second objet aurait dupliqué une machine à états qu'Odoo fournit déjà, pour lui
faire porter *exactement* la même sémantique (éditable / figé) sous un autre nom.

**2. Aucun vertical de l'écosystème (OCA, Enterprise) ne modélise de pré-facture.** Les
modules de facturation récurrente (`sale_subscription` côté Enterprise, les vues « Factures
à venir » d'Odoo Accounting) créent des `account.move` en brouillon à l'échéance, jamais un
objet intermédiaire distinct — le motif « brouillons en masse → review → post en lot » est
l'action de groupe native sur les listes de factures (sélection multi-lignes, bouton
« Valider »), pas un module séparé. Les verticaux métier qui ont *vraiment* besoin d'un
calcul intermédiaire complexe avant facturation (immobilier, énergie, assurance —
architectures à connecteur externe) le placent **hors** d'Odoo, dans le système source de
vérité métier, et ne poussent que le résultat prêt à facturer. C'est exactement notre
architecture : electricore calcule (énergies, TURPE, accise), la Période/la Régularisation
portent le résultat typé côté Odoo (ADR-0001, ADR-0006, ADR-0030), et **c'est cette
Période/Régularisation qui joue le rôle de « pré-facture »** — pas un nouvel objet, un rôle
déjà tenu par des modèles qui existaient avant ce chantier. Ajouter une pré-facture
`account.move`-like aurait été le troisième système à porter la même information (Période +
pré-facture + Facture), sans qu'aucun des deux precedents (interne ou écosystème) ne le
justifie.

## Décisions

1. **Le brouillon `account.move` est l'espace d'édition — aucune deuxième couche.** La
   Période (ou la Régularisation) reste la source analytique typée (ADR-0002, ADR-0006,
   ADR-0030) ; le brouillon de Facture en est la **projection éditable**, régénérée au fil de
   l'eau (#267, points d'entrée : refresh du pull, édition d'une Période non gelée, sync F15,
   recalcul de Régularisation — cf. `account.move._recomposer_lignes_generees` et ses
   appelants). Les lignes **générées** restent un miroir readonly de la source (provenance
   posée par la composition, ADR-0014 amendé, #266) ; les lignes **manuelles** (geste
   commercial en euros) survivent à toute régénération.

2. **L'émission est l'unique événement de gel.** `account.move._post()` regroupe, dans
   l'ordre : tampon de provision pour un contrat non lissé (ou la Période de clôture d'un
   lissé, ADR-0030 décision 2/ADR-0031 décision 4) → re-génération finale des lignes → post
   → verrou (dérivé) de la Période et des Relevés → solde de Régularisation (ADR-0030
   décision 4) → imputation du chèque énergie (ADR-0026, #265). Rien de tout cela ne se
   produit avant. Contrainte dure qui confirme ce choix : le lettrage natif d'Odoo (chèque
   énergie, ADR-0026) **exige des écritures postées des deux côtés** — Odoo lève
   littéralement *"You can only register payment for posted journal entries"* si on tente de
   lettrer un brouillon. L'imputation ne pouvait de toute façon pas vivre avant l'émission ;
   ce chantier aligne tout le reste sur cette même frontière plutôt que de la traiter comme
   un cas particulier.

3. **Le verrou de la Période et des Relevés devient une condition dérivée.**
   `souscription.periode._est_facturee_emise()` lit `facture_id.state == 'posted'` (ou
   `facture_legacy_ref`, toujours émise) — amende
   [ADR-0007](0007-snapshot-periode-type-verrou-facturation.md), qui avait explicitement
   écarté cette option en 2026-07 faute, à l'époque, d'un mécanisme de régénération pour
   éviter la dérive silencieuse Facture/Période. Ce mécanisme existe désormais (décision 1) ;
   l'objection tombe. Zéro champ stocké ajouté : la condition se lit à chaque `write()`, dans
   le même esprit que le reste du module (ADR-0025 §2, « signaux dérivés »).

4. **Immuabilité de l'émise : hachage seul, pas de verrou applicatif dur.** Une fois postée,
   la Facture devient définitive par le mécanisme comptable natif que la loi française prévoit
   pour l'anti-fraude — le **hash de séquence** (`restrict_mode_hash_table` sur le journal de
   ventes, un scellement cryptographique chaîné qui rend toute modification a posteriori
   détectable). C'est une **consigne de déploiement**, pas du code : `l10n_fr` ne l'active pas
   par défaut, à activer sur le journal de ventes en production. Ce module ne réimplémente ni
   ne renforce cette garantie — il s'appuie dessus, comme il s'appuie sur le lettrage natif
   (ADR-0026) ou l'immutabilité `posted` (ADR-0014 décision 1). Techniquement, `button_draft()`
   reste possible sur une mensuelle tant que le hash n'est pas activé (il ne l'est ni en test
   ni en démo) — la correction *documentée* après émission passe par un avoir ou une
   régularisation, jamais par une réouverture en brouillon ; le hash de production est ce qui
   rend cette discipline non contournable, pas un `if` applicatif de plus sur la table la plus
   chaude d'Odoo (même raisonnement qu'ADR-0014 décision 2).

5. **Enforcement doux partout, jamais de `write()` surchargé sur `account.move.line`.**
   Inchangé depuis l'amendement #266 d'[ADR-0014](0014-pas-de-verrou-lignes-facture-confiance-facturiste.md) :
   readonly de vue + garde `ondelete` étroite sur les lignes générées, jamais de garde sur le
   `write()` du modèle le plus sollicité d'Odoo. Ce chantier ajoute un verrou (`write()`) sur
   `souscription.periode`, un modèle **propre**, peu sollicité — pas sur `account.move.line`.

6. **Le DAG de campagne à deux étapes est conservé.** « Créer les factures » (brouillon) et
   « Émettre les factures » (post) restent deux étapes distinctes du DAG de la Campagne de
   facturation (ADR-0025) — ce chantier ne les fusionne pas : il rend la première **utile**
   (la fenêtre brouillon devient un vrai espace de review, pas une formalité qui fige déjà
   tout) sans changer la forme du DAG.

## Options écartées

- **Pré-facture `souscription.*` distincte de `account.move`** (voir ci-dessus) : troisième
  système d'information pour la même donnée (Période/Régularisation, pré-facture, Facture),
  sans precedent ni interne ni dans l'écosystème Odoo pour la justifier — la Période/la
  Régularisation jouent déjà ce rôle.
- **Verrou applicatif dur sur `button_draft()`/`unlink()` d'une Facture postée** (au-delà de
  ce qu'`account.move` fait déjà nativement) : dupliquerait le hash de séquence (décision 4)
  avec du code applicatif plus fragile et plus coûteux à maintenir à chaque montée de version
  Odoo — même raisonnement qu'ADR-0014 décision 2 (éviter de combattre les recomputes ORM sur
  le cœur comptable).
- **Fusionner « créer » et « émettre » en une seule étape de campagne** : supprimerait la
  fenêtre de review que ce chantier vient précisément de rendre utile ; le DAG à deux étapes
  (ADR-0025) reste le bon grain.
- **Un second champ stocké pour le verrou** (`periode.gelee`, calculé une fois puis figé) :
  réintroduirait un état à synchroniser à la main à chaque `button_draft()`/re-post,
  exactement le genre de champ que ADR-0025 §2 explique comment éviter — la condition
  dérivée (décision 3) coûte une lecture, pas une resynchronisation.

## Conséquences

- **ADR-0006/0007 amendés** (notes d'amendement datées #267) : le snapshot fait toujours
  autorité, mais ce qui le rend irréversible est désormais l'émission, pas l'existence d'une
  Facture. ADR-0026 amendé (note #265, rétroactive) : le lettrage du chèque énergie était
  déjà décrit au mauvais moment (« à la création ») avant même ce chantier.
- **Aucune migration de données.** La condition dérivée (`facture_id.state == 'posted'`)
  se lit à la volée : les Périodes existantes dont la Facture est restée en brouillon sous
  l'ancien régime sont *de fait* dé-gelées dès le déploiement de ce chantier, sans script —
  vérifié par test (`tests/test_gel_emission.py::TestDegelSansMigration`).
- **Surface de test déplacée** : chaque mécanisme (tampon, verrou, régénération) se teste
  désormais à deux moments (brouillon vs émis) plutôt qu'un seul — la suite en porte la
  trace (`test_periode_composition.py`, `test_periode_snapshot.py`, `test_releve.py`,
  `test_regularisation.py`, `test_pull_meta_periodes.py`, `test_sync_prestations.py`,
  `test_periode_facture.py`, `test_campagne_signaux.py`).
- **CONTEXT.md** (entrées *Facture*, *Période*, *Énergie facturée*, *Relevé*, *Geste
  commercial*) documentait déjà ce régime en amont du grill (#264, session du 2026-07-13) —
  ce chantier l'implémente, il ne le redéfinit pas.
- **FEATURES.md** : REQ-FAC-07/08/12/13 mis à jour pour ne plus encoder « figé/verrouillé à
  la facturation » comme l'ancien moment.

## Amendement (#268) — le geste de hash documenté à part

Décision 4 annonçait la consigne de déploiement sans la détailler. La tranche 4 du chantier
(#268) l'écrit : [`docs/deploiement-inalterabilite.md`](../deploiement-inalterabilite.md)
— le geste exact (Comptabilité → Configuration → Journaux → journal de ventes → Réglages
avancés → « Sécuriser les écritures comptabilisées avec une empreinte »), la vérification
dans le source Odoo que `l10n_fr` ne l'active pas seul, et le mécanisme qui rend le geste
irréversible dès la première écriture postée (`account.journal.write()` refuse de décocher
`restrict_mode_hash_table` dès qu'un `inalterable_hash` existe sur le journal). S'applique
à chaque base qui facture réellement, `souscriptions_prodlocal` comprise — jamais aux bases
de test/démo, qui doivent garder `button_draft()` disponible.
