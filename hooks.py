"""Post_init_hook / migration shim — setup compta du chèque énergie (#170, ADR 0026).

La logique elle-même vit désormais sur `souscription.cheque_energie._setup_compta()`
(#255, revue d'architecture : « le Chèque énergie possède toute son
histoire ») — ce module ne garde qu'un shim d'une ligne sous le même nom :
le manifeste (`post_init_hook`) et la migration `19.0.1.8.0` l'appellent par
nom, ils ne bougent pas.
"""


def setup_cheque_energie_compta(env):
    """Shim (#255) : délègue à `souscription.cheque_energie._setup_compta()`."""
    return env['souscription.cheque_energie']._setup_compta()
