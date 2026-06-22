# Souscriptions (module Odoo)

Module Odoo de gestion des contrats de fourniture d'électricité. Il porte le contrat, les
données de facturation historisées, les grilles de prix **fournisseur**, la facture légale,
les paiements et le portail. Tout le savoir métier **réseau** (énergies par cadran, TURPE,
accise, CTA, périmètre, événements C15) est calculé par
[electricore](https://github.com/Energie-De-Nantes/electricore) et consommé via son API.

## Vocabulaire partagé (défini ailleurs)

Le vocabulaire métier neutre — **PDL, RSC, cadran, HP/HC/Base, FTA, TURPE, accise, CTA,
méta-période, provision d'énergie, contrat lissé, facturation calendaire, régularisation** —
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
*raccordement*) — le PDL restant un attribut d'affichage/recherche.
_Éviter_ : **abonnement** (collision triple — le module Odoo de facturation récurrente qu'on
remplace, le terme pipeline d'electricore, la catégorie produit « Abonnements ») ; **devis**,
**commande**, `sale.order` (explicitement non utilisés : pas de cycle de vente) ; contrat
(trop générique).

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
`periode_id`). Porte un **index** (compteur cumulé) **par cadran réseau** — même axe *mesuré* que
les `energie_*` (registres physiques : HPH/HPB/HCH/HCB, ou HP/HC, ou Base selon le *calendrier de
comptage*), jamais par cadran **facturé**. Consigne **tous les index qu'electricore a utilisés**
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

**Grille de prix** :
Barème **fournisseur** daté (`grille.prix`), **tout-compris** : le TURPE y est **absorbé**, jamais
refacturé ligne à ligne (ADR 0002). Porte le prix d'abonnement **affine** — prix de base 3 kVA +
coefficient par kVA supplémentaire (ADR 0018) — et le prix de l'énergie par cadran facturé.
Sélectionnée par les dates d'une *Période*, ce qui permet de facturer une *régularisation* aux prix
historiques.
_Éviter_ : tarif (collision avec la FTA / tarif d'acheminement réseau), barème ; « prix par palier »
(l'abonnement est **affine**, pas tabulé par puissance).

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
être facturé en Base. electricore renvoie le détail par cadran réseau ; Odoo le **regroupe**
selon la formule fournisseur.
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
*souscripteur·rice* (`souscription.refacturation`). Porte un *Code Enedis*, un libellé, un prix et une
quantité. **Indépendante de la _Période_** : ce n'est pas un fait mensuel mais un en-cours rattaché à
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

**Facturiste** :
Rôle métier qui conduit la facturation mensuelle depuis Odoo et **vérifie les données avant
émission** des factures. Public cible de l'interface de vérification.

**Raccordement** :
Le workflow d'**entrée** (kanban `raccordement.demande`) qui instruit une demande de fourniture,
de la demande jusqu'à l'étape **« Souscrit »** ; à sa clôture il **crée** le·la
*souscripteur·rice*, le compte bancaire et la *Souscription*. C'est le point de **capture** des
données saisies à l'adhésion — **dont les consentements et la signature** (équivalent du *LSD* de
prod) —, **recopiées** sur la *Souscription* qui en devient **propriétaire** (système de
référence) ; la *demande* reste un intake transitoire. Les *conditions particulières* lisent ces
données sur la *Souscription*, jamais sur la demande.
_Éviter_ : confondre la **demande de raccordement** (intake) et la *Souscription* (l'enregistrement
qu'elle engendre) ; « raccordement » au sens réseau Enedis (mise en service physique du PDL).

**Portail** :
Espace en ligne en lecture du·de la *souscripteur·rice* (contrats, factures, infos utiles),
pensé dans une logique de commun (évolutif). L'historique des consommations (les *Périodes*
dont la *Facture* est **émise**) est présenté **directement** dans la page de détail d'une
*Souscription*, sans page dédiée.
_Éviter_ : espace client.
