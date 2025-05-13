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

    # Index (Après)
    apres_base = fields.Integer(readonly=True)
    apres_hc = fields.Integer(readonly=True)
    apres_hcb = fields.Integer(readonly=True)
    apres_hch = fields.Integer(readonly=True)
    apres_hp = fields.Integer(readonly=True)
    apres_hpb = fields.Integer(readonly=True)
    apres_hph = fields.Integer(readonly=True)
    apres_id_calendrier_distributeur = fields.Char(readonly=True)
    apres_id_calendrier_fournisseur = fields.Char(readonly=True)
    apres_nature_index = fields.Char(readonly=True)

    # Index (Avant)
    avant_base = fields.Integer(readonly=True)
    avant_hc = fields.Integer(readonly=True)
    avant_hcb = fields.Integer(readonly=True)
    avant_hch = fields.Integer(readonly=True)
    avant_hp = fields.Integer(readonly=True)
    avant_hpb = fields.Integer(readonly=True)
    avant_hph = fields.Integer(readonly=True)
    avant_id_calendrier_distributeur = fields.Char(readonly=True)
    avant_id_calendrier_fournisseur = fields.Char(readonly=True)
    avant_nature_index = fields.Char(readonly=True)

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
