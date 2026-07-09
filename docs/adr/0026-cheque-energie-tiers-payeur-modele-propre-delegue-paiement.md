# 0026 — Chèque énergie : tiers-payeur, modèle propre déléguant le lettrage à un `account.payment`

## Statut

Accepté (grill 2026-07-09).

## Contexte

Le chèque énergie est une aide de l'État versée **au fournisseur à la place** de
l'usager·ère. On veut le suivre (identité, état, solde) et l'imputer sur les *Factures*.

**Constat prod** (mirror `energie-de-nantes.odoo.com`) : le mécanisme existe déjà, mais
manuel et incohérent. Deux produits « acompte » posés à la main, ligne par ligne :
« Déduction acompte chèque énergie » (négatif → compte **419100 avances**, **sans TVA**,
~20 usages) et « Acompte chèque énergie » (positif → compte de **CA 707100**, 2 usages,
apparemment une erreur). Aucun suivi : ni valeur nominale, ni état, ni solde, ni lien entre
« chèque reçu de 194 € » et les déductions qui le consomment.

## Décision

**1. Nature — tiers-payeur, pas remise.** Le chèque ne minore ni le CA ni la TVA de la
*Facture*. La *Facture* reste à 100 % ; le chèque la **paie** partiellement. Il apparaît en
« payé / reste à payer », **jamais en ligne négative**. On abandonne donc la ligne de
déduction (produit 331) de la prod.

**2. Mécanique — `account.payment` lettré.** Le chèque génère un paiement entrant
(journal dédié « Chèques énergie »), lettré contre les *Factures* de l'usager·ère :

```
Dr  « Chèques énergie à recevoir de l'État » (actif)   194
    Cr  411 usager·ère (crédit en attente)                  194   → lettré contre les Factures
```

Le virement réel de l'État solde ensuite le compte « à recevoir » au relevé bancaire. On
récupère **natifs** : le **solde** (`amount_residual`), l'imputation **multi-factures**,
`min(solde, total)` sans négatif, et le **lettrage automatique** (outstanding credits +
petit hook à la création de facture, ordonné **FIFO par expiration**).

**3. Modèle — propre, déléguant.** `souscription.cheque_energie` **possède** l'identité
(numéro, montant, expiration) et le **cycle de vie** (reçu → validé → rejeté/expiré) ; il
**crée et poste** un `account.payment` lié à la **validation** (le gate), et lit le solde
en `related` sur celui-ci. Il ne réimplémente **pas** solde ni lettrage.

## Alternatives écartées

- **Garder la ligne de déduction (statu quo prod).** Manuel, sans suivi, et fragile
  comptablement (produit 332 qui gonfle le CA). Rejeté : c'est le problème, pas la solution.
- **Zéro modèle, étendre `account.payment` (3 champs + journal).** Le plus court. Rejeté :
  (a) le cycle de vie métier (rejeté-par-l'État, expiré) se plie mal à draft/posted/cancelled ;
  (b) la **tranche 2 portail** exigerait d'exposer un modèle comptable central à l'**écriture
  publique** — surface à risque. Le couplage à la réconciliation, lui, est **identique** aux
  deux designs (B1 l'impose), donc l'extension n'achète pas de découplage.
- **Modèle propre réimplémentant solde + imputation.** Rejeté : réinvente la réconciliation
  Odoo (la roue à ne pas refaire).

## Conséquences

- Le v1 ne touche **pas** au versant encaissement au sens manuel : le compte « à recevoir de
  l'État » est soldé par le rapprochement bancaire habituel (le paiement crée juste la
  créance lettrable).
- Setup compta requis : journal « Chèques énergie » + compte « chèques énergie à recevoir de
  l'État ».
- Le portail (saisie usager) est une **tranche séparée** : elle tape sur
  `souscription.cheque_energie`, jamais sur `account.payment` — c'est la raison d'être du
  modèle propre.
- Couplage résiduel à Odoo : la création/le lettrage du `account.payment`. Assumé (B1
  l'impose de toute façon), rangé derrière le modèle.
