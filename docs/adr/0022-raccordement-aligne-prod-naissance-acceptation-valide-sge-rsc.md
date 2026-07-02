# Raccordement aligné sur la prod : naissance à l'acceptation, « Validé sur SGE » par la RSC

[ADR-0021](0021-chaine-raccordement-pilotee-faits-naissance-instance-rsc-poll.md) a fixé la
chaîne de raccordement cible avec une naissance à la validation de l'abonnement et une attente
Enedis *post*-naissance (« En attente Enedis » → « En service »). La ré-exploration de la prod
(étapes, `base.automation`, `mail.template` — session de grill juillet 2026) et un fait métier
tranché par Virgile invalident cette queue de chaîne : **il n'y a pas de RSC sans le C15
d'effectivité de la mise en service**. L'attente Enedis se consomme donc *pendant* le suivi
d'affaire (colonnes F120/F130), pas après la naissance. Par ailleurs la prod n'envoie **rien**
au·à la souscripteur·rice à l'acceptation (le pack contractuel part à la main, après « Validé
sur SGE ») — trou que la cible répare. Cet ADR amende ADR-0021 §1, §5 et §6 ; les §3 (poll) et
§4 (mapping des motifs) restent intacts.

## Décision

1. **Chaîne cible = la chaîne prod, sans F305, avec les deux branches.**
   🔴 Nouveau → 🔴 PRO à valider *(routage auto à la création si `pro`)* → 🔴 Accepté et IBAN
   vérifié *(= naissance)* → ⏳ { Changement de fournisseur (F130) en cours | Mise en Service
   (F120) en cours } *(entrée factuelle : id_Affaire saisi)* → 🔴 Validé sur SGE *(entrée
   factuelle : RSC résolue)* → 🔴 Calcul de mensualités en cours → ✓ Abonnement Validé
   *(terminale, repliée, envoi du pack)*. Les étapes « Demande mesures faite », « Estimation
   mensualité », « Souscrit » et « En service » disparaissent.

2. **Naissance à l'acceptation** *(amende ADR-0021 §1)*. La Souscription est créée **en
   instance** à l'entrée en « Accepté et IBAN vérifié » (geste humain : acceptation — pour les
   PRO, après décision du collège). Justification hors CP : le poll continue de cibler les
   **Souscriptions en instance** (§3 d'ADR-0021 inchangé, pas de suivi côté demande) et le
   journal de consentement (ADR-0017) est horodaté à la capture, pas des semaines après.
   L'`id_affaire`, saisi sur la demande *après* la naissance, se recopie au fil de l'eau sur la
   Souscription (write-through), plus seulement à la création.

3. **« Validé sur SGE » = la RSC est le fait** *(amende ADR-0021 §5)*. Pas de RSC sans C15
   d'effectivité ⇒ RSC résolue ≡ affaire aboutie ≡ « validé sur SGE ». L'auto-move existant
   « RSC acquise → En service » est reciblé vers « Validé sur SGE ». Zéro chantier electricore :
   le contrat RSC actuel (xor RSC/motif) suffit, pas besoin de statut d'affaire additif.

4. **Situation d'entrée (MES F120 / CFNE F130).** Champ de la demande, prérempli par le
   formulaire de souscription, **éditable par l'accueilliste** (l'erreur du demandeur est un cas
   nominal). Il route l'auto-move de l'id_Affaire vers la bonne branche ; sa correction
   re-route la carte déjà en branche (on corrige le fait, la carte suit).

5. **Trichotomie visuelle des colonnes** : 🔴 *action attendue* (orange, liseré de carte),
   ⏳ *attente externe* — le poll travaille (neutre, pas de liseré), ✓ *fait* (vert, colonne
   repliée). Portée par le nom d'étape (préfixe) + la couleur d'étape existante, re-purposée
   (elle était décorative). Pas de champ ni de rendu custom. La progressbar (bloqué = rouge)
   reste le canal des alertes du poll.

6. **Mails.** À l'entrée des colonnes ⏳ (= la demande SGE vient réellement de partir) : mail
   de **rassurage** automatique, un template par branche — répare l'oubli CFNE de la prod. À
   l'entrée en « Abonnement Validé » : **pack de bienvenue** automatique (CP complète — RSC et
   mensualités réelles — + documents d'accueil, variantes particulier/pro/solidaire), là où la
   prod l'envoyait à la main. La CP part **en fin de chaîne, complète** ; le rassurage tient le
   rôle d'accusé de prise en compte.

7. **PRO : le collège valide le pro et son tarif.** La demande capte `coeff_pro` (majoration
   négociée) pendant « PRO à valider » ; la naissance la recopie sur la Souscription.

## Conséquences

- ADR-0021 : §1 (moment de naissance), §5 (« Validé sur SGE » humain) et §6 (queue « En attente
  Enedis → En service ») amendés ; §2 (état calculé), §3 (poll), §4 (motifs) intacts. Une
  Souscription née du raccordement passe toujours par *en instance* ; elle devient *en service*
  pendant que la carte est en branche ⏳.
- Pas de migration : le module du repo n'existe pas en prod (la prod tourne sur le modèle
  Studio `x_souscription_differe`) ; data/demo/tests réécrits dans la même PR.
- Références code à retoucher : `stage_demande_sge` (éclaté en deux branches),
  `stage_en_service`/`stage_souscrit` (supprimés), auto-moves reciblés, heuristiques par nom
  de `_onchange_stage_id` refondues, garde bloquante IBAN valide (si prélèvement) au drag
  d'acceptation.
- `CONTEXT.md` : entrée *Raccordement* réécrite (chaîne jusqu'à « Abonnement Validé »),
  nouveaux termes *Situation d'entrée* et *Collège (PRO)*.

## Options écartées

- **Naissance en fin de chaîne** (modèle prod, « Enregistrement de la souscription » à Validé
  sur SGE) : pendant l'attente F120/F130 la Souscription n'existerait pas — le poll devrait
  cibler les demandes et la RSC vivre sur la demande, ce qu'ADR-0010/0021 ont déjà écarté.
- **CP à l'acceptation avec provisions estimées** : les mensualités réelles exigent les données
  de conso, qui n'arrivent qu'après l'effectivité ; une CP estimée puis corrigée fait deux
  vérités. Le rassurage suffit à l'acceptation, la CP part complète.
- **Statut d'affaire additif exposé par electricore** pour « Validé sur SGE » : sans objet, la
  RSC est déjà le bon fait (pas de RSC sans C15 d'effectivité).
- **Champ `nature` d'étape + rendu kanban custom** pour la trichotomie : préfixe de nom +
  couleur font le même travail sans code ; on ne l'introduira que si le besoin de filtrage
  apparaît.

## Raison

Le kanban reste le tableau de bord des accueillistes : chaque colonne dit qui doit agir —
un humain (🔴), personne (⏳, le poll veille), plus personne (✓). Les étapes restent des
projections de faits (id_Affaire, RSC) qui ne se forcent pas. La naissance anticipée coûte un
déplacement de déclencheur et garde toute la mécanique poll/état déjà mergée ; l'envoi des
documents suit le rythme réel du process — accusé de prise en compte tôt, contrat complet
quand tout est vrai.
