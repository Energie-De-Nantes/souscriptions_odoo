from odoo import api, fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    periode_id = fields.Many2one('souscription.periode', string='Période facturée')

    souscription_id = fields.Many2one(
        related='periode_id.souscription_id',
        string='Souscription',
        store=True,
        readonly=True,
    )

    is_facture_energie = fields.Boolean(string="Facture d'énergie", compute='_compute_is_facture_energie', store=True)

    # Plomberie dérivée (#185, PRD #183) : la Souscription est l'unique source
    # de vérité du Mode de paiement (CONTEXT.md) — jamais saisi sur la
    # Facture. related stocké pour rester filtrable/groupable (vue
    # « Règlements en attente ») ; se recalcule quand la Souscription change.
    mode_paiement = fields.Selection(
        related='souscription_id.mode_paiement',
        string='Mode de paiement',
        store=True,
        readonly=True,
    )

    @api.depends('periode_id', 'souscription_id')
    def _compute_is_facture_energie(self):
        """Détermine si c'est une facture d'énergie (souscription électricité)"""
        for move in self:
            move.is_facture_energie = bool(move.periode_id and move.souscription_id)

    def _get_report_base_filename(self):
        """Nom de fichier personnalisé pour les factures d'énergie"""
        self.ensure_one()
        if self.is_facture_energie and self.souscription_id:
            return f'Facture_Energie_{self.souscription_id.name}_{self.name}'
        return super()._get_report_base_filename()
