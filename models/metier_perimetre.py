from odoo import models, fields

class MetierPerimetre(models.Model):
    _name = "metier.perimetre"
    _description = "Historique de périmètre (extrait synthétique)"
    _sql_constraints = [
        (
            'uniq_ref_situation_date',
            'UNIQUE(ref_situation_contractuelle, date_evenement)',
            'Un enregistrement avec cette référence contractuelle et cette date existe déjà.'
        )
    ]

    # Identifiants
    pdl = fields.Char(string="PDL", readonly=True)
    id_affaire = fields.Char(string="Id Affaire", readonly=True)
    ref_demandeur = fields.Char(string="Réf Demandeur", readonly=True)
    ref_situation_contractuelle = fields.Char(string="Réf Situation Contractuelle", readonly=True)

    # Dates
    date_evenement = fields.Datetime(string="Date Événement", readonly=True)
    date_derniere_modification_fta = fields.Char(string="Date Dernière Modif FTA", readonly=True)

    # Relations vers les index
    index_avant_id = fields.Many2one(
        "metier.mesure.index",
        string="Index avant événement",
        readonly=True,
        ondelete="set null"
    )
    index_apres_id = fields.Many2one(
        "metier.mesure.index",
        string="Index après événement",
        readonly=True,
        ondelete="set null"
    )

    # Métadonnées
    categorie = fields.Char(readonly=True)
    etat_contractuel = fields.Char(readonly=True)
    evenement_declencheur = fields.Char(readonly=True)
    type_evenement = fields.Char(readonly=True)
    formule_tarifaire_acheminement = fields.Char(readonly=True)
    marque = fields.Char(readonly=True)
    num_compteur = fields.Char(readonly=True)
    num_depannage = fields.Char(readonly=True)
    precision = fields.Char(readonly=True)
    puissance_souscrite = fields.Integer(readonly=True)
    segment_clientele = fields.Char(readonly=True)
    source = fields.Char(readonly=True)
    type_compteur = fields.Char(readonly=True)
