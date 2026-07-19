"""Repare le champ `code` des deux crons de vidange sur une base déjà
déployée (#342, ADR 0036 décision 10 — le « grand A »).

`_cron_vidanger_emettre_factures`/`_cron_vidanger_creer_factures` fusionnent
en une seule méthode paramétrée `_cron_vidanger(code)`
(models/core/souscription_campagne.py) : les deux enregistrements `ir.cron`
restent (xml_ids stables, `data/ir_cron_vidange_*.xml`), seul leur champ
`code` change de texte. Mais ces enregistrements vivent sous `noupdate="1"` —
un `-u` ne resynchronise JAMAIS leur contenu depuis l'XML une fois créés.
Sans ce backfill, une base déjà déployée garderait l'ancien texte
(`model._cron_vidanger_emettre_factures()`) et planterait au prochain
déclenchement (`AttributeError`, méthode supprimée par cette version).

SQL direct par `ir_model_data` (comme les migrations
19.0.1.14.0/19.0.1.16.0/19.0.1.17.0) : pas besoin de charger l'ORM pour une
mise à jour de deux lignes. Idempotent : un UPDATE vers la valeur exacte
attendue, rejouable sans effet.
"""


def migrate(cr, version):
    cr.execute(
        """
        UPDATE ir_cron SET code = %(code)s
        FROM ir_model_data
        WHERE ir_model_data.model = 'ir.cron'
          AND ir_model_data.res_id = ir_cron.id
          AND ir_model_data.module = 'souscriptions_odoo'
          AND ir_model_data.name = %(xml_id)s
        """,
        {'code': "model._cron_vidanger('creer_factures')", 'xml_id': 'ir_cron_vidange_creer_factures'},
    )
    cr.execute(
        """
        UPDATE ir_cron SET code = %(code)s
        FROM ir_model_data
        WHERE ir_model_data.model = 'ir.cron'
          AND ir_model_data.res_id = ir_cron.id
          AND ir_model_data.module = 'souscriptions_odoo'
          AND ir_model_data.name = %(xml_id)s
        """,
        {'code': "model._cron_vidanger('emettre_factures')", 'xml_id': 'ir_cron_vidange_emettre_factures'},
    )
