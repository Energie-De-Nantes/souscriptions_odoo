"""Bouton « Chronologie » — frise electricore au grain RSC (#200, ADR 0024).

Outil de diagnostic interne, lecture seule : tire `GET /facturation/chronologie`
(client épinglé 0.4.0, `client.chronologie(rsc=…)`, fabrique unique
`souscription.electricore.client`) et affiche le résultat en vue liste
transitoire — purgée puis recréée à chaque clic, scopée par souscription.
Pas de persistance métier : electricore reste autoritaire, on ne re-mirroire
aucune donnée réseau (CONTEXT.md, ADR 0001/0019).

Grain `rsc` uniquement (pas de repli `pdl` — une seconde action dédiée
pourrait un jour exposer la vue point, hors périmètre ici). Garde d'import +
mapping d'exceptions locaux à ce module, même posture que le wizard de pull
des méta-périodes (`souscription_pull_meta_periodes_wizard.py`, ADR 0024) :
la fabrique s'arrête à « rends-moi un client configuré », chaque appelant
garde son appel d'endpoint et son propre mapping.

Cette tranche pose le modèle de ligne transitoire et son mapping pur (3
types) ; le bouton lui-même (`action_ouvrir_chronologie`, appel réseau,
purge/recréation) arrive dans la tranche suivante.
"""

from __future__ import annotations

from odoo import api, fields, models


class SouscriptionChronologieLigne(models.Model):
    """Ligne de frise transitoire (union des 3 types du contrat v1 de
    `chronologie` : `evenement` | `releve` | `periode_energie`) — noms de
    champs repris tels quels du contrat electricore (single-source, ADR
    0019), sans traduction. Purgée et recréée en entier à chaque clic sur le
    bouton « Chronologie » : ce n'est jamais une donnée métier, seulement un
    instantané d'affichage."""

    _name = 'souscription.chronologie.ligne'
    _description = 'Ligne de chronologie electricore (transitoire, diagnostic)'
    _order = 'date, id'

    souscription_id = fields.Many2one(
        'souscription.souscription', string='Souscription', required=True, ondelete='cascade', index=True
    )
    type_ligne = fields.Selection(
        [('evenement', 'Événement'), ('releve', 'Relevé'), ('periode_energie', "Période d'énergie")],
        string='Type de ligne',
        required=True,
    )
    date = fields.Date(string='Date', required=True)
    pdl = fields.Char(string='PDL')
    ref_situation_contractuelle = fields.Char(string='RSC')

    # --- evenement ---
    source = fields.Char(string='Source')
    type_fait = fields.Char(string='Type de fait')
    evenement_declencheur = fields.Char(string='Événement déclencheur')
    puissance_souscrite_kva = fields.Float(string='Puissance souscrite (kVA)')
    formule_tarifaire_acheminement = fields.Char(string='FTA')
    niveau_ouverture_services = fields.Char(string='Niveau ouverture services')
    impacte_abonnement = fields.Boolean(string='Impacte abonnement')
    resume_modification = fields.Char(string='Résumé modification')

    # --- releve ---
    releve_id = fields.Char(string='Identifiant relevé')
    nature_index = fields.Char(string='Nature index')
    origine_releve = fields.Char(string='Origine relevé')
    ordre_index = fields.Integer(string='Ordre index')
    index_base_kwh = fields.Integer(string='Index Base (kWh)')
    index_hp_kwh = fields.Integer(string='Index HP (kWh)')
    index_hc_kwh = fields.Integer(string='Index HC (kWh)')
    index_hph_kwh = fields.Integer(string='Index HPH (kWh)')
    index_hch_kwh = fields.Integer(string='Index HCH (kWh)')
    index_hpb_kwh = fields.Integer(string='Index HPB (kWh)')
    index_hcb_kwh = fields.Integer(string='Index HCB (kWh)')

    # --- periode_energie ---
    debut = fields.Date(string='Début de période')
    fin = fields.Date(string='Fin de période')
    nb_jours = fields.Integer(string='Nb jours')
    qualite = fields.Selection(
        [('réelle', 'Réelle'), ('estimée', 'Estimée'), ('incalculable', 'Incalculable')],
        string='Qualité',
    )
    statut_communication = fields.Selection(
        [('communicante', 'Communicante'), ('non_communicante', 'Non communicante')],
        string='Statut de communication',
    )
    energie_base_kwh = fields.Float(string='Énergie Base (kWh)')
    energie_hp_kwh = fields.Float(string='Énergie HP (kWh)')
    energie_hc_kwh = fields.Float(string='Énergie HC (kWh)')
    energie_hph_kwh = fields.Float(string='Énergie HPH (kWh)')
    energie_hch_kwh = fields.Float(string='Énergie HCH (kWh)')
    energie_hpb_kwh = fields.Float(string='Énergie HPB (kWh)')
    energie_hcb_kwh = fields.Float(string='Énergie HCB (kWh)')

    # Colonnes spécifiques à chaque type_ligne, masquées par défaut (issue
    # #200 : « colonnes spécifiques optionnelles/masquées par défaut ») —
    # seules les colonnes communes (type_ligne, date, pdl, ref_situation_contractuelle)
    # restent visibles sans réglage de colonnes par l'utilisateur·rice.
    _CHAMPS_COMMUNS = ('type_ligne', 'date', 'pdl', 'ref_situation_contractuelle')

    @api.model
    def _vals_depuis_ligne(self, souscription, ligne):
        """Mappe une `LigneEvenement | LigneReleve | LignePeriodeEnergie`
        (déjà validée côté client, union discriminée sur `type_ligne`) vers
        les `vals` de `create()` — un seul `getattr` par champ du contrat,
        aucune traduction (même posture que `_amorcer_depuis_meta`)."""
        vals = {
            'souscription_id': souscription.id,
            'type_ligne': ligne.type_ligne,
            'date': ligne.date,
            'pdl': ligne.pdl,
            'ref_situation_contractuelle': ligne.ref_situation_contractuelle,
        }
        if ligne.type_ligne == 'evenement':
            vals.update(
                source=ligne.source,
                type_fait=ligne.type_fait,
                evenement_declencheur=ligne.evenement_declencheur,
                puissance_souscrite_kva=ligne.puissance_souscrite_kva,
                formule_tarifaire_acheminement=ligne.formule_tarifaire_acheminement,
                niveau_ouverture_services=ligne.niveau_ouverture_services,
                impacte_abonnement=ligne.impacte_abonnement,
                resume_modification=ligne.resume_modification,
            )
        elif ligne.type_ligne == 'releve':
            vals.update(
                source=ligne.source,
                releve_id=ligne.releve_id,
                nature_index=ligne.nature_index,
                origine_releve=ligne.origine_releve,
                ordre_index=ligne.ordre_index,
                evenement_declencheur=ligne.evenement_declencheur,
                index_base_kwh=ligne.index_base_kwh,
                index_hp_kwh=ligne.index_hp_kwh,
                index_hc_kwh=ligne.index_hc_kwh,
                index_hph_kwh=ligne.index_hph_kwh,
                index_hch_kwh=ligne.index_hch_kwh,
                index_hpb_kwh=ligne.index_hpb_kwh,
                index_hcb_kwh=ligne.index_hcb_kwh,
            )
        elif ligne.type_ligne == 'periode_energie':
            vals.update(
                debut=ligne.debut,
                fin=ligne.fin,
                nb_jours=ligne.nb_jours,
                qualite=ligne.qualite,
                statut_communication=ligne.statut_communication,
                energie_base_kwh=ligne.energie_base_kwh,
                energie_hp_kwh=ligne.energie_hp_kwh,
                energie_hc_kwh=ligne.energie_hc_kwh,
                energie_hph_kwh=ligne.energie_hph_kwh,
                energie_hch_kwh=ligne.energie_hch_kwh,
                energie_hpb_kwh=ligne.energie_hpb_kwh,
                energie_hcb_kwh=ligne.energie_hcb_kwh,
            )
        return vals
