"""Supprime la colonne `lisse` de souscription_periode (#347).

Fusion lisse/lisse_periode (split-brain latent, ADR 0006 famille des
snapshots `_periode`) : `lisse_periode` est désormais l'unique champ de
lissage figé à la maille Période — ses 3 lecteurs (template de facture ×2,
colonne liste) le lisent, et il rejoint `_LOCKED_FIELDS`. `lisse` disparaît
du modèle Python dans cette même version.

Odoo droppe normalement lui-même la colonne d'un champ retiré en fin de
chargement (nettoyage `ir.model.fields`, cf. migrations/19.0.1.9.0). On la
supprime ici explicitement, comme 19.0.1.9.0, pour documenter et fiabiliser
le geste plutôt que de compter en silence sur ce nettoyage. `lisse` et
`lisse_periode` étaient peuplés à l'identique par `create()` (même source
`sous.lisse`) : aucune perte de donnée, le drop ne fait que retirer la
copie redondante. Idempotent (`IF EXISTS`), no-op sur install neuve.
"""


def migrate(cr, version):
    cr.execute('ALTER TABLE souscription_periode DROP COLUMN IF EXISTS lisse')
