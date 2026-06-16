# Isolation comptable solidaire / standard : jeux de produits de facturation parallèles

Le *tarif solidaire* n'est pas qu'un prix réduit : il impose une **isolation comptable complète** du
solidaire vis-à-vis du standard — exigence **légale**, les deux univers de comptes ne doivent
**jamais** se mêler. Cet ADR fixe **comment** Odoo porte cette isolation côté facturation.

## Décision

Chaque *Produit de facturation* ([CONTEXT.md](../../CONTEXT.md)) existe en **deux exemplaires
parallèles** : un **standard** et un **solidaire**, chacun câblé sur ses propres comptes (et, le cas
échéant, sa propre TVA). L'axe `is_solidaire` n'est donc ni un attribut de ligne ni une position
fiscale : c'est le **sélecteur de l'univers comptable**.

La résolution *rôle → produit* vit dans un **catalogue** unique (`souscription.produit`,
`AbstractModel` sans donnée propre), structuré en **deux mondes parallèles** :

```
{ standard:  { abonnement, energie:{base,hp,hc}, refacturation:{prestation,indemnite} },
  solidaire: { abonnement, energie:{base,hp,hc}, refacturation:{prestation,indemnite} } }
```

→ **12 produits** (6 rôles × 2 univers). Le catalogue est l'**unique point** qui choisit l'univers ;
aucune ligne ne traverse. `produits_requis()` énumère les deux mondes et permet de **vérifier que le
catalogue est complet** (un produit manquant = un trou d'isolation = échec visible).

Cet ADR **étend** l'invariant d'[ADR-0009 §5](0009-prestation-refacturer-modele-independant-rassemble-sur-facture.md)
(« la TVA suit le produit ») : le **compte** *et* la TVA suivent le produit, et le produit suit le
couple (rôle, univers).

## Conséquences

- **Doublement du catalogue** : tout nouveau rôle de facturation se décline d'office en standard +
  solidaire. C'est voulu (l'isolation est par construction), **pas** une duplication à factoriser.
- **Un seul endroit applique l'axe solidaire** — le catalogue. Les composeurs (*Période*,
  *Refacturation*, *Grille de prix*) passent le drapeau ; ils n'incarnent pas la règle d'isolation.
- **Surface de test** : l'isolation se teste à l'interface du catalogue (le bon univers pour
  `(rôle, solidaire)`) et par `produits_requis()` (complétude), pas dispersée sur chaque composeur.

## Options écartées

- **Produit unique + position fiscale / compte mappé par solidaire** : la position fiscale gère la
  *TVA du client*, pas la **ségrégation des comptes de produits** ; et un override resterait local à
  la ligne — insuffisant pour une isolation *complète* et auditable.
- **Tag analytique solidaire sur une ligne standard** : l'analytique double la compta générale, elle
  ne l'**isole** pas ; les deux univers partageraient les mêmes comptes généraux — non conforme.
- **Sociétés séparées (multi-company)** : isolation totale mais surdimensionnée pour un même
  fournisseur, une même facturation, un même portail.

## Raison

L'exigence est **légale et binaire** (isolation complète), donc elle doit être **structurelle**, pas
une convention qu'une ligne peut contourner. Porter l'univers par le **produit** — déjà le support du
compte et de la TVA ([ADR-0009 §5](0009-prestation-refacturer-modele-independant-rassemble-sur-facture.md)) —
et centraliser le choix dans **un** catalogue rend l'isolation *impossible à franchir par accident*
et *vérifiable* (`produits_requis`).
