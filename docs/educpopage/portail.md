# Le portail usager·ère

## En deux mots

Chaque souscripteur·rice dispose d'un espace en ligne pour consulter ses contrats,
son historique de consommation, les relevés de son compteur et ses factures.
Il·elle n'y voit que ce qui le·la concerne — jamais les contrats de quelqu'un·e d'autre —
et uniquement des documents définitifs : rien de ce qui est encore en préparation
côté équipe n'y apparaît, jamais.

## Le geste au quotidien

### Ce que voit l'usager·ère en se connectant

Sur sa page d'accueil (`/my`), une carte **Souscriptions** affiche le nombre de ses
contrats. En cliquant, il·elle arrive sur **Mes Souscriptions** (`/my/souscriptions`) :
la liste de ses contrats avec la référence, le PDL (l'identifiant du point de livraison,
celui qui figure sur le compteur), la puissance, le type de tarif (Base ou HP/HC, avec
un badge **Solidaire** le cas échéant) et l'état du contrat — En instance, En service,
En attente de clôture ou Résiliée, le même libellé que celui que voit le·la facturiste
(voir [contrat](contrat.md)). Le bouton **Consulter** ouvre le détail.

### La page de détail d'une souscription

C'est la page centrale (`/my/souscription/<n°>`). Tout y est rassemblé, sans
sous-pages à explorer :

- **Informations** en barre latérale : période contractuelle, mode de paiement.
- **Informations techniques** et **Facturation** : puissance, type de tarif, et pour
  les contrats lissés la provision mensuelle en kWh.
- **Historique des consommations** : un tableau mois par mois — l'énergie facturée
  (colonne Base, ou colonnes HP et HC selon le contrat, avec la provision en
  dessous quand il y en a une), le TURPE fixe et variable, le montant TTC, le statut
  de paiement (Payée / Partielle / Impayée) et le lien vers la facture. Les douze
  derniers mois s'affichent, un bouton **Voir plus** déplie le reste.
- **Justificatif — relevés d'index utilisés** : pour chaque mois affiché, tous les
  index qui ont servi au calcul de la consommation, datés, par cadran de comptage,
  chacun étiqueté **Réel** ou **Estimé**. L'usager·ère peut les comparer aux index
  affichés sur son compteur et refaire le calcul — ce sont les mêmes relevés que
  ceux imprimés sur sa facture.
- **Totaux** (consommation totale, TURPE total, total facturé) et un encart
  **Informations** qui explique les sigles (TURPE, HP/HC) et, pour les contrats
  lissés, le principe de la régularisation.
- **Factures de régularisation** : une section propre qui liste les régularisations
  émises — période couverte, montant, statut de paiement, lien vers la facture
  (voir [regulariser](regulariser.md)).

### Les factures elles-mêmes

Chaque ligne de l'historique renvoie vers la facture sur le portail de facturation
(`/my/invoices`) : l'usager·ère la consulte en ligne et la télécharge en PDF, avec
son statut de paiement. C'est **exactement le même document** que le PDF reçu par
mail à l'émission — même design, même justificatif des relevés (voir [facture](facture.md)).
Il n'existe qu'une seule mise en forme de facture, quel que soit le chemin par
lequel on la regarde.

### Côté facturiste : le bouton « Aperçu portail »

Sur la fiche d'une Souscription, le bouton **Aperçu portail** ouvre la page
exactement comme l'usager·ère la voit, via un lien signé — sans avoir à se
connecter à sa place ni à connaître son mot de passe. C'est le bon réflexe avant de
répondre à un appel : « je regarde votre espace avec vous ».

À noter : l'accès portail est ouvert automatiquement (avec un mail d'invitation)
quand la Souscription naît d'une demande de raccordement (voir [raccordement](raccordement.md)).
Pour un contrat créé autrement, l'invitation se fait à la main.

!!! question "🤖 À valider avec vous"
    - L'historique des consommations est présenté directement dans la page du contrat, sans espace séparé à explorer — un espace pensé sobre et en lecture (on évite le vocabulaire « espace client »). Ce parti pris de simplicité vous convient-il ?
    - Le justificatif des relevés (tous les index utilisés, les estimés étiquetés comme tels) est visible en ligne : l'usager·ère peut refaire le calcul de sa consommation. On l'assume comme un droit de vérification, pas comme un bonus — d'accord pour le dire publiquement ?

## Les règles du jeu

### Chacun·e chez soi : le cloisonnement

Un·e usager·ère ne voit que **ses** souscriptions. Taper dans la barre d'adresse le
numéro du contrat de quelqu'un·e d'autre renvoie un refus d'accès. Cette étanchéité
n'est pas une promesse : elle est vérifiée par des tests automatiques qui rejouent
précisément ce scénario à chaque évolution du logiciel.

### Seul l'émis est visible — jamais un brouillon

Le portail applique la même frontière que toute la facturation (voir [facture](facture.md)) :

- Un mois n'apparaît dans l'historique **que lorsque sa facture est émise**. Une
  facture en préparation, même complète et prête à partir, reste invisible jusqu'à
  son émission.
- Les relevés d'index suivent la même règle : seuls ceux d'un mois émis
  s'affichent dans le justificatif.
- Les factures de régularisation aussi : une régularisation en cours de préparation
  ne fuite jamais ; elle apparaît le jour où sa facture est émise.

Conséquence pratique pour l'équipe : le brouillon est un espace de travail sûr. On
peut y corriger, refaire, annuler — l'usager·ère ne verra jamais un montant
provisoire ni un document qui change sous ses yeux.

### Ce que le portail montre — et ce qu'il ne montre pas encore

Le portail reflète l'état du contrat (les quatre états de vie, y compris En attente
de clôture et Résiliée) et le facturé gelé de chaque mois. En chantier, avec leur
propre calendrier :

- **Les avoirs** n'ont pas encore de présentation dédiée, ni le visuel croisé
  « telle régularisation solde tels mois » — c'est une évolution identifiée, à
  concevoir avec sa propre décision d'architecture.
- **Le retrait du consentement** aux données de consommation depuis le portail :
  chantier distinct annoncé, c'est un droit qui aura son écran (voir [consentement](consentement.md)).
- **La saisie du chèque énergie** par l'usager·ère : tranche prévue, séparée par
  conception de la comptabilité (voir [encaisser](encaisser.md)).

!!! question "🤖 À valider avec vous"
    - Un mois n'apparaît au portail que quand sa facture est émise : une facture en préparation, même prête, reste invisible pour l'usager·ère jusqu'à l'émission. C'est bien la règle voulue, sans exception ?

## Sous le capot

Modèles et code :

- Routes portail : [`controllers/portal.py`](https://github.com/Energie-De-Nantes/souscriptions_odoo/blob/main/controllers/portal.py) — filtre `facture_id.state == 'posted'` sur périodes et régularisations : la règle « seul l'émis est visible » vit dans le contrôleur.
- Gabarits : [`views/portal_templates.xml`](https://github.com/Energie-De-Nantes/souscriptions_odoo/blob/main/views/portal_templates.xml) — liste, page de détail, justificatif des relevés, section régularisations.
- [`models/core/souscription.py`](https://github.com/Energie-De-Nantes/souscriptions_odoo/blob/main/models/core/souscription.py) — `_compute_access_url` (portal.mixin), `action_apercu_portail` (URL signée par access_token), `_octroyer_acces_portail` (invitation à la naissance depuis le raccordement, idempotente).
- [`models/core/account_move.py`](https://github.com/Energie-De-Nantes/souscriptions_odoo/blob/main/models/core/account_move.py) — `_get_name_invoice_report` : porte unique du design de facture d'énergie ; portail, PDF mail et Imprimer traversent le même report.
- Tests : [`tests/test_portal.py`](https://github.com/Energie-De-Nantes/souscriptions_odoo/blob/main/tests/test_portal.py) — cloisonnement entre usagers (403), non-fuite des brouillons (périodes, relevés, régularisations), aperçu par token, design énergie sur `/my/invoices`.

Décisions d'architecture :

- [ADR 0004 — Lien Période ↔ Facture : une seule source](https://github.com/Energie-De-Nantes/souscriptions_odoo/blob/main/docs/adr/0004-lien-periode-facture-source-unique.md) : fonde « facturée » vs « émise », et le pendant avoirs/visuel croisé.
- [ADR 0015 — Relevés d'index : enfant figé de la Période](https://github.com/Energie-De-Nantes/souscriptions_odoo/blob/main/docs/adr/0015-releves-index-enfant-fige-periode-projete-facture.md) : le justificatif au portail comme sur le PDF.
- [ADR 0030 — Le facturé gelé, le mesuré vivant](https://github.com/Energie-De-Nantes/souscriptions_odoo/blob/main/docs/adr/0030-facture-gele-mesure-vivant-regularisation-modele-propre-solde-tampon.md) : les régularisations émises remontent au portail (fait — section dédiée).
- [ADR 0031 — La fin de souscription gouvernée par le fait C15](https://github.com/Energie-De-Nantes/souscriptions_odoo/blob/main/docs/adr/0031-fin-souscription-gouvernee-fait-c15-sorties-tirees-cloture-campagne.md) : le statut du contrat reflété au portail (fait — badge d'état).
- [ADR 0017 — Consentement : formulaire public + journal append-only](https://github.com/Energie-De-Nantes/souscriptions_odoo/blob/main/docs/adr/0017-consentement-donnees-conso-formulaire-odoo-journal-append-only.md) : l'UI de retrait au portail, chantier distinct.
- [ADR 0026 — Chèque énergie : tiers-payeur, modèle propre](https://github.com/Energie-De-Nantes/souscriptions_odoo/blob/main/docs/adr/0026-cheque-energie-tiers-payeur-modele-propre-delegue-paiement.md) : la saisie usager·ère au portail, tranche séparée — jamais d'écriture publique sur la comptabilité.
