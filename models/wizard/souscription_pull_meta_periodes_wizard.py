"""Wizard facturiste « Récupérer les périodes du mois » (#77, ADR 0011/0019).

Brancher le seam décidé : l'addon consomme le paquet `electricore-client`
(httpx + pydantic) et n'implémente que le mapping vers ses propres modèles
(`souscription.periode._amorcer_depuis_meta`). Le client est acquis auprès de
la fabrique unique `souscription.electricore.client` (ADR 0024) : ce module
ne porte plus ni garde d'import du client, ni drapeau de disponibilité, ni
lecture de config — seuls son propre appel d'endpoint (`meta_periodes` en
flux) et son mapping d'exceptions.
"""

from __future__ import annotations

from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError

# Garde d'import minimale (ADR 0024) : seules les exceptions du mapping de ce
# wizard sont importées ici — la construction du client (garde + drapeau +
# config) vit dans la fabrique. Si le paquet est absent, la fabrique lève
# avant qu'aucune de ces exceptions ne puisse être levée.
try:
    from electricore_client import ContractVersionError, IngestionEnCours
    from electricore_client.exceptions import PreconditionNonRemplie
except ImportError:  # pragma: no cover - paquet optionnel ; la fabrique lève avant tout mapping

    class ContractVersionError(Exception):
        """Repli si `electricore_client` est absent : jamais levée en pratique."""

    class IngestionEnCours(Exception):
        """Repli si `electricore_client` est absent : jamais levée en pratique."""

    class PreconditionNonRemplie(Exception):
        """Repli si `electricore_client` est absent : jamais levée en pratique."""


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
        résultat (créées / déjà existantes / sans RSC / erreurs).

        Le client est acquis en tête, avant toute recherche (échec rapide et
        déterministe, ADR 0024 §5) : un même clic produit toujours la même
        classe de résultat, que des souscriptions à RSC existent ou non."""
        self.ensure_one()
        client = self.env['souscription.electricore.client'].client()

        Souscription = self.env['souscription.souscription']
        Periode = self.env['souscription.periode']

        avec_rsc = Souscription.search([('ref_situation_contractuelle', '!=', False), ('active', '=', True)])
        sans_rsc = Souscription.search([('ref_situation_contractuelle', '=', False), ('active', '=', True)])
        par_rsc = {s.ref_situation_contractuelle: s for s in avec_rsc}

        creees, existantes, erreurs = [], [], []

        if par_rsc:
            mois_str = fields.Date.to_string(self.mois)
            try:
                with self._ouvrir_flux(client, mois_str, list(par_rsc)) as stream:
                    for meta in stream:
                        souscription = par_rsc.get(meta.ref_situation_contractuelle)
                        if souscription is None:
                            continue  # RSC hors du filtre demandé, ignorée silencieusement
                        try:
                            # Savepoint par élément (skip-and-report, ADR 0011) :
                            # un échec de mapping/contrainte sur une RSC ne doit
                            # ni écrire de résultat partiel ni casser le curseur
                            # pour les RSC suivantes du même lot.
                            with self.env.cr.savepoint():
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
        amorcé n'est jamais réécrit. Recherche explicite d'abord (lisible,
        rapide) ; la contrainte unique mensuelle (ADR 0020 §2) reste le
        garde-fou de dernier recours si deux amorçages se recouvraient malgré
        tout — remontée comme une erreur normale, absorbée par le savepoint
        appelant."""
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

    def _ouvrir_flux(self, client, mois_str, rsc):
        """Point de transport unique : ouvre le flux `meta_periodes` (context
        manager). Seul endroit qui parle réseau — c'est la couture patchée en
        tests (réponses en boîte, rien d'autre n'est mocké)."""
        return client.meta_periodes(mois=mois_str, rsc=rsc)
