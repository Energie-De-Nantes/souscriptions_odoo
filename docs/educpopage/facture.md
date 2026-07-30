# La facture d'énergie

## En deux mots

Chaque mois, chaque contrat en service reçoit sa facture d'électricité. Cette page raconte ce qu'il y a *dedans* et d'où viennent les chiffres. Tout part d'un brouillon mensuel — la **Période** — rempli automatiquement avec les mesures du compteur, relu par le·la facturiste, puis transformé en lignes de facture. Tant que la facture n'est pas émise, tout reste corrigeable ; une fois émise, plus rien ne bouge. Le pilotage du mois (qui clique quand) est raconté dans [facturer.md](facturer.md) — ici, on regarde le document lui-même.

## Le geste au quotidien

### La Période : le brouillon mensuel du contrat

Menu **Souscriptions → Périodes de facturation**, puis une ligne : c'est la **fiche Période**, le détail d'un mois d'un contrat. On y trouve :

- **les énergies par cadran** : la consommation mesurée du mois, en kWh, découpée selon le compteur — Base, ou Heures Pleines / Heures Creuses, ou quatre cadrans saisonniers. C'est le calendrier du *compteur* qui décide du découpage, pas la formule de prix du contrat ;
- **les provisions et les écarts** : pour un contrat mensualisé (lissé), la quantité prévue au contrat et l'écart avec le mesuré, qui attendra la [régularisation](regulariser.md) ;
- **les montants réseau et taxes** : le TURPE (le péage du réseau public d'électricité, fixe et variable), la CTA (contribution tarifaire d'acheminement) et le taux d'accise (la taxe sur l'électricité) — servis tels quels par electricore, le service qui fait tous les calculs métier ;
- **la puissance moyenne du mois** et le nombre de jours de la période ;
- **les relevés d'index utilisés** : la liste datée des lectures du compteur qui justifient le calcul. Quand les données manquent, le·la facturiste peut saisir un relevé à la main ;
- **les documents liés** : la facture du mois, et plus tard l'éventuelle régularisation.

### Scanner la masse, vérifier les lignes douteuses

L'écran **Périodes de facturation** est fait pour balayer tout un mois d'un coup d'œil. Chaque période porte deux verdicts, calculés par electricore et que le·la facturiste lit mais ne modifie jamais :

- la **Qualité** de l'énergie : *Réelle* (mesurée), *Estimée*, ou *Incalculable* (pas assez de données pour calculer) ;
- le **Statut de communication** du compteur : *Communicante* ou *Non communicante*.

Les filtres et regroupements de l'écran suivent exactement ces verdicts : « Qualité réelle / estimée / Incalculable », « Communicante / Non communicante », « Changement pendant la période » (un événement réseau a eu lieu : changement de compteur, de puissance…), « Lissé / Non lissé ». Le geste type : regrouper par Qualité, ouvrir les incalculables et les estimées, juger ligne à ligne.

Une période **incalculable est créée quand même** : on ne saute jamais un mois faute de données. Le·la facturiste y saisit une estimation à la main (énergies, relevé), et la facture part comme les autres.

### Les refacturations de prestations

Menu **Souscriptions → Refacturations** : les en-cours facturés par Enedis au fournisseur (une mise en service, un déplacement de technicien·ne, une indemnité…) et refacturés à l'usager·ère **à prix coûtant**. Le bouton « Tirer d'electricore » rapatrie les lignes du mois ; chacune est soit une *prestation* (avec TVA), soit une *indemnité* (sans TVA).

Par défaut, tout part sur la prochaine facture du contrat. Une ligne douteuse s'écarte avec l'interrupteur **« En attente »** — c'est le seul frein : rien ne bloque automatiquement. L'état de chaque ligne (À refacturer / En attente / Facturée / Émise) se déduit tout seul de sa situation.

### Le PDF de la facture

La facture d'énergie a son gabarit dédié, aux couleurs du fournisseur. On y lit : le PDL (le point de livraison, l'identifiant du compteur chez Enedis), le mix énergétique, la période facturée, la section **Abonnement** (la part fixe, en jours), la section **Énergie** (en kWh, par cadran), les notes « dont TURPE fixe / variable », la note d'option mensualisée le cas échéant, et le **justificatif de calcul** : le tableau des relevés d'index utilisés, chaque relevé étiqueté *Réel* ou *Estimé*.

C'est **le même document partout** : impression depuis la facture, pièce jointe du mail, téléchargement sur le [portail](portail.md).

!!! question "🤖 À valider avec vous"
    - Quand electricore ne fournit rien (période « Incalculable »), on crée quand même la période du mois : vous saisissez une estimation à la main et on facture — on ne saute jamais un mois faute de données. C'est bien votre pratique ?
    - Les prestations Enedis partent en refacturation automatiquement, sans validation préalable obligatoire : c'est à vous d'écarter (« En attente ») celles qui vous semblent douteuses avant la création des factures — rien ne bloque. Cette responsabilité vous va, ou faut-il un garde-fou ?

## Les règles du jeu

**Le mois civil, au prorata des jours.** Tout le monde est facturé au mois calendaire — jamais de « mois anniversaire » propre à chaque contrat. Un contrat qui entre ou sort en cours de mois a une période raccourcie : l'abonnement se facture **en jours** (le nombre de jours réels de la période × un prix par jour), l'énergie **en kWh**. Les unités apparaissent telles quelles sur les lignes.

**L'abonnement se prixe sur la puissance moyenne.** Le tarif d'abonnement dépend de la puissance ; quand la puissance change en cours de mois, on facture sur la **moyenne pondérée** mesurée du mois — mathématiquement équivalent à découper le mois, sans le découper. Le libellé de la ligne affiche cette puissance facturée. Si la moyenne est inconnue (période saisie à la main), on se replie sur la puissance souscrite du contrat.

**Le réel au réel, la provision au mensualisé.** Un contrat au réel est facturé de sa consommation mesurée. Un contrat mensualisé est facturé chaque mois de sa mensualité prévue, jamais du mesuré du mois ; l'écart s'accumule et attend la [régularisation](regulariser.md).

**Tout se fige à l'ÉMISSION, jamais avant.** C'est LA règle de la maison :

- **avant l'émission**, la facture est un brouillon et la Période reste corrigeable. On peut ajuster les quantités, saisir un relevé, corriger une estimation : les lignes de la facture se **recomposent** depuis la Période à l'émission — le brouillon n'est jamais une version gelée en avance ;
- **à l'émission**, tout gèle d'un coup : les lignes, les relevés justificatifs, la Période elle-même (verrouillée tant que sa facture émise existe). La facture et sa période racontent pour toujours la même histoire ;
- **après l'émission**, la facture est définitive. Toute correction passe par un **avoir** ou une régularisation — jamais par une remise en brouillon.

**Le geste commercial a deux maisons.** Pour faire un geste à un·e souscripteur·rice :

- **en quantités ou en jours** : on corrige la Période, avant émission — la facture recomposée suit ;
- **en euros** : on ajoute une **ligne manuelle** sur le brouillon de facture (une remise, un geste). Elle survit aux recompositions et reste visible telle quelle.

On ne **maquille jamais une ligne générée** : les lignes produites par le module (abonnement, énergie, refacturations, régularisation) ne sont pas modifiables à la main sur la facture — seules les lignes ajoutées par le·la facturiste restent libres. La raison est simple : une ligne générée est le miroir de sa source ; la modifier à la main, c'est mentir sur la source, et la modification serait perdue à la prochaine recomposition.

**L'avoir s'écrit à la main.** Un avoir corrige une facture émise : il est rédigé entièrement par le·la facturiste, lié à sa facture source pour la traçabilité, et **jamais régénéré** depuis la Période — recomposer un avoir écraserait la correction humaine qu'il porte. (Le chèque énergie, lui, ne réduit pas la facture : il la *paie* en partie — voir [encaisser.md](encaisser.md).)

**Le justificatif des relevés est complet.** Chaque facture affiche **tous** les index utilisés par le calcul, y compris les estimés (étiquetés comme tels). Le relevé de frontière apparaît deux fois : en fin d'un mois et en début du suivant — chaque facture se suffit à elle-même, sans renvoyer à la précédente. Lors d'un changement de compteur en cours de mois, le tableau montre les deux familles de cadrans côte à côte, fidèle à ce qui a réellement été relevé.

!!! note "Les factures d'avant le module"
    Les factures émises avant la bascule dans ce système ont été migrées et portent la coche **« Origine legacy »** — un filtre d'affichage pour les distinguer d'un coup d'œil des factures natives. Certains contrats mensualisés portent aussi des **périodes d'ouverture** : des Périodes reconstituées pour les mois facturés dans l'ancien système, qui portent le facturé (provision, jours) et la référence de la facture d'origine, mais **aucun document comptable ici** — la vraie facture vit dans l'ancien système. Les mois déjà soldés avant la bascule sont marqués « régularisée (legacy) » et ne réapparaîtront jamais dans une régularisation.

!!! question "🤖 À valider avec vous"
    - Le geste commercial a deux maisons : en euros, une ligne manuelle sur le brouillon (qui survit aux recompositions) ; en jours ou en quantités, une correction de la Période avant émission. On ne retouche jamais une ligne générée. Cette discipline vous convient ?
    - La facture affiche TOUS les index utilisés, y compris les estimés (étiquetés), et le même relevé apparaît en fin d'un mois et en début du suivant. Cette transparence-là est bien celle attendue par vos usager·ères ?

## Sous le capot

Modèles et gabarits :

- [`models/core/souscription_periode.py`](https://github.com/Energie-De-Nantes/souscriptions_odoo/blob/main/models/core/souscription_periode.py) — `souscription.periode` : snapshot contractuel, énergies par cadran, verdicts (`qualite`, `statut_communication`), `_quantite_facturee()` (mesuré vs provision tamponnée), `_composer_lignes()` (sections, unités kWh/jours, puissance moyenne affine, flag `souscription_ligne_generee`), verrou d'écriture quand la facture est émise, champs legacy (`facture_legacy_ref`, `legacy_regularisee`).
- [`models/core/souscription_releve.py`](https://github.com/Energie-De-Nantes/souscriptions_odoo/blob/main/models/core/souscription_releve.py) — le Relevé, enfant figé de la Période, projeté sur la facture.
- [`models/core/souscription_refacturation.py`](https://github.com/Energie-De-Nantes/souscriptions_odoo/blob/main/models/core/souscription_refacturation.py) — `souscription.refacturation` : état dérivé, `en_attente`, prestation taxée / indemnité hors TVA.
- [`models/core/account_move.py`](https://github.com/Energie-De-Nantes/souscriptions_odoo/blob/main/models/core/account_move.py) (`origine_legacy`, re-génération à l'émission, refus de remise en brouillon) et [`models/core/account_move_line.py`](https://github.com/Energie-De-Nantes/souscriptions_odoo/blob/main/models/core/account_move_line.py) (lignes générées non modifiables, lignes manuelles libres).
- [`reports/facture_energie_template.xml`](https://github.com/Energie-De-Nantes/souscriptions_odoo/blob/main/reports/facture_energie_template.xml) — le gabarit PDF dédié (PDL, mix, TURPE/mensualisation, justificatif des relevés).
- [`views/core/souscriptions_periode_views.xml`](https://github.com/Energie-De-Nantes/souscriptions_odoo/blob/main/views/core/souscriptions_periode_views.xml) — l'écran « Périodes de facturation », ses filtres et regroupements par verdict.

ADRs de référence :

- [ADR 0005 — Granularité de l'énergie pilotée par le calendrier de comptage](https://github.com/Energie-De-Nantes/souscriptions_odoo/blob/main/docs/adr/0005-granularite-energie-calendrier-comptage.md)
- [ADR 0006 — Le snapshot figé de la Période fait autorité à la facturation](https://github.com/Energie-De-Nantes/souscriptions_odoo/blob/main/docs/adr/0006-snapshot-periode-fait-autorite-facturation.md)
- [ADR 0007 — Snapshot typé et verrou à l'émission](https://github.com/Energie-De-Nantes/souscriptions_odoo/blob/main/docs/adr/0007-snapshot-periode-type-verrou-facturation.md)
- [ADR 0008 — Mesuré si non lissé, provision si lissé](https://github.com/Energie-De-Nantes/souscriptions_odoo/blob/main/docs/adr/0008-quantite-facturee-mesure-ou-provision-selon-lissage.md) (complété par l'[ADR 0030](https://github.com/Energie-De-Nantes/souscriptions_odoo/blob/main/docs/adr/0030-facture-gele-mesure-vivant-regularisation-modele-propre-solde-tampon.md) : énergie facturée universelle, tampon à l'émission)
- [ADR 0009 — Prestation à refacturer : modèle indépendant, rassemblé sur la facture](https://github.com/Energie-De-Nantes/souscriptions_odoo/blob/main/docs/adr/0009-prestation-refacturer-modele-independant-rassemble-sur-facture.md) et [ADR 0012 — état dérivé, mise en attente opt-out](https://github.com/Energie-De-Nantes/souscriptions_odoo/blob/main/docs/adr/0012-prestation-etat-derive-mise-en-attente-opt-out.md)
- [ADR 0014 — Pas de verrou global des lignes : provenance générée / manuelle](https://github.com/Energie-De-Nantes/souscriptions_odoo/blob/main/docs/adr/0014-pas-de-verrou-lignes-facture-confiance-facturiste.md)
- [ADR 0015 — Relevés d'index : enfant figé de la Période, projeté sur la facture](https://github.com/Energie-De-Nantes/souscriptions_odoo/blob/main/docs/adr/0015-releves-index-enfant-fige-periode-projete-facture.md) et [ADR 0028 — colonnes du justificatif : union des familles relevées](https://github.com/Energie-De-Nantes/souscriptions_odoo/blob/main/docs/adr/0028-releve-colonnes-union-familles-relevees.md)
- [ADR 0018 — Abonnement affine : base 3 kVA + coefficient par kVA](https://github.com/Energie-De-Nantes/souscriptions_odoo/blob/main/docs/adr/0018-abonnement-affine-base-3kva-plus-coefficient-kva.md)
- [ADR 0020 — Contrat méta-périodes v3 : verdicts, montants, provenance des relevés](https://github.com/Energie-De-Nantes/souscriptions_odoo/blob/main/docs/adr/0020-alignement-contrat-meta-periodes-v3.md)
- [ADR 0032 — Le brouillon gouverne : l'émission est l'unique événement de gel](https://github.com/Energie-De-Nantes/souscriptions_odoo/blob/main/docs/adr/0032-brouillon-gouverne-gel-a-lemission.md)

Pages sœurs : [facturer.md](facturer.md) (la campagne mensuelle qui orchestre tout ça), [regulariser.md](regulariser.md) (solder les écarts mesuré − facturé), [encaisser.md](encaisser.md) (paiements et chèque énergie), [portail.md](portail.md) (le même PDF côté usager·ère).
