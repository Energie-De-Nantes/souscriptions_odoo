# Consommation d'electricore : client fin distribué à part (httpx+pydantic), contrat typé versionné, AGPL de bout en bout

*Statut : accepté. Le spike de packaging côté electricore (agent dédié) a retiré l'inconnue porteuse : un paquet fin polars-free est faisable, et même additif pour le moteur (les routers facturiste n'ayant aujourd'hui aucun `response_model`). Précision imposée par la structure réelle — `electricore/__init__.py` n'étant pas vide, deux distributions ne peuvent pas partager le nom de package `electricore` ; le client fin est donc un **top-level distinct `electricore_client`** (dist `electricore-client`, sous-projet `packages/` du monorepo). La conception complète (layout hatchling, modèles, plan de migration) fait l'objet d'un ADR propre côté electricore.*

Odoo consomme electricore **en lecture** ([ADR-0001](0001-odoo-systeme-ecriture-electricore-api-read-only.md), [ADR-0011](0011-contrat-pull-facturation-electricore-cle-rsc-mois.md)). Reste à fixer le **comment** côté code : par quoi l'addon parle au service. Premier endpoint visé : la *vue facturiste* `/facturation/chronologie` — frise diagnostique **affichée non stockée** ([ADR-0002](0002-deux-sources-de-verite-marge-en-analytique.md)) — puis plus tard `/facturation/meta-periodes` (pull facturation, [ADR-0011](0011-contrat-pull-facturation-electricore-cle-rsc-mois.md)). Les deux rendent la **même enveloppe JSON** (`grain`/`contract_version`/`filters`/`pagination`/`data`), lignes en `dict` non typées sur le fil. Le client Python *existant* d'electricore est polars/Arrow (pour notebooks distants) : inimportable ici, où polars/pandas sont proscrits (CLAUDE.md).

## Décision

1. **Client fin distribué à part.** Odoo dépend d'un paquet **`electricore-client`** léger (**httpx + pydantic**, zéro polars ; import `electricore_client`, top-level distinct — cf. statut), publié depuis le monorepo electricore et **épinglé** (tag git d'abord, cible PyPI pour un build odoo.sh sans clone). Ni l'import du paquet `electricore` (moteur lourd), ni un *extra* (les extras s'**ajoutent** aux deps de base lourdes — pas d'install léger possible ainsi).
2. **Contrat typé single-source.** Les types du contrat sont définis dans electricore et **réutilisés comme `response_model` FastAPI** : une **union discriminée sur `type_ligne`** (`Evenement | Releve | PeriodeEnergie`) pour la chronologie, un modèle méta-période pour l'autre. Le serveur *valide* contre exactement ce que le client *parse* ; Odoo reçoit des **modèles typés**, pas des dicts.
3. **Garde de version runtime, par endpoint.** `contract_version` est **indépendant par endpoint** (chronologie=1, méta-périodes=3), pas un numéro global. Le client compare au numéro attendu : `reçu > attendu` → *avertissement* (tolérance additive, `extra="ignore"`), `reçu < attendu` → *erreur dure*. Champ déjà présent sur le fil. Le pin (1) couvre le compile-time, la garde couvre la dérive *service déployé ↔ client*.
4. **Grain de la chronologie.** `pdl` d'abord — le champ existe déjà sur la souscription, et la vue « toute l'histoire du point » est légitime pour un diagnostic ; `rsc` (une tenure) quand la souscription portera la RSC ([ADR-0010](0010-identite-souscription-rsc-cle-id-affaire-amorce.md)). La pull méta-périodes, elle, est clé `(RSC, mois)` et **requiert** donc le champ RSC.
5. **Licence.** `electricore-client` reste **AGPL-3** ; l'addon est déjà AGPL-3 → import cohérent, aucune contamination à arbitrer.

## Conséquences

- L'addon ne dépend que du **contrat HTTP** + d'un paquet httpx/pydantic léger ; pas de polars/duckdb/fastapi dans le runtime Odoo (CLAUDE.md respecté). Runtime `odoo:19` = **Python 3.12.3**, dans le plancher electricore (`>=3.12,<3.14`) — l'extra aurait suffi côté Python, c'est la *réalité des deps* qui impose la distribution séparée.
- **Contrat single-source** : un changement de forme se fait dans electricore, le serveur le valide via ses `response_model`, le client (donc Odoo) suit par bump de version pinné. Pas d'édition parallèle de code de transport entre les deux repos.
- **Tests partagés proprement** : electricore teste client + sérialisation (union discriminée incluse) ; Odoo ne teste plus que son mapping modèles → `souscription.*`, en mockant le client.
- **Déploiement** : l'addon doit `pip install electricore-client` (git+tag ou PyPI) — nouvelle étape de build (odoo.sh).
- Le **packaging réel côté electricore** (sous-projet `packages/electricore-client`, top-level distinct, modèles servis aussi en `response_model`, client Arrow existant inchangé) est délégué à electricore et à son propre ADR ; le spike dédié l'a **confirmé faisable** et additif pour le moteur. Pièges à traiter là-bas : `int` vs `float` sur le fil JSON, et `releves_utilises` (colonne `pl.Object`) sous `response_model`.

## Options écartées

- **Importer le paquet `electricore`** : tire polars/duckdb/fastapi dans l'addon (interdit CLAUDE.md) ; et son client est Arrow→DataFrame, sans même de méthode chronologie JSON.
- **Extra `electricore[client]`** : les extras s'ajoutent aux deps de base lourdes du moteur ; install non léger. Et « vider » les deps de base d'un moteur polars/duckdb pour les passer en extras casse `import electricore` pour ses vrais usagers.
- **Codegen depuis l'OpenAPI** (FastAPI le sert gratuitement) : sans types de ligne sur le fil, le client généré rend des dicts ; une fois l'union discriminée posée à la source (point 2), le bénéfice typage est déjà capté par le paquet fin — la codegen en plus n'apporte pas assez.
- **Client JSON local dans l'addon (« Option B »)** : zéro dépendance, couche anti-corruption — c'est le **repli** si le paquet fin electricore ne se matérialise pas proprement. Écarté comme *cible* car il duplique à la main la connaissance du contrat, ce qu'on veut justement déléguer à electricore via ses releases.

## Raison

electricore possède le calcul **et** le contrat ; Odoo possède la facturation. Mettre le client *et* les types là où vit l'API rend le contrat single-source et versionné par les releases — exactement la frontière voulue ([ADR-0001](0001-odoo-systeme-ecriture-electricore-api-read-only.md), [ADR-0002](0002-deux-sources-de-verite-marge-en-analytique.md)). Le repli local garde la décision **réversible** : on s'engage sur la cible sans se verrouiller, ce qui autorise à acter maintenant sans attendre le spike de packaging.
