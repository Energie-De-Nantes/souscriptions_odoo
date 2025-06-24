from odoo import models, fields

class MetierPrestation(models.Model):
    _name = "metier.prestation"
    _description = "Prestations issues de la facturation"
    _order = "date_debut"

    id_ev = fields.Char(string="Id Événement", readonly=True)
    libelle_ev = fields.Char(string="Libellé", readonly=True)
    nature_ev = fields.Char(string="Nature", readonly=True)
    date_debut = fields.Datetime(string="Début", readonly=True)
    date_fin = fields.Datetime(string="Fin", readonly=True)
    unite = fields.Char(string="Unité", readonly=True)
    quantite = fields.Float(string="Quantité", readonly=True)
    prix_unitaire = fields.Float(string="Prix unitaire", readonly=True)
    montant_ht = fields.Float(string="Montant HT", readonly=True)
    taux_tva_applicable = fields.Char(string="TVA", readonly=True)

    pdl = fields.Char(string="PDL", readonly=True)
    num_facture = fields.Char(string="N° Facture", readonly=True)
    date_facture = fields.Datetime(string="Date Facture", readonly=True)
    type_facturation = fields.Char(string="Type", readonly=True)
    source = fields.Char(string="Source", readonly=True)
    marque = fields.Char(string="Marque", readonly=True)
