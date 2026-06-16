"""Renommage du modèle souscription.presta → souscription.refacturation (#38).

L'umbrella « prestation » était ambigu — c'est aussi une *nature* (cf. CONTEXT.md) :
prestation (taxée) vs indemnité (hors champ TVA). Le modèle prend donc le nom de
l'ensemble, *Refacturation*.

Pre-migrate (avant chargement du module) : renomme la table et recâble les
métadonnées ORM pour préserver les données existantes. Le module n'est pas en
production aujourd'hui — c'est surtout pour les bases de dev déjà installées. Sur
une base neuve, la table n'existe pas encore et la migration ne fait rien.
"""


def migrate(cr, version):
    cr.execute("SELECT 1 FROM information_schema.tables WHERE table_name = 'souscription_presta'")
    if not cr.fetchone():
        return

    # 1. La table porteuse des données.
    cr.execute('ALTER TABLE souscription_presta RENAME TO souscription_refacturation')

    # 2. Métadonnées ORM : modèle, champs, relations, et records de ce modèle.
    cr.execute("UPDATE ir_model SET model = 'souscription.refacturation' WHERE model = 'souscription.presta'")
    cr.execute("UPDATE ir_model_fields SET model = 'souscription.refacturation' WHERE model = 'souscription.presta'")
    cr.execute("UPDATE ir_model_fields SET relation = 'souscription.refacturation' WHERE relation = 'souscription.presta'")
    cr.execute("UPDATE ir_model_data SET model = 'souscription.refacturation' WHERE model = 'souscription.presta'")

    # 3. xmlids du module renommés en même temps que les fichiers de données,
    #    pour éviter une suppression-puis-recréation des vues/actions/accès.
    renames = [
        ('model_souscription_presta', 'model_souscription_refacturation'),
        ('access_souscription_presta_user', 'access_souscription_refacturation_user'),
        ('access_souscription_presta_manager', 'access_souscription_refacturation_manager'),
        ('view_souscription_presta_list', 'view_souscription_refacturation_list'),
        ('view_souscription_presta_form', 'view_souscription_refacturation_form'),
        ('view_souscription_presta_search', 'view_souscription_refacturation_search'),
        ('action_souscription_presta', 'action_souscription_refacturation'),
        ('menu_souscription_presta', 'menu_souscription_refacturation'),
    ]
    for old, new in renames:
        cr.execute(
            "UPDATE ir_model_data SET name = %s WHERE module = 'souscriptions_odoo' AND name = %s",
            (new, old),
        )
