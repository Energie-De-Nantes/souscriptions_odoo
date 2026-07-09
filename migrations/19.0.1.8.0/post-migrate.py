"""Chèque énergie — tiers-payeur (#170, ADR 0026).

`post_init_hook` (hooks.setup_cheque_energie_compta) ne couvre que l'install
neuve : sur une instance déjà installée qui *upgrade* vers cette version, il
faut le rejouer ici pour poser le journal « Chèques énergie » + le compte
« à recevoir de l'État ».

Neutralise aussi les deux produits prod hérités du traitement manuel :
« Déduction acompte chèque énergie » (produit 331 → 419100) et « Acompte
chèque énergie » (produit 332 → CA 707100, incohérent). Le modèle propre
`souscription.cheque_energie` (#171/#172) les remplace.

Le compte « à recevoir de l'État » posé par `setup_cheque_energie_compta`
(classe 4 générique, code 467100) est, comme ces deux produits, un
paramétrage à préciser par la compta — cf. le commentaire dans hooks.py.

ponytail : ces deux produits ne sont jamais seedés par ce repo (cf.
data/produits_*.xml — ils n'existent qu'en prod, cf. ADR 0026 « Constat
prod »), donc matchés par nom plutôt que par xmlid/ID technique. No-op propre
sur une base sans ces enregistrements (dev/CI). Idempotent : ne touche que
les enregistrements encore actifs.
"""

from odoo import SUPERUSER_ID, api

NOMS_PRODUITS_A_NEUTRALISER = (
    'Déduction acompte chèque énergie',
    'Acompte chèque énergie',
)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})

    from odoo.addons.souscriptions_odoo.hooks import setup_cheque_energie_compta

    setup_cheque_energie_compta(env)

    produits = env['product.product'].search([('name', 'in', list(NOMS_PRODUITS_A_NEUTRALISER)), ('active', '=', True)])
    if produits:
        produits.write({'active': False, 'sale_ok': False})
