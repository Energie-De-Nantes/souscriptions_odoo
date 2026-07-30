# Les mails

## En deux mots

À chaque moment important de la vie d'un contrat, un mail part tout seul : quand la demande
de fourniture est vraiment lancée, quand le raccordement aboutit, quand une facture ou un
remboursement est émis. L'équipe garde la main sur les mots qui changent — la lettre du
mois, les textes d'accompagnement — pendant que le code garde les chiffres : montants,
numéros de facture et instructions de paiement ne peuvent plus être cassés par une faute de
frappe un vendredi soir.

## Le geste au quotidien

### Pendant le raccordement : deux mails de rassurage

Quand une demande quitte l'accueil et part réellement chez le gestionnaire de réseau
(Enedis), la carte entre dans une des deux colonnes d'attente du kanban de raccordement :
« ⏳ Mise en Service (F120) en cours » (emménagement, compteur hors service) ou
« ⏳ Changement de fournisseur (F130) en cours » (compteur déjà alimenté). À cette entrée,
le·la futur·e souscripteur·rice reçoit automatiquement un accusé de prise en compte :
« Votre emménagement est bien enregistré » ou « Votre changement de fournisseur est bien
enregistré ». Personne n'a de bouton à cliquer — c'est le déplacement de la carte qui envoie.
Voir [raccordement](raccordement.md) pour le détail du kanban.

### Le pack de bienvenue

Quand la carte atteint « ✓ Abonnement Validé », le pack de bienvenue part automatiquement,
dans la variante adaptée à la personne : particulier, professionnel ou tarif solidaire. Il
emporte en pièce jointe le PDF des Conditions particulières — le récapitulatif du contrat :
prix engagés, consentements, mensualités (voir [contrat](contrat.md)). Ces trois modèles de bienvenue
sont personnalisables par l'équipe et ne sont jamais écrasés par une mise à jour du module.

### La lettre du mois

Le mail qui accompagne les factures mensuelles porte, en plus des faits de facturation, un
éditorial : prochaines dates, permanences, tarif solidaire, appels à bénévoles. Cet
éditorial, c'est la **lettre du mois**, et elle vit sur la Campagne de facturation : fiche
Campagne, onglet « Lettre du mois ».

Le geste mensuel : à la création de la campagne, la lettre arrive **pré-remplie avec celle
du mois précédent**. Le·la facturiste l'ouvre, change les dates, retire ce qui est périmé,
ajoute le mot du mois — puis valide la porte « Mot du mois » sur le tableau de bord de la
campagne. Pas besoin d'un·e développeur·euse pour changer un horaire de permanence : c'est
un champ de texte riche, sous votre main.

### L'envoi des factures

L'envoi est une étape de la campagne comme les autres : « Envoyer factures », dans la phase
Facturer (voir [facturer](facturer.md)). Elle ne s'ouvre que quand deux conditions sont remplies :
toutes les factures du mois sont émises, **et** la porte « Mot du mois » est validée. La
campagne ne peut pas envoyer une lettre que personne n'a relue.

Un clic envoie toutes les factures du mois pas encore parties, chacune avec son PDF joint.
Si un envoi échoue (adresse invalide, boîte pleine), l'échec s'inscrit sur la fiche de **la**
facture fautive, sans bloquer les autres : le compteur de reste-à-faire de l'étape garde ces
factures en liste, et le clic suivant ne reprend **que** les échecs — jamais de doublon chez
celles et ceux qui ont déjà reçu leur mail. Un renvoi manuel depuis une facture (« je n'ai
rien reçu ») produit exactement le même mail que l'envoi en masse, lettre comprise.

### Les textes permanents et le QR-code

Menu « Souscriptions → Configuration des mails » : l'écran unique où vivent les textes qui
n'ont pas de rythme mensuel, modifiables avec les droits du module — sans droits
d'administration de la base :

- **Difficultés de paiement (régularisation)** — aides, étalement, « répondez-nous qu'on
  s'arrange », affiché sur les factures de régularisation ;
- **Appel au don (avoir)** — affiché sur les avoirs (voir [regulariser](regulariser.md)) ;
- **Accusé de clôture (résiliation)** — affiché sur la facture de solde de quelqu'un·e qui
  part ;
- **QR-code Moneko** — l'image que vous téléversez pour les payeur·euses en monnaie locale,
  remplaçable le jour où Moneko la réémet.

Un texte vide, c'est un bloc qui n'apparaît pas — jamais de résidu, jamais de texte par
défaut.

!!! question "🤖 À valider avec vous"
    - La lettre du mois porte TOUT l'éditorial du mail de facture — dates, permanences,
      tarif solidaire, bénévoles. Vous la réécrivez chaque mois à partir de celle du mois
      précédent, sans développeur·euse : changer un horaire ne demandera plus jamais un
      déploiement. C'est bien le pouvoir que vous vouliez ?
    - Valider la porte « Mot du mois » avec une lettre VIDE est légitime (« rien à dire ce
      mois-ci ») : la porte valide une décision, pas une écriture. D'accord ?

## Les règles du jeu

**Le mail de facture est unique, et il s'adapte tout seul.** Il n'y a plus de choix manuel
d'un modèle dans une liste : un seul corps de mail sait quoi dire selon la situation. Son
ouverture suit une priorité stricte — **clôture** (« votre résiliation est bien prise en
compte ») avant **avoir** (« voici votre avoir ») avant **facture de régularisation** avant
**facture mensuelle**. C'est ce choix manuel d'autrefois qui a produit la panne fondatrice :
un avoir de 54,25 € — de l'argent qu'on **devait** à l'usager·ère — envoyé sur le modèle
Moneko « payez-nous par QR-code », resté impayé 20 mois. Cette porte est fermée.

**L'instruction de paiement est explicite par mode, jamais par défaut.** Chaque mode de
paiement du contrat a son texte propre, croisé avec la situation : prélèvement × facture
(« le prélèvement interviendra le 10 »), Moneko × facture (QR-code), prélèvement × avoir
(remboursement), Moneko × avoir (remboursement en Moneko). Si le mode de paiement manque sur
la Souscription, **aucun bloc paiement n'apparaît** — le mail n'affirme jamais un moyen de
règlement qu'il ne connaît pas. L'ancien réflexe « en cas de doute, annoncer le
prélèvement » annonçait un prélèvement à des gens sans mandat ; la facture PDF jointe porte
le montant de toute façon. À ce jour, seuls prélèvement et Moneko ont un texte : espèces,
virement et chèque attendent leur rédaction par l'équipe (voir [encaisser](encaisser.md) pour les modes).

**La lettre du mois ne voyage que sur les factures mensuelles.** Une régularisation ou une
clôture ne la porte jamais : une clôture est la facture de quelqu'un·e qui part, la lettre
du mois n'y a pas sa place. À la place, ces mails portent le texte permanent de leur situation.

**Le squelette est en code, et il s'auto-répare.** Salutation, numéro, montant, instruction
de paiement et dates de paiement vivent dans le code du module, relus et testés. Un édit
manuel du modèle de mail dans l'interface est silencieusement écrasé au déploiement suivant
— c'est voulu : c'est la maladie qu'on soigne (le corps du mail de production avait été
cassé à la main). Vous pouvez toujours rater votre lettre ; vous ne pouvez plus jamais
casser un montant. Sur un chemin d'argent, on ne paraphrase pas, on cite.

**Le QR-code Moneko s'affiche, il ne s'affirme pas.** Il apparaît dans le mail seulement —
jamais incrusté dans la facture PDF, qui est immuable. S'il n'est pas téléversé, le mail
n'en parle simplement pas : la marche à suivre dans l'application et l'échéance tiennent
seules.

**L'envoi est gouverné et rattrapable.** Émettre (le gel comptable) et envoyer (la
communication) sont deux étapes distinctes : une adresse mail invalide ne peut jamais faire
échouer l'émission d'un lot. L'étape d'envoi est fermée tant que ses deux conditions —
factures émises, porte « Mot du mois » validée — ne sont pas remplies, et un échec d'envoi
se reprend au clic suivant, facture par facture.

!!! question "🤖 À valider avec vous"
    - Un mail n'affirme jamais un moyen de paiement qu'il ne connaît pas : chaque mode a son
      texte explicite, et si le mode manque, aucun bloc paiement n'apparaît. Cette prudence
      vous convient ? (Point en chantier : beaucoup de contrats migrés n'ont pas encore de
      mode de paiement renseigné — la direction prise est de le rendre obligatoire, comme la
      puissance.)
    - Le QR-code Moneko est une image que VOUS téléversez, affichée dans le mail seulement,
      jamais dans la facture PDF ; absent, le mail n'en parle pas. OK ?
    - Les textes pour espèces, virement et chèque n'existent pas encore : leur rédaction
      vous revient (aucun ancêtre dans les anciens mails). On planifie ça ensemble ?

## Sous le capot

Modèles et code :

- [`models/core/souscription_mail_config.py`](https://github.com/Energie-De-Nantes/souscriptions_odoo/blob/main/models/core/souscription_mail_config.py)
  — `souscription.mail.config` : QR-code Moneko + les trois Textes permanents ; modèle de
  config propre au module (délibérément ni `res.company` ni `res.config.settings`, hors
  d'atteinte du rôle facturiste), enregistrement unique ouvert par le menu.
- [`models/core/souscription_campagne.py`](https://github.com/Energie-De-Nantes/souscriptions_odoo/blob/main/models/core/souscription_campagne.py)
  — champ `lettre_mois` (report M-1 → M via `_reporter_lettre_precedente`), porte
  `mot_du_mois` (type `porte`, racine du DAG), étape `envoyer_factures` (dérivée de
  `is_move_sent`, gate dure, `action_envoyer_factures` délègue à la machinerie native
  `account.move.send` avec `allow_raising=False`).
- [`models/core/account_move.py`](https://github.com/Energie-De-Nantes/souscriptions_odoo/blob/main/models/core/account_move.py)
  — la facture **tire** : computes non stockés `lettre_du_mois`, `qr_moneko_image_url`,
  `is_regularisation_cloture`, textes permanents ; surcharge de `_get_mail_template()`
  (racine unique — envoi de masse et renvoi unitaire passent par elle, avoirs interceptés
  avant le routage core).
- [`data/mail_templates_facture_energie.xml`](https://github.com/Energie-De-Nantes/souscriptions_odoo/blob/main/data/mail_templates_facture_energie.xml)
  — le corps unique à branches (sans `noupdate` : auto-cicatrisant au `-u`) ;
  [`data/mail_templates_raccordement.xml`](https://github.com/Energie-De-Nantes/souscriptions_odoo/blob/main/data/mail_templates_raccordement.xml)
  et [`data/mail_templates_bienvenue.xml`](https://github.com/Energie-De-Nantes/souscriptions_odoo/blob/main/data/mail_templates_bienvenue.xml)
  (ceux-ci `noupdate` : personnalisables).
- [`models/raccordement/raccordement_demande.py`](https://github.com/Energie-De-Nantes/souscriptions_odoo/blob/main/models/raccordement/raccordement_demande.py)
  — `_envoyer_mail_rassurage` (à l'entrée effective d'une branche ⏳, re-routage compris)
  et `_envoyer_pack_bienvenue` (variante par faits : pro / solidaire / particulier).

Décisions :

- [ADR 0034 — La lettre du mois : l'éditorial vit sur la campagne, le squelette transactionnel vit en git](https://github.com/Energie-De-Nantes/souscriptions_odoo/blob/main/docs/adr/0034-lettre-du-mois-editorial-sur-campagne-squelette-en-git.md)
  : qui tient le stylo, pourquoi « aucune branche de repli », le contre-exemple de l'avoir
  Moneko, et l'extension « mails sans mois ».
- [ADR 0022 — Raccordement aligné sur la prod](https://github.com/Energie-De-Nantes/souscriptions_odoo/blob/main/docs/adr/0022-raccordement-aligne-prod-naissance-acceptation-valide-sge-rsc.md)
  : fixe le rassurage à l'entrée SGE et le pack de bienvenue à la validation.
- [ADR 0031 — La fin de souscription gouvernée par le fait C15](https://github.com/Energie-De-Nantes/souscriptions_odoo/blob/main/docs/adr/0031-fin-souscription-gouvernee-fait-c15-sorties-tirees-cloture-campagne.md)
  : les mails automatiques post-résiliation (#92) sont un suivi nommé et différé.

Pendants connus : textes de paiement espèces/virement/chèque (rédaction EDN), invariant
« toute Souscription a un mode de paiement » (chantier migration), mails post-résiliation
(#92).
