from odoo import fields, models


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
        string='Étape finale', help='Indique si cette étape correspond à la finalisation du raccordement'
    )

    # Étapes pilotées par les faits (#90, ADR 0021 §5) : la demande y avance
    # seule quand son fait déclencheur est vérifié (id_Affaire saisi, RSC
    # acquise). Le drag-in manuel y est refusé — on corrige le fait, la carte
    # suit — sauf pour les automatismes (contournement de contexte).
    entree_factuelle = fields.Boolean(
        string='Étape pilotée par un fait',
        help="Le drag-in manuel est refusé sur cette étape : elle n'avance que par "
        "un automatisme (saisie de l'id_Affaire, acquisition de la RSC).",
    )
