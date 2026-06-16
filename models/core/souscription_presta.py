from odoo import api, fields, models
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

    # Régime de TVA porté par la *nature*, pas par un taux par presta (ADR 0009 §5).
    # La nature choisit le produit de refacturation ; la TVA suit le produit
    # (configuré par le·la comptable), jamais un override de ligne — on ne
    # contourne donc pas les positions fiscales. Les `indemnité` (pénalités de
    # coupure dues par Enedis) sont hors champ TVA. Alimenté par le sync F15 (#37).
    nature = fields.Selection(
        [
            ('prestation', 'Prestation (TVA)'),
            ('indemnite', 'Indemnité (sans TVA)'),
        ],
        string='Nature',
        default='prestation',
        required=True,
    )

    # Mise en attente manuelle par le·la facturiste sur un doute (ADR 0012) :
    # opt-out de la facturation automatique. Tant que coché et non facturée, la
    # prestation est exclue de creer_factures() (cf. _facturer_prestations_a_refacturer).
    en_attente = fields.Boolean(string='En attente', default=False)

    # État dérivé pour le groupage/les stats de l'écran de vérification (ADR 0012).
    # L'ordre des valeurs pilote l'ordre des groupes. `facture_id` prime : il reste
    # l'unique source de vérité du « facturé » (ADR 0009 §4) ; `etat` ne fait que la
    # projeter. Stocké pour pouvoir grouper/filtrer/agréger côté SQL.
    etat = fields.Selection(
        [
            ('a_refacturer', 'À refacturer'),
            ('en_attente', 'En attente'),
            ('facturee', 'Facturée'),
            ('emise', 'Émise'),
        ],
        string='État',
        compute='_compute_etat',
        store=True,
    )

    @api.depends('facture_id', 'facture_id.state', 'en_attente')
    def _compute_etat(self):
        for presta in self:
            if presta.facture_id:
                presta.etat = 'emise' if presta.facture_id.state == 'posted' else 'facturee'
            elif presta.en_attente:
                presta.etat = 'en_attente'
            else:
                presta.etat = 'a_refacturer'

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
        """Produit de refacturation porté par la *nature* (ADR 0009 §5) : il
        porte le compte de produits **et la TVA** (prestation taxée vs indemnité
        hors champ). La ligne hérite de cette TVA via le produit ; pas de taux
        par presta, pas d'override de ligne."""
        self.ensure_one()
        xmlid = (
            'souscriptions_odoo.souscriptions_product_indemnite_enedis'
            if self.nature == 'indemnite'
            else 'souscriptions_odoo.souscriptions_product_prestation_enedis'
        )
        produit = self.env.ref(xmlid, raise_if_not_found=False)
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
