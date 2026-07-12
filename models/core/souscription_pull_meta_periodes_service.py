"""Propriétaire durable du pull des méta-périodes electricore (#233, tranche 1
du PRD #231 — « le facturé gelé, le mesuré vivant », ADR 0030).

Extrait du wizard transient `souscription.pull.meta.periodes.wizard` (#77),
qui en était jusqu'ici le seul propriétaire : ce module porte désormais la
méthode de transport nommée (couture de test, ADR 0024 §6), le mapping du
contrat v3 (`souscription.periode._amorcer_depuis_meta`) et la politique
d'écriture **actuelle** — create-missing-only, skip-and-report par savepoint
(ADR 0011) — sur un `AbstractModel` durable, même motif que
`souscription.rsc.service`. Le wizard mensuel et le bouton Campagne
(`souscription.campagne.facturation.action_pull_meta_periodes`) en deviennent
des coquilles minces qui délèguent à `pull()` et formatent le résultat :
**zéro changement de comportement observable** (pur prefactor, carte
« propriétaire durable du pull » de la revue d'architecture du 2026-07-12).

La politique unifiée gardée par l'empreinte (ADR 0030 §1 : `source_hash`
inchangé -> ne rien toucher, empreinte nouvelle + verdict réel/estimé ->
écraser) arrive à la tranche suivante — ce service reste create-missing-only
pour l'instant.
"""

from __future__ import annotations

from odoo import fields, models
from odoo.exceptions import UserError

from .electricore_client_fabrique import ContractVersionError, IngestionEnCours, PreconditionNonRemplie


class SouscriptionPullMetaPeriodesService(models.AbstractModel):
    _name = 'souscription.pull.meta.periodes.service'
    _description = 'Pull des méta-périodes electricore — propriétaire durable (ADR 0011/0024, #233)'

    def pull(self, souscriptions, mois):
        """Point d'entrée unique du pull (#233 AC1) : acquiert le client
        (fabrique `souscription.electricore.client`, ADR 0024), ouvre le flux
        `meta_periodes` pour `mois` sur les RSC de `souscriptions`, crée les
        périodes manquantes (create-missing-only) avec savepoint par élément
        (skip-and-report, ADR 0011) et mappe les exceptions typées electricore
        en `UserError`.

        Args:
            souscriptions: le périmètre déjà voulu par l'appelant (toutes-RSC
                pour le wizard ad-hoc, Périmètre de campagne du mois pour la
                Campagne) — aucun filtre supplémentaire ici, seules les
                souscriptions à RSC résolue participent au flux.
            mois: n'importe quelle date du mois à tirer (année/mois seuls
                comptent).

        Returns:
            tuple[list[str], list[str], list[str]] : `(creees, existantes,
            erreurs)`, trois listes de libellés consommées par le résumé du
            wizard ad-hoc et par le résultat/toast de la Campagne (#158/#176).
        """
        client = self.env['souscription.electricore.client'].client()
        Periode = self.env['souscription.periode']
        par_rsc = {s.ref_situation_contractuelle: s for s in souscriptions if s.ref_situation_contractuelle}

        creees, existantes, erreurs = [], [], []

        if par_rsc:
            mois_str = fields.Date.to_string(mois)
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

        return creees, existantes, erreurs

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

    def _ouvrir_flux(self, client, mois_str, rsc):
        """Point de transport unique : ouvre le flux `meta_periodes` (context
        manager). Seul endroit qui parle réseau — c'est la couture patchée en
        tests (réponses en boîte, rien d'autre n'est mocké)."""
        return client.meta_periodes(mois=mois_str, rsc=rsc)
