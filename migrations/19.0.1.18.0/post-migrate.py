"""Repointe les 8 produits de facturation sur leur vraie unité de mesure —
fin du placeholder kg / Units (#304).

Les 6 produits d'énergie (Base/HP/HC × standard/solidaire) sont créés en
`kg` (`uom.product_uom_kgm`, placeholder jamais voulu) et les 2 produits
d'abonnement n'ont pas d'unité (défaut Odoo `Units`,
`uom.product_uom_unit`) : une ligne de facture d'énergie se lisait
« 1234 kg » au lieu de « 1234 kWh ». `data/produits_energie.xml` et
`data/produits_abonnement_simple.xml` pointent désormais sur les bonnes
unités (`uom.product_uom_kwh` / `uom.product_uom_day`, livrées par le module
core `uom` — rien à créer), mais ces fichiers sont `noupdate="1"` : seules
les installations neuves en profitent. Ce script re-pointe les 8 produits
déjà présents en prod.

Produits de type `service` (pas de stock) : la garde d'Odoo contre un
changement de `uom_id` (`stock.product.product._update_uom`, clé sur
`stock.move`/`stock.move.line` existants) ne s'applique qu'aux produits
stockables — jamais déclenchée ici, écrire `uom_id` directement est sûr même
après facturation. Les lignes de facture déjà postées gardent leur propre
`product_uom_id` (snapshot pris à la composition) : elles ne sont PAS
retouchées par ce script, volontairement — c'est le figement voulu par
l'AC "les factures déjà comptabilisées ne sont pas modifiées".

Gardé sur l'unité ACTUELLE (encore le placeholder) : rejouable sans effet
(idempotent) et sans écraser un repointage manuel déjà fait en prod avant
cette migration. `env.ref(..., raise_if_not_found=False)` : un produit
supprimé/absent est ignoré, pas fatal.

`_repointer_unites(env)` est une fonction pure prenant `env` (pas `cr`) pour
être appelable directement depuis un test — `migrate(cr, version)` ne fait
que construire l'environnement et déléguer.
"""

from odoo import SUPERUSER_ID, api

PRODUITS_ENERGIE = (
    'souscriptions_product_energie_base',
    'souscriptions_product_energie_hp',
    'souscriptions_product_energie_hc',
    'souscriptions_product_energie_base_solidaire',
    'souscriptions_product_energie_hp_solidaire',
    'souscriptions_product_energie_hc_solidaire',
)
PRODUITS_ABONNEMENT = (
    'souscriptions_product_abonnement_standard',
    'souscriptions_product_abonnement_solidaire',
)


def _repointer_unites(env):
    kwh = env.ref('uom.product_uom_kwh')
    jour = env.ref('uom.product_uom_day')
    placeholder_energie = env.ref('uom.product_uom_kgm')
    placeholder_abonnement = env.ref('uom.product_uom_unit')

    for xmlid in PRODUITS_ENERGIE:
        produit = env.ref(f'souscriptions_odoo.{xmlid}', raise_if_not_found=False)
        if produit and produit.uom_id == placeholder_energie:
            produit.uom_id = kwh

    for xmlid in PRODUITS_ABONNEMENT:
        produit = env.ref(f'souscriptions_odoo.{xmlid}', raise_if_not_found=False)
        if produit and produit.uom_id == placeholder_abonnement:
            produit.uom_id = jour


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    _repointer_unites(env)
