from odoo import models
from odoo.exceptions import UserError


class SouscriptionProduit(models.AbstractModel):
    """Catalogue *Produit de facturation* (ADR 0013).

    Résout un *rôle de facturation* vers le `product.product` Odoo qui porte le
    compte de produits + la TVA, dans l'**univers** comptable standard ou
    solidaire. L'isolation standard/solidaire est légale et structurelle : deux
    mondes parallèles, aucune ligne ne traverse. `AbstractModel` = mappage sans
    donnée propre ; les produits eux-mêmes viennent de `data/produits_*.xml`.
    """

    _name = 'souscription.produit'
    _description = 'Catalogue des produits de facturation'

    # Deux univers comptables parallèles (ADR 0013). Chaque monde mappe une clé
    # de rôle → xmlid du product.product porteur du compte + TVA.
    _CATALOGUE = {
        False: {  # univers standard
            ('abonnement',): 'souscriptions_product_abonnement_standard',
            ('energie', 'base'): 'souscriptions_product_energie_base',
            ('energie', 'hp'): 'souscriptions_product_energie_hp',
            ('energie', 'hc'): 'souscriptions_product_energie_hc',
            ('refacturation', 'prestation'): 'souscriptions_product_prestation_enedis',
            ('refacturation', 'indemnite'): 'souscriptions_product_indemnite_enedis',
        },
        True: {  # univers solidaire
            ('abonnement',): 'souscriptions_product_abonnement_solidaire',
            ('energie', 'base'): 'souscriptions_product_energie_base_solidaire',
            ('energie', 'hp'): 'souscriptions_product_energie_hp_solidaire',
            ('energie', 'hc'): 'souscriptions_product_energie_hc_solidaire',
            ('refacturation', 'prestation'): 'souscriptions_product_prestation_enedis_solidaire',
            ('refacturation', 'indemnite'): 'souscriptions_product_indemnite_enedis_solidaire',
        },
    }

    def _produit(self, is_solidaire, cle):
        """Résout `(univers, clé de rôle)` → `product.product`.

        `UserError` si la clé est inconnue ou si le produit attendu est absent
        (catalogue incomplet = trou d'isolation, ADR 0013).
        """
        monde = self._CATALOGUE[bool(is_solidaire)]
        xmlid = monde.get(cle)
        if xmlid is None:
            raise UserError(f'Rôle de facturation inconnu : {cle}.')
        produit = self.env.ref(f'souscriptions_odoo.{xmlid}', raise_if_not_found=False)
        if not produit:
            univers = 'solidaire' if is_solidaire else 'standard'
            raise UserError(f'Produit de facturation introuvable : {cle} ({univers}).')
        return produit

    def produit_abonnement(self, is_solidaire):
        """Produit d'abonnement de l'univers demandé."""
        return self._produit(is_solidaire, ('abonnement',))

    def produit_energie(self, cadran, is_solidaire):
        """Produit d'énergie du cadran facturé (base/hp/hc), univers demandé."""
        return self._produit(is_solidaire, ('energie', cadran))

    def produit_refacturation(self, nature, is_solidaire):
        """Produit de refacturation de la nature (prestation/indemnité), univers demandé."""
        return self._produit(is_solidaire, ('refacturation', nature))

    def produits_requis(self):
        """Tous les *Produits de facturation* attendus, les deux univers réunis.

        Résout chaque entrée du catalogue (lève UserError si l'un manque) : c'est
        donc un contrôle de complétude de l'isolation standard/solidaire (ADR 0013).
        Le résultat étant un recordset, deux univers qui partageraient un produit
        feraient chuter le total sous 12.
        """
        produits = self.env['product.product']
        for is_solidaire, monde in self._CATALOGUE.items():
            for cle in monde:
                produits |= self._produit(is_solidaire, cle)
        return produits
