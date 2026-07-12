# Secrets electricore en dev : injectés depuis Proton Pass via pass-through docker-compose — le module reste `ir.config_parameter`

*Statut : accepté (pass-through validé le 2026-07-12 — `pr docker compose … config` affiche `<concealed by Proton Pass>` pour les deux variables). Applique la décision parc-wide [electricore ADR-0056](../../../electricore/docs/adr/0056-secrets-dev-proton-pass-par-espace.md) (Proton Pass = secrets de dev consommés par CLI ; SOPS+age = prod) au seul module Odoo, qui en est l'**exception** assumée. Ne re-décide pas [ADR-0024](0024-electricore-dependance-molle-garde-import-fabrique-client-unique.md) : elle fixe déjà que la config (`ELECTRICORE_URL` / `ELECTRICORE_API_KEY`) est une **donnée runtime** lue à l'usage via `ir.config_parameter` avec repli `os.environ`.*

Le module consomme electricore via deux secrets — `ELECTRICORE_URL`, `ELECTRICORE_API_KEY` — lus par la fabrique `souscription.electricore.client` : `ICP.get_param('souscriptions.electricore_*') or os.environ.get('ELECTRICORE_*', '')` (ADR-0024 §3b). En dev, le repli `os.environ` était alimenté par un `docker/.env` **en clair sur disque** — la vraie `ELECTRICORE_API_KEY` (= clé `operator` du trousseau API electricore) y traînait. C'était le **seul secret applicatif en clair du parc** (les autres repos sont passés à Proton Pass, ADR-0056 ; la prod est en SOPS+age, ADR-0044 electricore-secrets).

## Décision

1. **Secrets dev depuis Proton Pass, pas de fichier en clair.** Item Proton `souscriptions_odoo` (vault `cli-edn`, champs verbatim `ELECTRICORE_URL` / `ELECTRICORE_API_KEY`). Un `.env.pass` (gitignoré) porte les refs `pass://cli-edn/souscriptions_odoo/<VAR>`. Le `docker/.env` en clair est **supprimé** (`shred`).
2. **Injection par pass-through, zéro écriture disque.** `pr ./scripts/dev.sh` → `pass-cli run` résout les refs dans l'env **shell** → `docker-compose` les interpole (`ELECTRICORE_URL=${ELECTRICORE_URL:-}`, déjà en place) → env du **conteneur** → `os.environ.get()` de la fabrique. Le secret ne touche jamais le disque ; il vit le temps du process compose.
3. **Le module N'EST PAS migré vers pydantic-settings.** Contrairement à `souscriptions_migration` et electricore (ADR-0056), l'idiome de config d'un module Odoo est `ir.config_parameter` (éditable à chaud, ADR-0024 §3b) — on ne force pas pydantic dans le runtime Odoo pour deux variables. **Aucun changement de code** : le repli `os.environ` existait déjà.
4. **Prod inchangée.** En prod les paramètres système (`souscriptions.electricore_*`) sont renseignés à la main dans Odoo ; ni Proton, ni `.env.pass`, ni `docker/.env` n'interviennent — priorité au param système (ADR-0024 §3b), le repli env reste vide.

## Conséquences

- **Plus aucun secret applicatif en clair sur disque** dans le parc.
- Intégration electricore active en dev sans y penser : `dev.sh` s'auto-wrappe sous `pass-cli run` quand `ELECTRICORE_URL` manque et que `.env.pass` + pass-cli sont présents (amendement post-validation : oublier `pr` coûtait un conteneur démarré sans secrets et un redémarrage). Sans `.env.pass` ni pass-cli, les vars restent vides → l'intégration se **désactive proprement** (repli `or ''`, `UserError` actionnable au clic, ADR-0024), pas de crash.
- `docker/.env.example` (committé, valeurs vides) reste le **template documentaire** des deux variables.
- La clé `operator` est **dupliquée** dans l'item `souscriptions_odoo` plutôt que référencée cross-vault vers l'item `electricore` : pour deux valeurs, un item dédié évite un token cross-vault (ADR-0056, ergonomie du scope par vault).

## Options écartées

- **Migrer le module vers pydantic-settings** (uniformité avec le reste du parc) : se battre contre le système de config natif d'Odoo (`ir.config_parameter`, éditable à chaud sans redémarrage) pour deux variables. ADR-0056 exempte explicitement ce module.
- **`pass-cli inject` → génère `docker/.env`** : réécrit du clair sur disque — exactement ce que ce changement supprime.
- **Référencer cross-vault** `pass://cli-edn/electricore/API__TROUSSEAU__operator__KEY` : le token `cli-edn` devrait alors couvrir l'item `electricore` ; pour deux valeurs, dupliquer < complexité de scope.

## Raison

Le secret doit vivre **là où le module le lit** — l'env du conteneur — et **seulement à ce moment**. pass-cli l'injecte juste-à-temps dans l'env shell que compose propage ; il n'est jamais au repos sur disque, jamais dans l'historique. La frontière d'ADR-0024 (config = donnée runtime, vérifiée à l'usage) est préservée telle quelle. Le seul maillon empirique restant — que l'interpolation pass-through livre bien la valeur au conteneur — se valide en une commande : `pr docker compose -f docker/docker-compose.yml config | grep -i electricore` (valeur `<concealed by Proton Pass>` = injectée). Sur GO, cet ADR passe accepté.
