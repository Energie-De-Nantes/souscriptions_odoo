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
  #   souscriptions_odoo.report_facture_energie                    (record model: account.move)
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
