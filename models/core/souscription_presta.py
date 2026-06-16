from odoo import fields, models
from odoo.exceptions import UserError


class SouscriptionPresta(models.Model):
    """Prestation Enedis à refacturer (#8 / ADR 0009).

    Poste de facturation ponctuel d'origine Enedis (mise en service, déplacement,
    pénalité de coupure…) que le fournisseur refacture au·à la souscripteur·rice.
    Indépendante de la Période : c'est un en-cours refacturable rattaché à une
    Souscription. `facture_id` NULL = file « à refacturer » ; il est posé quand
    une Facture rassemble la prestation (lien côté presta, ADR 0004).
    """

    _name = 'souscription.presta'
    _description = 'Prestation Enedis à refacturer'

    souscription_id = fields.Many2one(
        'souscription.souscription', required=True, ondelete='cascade', string='Souscription'
    )
    pdl = fields.Char(string='PDL')
    reference_enedis = fields.Char(string='Référence Enedis', required=True)
    code_enedis = fields.Char(string='Code Enedis')
    libelle = fields.Char(string='Libellé', required=True)
    prix = fields.Float(string='Prix (€)', help='Prix de refacturation ; peut être négatif (avoir/pénalité).')
    quantite = fields.Float(string='Quantité', default=1.0)

    # Marqueur « facturé » et unique lien Période-libre ↔ Facture : posé quand la
    # prestation est rassemblée sur une facture (ADR 0004, lien côté « plusieurs »).
    # `set null` : supprimer la facture re-met la prestation dans la file.
    facture_id = fields.Many2one('account.move', string='Facture', readonly=True, ondelete='set null', copy=False)

    # Clé de dédup du sync electricore (ADR 0009) : une prestation = une référence
    # Enedis. Pull-tout-et-dédup s'appuie dessus pour rester idempotent.
    _unique_reference_enedis = models.Constraint(
        'UNIQUE(reference_enedis)',
        'Une prestation existe déjà pour cette référence Enedis.',
    )

    def _get_produit_prestation(self):
        produit = self.env.ref('souscriptions_odoo.souscriptions_product_prestation_enedis', raise_if_not_found=False)
        if not produit:
            raise UserError('Produit générique de prestation non trouvé')
        return produit

    def _composer_ligne(self):
        """Compose la ligne de facture (`(0, 0, vals)`) de cette prestation.

        Surface de test des règles de refacturation : produit générique pour la
        plomberie comptable, libellé/prix/quantité de la prestation. Ne crée
        aucun `account.move`.
        """
        self.ensure_one()
        produit = self._get_produit_prestation()
        return (
            0,
            0,
            {
                'product_id': produit.id,
                'name': self.libelle,
                'quantity': self.quantite,
                'price_unit': self.prix,
            },
        )
