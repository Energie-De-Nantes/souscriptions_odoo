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

**Période** :
Période mensuelle de facturation d'une *Souscription* (`souscription.periode`). **Brouillon de
travail facturable** : amorcé par les quantités calculées par electricore (méta-période), puis
**complété/corrigé par le·la facturiste** avant facturation — saisie manuelle d'estimations quand
le flux Enedis manque, *gestes commerciaux*, ajustements. À la facturation, ses valeurs (quantités
par cadran, jours, puissance, taxes) sont **figées** (historisation) et liées à la facture. Porte
ce qui est **facturé** — pas une copie du coût réseau ; la marge se calcule à la demande côté
analytique en rejouant electricore.
_Éviter_ : méta-période (concept amont, côté electricore), mois ; « instantané fidèle » (la Période
est un brouillon facturable, pas une copie figée d'electricore).

**Grille de prix** :
Barème **fournisseur** daté (`grille.prix`) : prix d'abonnement par puissance, prix de l'énergie
par cadran facturé. Sélectionnée par les dates d'une *Période*, ce qui permet de facturer une
*régularisation* aux prix historiques.
_Éviter_ : tarif (collision avec la FTA / tarif d'acheminement réseau), barème.

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

**Portail** :
Espace en ligne en lecture du·de la *souscripteur·rice* (contrats, factures, infos utiles),
pensé dans une logique de commun (évolutif). L'historique des consommations (les *Périodes*
dont la *Facture* est **émise**) est présenté **directement** dans la page de détail d'une
*Souscription*, sans page dédiée.
_Éviter_ : espace client.
