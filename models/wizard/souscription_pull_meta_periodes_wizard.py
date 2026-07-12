"""Wizard facturiste « Récupérer les périodes du mois » (#77, ADR 0011/0019).

Coquille mince (#233, tranche 1 du PRD #231) : le propriétaire durable du
pull — méthode de transport nommée, mapping du contrat v3, politique
d'écriture gardée par l'empreinte (ADR 0030 décision 1, #235) — vit désormais
dans `souscription.pull.meta.periodes.service`. Ce wizard ne fait plus que
construire le périmètre (toutes les souscriptions, avec/sans RSC), déléguer
le tirage au service (scope facturation, `pull()`) et formater le résumé
(créées / rafraîchies / inchangées / conservées / sans RSC / erreurs).
"""

from __future__ import annotations

from datetime import timedelta

from odoo import api, fields, models


class SouscriptionPullMetaPeriodesWizard(models.TransientModel):
    _name = 'souscription.pull.meta.periodes.wizard'
    _description = 'Récupérer les périodes du mois (pull electricore)'

    mois = fields.Date(
        string='Mois',
        required=True,
        default=lambda self: self._default_mois(),
        help="Mois à récupérer — n'importe quelle date du mois convient, seuls l'année et le mois comptent.",
    )
    state = fields.Selection([('form', 'Formulaire'), ('done', 'Résultat')], default='form')
    resultat = fields.Text(string='Résumé', readonly=True)

    @api.model
    def _default_mois(self):
        """1er du mois précédent — même calcul que `ajouter_periodes_mensuelles`
        (souscription.py), sans dépendance à dateutil."""
        premier_mois_courant = fields.Date.context_today(self).replace(day=1)
        return (premier_mois_courant - timedelta(days=1)).replace(day=1)

    def action_lancer(self):
        """Récupère les méta-périodes du mois pour toutes les souscriptions à
        RSC (scope facturation, `pull()`) : crée les périodes manquantes,
        rafraîchit les existantes selon la politique gardée par l'empreinte
        (ADR 0030 décision 1, #235), résume le résultat (créées / rafraîchies
        / inchangées / conservées / sans RSC / erreurs).

        Chemin ad-hoc (mois saisi, portée toutes-RSC) : délègue le tirage au
        service `souscription.pull.meta.periodes.service` (#233), le même que
        le chemin Campagne
        (`souscription.campagne.facturation.action_pull_meta_periodes`,
        portée Périmètre de campagne) — ce wizard ne fait plus que construire
        le périmètre et formater le résumé."""
        self.ensure_one()
        Souscription = self.env['souscription.souscription']

        avec_rsc = Souscription.search([('ref_situation_contractuelle', '!=', False), ('active', '=', True)])
        sans_rsc = Souscription.search([('ref_situation_contractuelle', '=', False), ('active', '=', True)])

        creees, rafraichies, inchangees, conservees, erreurs = self.env['souscription.pull.meta.periodes.service'].pull(
            avec_rsc, self.mois
        )

        self.resultat = self._formatter_resultat(creees, rafraichies, inchangees, conservees, sans_rsc, erreurs)
        self.state = 'done'
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    @staticmethod
    def _formatter_resultat(creees, rafraichies, inchangees, conservees, sans_rsc, erreurs):
        lignes = [
            f'Créées : {len(creees)}',
            f'Rafraîchies : {len(rafraichies)}',
            f'Inchangées : {len(inchangees)}',
            f'Conservées (signalées) : {len(conservees)}',
            f'Sans RSC (ignorées) : {len(sans_rsc)}',
            f'Erreurs : {len(erreurs)}',
            '',
        ]
        if creees:
            lignes += ['Périodes créées :'] + [f'  - {ligne}' for ligne in creees] + ['']
        if rafraichies:
            lignes += ['Rafraîchies (mesuré v3 en bloc) :'] + [f'  - {ligne}' for ligne in rafraichies] + ['']
        if conservees:
            lignes += (
                ['Conservées (empreinte incertaine ou mois absent, signalées) :']
                + [f'  - {ligne}' for ligne in conservees]
                + ['']
            )
        if sans_rsc:
            lignes += ['Souscriptions sans RSC (ignorées) :'] + [f'  - {s.name}' for s in sans_rsc] + ['']
        if erreurs:
            lignes += ['Erreurs :'] + [f'  - {ligne}' for ligne in erreurs]
        return '\n'.join(lignes)
