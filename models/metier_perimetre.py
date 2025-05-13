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
    pdl = fields.Char(string="PDL")
    id_affaire = fields.Char(string="Id Affaire")
    ref_demandeur = fields.Char(string="Réf Demandeur")
    ref_situation_contractuelle = fields.Char(string="Réf Situation Contractuelle")

    # Dates
    # apres_date_releve = fields.Datetime(string="Après Date Relevé")
    # avant_date_releve = fields.Datetime(string="Avant Date Relevé")
    date_evenement = fields.Datetime(string="Date Événement")
    date_derniere_modification_fta = fields.Char(string="Date Dernière Modif FTA")  # resté object, non parsé

    # Index (Avant / Après)
    apres_base = fields.Float()
    apres_hc = fields.Float()
    apres_hcb = fields.Float()
    apres_hch = fields.Float()
    apres_hp = fields.Float()
    apres_hpb = fields.Float()
    apres_hph = fields.Float()
    apres_id_calendrier_distributeur = fields.Char()
    apres_id_calendrier_fournisseur = fields.Char()
    apres_nature_index = fields.Char()

    avant_base = fields.Float()
    avant_hc = fields.Float()
    avant_hcb = fields.Float()
    avant_hch = fields.Float()
    avant_hp = fields.Float()
    avant_hpb = fields.Float()
    avant_hph = fields.Float()
    avant_id_calendrier_distributeur = fields.Char()
    avant_id_calendrier_fournisseur = fields.Char()
    avant_nature_index = fields.Char()

    # Métadonnées
    categorie = fields.Char()
    etat_contractuel = fields.Char()
    evenement_declencheur = fields.Char()
    type_evenement = fields.Char()
    formule_tarifaire_acheminement = fields.Char()
    marque = fields.Char()
    num_compteur = fields.Char()
    num_depannage = fields.Char()
    precision = fields.Char()
    puissance_souscrite = fields.Float()
    segment_clientele = fields.Char()
    source = fields.Char()
    type_compteur = fields.Char()
