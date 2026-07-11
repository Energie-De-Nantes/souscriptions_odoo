"""Suppression de l'« État de facturation » (#180).

L'upgrade Odoo droppe bien la colonne `etat_facturation_id` (métadonnées
ir.model.fields nettoyées), mais laisse la table `souscription_etat`
orpheline (constaté sur copie de prodlocal : la table et ses 3 lignes
survivent à deux passes de `-u`). On la droppe ici. Idempotent (IF EXISTS),
no-op sur install neuve.
"""


def migrate(cr, version):
    cr.execute('DROP TABLE IF EXISTS souscription_etat')
