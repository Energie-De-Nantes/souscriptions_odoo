"""Purge de l'ancien index unique partiel (#239, ADR 0030 décision 3).

`souscription_periode_mois_mensuelle_unique` était posé à la main dans
`init()` (raw SQL — hors du vocabulaire `models.Constraint`, qui ne sait pas
exprimer de clause `WHERE`). La Période étant désormais purement mensuelle,
il est redondant avec `_unique_mois` — la contrainte UNIQUE pleine que le
nouveau `models.Constraint` fait poser par Odoo lui-même au chargement du
module. Créé hors ORM, cet index n'est jamais tracké par
`ir_model_constraint` — jamais nettoyé automatiquement, on le droppe donc à
la main. Idempotent (`IF EXISTS`), no-op sur install neuve ou base déjà
migrée.
"""


def migrate(cr, version):
    cr.execute('DROP INDEX IF EXISTS souscription_periode_mois_mensuelle_unique')
