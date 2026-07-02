# Migration des contrats : reprise à 100 %, mois régularisés réputés soldés, backfill ciblé des mois non régularisés, régularisation enjambante côté nouveau système

Complète l'[ADR-0003](0003-strategie-migration-odoo19-odoo-sh.md) (stratégie d'upgrade et de bascule) en fixant les décisions de **données** de l'ETL `sale.order` (abonnements 17 + champs Studio) → `souscription.*`, instruites par exploration read-only de la prod (juillet 2026, ~1 022 contrats : 823 en cours, 168 résiliés). Point clé découvert : les régularisations prod des contrats lissés sont **~annuelles, à date anniversaire non synchronisée, calculées à la main en xlsx** (sans gérer les changements de compteur) — il n'existe aucun mécanisme de régul fiable dans le système sortant.

**Décisions.**

1. **Reprise à 100 %** : tous les contrats migrent en `souscription.*`, résiliés compris (`date_fin` → état *résiliée* dérivé). Pas de cohabitation opérationnelle avec les abonnements legacy (cassés en 19 de toute façon) ; ils restent en base liftée comme archive morte. Les chaînes de renouvellement fusionnent en **une souscription par RSC** (contrainte d'unicité) ; brouillons et sans-état sortent au rapport pour triage humain.
2. **Mois régularisés = soldés** (*settled is settled*) : on ne rouvre jamais un mois couvert par une facture de régul prod, même si le calcul xlsx était douteux — rouvrir = avoirs en cascade sur des factures NF inaltérables. La frontière par contrat = fin de couverture de sa dernière facture de régul (parsée dans les lignes « *Mois — Ecart de X kWh* »).
3. **Backfill ciblé, et seulement lui** : pas de reconstruction des Périodes historiques (réversible : electricore garde tout, un backfill ultérieur reste possible), **sauf** les mois non régularisés des contrats lissés : l'ETL crée ces Périodes depuis les factures prod (provision kWh **facturée**, jours, prix appliqué), liées aux factures legacy. Ce sont des Périodes légitimes au sens du modèle : elles portent du *facturé*.
4. **Pas de régul générale pré-bascule** : le seul calculateur de confiance est la régularisation du nouveau système (rejeu des Périodes aux prix historiques, ADR-0008, quantités electricore). Sa **première exécution enjambe la couture** et solde le span non régularisé (jusqu'à ~11 mois selon l'anniversaire) avec la machinerie normale — zéro code spécial migration.
5. **Consentements** : journal vide à la migration — la prod n'a jamais capté de consentement granulaire données de conso (seulement l'acceptation CGV + recontact). Seuls les faits contractuels migrent (date de validation, renonciation à la rétractation dérivée du choix de mise en service). Le trou de conformité sur la collecte quotidienne devient visible → campagne de recueil post-bascule (décision métier, hors migration) ; si les CGV contiennent une clause, une entrée sourcée « CGV vX » reste ajoutable après coup (journal append-only).

## Options écartées

- **Migrer les seuls contrats actifs** : impose de consulter deux systèmes au quotidien avec un legacy dysfonctionnel en 19.
- **Régul générale en prod avant bascule** : un dernier tour de xlsx à grande échelle sur de vraies factures ; et le délai de consolidation Enedis (~1,5 mois) laisserait de toute façon un résidu non régularisé.
- **Backfill complet depuis electricore** : archéologie comptable massive adossée à une migration déjà risquée, pour un besoin (portail/analytique rétroactifs) non confirmé — et réversible plus tard, contrairement au reste.
- **ETL des demandes de raccordement en vol** : ~23 cartes au fil de l'eau ; re-saisie manuelle dans le nouveau kanban (piloté par les faits) = une heure humaine + revue de contrôle gratuite, l'ETL d'un modèle Studio ne s'amortit jamais.

## Conséquences

- **Chantier modèle pré-migration** (bloquant pour le load) : axe *régime de prix* sur `grille.prix` + désignation sur la souscription (~14 contrats Moulin), champ adresse du PDL, champ *blaze* sur le partenaire, support des Périodes d'ouverture backfillées.
- **Grilles historiques à seeder** jusqu'au plus vieux mois non régularisé du parc (le rapport d'extraction en donne la profondeur) — saisies main, contre-vérifiées par l'ETL sur les prix des lignes prod (`prix ligne = grille(régime, date) × (1 + coeff_pro dérivé)`).
- Le chantier **régularisation (#20)** devient le jalon aval de la migration ; simple sur le parc communicant, terrain vierge sur le non-communicant → le rapport segmente les lissés par type de compteur.
- Premières réguls potentiellement grosses (plusieurs mois d'écarts) : communication aux souscripteur·rices à préparer dans la check-list de bascule.
- Données réelles en dev sous garde-fous : snapshots hors git, SMTP neutralisé, crons off, pas de génération SEPA, instance non exposée.

## Raison

On minimise les actes dans le système mourant (aucune facturation nouvelle pilotée par le legacy, aucune régul xlsx supplémentaire) et on donne au nouveau système exactement les entrées dont sa machinerie normale a besoin pour solder le passé **correctement** — plutôt que de perpétuer un calcul faux pour fabriquer une couture « propre » en apparence.
