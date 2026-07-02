# Chaîne de raccordement pilotée par les faits : naissance *en instance*, RSC acquise par poll

[ADR-0010](0010-identite-souscription-rsc-cle-id-affaire-amorce.md) a fait de la RSC la clé
d'articulation de la *Souscription*, acquise en résolvant l'`id_Affaire`, et conditionnait la
facturabilité à une « bascule raccordement effectué » — transition qui n'existe pas dans le
modèle. Le kanban prod (« souscription différée », ~1 000 demandes) montre le process réel,
pensé par et pour les *accueillistes* : deux situations d'entrée (MES F120 / CFNE F130), un
suivi d'affaire aujourd'hui **manuel** sur le portail SGE (le help du champ prod pointe l'écran
de recherche d'affaire), et un abonnement créé **avant** l'effectivité. electricore expose
désormais la résolution batch `POST /facturation/rsc` (contrat figé `docs/contrat-rsc.md` :
un résultat par `id_affaire`, **xor** RSC/motif d'erreur). Cet ADR fixe la chaîne cible
(issue #79).

## Décision

1. **Naissance *en instance*, avant l'effectivité.** La *Souscription* est créée à la
   **validation de l'abonnement** (après le calcul des mensualités, comme en prod), avec
   l'`id_affaire` recopié de la demande. Elle est signée et complète **commercialement** — les
   *conditions particulières* peuvent partir
   ([ADR-0016](0016-documents-contractuels-projection-souscription-consentements-raccordement.md)
   intact) — mais **non facturable** tant que la RSC manque.

2. **État de cycle de vie explicite mais calculé.** Un champ `etat` (selection,
   compute/store) dérivé des faits, jamais inscriptible : **en instance** (RSC absente),
   **en service** (RSC présente), résiliée (date de fin — chantier dédié ultérieur).
   **Facturable ≡ RSC présente** : le pull
   d'[ADR-0011](0011-contrat-pull-facturation-electricore-cle-rsc-mois.md) continue d'ignorer
   les en-instance. Pas d'état saisi = pas de dérive possible entre l'état et le fait.

3. **Acquisition de la RSC par poll quotidien.** Un cron quotidien (calé après l'ingestion des
   flux côté electricore) + une action manuelle « résoudre maintenant » (utile après correction
   d'un `id_affaire`). Cible : les Souscriptions **en instance avec `id_affaire`** — indépendant
   de la demande, donc les souscriptions saisies à la main sont couvertes. Un seul POST batch
   `resoudre_rsc` ; electricore *calcule-et-renvoie*, **Odoo écrit son propre champ**
   ([ADR-0001](0001-odoo-systeme-ecriture-electricore-api-read-only.md) préservé). L'interdit
   de cron d'ADR-0011 ne s'applique pas ici : écriture idempotente d'un champ vide, aucun
   brouillon à écraser, aucune pression — on n'écrit que ce qu'Enedis a confirmé.

4. **Mapping des motifs du contrat RSC.**
   - **Résolue** → RSC écrite, la Souscription passe *en service*, la demande liée avance à
     « En service », trace au chatter.
   - **Connue (X12) sans situation contractuelle C15** → attente silencieuse : c'est l'état
     normal du suivi.
   - **Affaire inconnue** → tolérée **3 jours** après la saisie de l'`id_affaire` (décalage
     d'ingestion X12 : une affaire créée aujourd'hui dans SGE n'y est pas encore), puis alerte
     (typo probable).
   - **Résolution ambiguë** → alerte immédiate (décision humaine).

   Alerte = kanban « bloqué » sur la demande + **une** activité pour l'accueilliste (pas de
   spam quotidien) + motif et date de dernière résolution stockés sur la Souscription.

5. **Étapes pilotées par les faits.** Une étape dont l'entrée est un fait vérifiable ne se
   force pas à la main ; on corrige le **fait**, la carte suit :
   - saisie de l'`id_affaire` → la carte avance seule à « demande SGE en cours »
     (drag-in interdit) ;
   - RSC résolue → « En service » (drag-in interdit) ;
   - échappatoire quand Enedis/electricore déraille : la RSC reste saisissable à la main
     (groupe restreint) — l'état calculé et la carte suivent.

   Les gestes humains restent des drags/boutons : acceptation + IBAN, « Validé sur SGE »
   (automatisable plus tard si le contrat RSC expose un `statut` additif), lancement des
   mensualités, validation de l'abonnement.

6. **Chaîne cible = la chaîne prod, sans F305.** Nouveau → PRO à valider → Accepté et IBAN
   vérifié → { F130 CFNE en cours | F120 MES en cours } → Validé sur SGE → Calcul de
   mensualités → *(naissance)* → En attente Enedis → **En service** (finale, repliée). La
   refonte complète du kanban (branches MES/CFNE, PRO, champs manquants) et l'**estimation
   automatique des provisions** (M023 → flux R67 → endpoint provisions ; electricore
   ADR-0047/0048) sont des chantiers séparés qui s'emboîtent dans cette chaîne.

## Conséquences

- ADR-0010 §3 amendé : la « bascule raccordement effectué » n'est pas une transition
  manuelle — c'est le flip *en instance → en service* produit par l'acquisition de la RSC.
- Nouveaux champs : `id_affaire` (demande + Souscription), `ref_situation_contractuelle`,
  `etat` calculé, motif/date de dernière résolution (Souscription).
- La création des entrées Odoo (partner, banque, Souscription) quitte l'étape finale du kanban
  (`is_close`) pour la validation de l'abonnement ; l'étape finale devient « En service »,
  atteinte par le poll.
- La demande vit jusqu'à « En service » mais reste un intake transitoire : la RSC et l'état
  vivent sur la Souscription, la carte ne fait que refléter.
- Le poll remplace la vérification manuelle des affaires sur le portail SGE.
- `CONTEXT.md` : nouveaux termes *Accueilliste*, *En instance / En service* ; entrée
  *Raccordement* réécrite (la chaîne va jusqu'à « En service », plus jusqu'à « Souscrit »).

## Options écartées

- **Souscription créée seulement à la RSC résolue** : la CP ne pourrait partir qu'à
  l'effectivité, des jours/semaines après la signature — or elle projette la Souscription
  (ADR-0016). L'intention (« rien de facturable sans RSC ») est tenue par l'état calculé.
- **Champ d'état inscriptible** : deux vérités (état vs RSC) qui peuvent diverger, invariants
  à surveiller.
- **Suivi porté par la demande (RSC sur la demande)** : les souscriptions nées hors
  raccordement (migration, saisie manuelle) seraient hors poll ; ADR-0010 met la RSC sur la
  Souscription.
- **Réutiliser `souscription.etat`** : mélangerait le cycle mensuel de facturation
  (À facturer/Facturé) et le cycle de vie.
- **Poll manuel façon ADR-0011** : reproduirait la charge de suivi quotidienne qu'on cherche
  à éliminer ; les raisons anti-cron de 0011 ne s'appliquent pas ici.
- **Forçage d'étape toléré sur les étapes factuelles** : une carte « En service » sans RSC
  redeviendrait possible — le kanban pourrait mentir.
- **Étape kanban « En attente MES » sans naissance anticipée** (demande close à « Souscrit »,
  suivi hors kanban) : le kanban est le tableau de bord réel des accueillistes en prod — le
  suivi doit y être visible.

## Raison

Le kanban est le tableau de bord des accueillistes ; l'automatisation ne le remplace pas, elle
remplace la **vérification manuelle sur SGE** par un fait poll-able. Les étapes deviennent des
projections de faits — elles ne mentent jamais. La Souscription naît quand elle est complète
**commercialement** (signature, provisions estimées) et devient facturable quand le **réseau**
la confirme (RSC) — correction avant automatisation, comme ADR-0010 : on ne facture jamais sur
une identité douteuse.
