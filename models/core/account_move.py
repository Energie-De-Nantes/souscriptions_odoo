from odoo import models, fields, api

class AccountMove(models.Model):
    _inherit = 'account.move'

    periode_id = fields.Many2one('souscription.periode', string='Période facturée')

    souscription_id = fields.Many2one(
        related='periode_id.souscription_id',
        string="Souscription",
        store=True,
        readonly=True,
    )

    is_facture_energie = fields.Boolean(
        string="Facture d'énergie", 
        compute='_compute_is_facture_energie',
        store=True
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
            return f"Facture_Energie_{self.souscription_id.name}_{self.name}"
        return super()._get_report_base_filename()
