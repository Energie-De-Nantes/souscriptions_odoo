# Migration vers Odoo 19 sur odoo.sh : reprise complète de la base, bascule unique combinée, conditionnée à electricore

La production tourne déjà sur **odoo.sh en version 17**, sur des **abonnements natifs Odoo** habillés de **Studio** (champs `x_`, automatisations, rapports personnalisés), avec des factures légales déjà émises (chaîne de hachage NF, inaltérables). electricore **écrit** aujourd'hui dans Odoo ; le prototype code historique du module n'a **jamais** été en production. Cible : `souscriptions_odoo` (réécrit) sur Odoo 19, electricore basculé en lecture (Odoo *tire* les méta-périodes, cf. [ADR-0001](0001-odoo-systeme-ecriture-electricore-api-read-only.md)).

**Décision.** On **reprend la base entière** (« lift-and-upgrade ») via le **service d'upgrade managé d'Odoo** intégré à odoo.sh — l'historique de factures reste *vivant* dans le système, hachage intact. On exécute **une seule bascule combinée** (upgrade 17→19 + déploiement du module + ETL des contrats + bascule de l'intégration electricore), **répétée jusqu'à fiabilité sur une branche de *staging* neutralisée**, puis tirée dans une fenêtre d'arrêt courte. On **reste sur 17 tant que les trois pieds — endpoint de lecture electricore, module installable sur 19, ETL prouvé — ne sont pas tous debout**, quitte à dépasser la fin de support de 17. Le **chemin critique est l'endpoint de lecture electricore (ADR-0001), non encore cadré** : il conditionne toute la bascule métier ; le reste, côté Odoo, est mécanique et répétable en parallèle.

## Options écartées

- **Base 19 neuve + à-nouveaux comptables** : repart propre, mais sort l'historique de factures du système vivant (re-hachage impossible à l'identique), élargit la surface d'ETL et oblige à conserver l'ancienne instance comme archive légale. La reprise complète est plus sûre vu l'inaltérabilité NF.
- **OpenUpgrade auto-géré** : on est sur odoo.sh (Entreprise) → le service managé fait l'upgrade des modules *standard* sans script ; OpenUpgrade 19 était par ailleurs incomplet début 2026 (lot `account` non terminé).
- **Bascule en deux temps (upgrade maintenant, métier plus tard)** : écartée car l'arrêt total est requis de toute façon et les champs Studio sont *remplacés* par le module — pas d'état intermédiaire « 19 + abonnements natifs » qui mérite d'être préservé. Deux arrêts pour aucun gain.
- **Bascule combinée *rapide* pour battre l'horloge de support** : écartée — on refuse de précipiter une migration métier sur de vraies factures clients pour tenir un calendrier. Correction avant calendrier.

## Conséquences

- **Risque d'horloge assumé.** À la sortie d'Odoo 20 (~fin 2026), 17 sort de la fenêtre des 3 versions supportées par odoo.sh : plus de correctifs de sécurité, et odoo.sh peut à terme *forcer* l'upgrade. Plus l'attente dure, plus le saut final grossit (17→20, 17→21…) et plus la casse Studio à absorber dans la fenêtre unique s'alourdit. Tenable **seulement si l'endpoint electricore reste une priorité active**. *À vérifier* : la politique réelle d'odoo.sh sur l'exécution d'une version hors support (durée de grâce, backports sécurité).
- **Extraction des données contrat *avant* l'upgrade.** L'ETL ne doit pas dépendre de la survie des champs Studio au saut de version : on snapshote la source depuis la base 17, puis upgrade, puis charge `souscription.*` depuis le snapshot.
- **Au moment de la bascule, dans la même fenêtre : désactiver les automatisations Studio *et* stopper les abonnements natifs** avant que le module ne prenne la main sur la facturation — risque n°1 de double facturation de clients réels.
- **ETL idempotent, clé sur identifiants externes**, ordonné par dépendances (partenaires → grilles → contrats → périodes), dans un **dépôt de migration jetable** (jamais dans l'addon).
- **Standard de migrabilité future** (le vrai gain) : tout dans l'addon versionné (zéro Studio), **champs typés et non `Char`**, l'addon embarque ses propres scripts `migrations/<version>/` → le saut 19→20 devient un script relu, pas de l'archéologie.
- Le glossaire ([CONTEXT.md](../../CONTEXT.md)) n'est pas touché : aucune notion métier nouvelle, c'est une décision d'exploitation.

## Raison

Sur de vraies factures inaltérables, on veut un grand livre *ennuyeux et intact* (reprise complète managée) et une bascule métier *faite une fois, correctement* (fenêtre unique répétée sur staging), pas une migration rapide tributaire d'un calendrier. La réécriture « propre » concerne le schéma *du module*, pas la comptabilité.
