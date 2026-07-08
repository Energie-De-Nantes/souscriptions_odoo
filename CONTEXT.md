# Souscriptions (module Odoo)

Module Odoo de gestion des contrats de fourniture d'électricité. Il porte le contrat, les
données de facturation historisées, les grilles de prix **fournisseur**, la facture légale,
les paiements et le portail. Tout le savoir métier **réseau** (énergies par cadran, TURPE,
accise, CTA, périmètre, événements C15) est calculé par
[electricore](https://github.com/Energie-De-Nantes/electricore) et consommé via son API.

## Vocabulaire partagé (défini ailleurs)

Le vocabulaire métier neutre — **PDL, RSC, affaire / id_Affaire, cadran, HP/HC/Base, FTA,
TURPE, accise, CTA, méta-période, provision d'énergie, contrat lissé, facturation calendaire,
régularisation** —
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

**En instance / En service** :
États de cycle de vie de la *Souscription*, **calculés depuis les faits**, jamais saisis.
**En instance** : née à l'**acceptation** de la demande de *raccordement* (signée, consentements
journalisés) mais **sans RSC** : non facturable, ignorée du pull de facturation. **En service** :
la RSC est acquise — le C15 d'effectivité est arrivé, la mise en service est réelle (ADR 0022) —
facturable. La correction passe par le **fait** (la RSC), jamais par l'état. La résiliation
est un chantier distinct.
_Éviter_ : **brouillon** (la Souscription est conclue et signée ; « brouillon » est réservé à
la *Période* et à la *Facture*) ; « active » (collision avec l'archivage Odoo) ;
« raccordement effectué » comme bascule manuelle (l'état découle de la RSC, ADR 0021).

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
(les consentements et la date de signature sont **portés par la *Souscription***), jamais un
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
le flux Enedis manque, *gestes commerciaux*, ajustements. À la facturation, ses valeurs (quantités
par cadran, jours, puissance, taxes) sont **figées** (historisation) et liées à la facture. Porte
ce qui est **facturé** — pas une copie du coût réseau ; la marge se calcule à la demande côté
analytique en rejouant electricore. Elle est la **source analytique** typée : ses champs se lisent
et s'agrègent **directement**, jamais reconstruits depuis les lignes de facture (`ligne → produit →
catégorie`) ; la *Facture* en est une **projection** (dérive manuelle bornée tolérée, ADR 0014).
_Éviter_ : méta-période (concept amont, côté electricore), mois ; « instantané fidèle » (la Période
est un brouillon facturable, pas une copie figée d'electricore).

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
**Figé** avec le snapshot de la Période et verrouillé après facturation (ADR 0006/0014) ; le relevé
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
*Souscription* et les dates d'une *Période*, ce qui permet de facturer une *régularisation* aux prix
historiques.
_Éviter_ : tarif (collision avec la FTA / tarif d'acheminement réseau), barème ; « prix par palier »
(l'abonnement est **affine**, pas tabulé par puissance).

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

**Facture** :
Le document comptable légal (`account.move`, *facture d'énergie*) émis à partir d'une *Période*
qu'il référence (`periode_id`). Une *Période* est dite **facturée** dès qu'une *Facture* la
référence ; elle est **émise** (finalisée, opposable) à un état ultérieur. Seules les *Périodes*
dont la *Facture* est **émise** sont visibles du·de la *souscripteur·rice* au *Portail* — un
brouillon de facture ne fuite jamais côté usager.
_Éviter_ : confondre « facturée » (une facture existe) et « émise » (facture finalisée).

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

**Consentement (données de consommation)** :
La base légale RGPD (art. 6-1-a) par laquelle un·e *souscripteur·rice* autorise EDN à faire
**collecter auprès d'*Enedis*** ses données de consommation **plus fines que l'index de
facturation** (consommations quotidiennes transmises au fournisseur, courbe de charge). Distinct de
l'**acceptation contractuelle** (CGV / *conditions particulières*) et du **mandat SEPA**. Capté par
un **acte positif** au *raccordement* (formulaire public, cases **non** pré-cochées, **par
finalité**), tracé dans un **journal append-only** possédé par la *Souscription* — preuve opposable
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
comme distinct de la réalité *physique* mesurée par electricore.

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
émission** des factures. Public cible de l'interface de vérification.

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
saisies à l'adhésion — **dont les consentements et la signature** (équivalent du *LSD* de
prod) —, **recopiées** sur la *Souscription* qui en devient **propriétaire** (système de
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
