import logging
from datetime import date, timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

# Puissance de référence (kVA) du tarif d'abonnement affine : base à 3 kVA,
# coefficient appliqué au-delà (ADR 0018).
PUISSANCE_BASE_KVA = 3.0

# Nombre de jours servant de base au prorata journalier de l'abonnement.
# Convention TURPE : le prix annuel est divisé par 365 quelle que soit l'année.
JOURS_PAR_AN = 365.0


class GrillePrix(models.Model):
    _name = 'grille.prix'
    _description = 'Grille de prix énergétique'
    _order = 'date_debut desc'

    name = fields.Char('Nom de la grille', required=True)
    date_debut = fields.Date('Valable à partir du', required=True)
    date_fin = fields.Date(
        "Valable jusqu'au", readonly=True, help="Calculé automatiquement lors de la création d'une nouvelle grille"
    )
    active = fields.Boolean('Active', default=True)

    ligne_ids = fields.One2many('grille.prix.ligne', 'grille_id', string='Lignes de prix')

    # Champs calculés pour info
    nb_lignes = fields.Integer('Nombre de lignes', compute='_compute_nb_lignes')

    @api.depends('ligne_ids')
    def _compute_nb_lignes(self):
        for grille in self:
            grille.nb_lignes = len(grille.ligne_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            date_debut_nouvelle = vals['date_debut']

            # Fermer la grille précédente (la plus récente avant cette date)
            grille_precedente = self.search(
                [
                    ('date_debut', '<', date_debut_nouvelle),
                    ('date_fin', '=', False),  # Grille ouverte
                ],
                order='date_debut desc',
                limit=1,
            )

            if grille_precedente:
                # Fermer la grille précédente la veille de la nouvelle
                date_fin_precedente = fields.Date.from_string(date_debut_nouvelle) - timedelta(days=1)
                grille_precedente.date_fin = date_fin_precedente
                _logger.info(f'Grille {grille_precedente.name} fermée au {date_fin_precedente}')

        return super().create(vals_list)

    @api.model
    def get_grille_active(self, date_facture=None):
        """Récupère la grille dont la période de validité couvre la date donnée.

        La sélection se fait sur la plage [date_debut, date_fin] (date_fin vide =
        grille ouverte), et non sur le drapeau ``is_current`` : une facturation
        rétroactive utilise ainsi la grille en vigueur à la date concernée.
        """
        if date_facture is None:
            date_facture = fields.Date.today()

        grille = self.search(
            [
                ('date_debut', '<=', date_facture),
                '|',
                ('date_fin', '=', False),
                ('date_fin', '>=', date_facture),
            ],
            order='date_debut desc',
            limit=1,
        )

        if not grille:
            raise UserError(
                f'Aucune grille de prix ne couvre la date {date_facture}. '
                f'Vérifiez la couverture des grilles (trou de période ?).'
            )

        return grille

    @api.constrains('date_debut', 'date_fin')
    def _check_no_overlap(self):
        """Interdit le chevauchement des périodes de validité entre grilles."""
        for grille in self:
            if not grille.date_debut:
                continue
            start_a = grille.date_debut
            end_a = grille.date_fin or date.max
            if start_a > end_a:
                raise ValidationError(f"La grille '{grille.name}' a une date de fin antérieure à sa date de début.")
            for other in self.search([('id', '!=', grille.id)]):
                start_b = other.date_debut
                end_b = other.date_fin or date.max
                if start_a <= end_b and start_b <= end_a:
                    raise ValidationError(
                        f"La période de la grille '{grille.name}' chevauche celle de la grille '{other.name}'."
                    )

    def get_prix_dict(self):
        """Retourne un dict {product_id: prix_interne} pour toute la grille"""
        self.ensure_one()
        return {ligne.product_id.id: ligne.prix_interne for ligne in self.ligne_ids if ligne.product_id}

    def get_prix_abonnement(self, puissance_kva, coeff_pro=0.0, is_solidaire=False):
        """Retourne le prix d'abonnement journalier (€/jour) pour une puissance.

        Tarif affine (ADR 0018) : la grille porte deux paramètres par univers,
        ``prix_base_3kva`` (€/an à 3 kVA) et ``coef_kva`` (€/an par kVA
        supplémentaire). Le prix journalier vaut
        ``(prix_base_3kva + coef_kva x (puissance_kva - 3)) / 365``, puis la
        majoration PRO ``x (1 + coeff_pro / 100)`` est appliquée.

        L'univers (standard / solidaire) est porté par le produit du catalogue
        (ADR 0013), jamais ré-encodé dans la grille.
        """
        self.ensure_one()

        product = self.env['souscription.produit'].produit_abonnement(is_solidaire)

        ligne_abo = self.ligne_ids.filtered(lambda l: l.product_id == product and l.type_produit == 'abonnement')
        if not ligne_abo:
            type_abo = 'solidaire' if is_solidaire else 'standard'
            raise UserError(f"Aucun tarif d'abonnement {type_abo} dans la grille {self.name}.")

        ligne = ligne_abo[0]
        prix_annuel = ligne.prix_base_3kva + ligne.coef_kva * (float(puissance_kva) - PUISSANCE_BASE_KVA)
        prix_journalier = prix_annuel / JOURS_PAR_AN

        if coeff_pro > 0:
            prix_journalier = prix_journalier * (1 + coeff_pro / 100.0)

        return prix_journalier

    def dupliquer_cette_grille(self):
        """Action pour dupliquer cette grille avec toutes ses lignes"""
        self.ensure_one()

        # Créer une copie de la grille avec date d'aujourd'hui
        today = fields.Date.today()

        # Préparer les lignes à copier
        lignes_vals = []
        for ligne in self.ligne_ids:
            lignes_vals.append(
                (
                    0,
                    0,
                    {
                        'product_id': ligne.product_id.id,
                        'type_produit': ligne.type_produit,
                        'prix_unitaire': ligne.prix_unitaire,
                        'prix_base_3kva': ligne.prix_base_3kva,
                        'coef_kva': ligne.coef_kva,
                    },
                )
            )

        # Créer la nouvelle grille avec ses lignes
        nouvelle_grille = self.create(
            {
                'name': f'Copie de {self.name}',
                'date_debut': today,
                'date_fin': False,
                'ligne_ids': lignes_vals,
            }
        )

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'grille.prix',
            'res_id': nouvelle_grille.id,
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'form_view_initial_mode': 'edit',
            },
        }


class GrillePrixLigne(models.Model):
    _name = 'grille.prix.ligne'
    _description = 'Ligne de prix énergétique'
    _order = 'type_produit, product_id'

    grille_id = fields.Many2one('grille.prix', string='Grille', required=True, ondelete='cascade')

    product_id = fields.Many2one(
        'product.product',
        string='Produit',
        required=True,
        domain=[('type', '=', 'service')],
        help='Produit de service pour la facturation énergétique',
    )

    # Rôle de la ligne. L'univers (standard / solidaire) est porté par le
    # produit du catalogue (ADR 0013), jamais par ce champ.
    type_produit = fields.Selection(
        [('abonnement', 'Tarifs abonnement'), ('energie', 'Énergie (€/kWh)')],
        string='Type',
        required=True,
        default='energie',
    )

    # Pour les abonnements : tarif affine (ADR 0018) — base à 3 kVA + coef/kVA.
    prix_base_3kva = fields.Float(
        'Abonnement base 3 kVA (€/an)',
        digits=(16, 6),
        help="Prix annuel de l'abonnement à 3 kVA, proratisé au jour (÷365) lors de la facturation.",
    )
    coef_kva = fields.Float(
        'Coefficient par kVA (€/an)',
        digits=(16, 6),
        help='Prix annuel ajouté par kVA souscrit au-delà de 3 kVA.',
    )

    # Pour les énergies : prix unitaire classique
    prix_unitaire = fields.Float('Prix unitaire (€/kWh)', digits=(16, 6), help='Prix unitaire pour les énergies')

    # Prix interne calculé
    prix_interne = fields.Float(
        'Prix interne', compute='_compute_prix_interne', store=True, help='Prix utilisé pour les calculs de facturation'
    )

    # Champs informatifs
    unite_saisie = fields.Char('Unité saisie', compute='_compute_unites', store=False)
    unite_calcul = fields.Char('Unité calcul', compute='_compute_unites', store=False)

    @api.depends('type_produit')
    def _compute_unites(self):
        for ligne in self:
            if ligne.type_produit == 'abonnement':
                ligne.unite_saisie = '€/an'
                ligne.unite_calcul = '€/jour'
            else:
                ligne.unite_saisie = '€/kWh'
                ligne.unite_calcul = '€/kWh'

    @api.depends('type_produit', 'prix_unitaire', 'prix_base_3kva')
    def _compute_prix_interne(self):
        for ligne in self:
            if ligne.type_produit == 'abonnement':
                # Prix indicatif (€/jour) à la puissance de base ; le prix facturé
                # est calculé par get_prix_abonnement (affine, ADR 0018).
                ligne.prix_interne = ligne.prix_base_3kva / JOURS_PAR_AN if ligne.prix_base_3kva else 0.0
            else:
                # Énergies : prix interne = prix saisi.
                ligne.prix_interne = ligne.prix_unitaire or 0.0

    _unique_produit_grille = models.Constraint(
        'UNIQUE(grille_id, product_id)',
        "Un produit ne peut apparaître qu'une seule fois par grille.",
    )
