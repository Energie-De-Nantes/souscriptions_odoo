from odoo import models, fields, api

class RaccordementStage(models.Model):
    _name = 'raccordement.stage'
    _description = 'Étapes de raccordement'
    _order = 'sequence, id'

    name = fields.Char(string='Nom', required=True, translate=True)
    sequence = fields.Integer(string='Séquence', default=10)
    fold = fields.Boolean(string='Replié dans la vue kanban', default=False)
    description = fields.Text(string='Description')
    color = fields.Integer(string='Couleur')
    
    is_close = fields.Boolean(
        string='Étape finale',
        help="Indique si cette étape correspond à la finalisation du raccordement"
    )
    
    demande_ids = fields.One2many(
        'raccordement.demande',
        'stage_id',
        string='Demandes'
    )