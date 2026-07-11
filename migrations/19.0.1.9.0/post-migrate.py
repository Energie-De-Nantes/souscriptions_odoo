"""Suppression de l'« État de facturation » (#180).

L'upgrade Odoo droppe bien la colonne `etat_facturation_id` en fin de
chargement (nettoyage ir.model.fields), mais laisse la table
`souscription_etat` orpheline (constaté sur copie de prodlocal : la table
et ses 3 lignes survivent à deux passes de `-u`). On droppe la colonne
d'abord nous-mêmes : au moment du post-migrate le nettoyage n'a pas encore
eu lieu et sa FK empêcherait le DROP TABLE (« other objects depend on it »).
Idempotent (IF EXISTS), no-op sur install neuve.
"""


def migrate(cr, version):
    cr.execute('ALTER TABLE souscription_souscription DROP COLUMN IF EXISTS etat_facturation_id')
    cr.execute('DROP TABLE IF EXISTS souscription_etat')
