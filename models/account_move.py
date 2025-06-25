# -*- coding: utf-8 -*-
from odoo import models, fields, api

class AccountMove(models.Model):
    _inherit = 'account.move'
    
    # Relation avec les souscriptions via les périodes
    periode_id = fields.Many2one(
        'souscription.periode',
        string='Période de facturation',
        help='Période de souscription associée à cette facture'
    )
    
    souscription_id = fields.Many2one(
        'souscription.souscription',
        string='Souscription',
        related='periode_id.souscription_id',
        store=True,
        help='Souscription électrique associée à cette facture'
    )