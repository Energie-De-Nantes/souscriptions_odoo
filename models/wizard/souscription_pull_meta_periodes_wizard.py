"""Wizard facturiste « Récupérer les périodes du mois » (#77, ADR 0011/0019).

Brancher le seam décidé : l'addon consomme le paquet `electricore-client`
(httpx + pydantic) et n'implémente que le mapping vers ses propres modèles
(`souscription.periode._amorcer_depuis_meta`). Le paquet n'est pas une
dépendance dure d'installation (cf. `requirements.txt` + garde d'import
ci-dessous) : un déploiement sans le paquet installe le module, le bouton du
wizard échoue avec un message actionnable.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Garde d'import (#77 AC1) : `electricore_client` est un paquet PyPI épinglé
# (requirements.txt), pas une dépendance dure Odoo — `external_dependencies`
# ferait échouer l'installation du module sur toute instance qui ne l'a pas
# encore, ce qui contredit « module installable » (cf. rapport de la PR).
try:
    from electricore_client import (
        ContractVersionError,
        ElectricoreClient,
        IngestionEnCours,
    )
    from electricore_client.exceptions import PreconditionNonRemplie

    ELECTRICORE_CLIENT_DISPONIBLE = True
except ImportError:  # pragma: no cover - exercé par test_client_manquant
    ELECTRICORE_CLIENT_DISPONIBLE = False


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
        RSC, crée les périodes manquantes (create-missing-only), résume le
        résultat (créées / déjà existantes / sans RSC / erreurs)."""
        self.ensure_one()
        if not ELECTRICORE_CLIENT_DISPONIBLE:
            raise UserError(
                "Le paquet 'electricore_client' n'est pas installé sur ce serveur. "
                'Installez-le (pip install electricore-client==0.1.0) puis réessayez.'
            )

        Souscription = self.env['souscription.souscription']
        Periode = self.env['souscription.periode']

        avec_rsc = Souscription.search([('ref_situation_contractuelle', '!=', False), ('active', '=', True)])
        sans_rsc = Souscription.search([('ref_situation_contractuelle', '=', False), ('active', '=', True)])
        par_rsc = {s.ref_situation_contractuelle: s for s in avec_rsc}

        creees, existantes, erreurs = [], [], []

        if par_rsc:
            client = self._client()
            mois_str = fields.Date.to_string(self.mois)
            try:
                with client.meta_periodes(mois=mois_str, rsc=list(par_rsc)) as stream:
                    for meta in stream:
                        souscription = par_rsc.get(meta.ref_situation_contractuelle)
                        if souscription is None:
                            continue  # RSC hors du filtre demandé, ignorée silencieusement
                        try:
                            self._amorcer_une(Periode, souscription, meta, creees, existantes)
                        except Exception as exc:
                            erreurs.append(f'{souscription.name} ({meta.ref_situation_contractuelle}) : {exc}')
            except IngestionEnCours:
                raise UserError("L'ingestion electricore est en cours (verrou base) : réessayez plus tard.")
            except PreconditionNonRemplie as exc:
                raise UserError(f'Précondition non remplie côté electricore : {exc}')
            except ContractVersionError as exc:
                raise UserError(f'Contrat electricore obsolète : {exc}')

        self.resultat = self._formatter_resultat(creees, existantes, sans_rsc, erreurs)
        self.state = 'done'
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def _amorcer_une(self, Periode, souscription, meta, creees, existantes):
        """Create-missing-only (ADR 0011) : un `(souscription, mois)` déjà
        amorcé n'est jamais réécrit. La contrainte unique mensuelle
        (ADR 0020 §2) fait foi ; on vérifie d'abord pour ne pas dépendre d'un
        rollback de savepoint par élément."""
        mois_cle = fields.Date.to_date(meta.debut).replace(day=1)
        existante = Periode.search(
            [
                ('souscription_id', '=', souscription.id),
                ('mois', '=', mois_cle),
                ('type_periode', '=', 'mensuelle'),
            ],
            limit=1,
        )
        if existante:
            existantes.append(f'{souscription.name} ({meta.mois_annee})')
            return
        Periode._amorcer_depuis_meta(souscription, meta)
        creees.append(f'{souscription.name} ({meta.mois_annee})')

    @staticmethod
    def _formatter_resultat(creees, existantes, sans_rsc, erreurs):
        lignes = [
            f'Créées : {len(creees)}',
            f'Déjà existantes : {len(existantes)}',
            f'Sans RSC (ignorées) : {len(sans_rsc)}',
            f'Erreurs : {len(erreurs)}',
            '',
        ]
        if creees:
            lignes += ['Périodes créées :'] + [f'  - {ligne}' for ligne in creees] + ['']
        if existantes:
            lignes += ['Déjà existantes (non réécrites) :'] + [f'  - {ligne}' for ligne in existantes] + ['']
        if sans_rsc:
            lignes += ['Souscriptions sans RSC (ignorées) :'] + [f'  - {s.name}' for s in sans_rsc] + ['']
        if erreurs:
            lignes += ['Erreurs :'] + [f'  - {ligne}' for ligne in erreurs]
        return '\n'.join(lignes)

    def _client(self):
        """Construit le client electricore depuis `ir.config_parameter`
        (`souscriptions.electricore_url` / `souscriptions.electricore_api_key`)."""
        ICP = self.env['ir.config_parameter'].sudo()
        url = ICP.get_param('souscriptions.electricore_url')
        api_key = ICP.get_param('souscriptions.electricore_api_key')
        if not url or not api_key:
            raise UserError(
                'Configuration electricore manquante : renseignez les paramètres système '
                "'souscriptions.electricore_url' et 'souscriptions.electricore_api_key'."
            )
        return ElectricoreClient(url=url, api_key=api_key)
