# Cookbook

Routines registry for this repo. Each recipe is a way to reach a state or
exercise a change. `mode: afk` = an agent can run it headless; `mode: human` =
a present person runs it (usually needs eyeballs). `how-to` selects the fitting
recipe(s) for a change and fills the `{placeholders}`.

## bring-up
mode: afk
when: you need a live instance to exercise a change end to end
do: `./scripts/dev.sh` (runs a server — background it; `--data=prod` switches to souscriptions_prodlocal without demo; `--reset` rebuilds the current mode's DB from scratch)
observe: startup logs — ready when it prints `Odoo démarre sur http://localhost:8069` (login admin / admin, DB souscriptions_demo)

## tests
mode: afk
when: a change to models/, controllers/, reports/, security/, or data/
do: `./scripts/run-tests.sh` (whole suite) — or `TEST_TAGS={tag} ./scripts/run-tests.sh` to narrow (Odoo 19 in Docker; needs sandbox bypass)
observe: exit code + test summary; a real failure is timestamp-prefixed (`2026-… ERROR test_db …`), docutils `<string>:N:` noise is filtered

## page-render
mode: human
when: a change to a view (views/), the portal (controllers/), or a menu/action
do: start the app (see `bring-up`), log in admin / admin
look: http://localhost:8069/   # TODO(you): the route to the changed view/record
expect: the page renders your change

## report-render
mode: human
when: a change to a QWeb report in reports/
do: start the app (see `bring-up`), log in admin / admin, open the report PDF URL
look: http://localhost:8069/report/pdf/{report_name}/{record_id}
  # report_name is one of:
  #   account.account_invoices                                     (facture d'énergie, record model: account.move — routée par _get_name_invoice_report(), #289)
  #   souscriptions_odoo.souscription_attestation_document         (record model: souscription.souscription)
  #   souscriptions_odoo.souscription_conditions_particulieres_document  (record model: souscription.souscription)
  # TODO(you): the {record_id} to print
expect: the PDF renders your change (company layout borders all tables — see report-rendering notes)

## inspect-data
mode: afk
when: you need to check records/fields in the running instance, not just the code
do: use the odoo MCP tools (search_records, read_record, get_model_fields…) against instance `dev`
  # `dev`     = http://localhost:8069, db souscriptions_demo — the local docker; HAS the souscriptions module
  # `default` = energie-de-nantes.odoo.com SaaS — does NOT carry the souscriptions module
observe: the returned records/fields

## odoo-shell
mode: human
when: you need an interactive Python shell to read/write records (MCP is read-only) — purge/fix data, run ORM code
do: stack up (see `bring-up`), then in another terminal:
  `docker compose -f docker/docker-compose.yml exec odoo odoo shell -d {db} --db_host=db --db_user=odoo --db_password=odoo --no-http`
  # {db}: souscriptions_demo (mode demo) OR souscriptions_prodlocal (mode prod, real electricore sync data)
  # the db flags are mandatory — `exec` skips the entrypoint, so shell would hit a local socket without them
  # writes need an explicit `env.cr.commit()` — the shell never commits on its own
look: prompt with `env`/`self` bound; pick the db that actually holds your records
  # gotcha: souscriptions_demo carries only the F15-DEMO-* demo rows; real synced data lives in souscriptions_prodlocal
  # gotcha: a stale schema (e.g. `column … does not exist`) means the module wasn't upgraded on that db — re-run bring-up with --reset, or `-u souscriptions_odoo`
expect: your ORM code runs; after `env.cr.commit()` the change persists

## docs-site-build
mode: afk
when: a change to docs/educpopage/, mkdocs.yml, or the cozy stylesheets — verify the site still builds
do: `uv sync --group docs && uv run --group docs mkdocs build --strict`
observe: exit code — strict turns any warning (dead internal link, page missing from nav) into a failure
covered-by: ci-pr — job « build (mkdocs --strict) » in .github/workflows/docs.yml

## docs-site-render
mode: human
when: a change to docs/educpopage/, mkdocs.yml, or the cozy stylesheets — see the rendering with your own eyes
do: `uv sync --group docs && uv run --group docs mkdocs serve`
look: http://127.0.0.1:8000/ — navigate to the changed page
expect: style « Warm Cosy » identique à la doc electricore (papier crème, bandeau sombre, police Excalifont) ; la nav et la page reflètent ton changement
