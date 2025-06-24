from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class SouscriptionMetierMixin(models.AbstractModel):
    """
    Mixin pour l'intégration des données métier avec les souscriptions.
    
    Ce mixin sera utilisé dans le module souscriptions_bridge pour ajouter
    les computed fields métier sans créer de dépendance directe dans le core.
    """
    _name = 'souscription.metier.mixin'
    _description = 'Mixin pour intégration données métier'

    # Computed fields vers les données métier
    historique_perimetre_ids = fields.One2many(
        comodel_name="metier.perimetre",
        compute="_compute_historique_perimetre",
        string="Historique périmètre",
        help="Historique des situations contractuelles depuis Enedis"
    )

    prestations_ids = fields.One2many(
        comodel_name="metier.prestation",
        compute="_compute_prestations",
        string="Prestations liées",
        help="Prestations facturées depuis les systèmes externes"
    )

    @api.depends('pdl')
    def _compute_historique_perimetre(self):
        """Calcule l'historique périmètre basé sur le PDL"""
        _logger.info("Calcul de l'historique périmètre")
        for rec in self:
            if rec.pdl:
                rec.historique_perimetre_ids = self.env['metier.perimetre'].search([
                    ('pdl', '=', rec.pdl)
                ])
            else:
                rec.historique_perimetre_ids = []
    
    @api.depends('pdl')
    def _compute_prestations(self):
        """Calcule les prestations liées basées sur le PDL"""
        for rec in self:
            if rec.pdl:
                rec.prestations_ids = self.env['metier.prestation'].search([
                    ('pdl', '=', rec.pdl)
                ])
            else:
                rec.prestations_ids = []