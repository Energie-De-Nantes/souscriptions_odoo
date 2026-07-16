# Campagne : les étapes lourdes passent en tâche de fond — l'étape persiste une intention, `ir.cron` natif vidange

*Statut : accepté. Instruit le PRD **#324** (« étapes de campagne en tâche de fond »), tranche
`docs` (#325) d'une pile linéaire à trois tranches — #326 câble le mécanisme sur
`emettre_factures`, #327 y ajoute `creer_factures`. Cet ADR fixe l'architecture avant que le
code n'atterrisse, comme ADR 0025 l'avait fait pour la Campagne elle-même. Ne re-décide ni la
forme DAG-rollup ni la porte à la maille campagne (ADR 0025) : il décide **comment une étape
lourde s'exécute** sans bloquer la requête HTTP qui l'a demandée, et amende ADR 0025 en
conséquence. CONTEXT.md (« Campagne de facturation ») est mis à jour par ce même changement.*

## Le déclencheur : une mesure, pas une intuition

`action_emettre_factures` a été tuée par `limit_time_real` (120 s) après 161 s sur 810
factures — `cursor already closed`. Le réflexe aurait été de chercher un bug. La mesure dit
autre chose : ce n'est **pas** un bug de code, c'est un temps de travail qui a dépassé la
fenêtre d'une requête synchrone. Mesuré sur le parc réel (928 souscriptions, 810 factures de
juin 2026), via l'API electricore réelle, en `odoo shell`, chaque étape isolée puis rollback :

| Étape | Mesuré | À 5 000 |
|---|---|---|
| `pull_sorties_c15` | 2,1 s (2,0 s réseau en 1 RPC, 0,1 s d'écriture) | ~11 s |
| `pull_meta_periodes` | 3,2 s | ~20 s |
| `sync_f15` | 9,3 s | ~50 s |
| `creer_factures` | 81 s | ~500 s |
| `emettre_factures` | 161 s → tuée à 120 s | ~420 s |

**Réserve sur `pull_meta_periodes` : la mesure est faite sur un rafraîchissement, pas une
création à froid.** Une campagne qui s'amorce (premier pull du mois) peut coûter nettement
plus cher qu'un second appel qui ne fait que rapprocher l'existant — non mesuré ici, faute
d'avoir eu l'occasion de monter une campagne à froid pendant la fenêtre de mesure. À vérifier
le jour où ce cas se présente ; si le coût à froid est très supérieur, l'étape rejoint le
harnais décrit plus bas.

Horizon de dimensionnement voulu : **5 000 souscriptions**. À cette échelle, quatre des six
étapes proportionnelles au parc sont **innocentées par la mesure** (11 à 50 s) — seules
`creer_factures` et `emettre_factures` sortent du budget d'une requête HTTP.

### D'où vient le coût — et pourquoi ce n'est pas le métier

Décomposée, la composition des lignes d'une facture — tout le métier : *Grille de prix*, prix,
cadrans, refacturations — coûte **1,2 ms**, soit **1,4 %** du temps total par facture. Le
reste est la **resynchronisation des lignes d'`account`**, repayée **1 620 fois pour 810
factures** (une fois à la création du brouillon, une fois à l'émission). Le `_post` natif
d'Odoo traite un lot en **7,7 ms par facture** ; notre recomposition en coûte **~88 ms** —
**92 % du coût est notre boucle, pas le natif**. Le problème n'est pas la richesse du calcul
métier, c'est le nombre de fois où le framework resynchronise autour de lui.

## Décision

1. **L'étape persiste une intention, pas un avancement.** Le bouton **demande**, il ne
   **fait** plus. Le succès se lit ailleurs — dans le **reste-à-faire dérivé**, comme le veut
   déjà ADR 0025 (§2 : la Campagne ne porte que des signaux dérivés ou des portes, jamais un
   drapeau d'avancement métier). Un clic qui déclenchait un traitement synchrone de bout en
   bout ne peut plus, à 5 000 souscriptions, garantir avoir fini avant que la page ne
   réponde ; il ne doit donc plus prétendre l'avoir fait.

2. **La vidange s'appuie sur l'API de progression native d'`ir.cron` (Odoo 17+) : un paquet
   par appel, `_commit_progress`, replanification ASAP tant qu'il reste du travail. Aucune
   file de jobs, aucune dépendance ajoutée.** La méthode ne boucle pas — c'est `_run_job` qui
   la rappelle. Art antérieur : `account.move._autopost_draft_entries`, que le module cite
   déjà comme modèle pour son repli par facture (#268, REQ-FAC-19) ; ce chantier réutilise le
   même mécanisme natif pour l'étalement dans le temps, pas seulement pour l'isolation des
   erreurs. Aucune brique tierce (Celery, RQ, `queue_job` OCA) là où le cœur d'Odoo suffit
   déjà.

3. **Règle d'arrêt « pas de progrès » : une passe qui ne traite aucune unité retombe
   l'intention.** Seul écart au comportement natif, qui replanifierait ASAP indéfiniment sur
   un échec permanent — une *Grille de prix* manquante ne se répare pas toute seule entre deux
   passes du cron. Sans cette garde, le harnais retenterait le même paquet en boucle serrée,
   consommant des workers pour un travail qui ne peut pas aboutir tant qu'un humain n'a pas
   corrigé la donnée en cause.

4. **La liste de travail n'est pas `_reste_a_faire`.** Deux concepts distincts : `_reste_a_faire`
   répond « à quelle distance de la cible du DAG suis-je ? » (sémantique de **porte**, ADR
   0025) ; la liste de travail répond « que dois-je traiter au prochain paquet ? » (sémantique
   d'**avancement du cron**). `_reste_a_faire` ne bouge pas — elle reste la lecture d'état du
   DAG, consommée par l'affichage et les autres étapes ; mélanger les deux aurait fait porter à
   la porte du DAG une responsabilité de pagination qui n'est pas la sienne.

5. **Le travail s'exécute sous l'identité du·de la Facturiste demandeur·se.** Un acte
   comptable porte un nom d'humain — propriété que le module tient depuis ADR 0025 (le DAG
   « rejouable par un automate » ne veut pas dire anonyme). Le cron s'exécute
   `with_user(demande_par_id)`, jamais sous l'utilisateur technique du cron : les écritures que
   la vidange produit doivent rester attribuables à la personne qui a cliqué, exactement comme
   si elle avait cliqué facture par facture.

6. **La cause d'un échec va au chatter de l'enregistrement fautif, pas sur la Campagne.** La
   Campagne reste une fine couche d'orchestration (ADR 0025) : elle n'accumule pas un journal
   d'erreurs qui la transformerait en modèle métier à elle seule. La souscription, la période
   ou la facture en cause porte la trace de ce qui a coincé — au même endroit où le·la
   Facturiste ira de toute façon la corriger.

## Options écartées

- **Optimiser la boucle plutôt que la sortir de la requête.** Brancher tout le lot sur le
  container de synchronisation d'`account` (celui que le `_post` en lot utilise déjà) donne un
  gain réel mais insuffisant : **1,8×** (83 → 48 ms/facture, soit 417 → 238 s à 5 000).
  Toujours le double du budget d'une requête HTTP : ça ne change pas de **classe** le problème,
  seulement sa constante — et en tâche de fond, personne ne distingue 4 minutes de 7 minutes.
  Chiffré et écarté ici pour ne pas être re-proposé dans six mois comme s'il n'avait jamais été
  mesuré.
- **Faire passer les six étapes proportionnelles au parc par le même harnais.** Quatre d'entre
  elles sont **innocentées par la mesure** (11 à 50 s à 5 000 souscriptions) — les faire
  transiter par un mécanisme de paquets/replanification serait de la complexité pour un
  problème que la mesure dit ne pas exister. Seules `creer_factures` et `emettre_factures`
  rejoignent le harnais dans cette pile (#326, #327) ; `sync_f15` et `pull_sorties_c15`
  n'y entrent que « quand un chiffre le demandera, pas avant ».
- **Un compteur de tentatives.** C'est l'état de progression qu'on refuse d'inventer : la
  liste de travail (décision 4) et la règle d'arrêt (décision 3) suffisent à borner le
  comportement sans persister un nombre d'essais par unité.
- **Une classification transitoire/permanent des exceptions.** Séduisante en théorie, dangereuse
  en pratique : la première exception mal classée boucle indéfiniment (classée transitoire à
  tort) ou abandonne un travail qui aurait fini par passer (classée permanente à tort). La
  règle « pas de progrès » (décision 3) obtient le même effet protecteur sans avoir à deviner
  la nature de chaque exception possible.
- **`mail.thread` sur la Campagne.** Aurait donné à la Campagne elle-même un journal
  d'activité — redondant avec la décision 6 : ses enregistrements (souscription, période,
  facture) racontent déjà mieux l'échec que la Campagne ne pourrait le faire depuis son
  survol mensuel.

## Conséquences

- Aucune dépendance ajoutée au manifest : `ir.cron` et son API de progression sont du cœur
  Odoo 17+, déjà présents dans Odoo 19.
- Le champ `lance` (catalogue `ETAPES_CAMPAGNE`, type `action`) change de sens pour les étapes
  vidées en tâche de fond : il note désormais qu'un traitement a été **demandé**, jamais qu'il
  est **terminé** — cf. l'amendement à ADR 0025 ci-dessous.
- Le mécanisme lui-même (modèle du paquet, câblage du `_trigger()`, écriture de la liste de
  travail) est hors du périmètre de cette tranche : il atterrit avec `emettre_factures` (#326)
  puis `creer_factures` (#327), sur la base architecturale posée ici.
- FEATURES.md n'est pas modifié par cette tranche : aucune REQ existante ne décrit un
  comportement d'émission *synchrone* qu'il faudrait corriger — REQ-FAC-19 documente déjà le
  repli par facture façon `_autopost_draft_entries`, qui reste vrai à l'échelle du paquet.

## Amendement à ADR 0025 — le cron est l'automate que la décision 3 attendait

ADR 0025 §Décision 3 anticipait : *« Le DAG est pensé rejouable par un automate […] sans
distinguer un parcours humain d'un parcours automatisé »*. Cet ADR **exploite** cette
propriété, il ne la contredit pas : le cron `ir.cron` qui vidange `creer_factures` et
`emettre_factures` en tâche de fond **est** l'automate qu'ADR 0025 avait déjà prévu de pouvoir
parcourir le même DAG. Rien dans la forme DAG-rollup ne change ; ce qui change est **qui**
relit le catalogue `ETAPES_CAMPAGNE` entre deux clics — parfois un humain qui revient sur la
page, parfois un cron qui se replanifie lui-même.

**Ce que cela précise, et qui n'était pas explicite en 2026-07** : pour une étape de type
`action` dont le lancement déclenche un traitement qui peut dépasser la durée d'une requête,
`lance` **devient une intention posée au clic** — « demandé » — et non plus un accompli. Le
`fait` d'une telle étape ne se lit donc plus sur `lance` seul : il se lit, comme pour toute
étape `derive`, dans le **reste-à-faire dérivé** qui existe déjà pour elle
(`creer_factures`/`emettre_factures` sont de type `derive` depuis l'origine — leur `fait` a
toujours été `nb_reste_a_faire == 0`, jamais `lance`). L'amendement généralise donc, pour toute
future étape `action` qui rejoindrait le harnais, la règle déjà vraie de fait pour ces deux-là :
**demander n'est pas terminer**, et seul un signal dérivé des données peut affirmer qu'une étape
est faite. Une étape `action` qui ne dispose d'aucun signal dérivé (`sync_f15`,
`pull_sorties_c15` aujourd'hui) et qui rejoindrait un jour le harnais devrait donc, à ce
moment-là, s'en doter — `lance` seul ne suffira plus à répondre « fait ».

Ce raisonnement n'ouvre pas une nouvelle porte de vérification (ADR 0025 §2 reste entier :
zéro champ de vérification sur `souscription.periode`/`souscription.refacturation`) — il
précise seulement la lecture d'un champ déjà existant (`lance`) le jour où son lancement cesse
d'être instantané.
