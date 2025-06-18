from odoo import models, fields, api
from odoo.exceptions import UserError
from datetime import timedelta
import logging

_logger = logging.getLogger(__name__)

class GrillePrix(models.Model):
    _name = 'grille.prix'
    _description = 'Grille de prix énergétique'
    _order = 'date_debut desc'

    name = fields.Char("Nom de la grille", required=True)
    date_debut = fields.Date("Valable à partir du", required=True)
    date_fin = fields.Date("Valable jusqu'au", readonly=True, 
                          help="Calculé automatiquement lors de la création d'une nouvelle grille")
    active = fields.Boolean("Active", default=True)
    
    ligne_ids = fields.One2many('grille.prix.ligne', 'grille_id', string="Lignes de prix")
    
    # Champs calculés pour info
    nb_lignes = fields.Integer("Nombre de lignes", compute='_compute_nb_lignes')
    is_current = fields.Boolean("Grille actuelle", default=False, 
                               help="Une seule grille peut être active à la fois")
    
    @api.depends('ligne_ids')
    def _compute_nb_lignes(self):
        for grille in self:
            grille.nb_lignes = len(grille.ligne_ids)
    
    
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            date_debut_nouvelle = vals['date_debut']
            
            # Fermer la grille précédente (la plus récente avant cette date)
            grille_precedente = self.search([
                ('date_debut', '<', date_debut_nouvelle),
                ('date_fin', '=', False)  # Grille ouverte
            ], order='date_debut desc', limit=1)
            
            if grille_precedente:
                # Fermer la grille précédente la veille de la nouvelle
                date_fin_precedente = fields.Date.from_string(date_debut_nouvelle) - timedelta(days=1)
                grille_precedente.date_fin = date_fin_precedente
                _logger.info(f"Grille {grille_precedente.name} fermée au {date_fin_precedente}")
        
        return super().create(vals_list)
    
    @api.model
    def get_grille_active(self, date_facture=None):
        """Récupère la grille marquée comme active"""
        grille = self.search([('is_current', '=', True)], limit=1)
        
        if not grille:
            raise UserError("Aucune grille de prix définie comme active")
        
        return grille
    
    @api.constrains('is_current')
    def _check_unique_current_grille(self):
        """S'assure qu'une seule grille est marquée comme actuelle"""
        for grille in self.filtered('is_current'):
            autres_actives = self.search([
                ('is_current', '=', True),
                ('id', '!=', grille.id)
            ])
            if autres_actives:
                raise UserError(
                    f"Une seule grille peut être active à la fois. "
                    f"La grille '{autres_actives[0].name}' est déjà active."
                )
    
    def get_prix_dict(self):
        """Retourne un dict {product_id: prix_interne} pour toute la grille"""
        self.ensure_one()
        return {ligne.product_id.id: ligne.prix_interne for ligne in self.ligne_ids if ligne.product_id}
    
    def dupliquer_cette_grille(self):
        """Action pour dupliquer cette grille avec toutes ses lignes"""
        self.ensure_one()
        
        # Créer une copie de la grille avec date d'aujourd'hui
        today = fields.Date.today()
        
        # Préparer les lignes à copier
        lignes_vals = []
        for ligne in self.ligne_ids:
            lignes_vals.append((0, 0, {
                'product_id': ligne.product_id.id,
                'prix_unitaire': ligne.prix_unitaire,
            }))
        
        # Créer la nouvelle grille avec ses lignes (pas active par défaut)
        nouvelle_grille = self.create({
            'name': f"Copie de {self.name}",
            'date_debut': today,
            'date_fin': False,
            'is_current': False,  # Pas active par défaut
            'ligne_ids': lignes_vals,
        })
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'grille.prix',
            'res_id': nouvelle_grille.id,
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'form_view_initial_mode': 'edit',
            }
        }
    
    def definir_comme_grille_actuelle(self):
        """Action pour définir cette grille comme la grille actuelle"""
        self.ensure_one()
        
        # Décocher toutes les autres grilles
        autres_grilles = self.search([
            ('is_current', '=', True),
            ('id', '!=', self.id)
        ])
        
        if autres_grilles:
            autres_grilles.write({'is_current': False})
            _logger.info(f"Grilles {autres_grilles.mapped('name')} désactivées")
        
        # Activer cette grille
        self.is_current = True
        _logger.info(f"Grille {self.name} définie comme active")
        
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }


class GrillePrixLigne(models.Model):
    _name = 'grille.prix.ligne'
    _description = 'Ligne de prix énergétique'
    _order = 'product_id'

    grille_id = fields.Many2one('grille.prix', string="Grille", required=True, ondelete='cascade')
    
    product_id = fields.Many2one('product.product', string="Produit", required=True,
                                domain=[('type', '=', 'service')],
                                help="Produit de service pour la facturation énergétique")
    
    prix_unitaire = fields.Float("Prix unitaire", required=True, digits=(16, 6),
                                 help="Prix en €/mois pour abonnements, €/kWh pour énergies")
    
    # Prix interne en €/jour pour abonnements (calculé automatiquement)
    prix_interne = fields.Float("Prix interne (€/jour)", compute='_compute_prix_interne', store=True,
                               help="Prix utilisé pour les calculs de facturation")
    
    # Type de produit pour la conversion des prix
    type_produit = fields.Selection([
        ('abonnement', 'Abonnement (€/mois → €/jour)'),
        ('energie', 'Énergie (€/kWh)'),
        ('autre', 'Autre (€)')
    ], string="Type", required=True, default='autre')
    
    # Champs informatifs
    unite_saisie = fields.Char("Unité saisie", compute='_compute_unites', store=False)
    unite_calcul = fields.Char("Unité calcul", compute='_compute_unites', store=False)
    
    @api.depends('type_produit')
    def _compute_unites(self):
        for ligne in self:
            if ligne.type_produit == 'abonnement':
                ligne.unite_saisie = "€/mois"
                ligne.unite_calcul = "€/jour"
            elif ligne.type_produit == 'energie':
                ligne.unite_saisie = "€/kWh"
                ligne.unite_calcul = "€/kWh"
            else:
                ligne.unite_saisie = "€"
                ligne.unite_calcul = "€"
    
    @api.depends('type_produit', 'prix_unitaire')
    def _compute_prix_interne(self):
        for ligne in self:
            if ligne.type_produit == 'abonnement':
                # Conversion €/mois → €/jour (divisé par 30)
                ligne.prix_interne = ligne.prix_unitaire / 30.0 if ligne.prix_unitaire else 0.0
            else:
                # Pour énergies et autres : prix interne = prix saisi
                ligne.prix_interne = ligne.prix_unitaire or 0.0
    
    _sql_constraints = [
        ('unique_produit_grille', 
         'UNIQUE(grille_id, product_id)',
         'Un produit ne peut apparaître qu\'une seule fois par grille.')
    ]