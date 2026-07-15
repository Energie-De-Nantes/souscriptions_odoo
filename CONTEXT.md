# Souscriptions (module Odoo)

Module Odoo de gestion des contrats de fourniture d'électricité. Il porte le contrat, les
données de facturation historisées, les grilles de prix **fournisseur**, la facture légale,
les paiements et le portail. Tout le savoir métier **réseau** (énergies par cadran, TURPE,
accise, CTA, périmètre, événements C15) est calculé par
[electricore](https://github.com/Energie-De-Nantes/electricore) et consommé via son API.

## Vocabulaire partagé (défini ailleurs)

Le vocabulaire métier neutre — **PDL, RSC, affaire / id_Affaire, cadran, HP/HC/Base, FTA,
TURPE, accise, CTA, méta-période, provision d'énergie, contrat lissé, facturation calendaire,
régularisation, chronologie** —
est défini dans le glossaire core d'electricore (`electricore/core/CONTEXT.md`). Ce fichier
ne redéfinit aucun de ces termes ; il ne définit que les notions propres à la représentation
Odoo et au rôle fournisseur.

## Langue

Français, cohérent avec electricore.

## Termes

**Souscription** :
Le contrat de fourniture d'électricité conclu avec un·e *souscripteur·rice*, matérialisé par
`souscription.souscription`. Système de référence de toutes les données métier/contractuelles
côté fournisseur ; n'est *pas* stocké dans le module comptable. Porte la *RSC* electricore
comme clé d'articulation — réconciliée depuis l'`id_Affaire` Enedis (amorce capturée au
*raccordement*) — le PDL restant un attribut d'affichage/recherche. Naît **en instance** au
*raccordement*, devient **en service** — facturable — à l'acquisition de la RSC (cf. *En
instance / En service*).
_Éviter_ : **abonnement** (collision triple — le module Odoo de facturation récurrente qu'on
remplace, le terme pipeline d'electricore, la catégorie produit « Abonnements ») ; **devis**,
**commande**, `sale.order` (explicitement non utilisés : pas de cycle de vente) ; contrat
(trop générique).

**En instance / En service / En attente de clôture / Résiliée** :
États de cycle de vie de la *Souscription*, **calculés depuis les faits**, jamais saisis.
**En instance** : née à l'**acceptation** de la demande de *raccordement* (signée, consentements
journalisés) mais **sans RSC** : non facturable, ignorée du pull de facturation. **En service** :
la RSC est acquise — le C15 d'effectivité est arrivé, la mise en service est réelle (ADR 0022) —
facturable. **En attente de clôture** : une sortie C15 (`RES`/`CFNS`, symétriques pour nous) a
posé la date de fin — **dernier jour servi** (le fait C15, demi-ouvert, est converti à la
couture ; la *Période*, elle, reste bornée en demi-ouvert), champ à **auteur unique**, jamais
saisi (ADR 0031) — et la clôture n'est pas encore soldée. **Résiliée** : clôture soldée — la
*Période* contenant la date de fin est facturée **et** la *Régularisation* de clôture est émise
(ou rien à solder : non-lissés, résiliés migrés « régularisée »). La **file d'attente des sorties
à traiter est la vue « en attente de clôture »** — aucun statut de traitement à la main. La
correction passe par le **fait** (la RSC, le C15 de sortie), jamais par l'état.
_Éviter_ : **brouillon** (la Souscription est conclue et signée ; « brouillon » est réservé à
la *Période* et à la *Facture*) ; « active » (collision avec l'archivage Odoo) ;
« raccordement effectué » comme bascule manuelle (l'état découle de la RSC, ADR 0021) ;
**date de fin saisie à la main** (anticipation et ratés vivent hors mécanisme : process de
demande sortante, geste commercial — ADR 0031).

**Souscripteur·rice** :
La personne ou l'organisation titulaire d'une *Souscription*. Désigné·e *usager·ère* dans le
contexte du *portail*.
_Éviter_ : client, abonné·e.

**Conditions particulières** :
Le document (PDF) qui récapitule au·à la *souscripteur·rice* les conditions **propres à sa
*Souscription*** — *PDL*, puissance, *Configuration fournisseur*, prix engagés (*Grille de prix*),
lissage/provisions, mode de paiement — **et porte ses déclarations/consentements** (choix EDN,
adhésion association, acceptation CGV, courbe de charge, renonciation rétractation) **et la
signature électronique**. Il **complète** les *conditions générales* (CGV — cadre légal générique,
**référencées** et non reproduites), pas l'inverse. C'est une **projection** de la *Souscription*
(les actes — consentements, acceptation CGV, renonciation, signature — sont **portés par le
*Journal des actes*** de la *Souscription*), jamais un
enregistrement distinct ni un acte de vente. Lève l'ambiguïté du terme « contrat » : le cadre
contractuel = *CGV* + *conditions particulières* ; l'enregistrement = la *Souscription*.
_Éviter_ : « contrat » seul (préciser *conditions particulières*, *CGV* ou *Souscription*) ;
**devis**, **offre** (pas de cycle de vente, cf. *Souscription*).

**Attestation de fourniture** :
Document **court** prouvant qu'un·e *souscripteur·rice* est titulaire d'un contrat de fourniture
**actif** — titulaire, *PDL*, adresse, **date d'effet** (« actif depuis »), puissance —, destiné aux
tiers (bailleur, CAF, assurance). **Attestée par le fournisseur** : ne porte **ni** prix, **ni**
consentements, **ni** signature de l'usager·ère (à la différence des *conditions particulières*).
Comme la CP, c'est une **projection** de la *Souscription*.
_Éviter_ : confondre avec les *conditions particulières* (l'acte d'adhésion complet) ; « attestation
de contrat » au sens du rapport prod (qui est en réalité la CP, pas une attestation).

**Période** :
Période mensuelle de facturation d'une *Souscription* (`souscription.periode`). **Brouillon de
travail facturable** : amorcé par les quantités calculées par electricore (méta-période), puis
**complété/corrigé par le·la facturiste** avant facturation — saisie manuelle d'estimations quand
le flux Enedis manque, *gestes commerciaux*, ajustements. À l'**émission** de sa *Facture*, son
**facturé** — l'*énergie facturée* par cadran, jours, puissance, taxes, relevés-justificatifs —
est **figé** (historisation) et lié à la facture ; son **mesuré** (énergies par cadran, verdicts, coûts réseau
servis par electricore) reste **vivant** : electricore fait foi et le raffine à tout moment, y
compris après facturation. Porte
ce qui est **facturé** — pas une copie du coût réseau ; la marge se calcule à la demande côté
analytique en rejouant electricore. Elle est la **source analytique** typée : ses champs se lisent
et s'agrègent **directement**, jamais reconstruits depuis les lignes de facture (`ligne → produit →
catégorie`) ; la *Facture* en est une **projection** (dérive manuelle bornée tolérée, ADR 0014).
_Éviter_ : méta-période (concept amont, côté electricore), mois ; « instantané fidèle » (la Période
est un brouillon facturable, pas une copie figée d'electricore).

**Période d'ouverture** :
Une *Période* backfillée par la migration (#107, ADR 0023 décision 3) pour un mois non
régularisé d'un contrat *lissé*, dont la facture vit dans l'ancien système (Odoo 17) : le champ
`facture_legacy_ref` la marque, **aucun** `account.move` n'est créé ici (pas de move fictif, ADR
0004 — `facture_id` reste dérivé de `move_ids` et donc vide). Elle reste `type_periode='mensuelle'`
— même périmètre qu'une Période facturée normale (régularisation #20). Une facture legacy est déjà
**créée et émise** dans l'ancien système : la Période d'ouverture est donc **terminale** — statut
`émise` — dans le **statut de facturation** dérivé par la *Campagne* (à tirer → à facturer →
facturée → émise, cf. *Campagne de facturation*), exclue des deux reste-à-faire (créer, émettre)
comme `creer_factures()` l'excluait déjà de la création (#284).
_Éviter_ : la classer `à facturer` (bloque « Créer factures » et « Émettre factures » à vie, #284).

**Énergie facturée** :
La quantité d'énergie, par cadran facturé, que les *Factures* émises ont réellement portée pour
une *Période* — le « facturé ». **N'évolue que par l'émission d'une facture qui la porte** :
fixée à la **création** de la Période pour un contrat *lissé* (la provision contractuelle), à
l'**émission** pour un contrat non lissé (la meilleure mesure/estimation du moment), puis
déplacée uniquement par l'émission d'une facture de *régularisation* qui solde l'écart — la
Période reste en permanence la somme exacte de ce que ses factures ont porté (historisation
**raffinée**, toujours opposable, ADR 0030). Gelée contre tout le reste : pulls, éditions. Se distingue de l'**énergie
mesurée** — la meilleure connaissance electricore, **vivante**, raffinable même après facturation
(electricore fait foi). L'**écart** mesuré − facturé, par cadran, est la matière première de toute
*régularisation* — y compris, à terme, celle d'un contrat non lissé dont les mesures ont été
rééditées après facturation.
_Éviter_ : « provision d'énergie » pour le cas non lissé (le terme amont electricore ne couvre que
l'avance du contrat *lissé* — ici c'est le facturé, quel que soit le lissage) ; figer le mesuré
(seul le facturé gèle) ; reconstruire le facturé depuis les lignes de facture (la Période reste la
source analytique typée).

**Régularisation (solde)** :
Le document par lequel les écarts mesuré − facturé des mois soldables d'une *Souscription* sont
facturés — ou remboursés par avoir — **aux prix historiques**, ventilés par *Grille de prix*
(ADR 0030). Un
**modèle propre**, pas une *Période* (il ne porte aucune énergie mensuelle) — même motif que la
*Refacturation* : modèle indépendant rassemblé sur une *Facture*. Porte la ventilation **typée**
(une ligne par grille × cadran : sous-période, écart kWh, prix) dont la facture est la
**projection** (notes par mois), et les relevés frais en justificatif. Candidats : tous les mois
facturés à écart non nul dont le mesuré est **connu** (verdict *réelle*/*estimée*) et non déjà
soldés avant bascule (état « régularisée » migré) — les compteurs
non communicants relèvent d'un autre processus. Son **émission** solde les mensuelles couvertes :
leur *énergie facturée* est tamponnée de l'écart, l'écart retombe à zéro, chacune garde la trace
de la Régularisation qui l'a soldée — relancer une régularisation juste après est un non-événement
(idempotence), et un mesuré qui bouge encore fait renaître l'écart pour la suivante. **Émise, elle
est immuable** : la correction passe par **compensation** — nouvelle Régularisation ou avoir —
jamais par mutation du document émis.
_Éviter_ : « période de régularisation » (une Régularisation n'est **pas** une Période — champs
mensuels sans objet) ; la borner par une fenêtre stockée (les candidats se sélectionnent par
l'écart et le verdict, jamais par des dates de fenêtre) ; « je ne sais pas » qui écrase « je
savais » (un verdict *incalculable* ou un mois absent du flux ne réécrit jamais un mesuré stocké) ;
remettre en brouillon ou annuler une Régularisation émise (le tampon est déjà consommé).

**Relevé (d'index)** :
Événement de lecture **daté** du compteur, enfant d'une *Période* (`souscription.releve`,
`periode_id`). Porte un **index** (compteur cumulé) **par registre réel** du compteur
(HPH/HPB/HCH/HCB, ou HP/HC, ou Base selon le *calendrier de comptage*), jamais par cadran
**facturé** — c'est le seul endroit où ce détail survit, les énergies de la *Période* arrivant
déjà regroupées (contrat v3, ADR 0020). Porte sa **provenance** (`releve_externe_id`,
`origine`) : l'identifiant du justificatif côté electricore, support de la dédup au re-pull. Consigne **tous les index qu'electricore a utilisés**
pour le calcul d'énergie de la Période — **obligation légale** sur la *Facture* et support de
**vérification** par le·la *souscripteur·rice*. Chaque relevé déclare sa **nature** : *réel*
(mesure Enedis) ou *estimé* (estimation electricore ou *facturiste*), étiquetée sur la facture.
**Figé** avec le snapshot de la Période et verrouillé à l'**émission** de la *Facture* (ADR
0006/0014 amendés) ; le relevé
**frontière** est dupliqué entre deux Périodes consécutives — assumé : chaque facture est
auto-portante. Source : electricore (pull, ADR 0011), saisi à la main par le·la *facturiste* tant
que l'intégration manque (#12). C'est un **justificatif**, pas la quantité facturée : l'énergie
facturée reste pilotée par `energie_*`/provision (un contrat *lissé* facture la provision, pas
`fin − début`).
_Éviter_ : confondre **index** (la valeur cumulée d'un registre) et **relevé** (l'événement daté qui
en porte plusieurs) ; confondre avec `energie_*` (la *consommation* dérivée des relevés) ; cadran
facturé.

**Qualité (verdict)** :
Verdict electricore sur l'énergie d'une *Période* : **réelle**, **estimée** ou **incalculable** —
les termes du glossaire electricore, portés **tels quels** (accents compris) sur la Période
(ADR 0020 : noms *et valeurs* du contrat). Concept **amont** : le rollup depuis la nature des
relevés bornants (pire-gagne) appartient à electricore (son ADR-0033) ; côté addon le·la
*facturiste* le **lit**, ne le calcule ni le modifie. Une période *incalculable* est créée quand
même (brouillon facturable, cf. *Période*). Jumeau : **statut de communication**
(communicante / non communicante), même provenance, même statut readonly.
_Éviter_ : `data_complete` (l'ancien drapeau binaire qu'il remplace) ; confondre avec la **nature**
d'un *Relevé* (réel/estimé au grain relevé — la qualité est le verdict au grain *période*) ;
désaccentuer les valeurs (`reelle` n'existe pas sur le fil — bug S0001).

**Grille de prix** :
Barème **fournisseur** daté (`grille.prix`), **tout-compris** : le TURPE y est **absorbé**, jamais
refacturé ligne à ligne (ADR 0002). Porte le prix d'abonnement **affine** — prix de base 3 kVA +
coefficient par kVA supplémentaire (ADR 0018) — et le prix de l'énergie par cadran facturé.
Chaque grille appartient à un *régime de prix* ; elle est sélectionnée par le régime de la
*Souscription* et la **date de début** d'une *Période*, ce qui permet de facturer une
*régularisation* aux prix historiques. Sa validité est **demi-ouverte** comme celle de la *Période*
(`[début, fin)` — même convention de borne partout : une grille se termine le jour où la suivante
commence, jamais la veille), et un changement de grille **tombe toujours un 1er du mois** : aucune
*Période* n'enjambe donc deux grilles, et sa seule date de début suffit à la désigner — il n'existe
pas de prix au prorata. La **fin** de validité est **dérivée** (le début de la grille suivante du
même régime) : elle s'affiche, elle ne se saisit ni ne se stocke — une grille en vigueur est
simplement la plus récente à avoir commencé. C'est aussi l'unique **moteur de prix** : la règle qui
assemble barème et configuration — abonnement affine, prix par cadran facturé, *Majoration PRO*,
choix du *Produit de facturation* (standard ou solidaire) — n'a qu'une implémentation, portée par la
grille, que la *Facture* et les *conditions particulières* **projettent** chacune avec **sa** grille :
historique (à la date de début de la *Période*) pour la Facture, engagée (à la date de début de la
*Souscription*) pour la CP. Les **valeurs** divergent donc
dans le temps — c'est le domaine ; la **règle**, jamais. Une grille incapable de prixer une
configuration **échoue bruyamment** — jamais de prix nul par défaut sur un document.
_Éviter_ : tarif (collision avec la FTA / tarif d'acheminement réseau), barème ; « prix par palier »
(l'abonnement est **affine**, pas tabulé par puissance) ; « aligner » les prix de la CP sur les
factures (la divergence de **valeurs** est voulue — seule la **règle** est unique) ; un prix à 0
quand la grille est incomplète (échec bruyant) ; une grille qui change **en cours de mois** (la
borne est le 1er — sinon un mois se facture en entier au mauvais prix, sans erreur) ; une **fin de
validité saisie** ou fermée à la main (elle est dérivée de la suivante) ; sélectionner la grille sur
la date de **fin** d'une *Période* (c'est la grille du mois **suivant** — la borne de fin est
exclue).

**Régime de prix** :
L'axe qui désigne **quel barème** s'applique à une *Souscription* : **standard** ou **Moulin**.
Chaque *Grille de prix* appartient à un régime, et chaque régime versionne ses grilles
**indépendamment** (les deux barèmes ne bougent ni au même rythme ni pour les mêmes raisons).
Orthogonal au *Tarif solidaire* (isolation comptable) et à la *Majoration PRO* (surcoût %) : les
trois axes se composent librement.
_Éviter_ : confondre avec le *Tarif solidaire* (comptable, pas tarifaire) ; « option » (collision
avec l'option tarifaire réseau).

**Tarif Moulin** :
Le *régime de prix* « prix coûtant » proposé aux personnes qui s'engagent dans le commun EDN. Un
barème à part entière, versionné par ses propres *Grilles de prix* : il évolue avec les coûts du
commun, jamais en pourcentage du barème standard. Se compose avec le *Tarif solidaire*.
_Éviter_ : « remise Moulin » (ce n'est pas une remise) ; produits de facturation dédiés (seul le
**prix** change via la grille — fiscalité et comptes restent ceux du standard).

**Majoration PRO** :
Surcoût commercial (`coeff_pro`, en %) **propre à chaque *Souscription*** (négocié au cas par cas),
appliqué à **toutes les lignes de fourniture** — *abonnement* et *énergie* — mais **jamais** à la
*Refacturation* (transit de coût Enedis). N'est **pas** dans la *Grille de prix* (≠ prix maîtrisé,
versionné).
_Éviter_ : confondre avec un univers comptable (le PRO partage les comptes/TVA du standard, à la
différence du *Tarif solidaire*).

**Produit de facturation** :
Le `product.product` Odoo porté sur une ligne de *Facture*, choisi par son **rôle de facturation**
(*abonnement* ; *énergie* par cadran facturé ; *Refacturation* par nature) **et** par le *tarif
solidaire*. Il porte le **compte de produits et la TVA** : la ligne hérite de la fiscalité de son
produit (positions fiscales comprises), jamais d'un taux saisi sur la ligne (ADR 0009 §5). Le
**catalogue** — un mappage *rôle → produit*, sans donnée propre — est l'unique endroit qui résout ce
choix. Le solidaire impose **deux exemplaires parallèles** de chaque produit (standard / solidaire),
comptablement **isolés** (cf. *Tarif solidaire*, ADR 0013).
_Éviter_ : *article* ; confondre avec la *Grille de prix* (qui porte le **prix**, pas le compte/la TVA).
_Migré_ : les factures **migrées** portent leurs libellés **legacy verbatim** — nom du produit prod
(`sale_subscription` : un produit par tarif×puissance×type×ère, « Abonnement Base 6 kVA ») **+** le
suffixe de récurrence (« - 1 Mois\n<date> au <date> »). Ce sont des documents **postés** (registre
légal de ce qui a été facturé) : on **ne les réécrit pas**. Le catalogue ci-dessus ne labellise que
le **going-forward** (« Abonnement 6 kVA ») ; un libellé moche sur une facture n'est donc pas un bug
de génération mais un artefact d'historique. Le vrai risque associé (des périodes **futures**
postées d'avance en prod que la migration traînerait dans le parc vivant → **double-facturation**)
est une question de **borne de bascule**, hors de ce module (`souscriptions_migration`).

**Facture** :
Le document comptable légal (`account.move`, *facture d'énergie*) émis à partir d'une *Période*
qu'il référence (`periode_id`). Vit en deux temps. **Brouillon** : l'espace de travail du·de la
*facturiste* — ses lignes **générées** sont le miroir en lecture seule de la source (*Période*,
*Régularisation*, *Refacturations* rassemblées), régénérées tant qu'elle bouge ; ses lignes
**manuelles** (*gestes commerciaux* en euros, corrections) s'y ajoutent et **survivent à la
régénération**. Rien ne gèle au brouillon — la *Période* reste corrigeable. **Émise** :
l'émission est l'**unique événement de gel** — elle re-génère une dernière fois (la source fait
foi à l'instant T), fige le facturé, verrouille la *Période* et ses *Relevés*, impute le *chèque
énergie* — et la facture devient **définitive** : la correction passe par un avoir ou une
*Régularisation*, jamais par un retour en brouillon (inaltérabilité par hachage, configurée au
journal de ventes au déploiement). Une *Période* est dite **facturée** dès qu'une *Facture* la
référence, **émise** quand cette facture l'est. Seules les *Périodes* dont la *Facture* est
**émise** sont visibles du·de la *souscripteur·rice* au *Portail* — un brouillon de facture ne
fuite jamais côté usager.
_Éviter_ : confondre « facturée » (une facture existe) et « émise » (facture finalisée) ;
**pré-facture** (rejetée : le brouillon d'`account.move` **est** l'espace intermédiaire
d'édition — jamais de deuxième couche) ; éditer une ligne **générée** (les quantités se
corrigent à la source, les euros par ligne manuelle) ; supprimer le brouillon pour « défiger »
(rien n'est figé avant l'émission).

**Avoir** :
Le document comptable (`account.move`, `out_refund`) par lequel le·la *facturiste* corrige une
*Facture* **émise** — avec la *Régularisation*, l'une des deux seules portes de correction (une
facture émise est définitive, cf. *Facture*). **Autonome** : ses lignes sont écrites **à la
main**, jamais une projection d'une *Période* ni d'une *Régularisation*. Il **porte le lien**
vers sa source (`periode_id`) — traçabilité, rattachement à la *Souscription*, suivi des
*Modes de paiement* — mais n'est **jamais _la_ Facture de cette source** : `periode.facture_id`,
qui ne désigne que l'`out_invoice`, ne le retient pas. C'est cette distinction qui **gouverne** : le
gel, la re-génération des lignes générées et le rassemblement des *Refacturations* s'adressent
tous à `facture_id`, jamais au lien brut — un avoir n'est donc ni recomposé, ni pourvoyeur de
*Refacturations*.
_Éviter_ : **recomposer un avoir depuis sa source** (il doublerait ses lignes et raflerait les
*Refacturations* en file — le bug que cette définition ferme) ; « avoir » pour désigner une
*Régularisation* à net négatif (elle s'émet **en tant qu'**`out_refund` mais reste une
Régularisation **projetée**, avec sa ventilation typée) ; corriger un avoir émis (immuable comme
toute facture émise : compenser).

**Chèque énergie** :
Aide de l'État versée **au fournisseur à la place** du·de la *souscripteur·rice* (`souscription.cheque_energie`). C'est un **tiers-payeur**, **jamais une remise** : la fourniture n'est pas moins chère, une partie est payée par l'État — le **chiffre d'affaires et la TVA de la _Facture_ restent intacts**. Sur la *Facture*, il apparaît en **« payé / reste à payer »**, pas en ligne négative. Porte une **valeur nominale**, un **numéro** (unique), une **date d'expiration** (~mars N+1) et un **cycle de vie** : **reçu** (saisi, sans effet) → **validé** (la **porte** : saisie *à la main* sur le site étatique par le·la *facturiste* — aucun signal dérivable — qui le rend **imputable**) → **rejeté / expiré**. Rattaché au·à la *souscripteur·rice* (nominatif à la personne, pas au contrat) ; s'impute sur ses *Factures* **à leur émission**, à hauteur de `min(solde, total)` sans jamais rendre la facture négative, **FIFO par expiration** quand la personne en détient plusieurs (renouvellement annuel). L'expiration borne la **validation** (la porte étatique), jamais l'imputation : un chèque **validé** est une créance acquise sur l'État et reste imputable après sa date — à l'imputation, la date ne sert qu'à l'ordre FIFO, l'**état** est la seule porte. Le **solde** (portion non encore imputée) est **dérivé**, pas saisi. Un rejet/expiration *après* imputation se corrige **à la main** (pas d'automatisme). Le modèle **possède** l'identité et le cycle de vie ; la mécanique de solde et de lettrage est **déléguée** (cf. ADR 0026), non réimplémentée.
_Éviter_ : **« remise »** ou ligne négative sur la *Facture* (c'est un paiement tiers, pas une minoration du prix ni de la TVA) ; imputer un chèque **non validé** (le site étatique est la porte) ; **écarter de l'imputation un chèque validé à date passée** (l'expiration gouverne la validation, pas l'imputation) ; « solde saisi » (il est dérivé).

**Mode de paiement** :
La façon dont le·la *souscripteur·rice* règle le **solde** de ses *Factures*, portée par la
**Souscription** (c'est le contrat qui fait foi, pas la personne : deux *Souscriptions* d'une même
personne peuvent avoir des modes différents). Valeur **exclusive** parmi : prélèvement, monnaie
locale (Moneko), espèces, virement, chèque. Sépare les factures en circuits de règlement selon
**ce qui fait foi de l'encaissement** :
- **prélèvement** — fichier SEPA en masse, adossé à un mandat ; l'outillage comptable encaisse.
- **saisie manuelle**, scindée par la **traçabilité bancaire** de l'encaissement :
  - **bancaire-rapprochable** (virement, chèque) — l'argent atterrit sur un **relevé bancaire** ; le
    **rapprochement** fait foi, jamais une attestation ;
  - **attestation-pure** (monnaie locale/Moneko, espèces) — **aucune trace bancaire, jamais** ;
    l'encaissement n'a d'autre source de vérité que l'**attestation à la main** du·de la *facturiste*.

Ne concerne que les factures à **reste à payer non nul** — une facture soldée (chèque
énergie, 0 €) ne déclenche aucun règlement.
_Éviter_ : le *Chèque énergie* comme mode de paiement (c'est un **tiers-payeur** qui s'impute
avant règlement, le reste dû suit le mode de paiement normal) ; les **étiquettes** partenaire
comme source de vérité du mode (non exclusives, non historisées, rattachées à la personne et non
au contrat) ; **attester à la main** l'encaissement d'un *virement* ou d'un *chèque* — le relevé
bancaire fait foi, une attestation créerait une **double vérité** contre le rapprochement.

**Mandat de prélèvement (SEPA)** :
L'autorisation signée par le·la *souscripteur·rice* de débiter son compte, identifiée par un
**RUM** unique, adossée à un IBAN et à l'ICS du fournisseur. Préalable obligatoire à tout
*Mode de paiement* « prélèvement ». Le cycle de vie (actif → clos/révoqué, séquences, fichier
SEPA) est **délégué à l'outillage comptable**, non réimplémenté ; le module ne fait que le
**créer, actif d'emblée**, à l'acceptation d'un *raccordement* en prélèvement — l'acceptation
est la porte humaine (IBAN vérifié, mandat signé exigé), pas de re-validation ensuite.
_Éviter_ : un second circuit de validation du mandat (l'acceptation de la demande est la porte) ;
prélever sans mandat actif ; re-saisir à la main ce que la demande de raccordement porte déjà.

**Résolution du journal de prélèvement** :
Le journal comptable portant la méthode `sdd` est résolu dynamiquement, jamais nommé en dur.
Un seul journal `sdd` fait foi. **Plusieurs** (cas prod : `sdd` exposée sur Nef, Livret bleu,
Crédit mutuel, Moneko — un seul mandaté) sont désambiguïsés par le pointeur société
**`journal_prelevement_sdd_id`**, même idiome que `journal_monnaie_locale_id`
([ADR 0033](docs/adr/0033-encaissement-une-clic-attestation-pure-reouverture-bornee-option-b.md)) :
le rôle « journal de prélèvement » vit sur `res.company`, jamais comme marqueur sur
`account.journal`. Pointeur absent ou hors des journaux `sdd` → erreur explicite (jamais de
mandat rattaché au mauvais journal). Surfacé plus tard dans la config « Souscriptions » (#291).

**Configuration Enedis** :
La configuration *réseau* d'un PDL — FTA, calendrier distributeur, puissance réseau, cadrans
réseau — propriété d'electricore (source : C15). Détermine le coût d'acheminement (TURPE).
Référencée côté Odoo, jamais recopiée comme donnée éditable.
Les **cadrans réseau** (*calendrier de comptage* : Base mono-index, HP/HC, ou 4 cadrans
saisonniers HPH/HPB/HCH/HCB) dépendent du **compteur** et déterminent la granularité
**mesurée** — donc saisissable — de l'énergie. Cette granularité est **orthogonale au type de
tarif** fournisseur (qui ne fait que *regrouper* en cadrans **facturés**) : un même
`type_tarif` HP/HC peut correspondre à un compteur 2 registres *ou* 4 cadrans, que seul le
calendrier de comptage distingue.

**Calendrier distributeur** :
L'identifiant **autoritatif** côté electricore du *calendrier de comptage* d'un PDL (source C15,
propriété de la *Configuration Enedis*) — distinct de `config_cadrans`, sa copie **snapshottée à
la main** côté Odoo tant que le contrat d'intégration manque (#12, ADR 0005). Consommé **à terme**
pour remplacer la saisie manuelle par un pull ; en attendant, le justificatif des *Relevés*
**infère** les familles de cadrans réellement présentes depuis les index saisis, avec repli sur
`config_cadrans` déclaré si aucun index n'est renseigné (ADR 0015 amendé, #138).
_Éviter_ : confondre avec `config_cadrans` (la copie Odoo, aujourd'hui déclarative et sujette à
repli, pas encore reliée à ce calendrier autoritatif).

**Configuration fournisseur** :
La configuration *commerciale* portée par la *Souscription* : formule tarifaire fournisseur
(cadrans **facturés** : Base, ou HP/HC), lissage, provisions, mode de paiement. **Orthogonale
à la _Configuration Enedis_** : un PDL peut avoir une FTA 4 cadrans (pour minorer le TURPE) et
être facturé en Base. electricore sert l'énergie **déjà regroupée** depuis les 4 cadrans
saisonniers (HP = HPH+HPB, HC = HCH+HCB — contrat v3, ADR 0020) ; ne reste côté Odoo que le
regroupement final vers le cadran **facturé** (HP/HC → Base si la formule fournisseur est
Base), le détail par registre réel ne survivant que dans les index des *Relevés*.
_Éviter_ : FTA (c'est l'acheminement réseau, côté Enedis), option tarifaire.

**Tarif solidaire** :
Régime tarifaire social porté par la *Souscription* (`tarif_solidaire`). Au-delà du prix, il impose
une **isolation comptable complète** vis-à-vis du standard (exigence **légale**) : tout flux solidaire
atterrit sur des comptes **séparés**, jamais mêlés au standard. Conséquence : chaque *Produit de
facturation* existe en deux exemplaires parallèles — standard et solidaire — et le catalogue
sélectionne le bon selon ce drapeau (ADR 0013).
_Éviter_ : réduire le solidaire à une **remise** (ce n'est pas qu'un prix : c'est une comptabilité isolée).

**Journal des actes** :
Le registre **append-only** possédé par la *Souscription* (`souscription.consentement` — le nom
technique reste, le vocabulaire vivant est *Journal des actes*, ADR 0027) où chaque **Acte** du·de
la *souscripteur·rice* est tracé : une ligne = une **finalité**, un **horodatage**, la **version du
texte montré**, une **source/canal**. Deux **natures** d'actes :
- **consentement RGPD** (cf. *Consentement (données de consommation)*) — **révocable** : le retrait
  **ajoute** une ligne, n'écrase rien ;
- **acte d'adhésion** (acceptation CGV, renonciation au délai de rétractation) — **irrévocable**
  (one-shot contractuel : on ne « retire » pas une signature) : le journal **refuse** le retrait ;
  l'horodatage **est** la date de signature.
L'état courant d'une finalité est sa **dernière** ligne ; l'**absence de ligne** est la seule
représentation du « non » (pas d'acte = pas de preuve). Les *conditions particulières* lisent le
journal, jamais des champs plats.
_Éviter_ : « journal de consentement » pour l'ensemble (le consentement RGPD n'est qu'une des deux
natures) ; un booléen ou une date plate comme preuve d'un acte ; fabriquer une ligne sans acte réel.

**Consentement (données de consommation)** :
La base légale RGPD (art. 6-1-a) par laquelle un·e *souscripteur·rice* autorise EDN à faire
**collecter auprès d'*Enedis*** ses données de consommation **plus fines que l'index de
facturation** (consommations quotidiennes transmises au fournisseur, courbe de charge). Distinct de
l'**acceptation contractuelle** (CGV / *conditions particulières*) et du **mandat SEPA**. Capté par
un **acte positif** au *raccordement* (formulaire public, cases **non** pré-cochées, **par
finalité**), tracé dans le *Journal des actes* — preuve opposable
(*accountability*, art. 7-1) à la CNIL **et** à Enedis (à qui EDN **déclare** détenir le
consentement), retrait compris (art. 7-3). L'**index** seul, pour facturer, relève de l'**exécution
du contrat** (art. 6-1-b) et **ne requiert pas** de consentement.
_Éviter_ : le confondre avec l'acceptation des CGV (contractuel) ou avec une « signature » (il n'y
en a pas, cf. *conditions particulières*) ; le réduire à un **booléen** (la preuve exige horodatage
+ version du texte + retrait) ; « consentement » pour l'index de facturation (c'est l'exécution du
contrat).

**Geste commercial** :
Ajustement par le·la *facturiste* de ce qui est **facturé** à un·e souscripteur·rice pour raison
commerciale (ex. : RES oubliée non encore traitée par Enedis → jours facturés réduits), assumé
comme distinct de la réalité *physique* mesurée par electricore. Deux maisons selon sa langue :
en **quantités/jours**, il s'applique à la *Période* (tant qu'elle n'est pas gelée) ; en
**euros**, c'est une **ligne manuelle** du brouillon de *Facture* — traçable telle quelle sur la
facture émise.
Sur la *Campagne*, une **porte** « Gestes commerciaux » garde l'**émission** : le·la *facturiste*
confirme les avoir appliqués avant le gel.
_Éviter_ : maquiller une ligne **générée** ou une quantité pour porter une remise en euros (le
geste reste une ligne identifiable).

**Refacturation (Enedis)** :
En-cours refacturable d'origine **Enedis** que le fournisseur **refacture** au·à la
*souscripteur·rice* (`souscription.refacturation`). Porte une *Référence de contenu*, un *Code
Enedis*, un libellé, un prix et une quantité. **Indépendante de la _Période_** : ce n'est pas un fait mensuel mais un en-cours rattaché à
un·e *souscripteur·rice*, qu'une *Facture* **rassemble** au moment de la facturation (plusieurs
*Refacturations* par *Facture*).
Deux **natures** :
- **prestation** — service **taxé** (mise en service, déplacement, changement de puissance…) ;
- **indemnité** — pénalité due par Enedis (p. ex. coupure), **hors champ TVA**, au **bénéfice** de
  l'usager·ère (montant pouvant être négatif).
La *nature* (et le *tarif solidaire*) choisit le *Produit de facturation*, qui porte le compte et la
TVA (la TVA suit le produit, ADR 0009 §5). Distincte du *Geste commercial* (ajustement *à la baisse*
sans contrepartie réseau) : une *Refacturation* a une contrepartie Enedis identifiée.
**États** (du point de vue du·de la *facturiste*) : **à refacturer** (défaut — dans la file, balayée
par la facturation automatique), **en attente** (retirée de la file *à la main* sur un doute, donc
**exclue** de la facturation automatique jusqu'à levée), **facturée** puis **émise** (cf. *Facture* —
dès qu'une *Facture* la rassemble, resp. une fois finalisée). C'est la **responsabilité du·de la
_facturiste_** de vérifier les *Refacturations* (montants élevés en priorité) **avant** de créer les
factures : il n'y a pas de garde-fou bloquant.
_Éviter_ : **« prestation » pour désigner l'ensemble** (c'est une *nature*, pas l'umbrella — dire
*Refacturation*) ; « presta » seule ; *service* ; confondre avec un *Geste commercial* ; **« en attente »
pour la file par défaut** (c'est *à refacturer*).

**Référence de contenu** :
La clé d'identité d'une *Refacturation* (champ `reference`, libellé « Référence (electricore) »),
**fabriquée par electricore** à partir du contenu de la ligne (contrat `prestations` v1, cf.
Energie-De-Nantes/electricore#590 et `docs/contrat-prestations.md` côté electricore). Ce n'est
**pas** une référence Enedis : le flux F15 n'a **aucun identifiant de ligne**. Le champ porte le
nom exact du payload du contrat (`reference` — symétrie producteur/consommateur) et une contrainte
UNIQUE : c'est elle qui rend le sync pull-tout-et-dédup **idempotent** (ADR 0009 §2).
_Éviter_ : « référence Enedis » (le F15 n'en fournit pas) ; confondre avec le *Code Enedis* (qui
identifie le **type** de prestation au catalogue Enedis, pas une ligne précise).

**Facturiste** :
Rôle métier qui conduit la facturation mensuelle depuis Odoo et **vérifie les données avant
émission** des factures. Public cible de l'interface de vérification. Sa *Campagne de
facturation* est son tableau de bord — le pendant, côté facturation, du kanban de
*raccordement* de l'*accueilliste*.

**Campagne de facturation** :
Le tableau de bord mensuel du·de la *Facturiste* (`souscription.campagne.facturation`), pendant
du kanban de *raccordement*. **Un enregistrement par mois** : orchestre les étapes de la
facturation du mois — pulls electricore (méta-périodes, prestations F15), vérifications, création
puis émission des factures — sous forme de **matrice à prérequis**, un **DAG d'étapes fixes**
(pas une file linéaire : le sync F15 et le pull méta-périodes sont indépendants). Chaque étape
affiche un **reste-à-faire dérivé** des données là où le signal existe (périodes tirées, factures
créées/émises) et une **porte de validation manuelle** là où il manque (vérifs) : la campagne ne
porte **aucun** drapeau de vérification sur les *Périodes* ni les *Refacturations* — elle reste
une fine couche d'orchestration au-dessus d'états **dérivés**. Draine un **statut de facturation
par souscription** dérivé à **zéro champ** (à tirer → à facturer → facturée → émise). Porte des
**notes** dont certaines, marquées « à reporter », renaissent en **prérequis (rappel doux, non
bloquant)** de la campagne suivante à sa création — les validations manuelles et ces notes sont
le seul état vraiment **persisté**, l'historique n'étant que la liste des campagnes passées. Le
DAG est pensé pour être **rejouable par un automate** (facturation automatique suivant les mêmes
étapes qu'un humain). L'ancien champ stocké « État de facturation » (`etat_facturation_id`,
modèle `souscription.etat`) est supprimé (#180) : c'était un reliquat pré-Campagne, jamais
transitionné par la logique métier — le statut dérivé ci-dessus est désormais le seul vocabulaire
vivant.
_Éviter_ : **cycle de facturation** pour l'instance (c'est la *récurrence* / le nom du menu, pas
l'enregistrement mensuel) ; **pipeline linéaire** (les étapes forment un DAG) ; instrumenter les
*Périodes* / *Refacturations* d'un drapeau « vérifiée » (la vérif est une porte à la maille
campagne).

**Périmètre de campagne** (souscriptions concernées par le mois M) :
L'ensemble des *Souscriptions* qu'une *Campagne de facturation* du mois M doit traiter — base de
tous ses **reste-à-faire** dérivés (pull, création, émission). Défini par **recouvrement de
l'intervalle de service avec M**, calculé sur les **dates propres** de la Souscription : RSC
acquise **et** `date_debut ≤ dernier jour de M` **et** (`date_fin` vide **ou** `date_fin ≥ premier
jour de M`). C'est **historique et figé** par le mois — à distinguer de l'état *En service* qui est
un **instantané vivant** (« a une RSC et n'est pas encore résiliée *aujourd'hui* »). Utiliser
l'instantané pour cadrer une campagne d'un mois passé **sur-compte** les souscriptions entrées en
service après M (jamais concernées, reste-à-faire jamais résorbé) et **sous-compte** celles
résiliées depuis (concernées par M, mais devenues *Résiliée*). Corollaire : la justesse du périmètre
**dépend** de la fiabilité de `date_debut` / `date_fin`.
_Éviter_ : cadrer le périmètre sur `etat == 'en_service'` (instantané, pas maille-mois).

**Lettre du mois** :
Le corps **éditorial** du mail qui accompagne les factures mensuelles — porté par la *Campagne de
facturation*, donc **une par mois**, historisée, jamais écrasée. Rédigée par le·la *Facturiste* et
**reportée depuis la campagne précédente** à sa création (même idiome que les *notes* « à
reporter », qui chaînent N → N+1 → N+2…) : l'evergreen — permanences, tarif solidaire, appels à
bénévoles — se transmet sans retype **ni déploiement**, seules les dates changent. Le *template*
de mail, lui, vit en git et ne porte que le **squelette transactionnel** — bonjour, n° et montant
de facture, instruction de paiement, signature — qu'un édit éditorial ne doit **jamais** pouvoir
casser. La *Facture* **tire** la lettre via son propre mois (`periode_id.mois` → campagne du mois,
`UNIQUE(mois)` rend la résolution non ambiguë) ; la campagne ne la pousse pas — le corps est rendu
une fois **par facture**, avec le montant et le client que seule la facture connaît. Une **porte**
manuelle ferme la fenêtre éditoriale avant l'envoi : valider avec une lettre **vide** est
légitime (« rien à dire ce mois-ci ») — la porte valide une **décision**, pas une écriture.
_Éviter_ : « mot du mois » / « encart » / « blurb » (ce n'est pas un bloc inséré dans un texte
permanent — c'est **tout** l'éditorial, evergreen compris, sinon changer un horaire de permanence
redemande un dev) ; « newsletter » au sens `mass_mailing` (elle ne part jamais seule, elle
chevauche la facture) ; porter la lettre sur `res.company` (globale, écrasée d'un mois sur
l'autre, et hors d'atteinte du·de la *Facturiste*, qui n'a pas `base.group_system`) ; la faire
porter par les factures de **régularisation** (une clôture est la facture de quelqu'un qui part).

**Textes permanents** (des mails de facture) :
L'**éditorial sans rythme** des mails de facture — paragraphe difficultés (aides, étalement),
appel au don sur les avoirs, accusé de prise en compte d'une résiliation. Même nature que la
*Lettre du mois* (écrit par le·la *Facturiste*, c'est sa voix et sa politique sociale, jamais du
squelette), mais **sans mois** : il accompagne les projections d'une *Régularisation*, qui n'ont
pas de *Campagne* d'où se reporter. D'où un second foyer — des champs de **configuration** propres
au module, sous ACL du module. La ligne de partage entre les deux foyers est le **rythme**, pas le
contenu : mensuel → la Lettre, sans rythme → les Textes permanents. Ce qui n'est **pas** éditorial
(l'instruction de paiement et ses dates — un chemin d'argent) reste en git, revu et testé.
_Éviter_ : les porter par `res.company` / `res.config.settings` (écriture réservée à
`base.group_erp_manager` / `base.group_system` — hors d'atteinte du·de la Facturiste) ; les laisser
dans le corps du *template* (le module le ré-affirme au déploiement : tout édit manuel y est
silencieusement écrasé — cf. ADR 0034, « l'éditorial est toujours un champ ») ; en faire une
variante de mail **par mode de paiement** (le paiement est un bloc **orthogonal** à la situation,
c'est ce qui remplit d'un coup les cases Moneko manquantes).

**Accueilliste** :
Rôle métier qui instruit les demandes de *raccordement* au quotidien : accueil des nouvelles
demandes, demandes SGE selon la *situation d'entrée* (F120 / F130), saisie de l'*id_Affaire*,
calcul des mensualités et validation de l'abonnement une fois la mise en service effective.
Le kanban de raccordement est son tableau de bord.
_Éviter_ : le confondre avec le·la *facturiste* (facturation mensuelle, autre rôle).

**Raccordement** :
Le workflow d'**entrée** (kanban `raccordement.demande`), conduit par l'*accueilliste*, qui
instruit une demande de fourniture de l'arrivée du formulaire jusqu'à la **validation de
l'abonnement** (étape « Abonnement Validé ») : acceptation (pour les PRO, décision du *collège*),
demande SGE selon la *situation d'entrée* (F120 / F130), saisie de l'*id_Affaire*, **suivi de
l'affaire** Enedis — automatisé par la résolution périodique `id_Affaire → RSC` (ADR 0021/0022) —
puis calcul des mensualités une fois la mise en service effective. À l'**acceptation** il
**crée** le·la *souscripteur·rice*, le compte bancaire et la *Souscription* — née *en instance*
(cf. *En instance / En service*) ; un mail de **rassurage** part quand la demande SGE est
déposée, les *conditions particulières* partent **complètes** à la validation de l'abonnement.
Les étapes à entrée **factuelle** (id_Affaire saisi, RSC acquise) avancent seules et ne se
forcent pas : on corrige le fait, la carte suit. Chaque colonne du kanban dit qui doit agir :
**action attendue** (un humain), **attente externe** (personne — le poll veille), **fait**.
C'est le point de **capture** des données
saisies à l'adhésion — **dont les actes** (consentements, acceptation CGV, renonciation —
équivalent du *LSD* de prod) —, **journalisées** dans le *Journal des actes* de la *Souscription*
qui en devient **propriétaire** (système de
référence) ; la *demande* reste un intake transitoire. Les *conditions particulières* lisent ces
données sur la *Souscription*, jamais sur la demande.
_Éviter_ : confondre la **demande de raccordement** (intake) et la *Souscription* (l'enregistrement
qu'elle engendre) ; « raccordement » au sens réseau Enedis (mise en service physique du PDL) ;
**« Souscrit » ou « En service » comme colonnes** (la chaîne se clôt à « Abonnement Validé » ;
la mise en service est un fait porté par la *Souscription*, reflété par « Validé sur SGE »).

**Situation d'entrée** :
La voie SGE par laquelle un·e *souscripteur·rice* entre dans le périmètre : **mise en service**
(F120 — PDL hors service, emménagement) ou **changement de fournisseur** (CFNE F130 — PDL
alimenté par un autre fournisseur). Déclarée au formulaire de souscription, **corrigeable par
l'accueilliste** (l'erreur du demandeur est un cas nominal) ; elle route le suivi de l'affaire
dans la branche F120 ou F130 du *raccordement*.
_Éviter_ : « type de demande » (trop générique) ; la confondre avec la *Configuration fournisseur*.

**Collège (PRO)** :
Instance humaine qui **accepte** les demandes professionnelles : elle valide le PRO **et son
tarif** (la *Majoration PRO* négociée) avant de faire avancer la carte — l'acceptation d'un PRO
n'est jamais le geste d'un·e seul·e *accueilliste*.

**Portail** :
Espace en ligne en lecture du·de la *souscripteur·rice* (contrats, factures, infos utiles),
pensé dans une logique de commun (évolutif). L'historique des consommations (les *Périodes*
dont la *Facture* est **émise**) est présenté **directement** dans la page de détail d'une
*Souscription*, sans page dédiée.
_Éviter_ : espace client.
