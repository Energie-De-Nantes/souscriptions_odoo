"""Propriétaire durable du pull des méta-périodes electricore — pull **unifié**
gardé par l'empreinte (#235, tranche 2 du PRD #231 — ADR 0030 décision 1,
amende ADR-0011/0015).

Politique d'écriture unique, appliquée à chaque `(souscription, mois)` déjà
amorcé :

- `source_hash` **inchangé** -> rien n'est touché (une correction manuelle du·
  de la facturiste survit à la relecture de données inchangées) ;
- empreinte **nouvelle** + verdict `réelle`/`estimée` -> écrase l'atterrissage
  réseau v3 **en bloc** (`souscription.periode._rafraichir_depuis_meta`) —
  jamais d'énergie fraîche sur TURPE périmé — et, **seulement si la Période
  n'est pas facturée**, remplace aussi les relevés en bloc (le re-pull promis
  par ADR 0015) ;
- `incalculable` ou mois absent du flux -> la valeur stockée est conservée,
  signalée au rapport (« je ne sais pas » n'écrase pas « je savais »).

Le create-missing-only **strict** d'ADR 0011 meurt : create-missing reste la
politique de **création** (une Période déjà amorcée n'est jamais recréée),
mais elle n'est plus systématiquement **ignorée** — elle est désormais
évaluée par l'empreinte ci-dessus.

Exemption chirurgicale du verrou de facturation (#14) : le **mesuré** d'une
Période facturée redevient réécrivable par ce service (et par le·la
facturiste à la main, cf. `souscription.periode._LOCKED_FIELDS`). Le
**facturé** (provisions, jours, snapshot contractuel, relevés-justificatifs)
reste refusé — ce service n'écrit **jamais** `provision_*`.

Deux scopes partagent cette politique (ADR 0030 conséquences) :
- `pull(souscriptions, mois)` — scope **facturation** : un mois, crée les
  Périodes manquantes (wizard ad-hoc, bouton Campagne) ;
- `refresh(souscriptions, mois_debut, mois_fin)` — scope **refresh** : plage
  de mois, ne crée jamais de Période (consommé par la Régularisation,
  tranche 4 du PRD #231, pour rafraîchir le mesuré des mois candidats avant
  de calculer les écarts).
"""

from __future__ import annotations

from datetime import date

from odoo import fields, models
from odoo.exceptions import UserError

from .electricore_client_fabrique import ContractVersionError, IngestionEnCours, PreconditionNonRemplie

# Verdicts electricore jugés fiables pour écraser le mesuré stocké (ADR 0030
# décision 1) — les termes du glossaire electricore, accents compris
# (CONTEXT.md « Qualité »).
_QUALITES_FIABLES = ('réelle', 'estimée')


class SouscriptionPullMetaPeriodesService(models.AbstractModel):
    _name = 'souscription.pull.meta.periodes.service'
    _description = "Pull unifié des méta-périodes electricore, gardé par l'empreinte (ADR 0030, #235)"

    def pull(self, souscriptions, mois):
        """Scope **facturation** (#233/#235) : un mois, crée les Périodes
        manquantes (create-missing) et rafraîchit les existantes selon la
        politique gardée par l'empreinte (docstring du module).

        Args:
            souscriptions: le périmètre déjà voulu par l'appelant (toutes-RSC
                pour le wizard ad-hoc, Périmètre de campagne du mois pour la
                Campagne) — aucun filtre supplémentaire ici, seules les
                souscriptions à RSC résolue participent au flux.
            mois: n'importe quelle date du mois à tirer (année/mois seuls
                comptent).

        Returns:
            tuple[list[str], list[str], list[str], list[str], list[str]] :
            `(creees, rafraichies, inchangees, conservees, erreurs)`, cinq
            listes de libellés consommées par le résumé du wizard ad-hoc et
            par le résultat/toast de la Campagne (#158/#176).
        """
        return self._pull_un_mois(souscriptions, mois, creer_manquantes=True)

    def refresh(self, souscriptions, mois_debut, mois_fin):
        """Scope **refresh** (#235 AC6) : rafraîchit, gardé par l'empreinte,
        les Périodes déjà amorcées sur la plage `[mois_debut, mois_fin]`
        (bornes incluses, tronquées au 1er du mois) — ne crée **jamais** de
        Période manquante. Consommé par la Régularisation (tranche 4 du PRD
        #231) pour rafraîchir le mesuré des mois candidats avant de calculer
        les écarts.

        Un appel de flux electricore **par mois** : l'endpoint
        `meta_periodes` (contrat v3) ne sait interroger qu'un seul mois à la
        fois — le coût est proportionnel au nombre de mois de la plage, pas
        au nombre de souscriptions.

        Returns:
            Même forme à cinq listes que `pull()` (`creees` toujours vide).
        """
        debut = fields.Date.to_date(mois_debut).replace(day=1)
        fin = fields.Date.to_date(mois_fin).replace(day=1)
        creees, rafraichies, inchangees, conservees, erreurs = [], [], [], [], []
        mois_courant = debut
        while mois_courant <= fin:
            c, r, i, cons, e = self._pull_un_mois(souscriptions, mois_courant, creer_manquantes=False)
            creees += c
            rafraichies += r
            inchangees += i
            conservees += cons
            erreurs += e
            mois_courant = self._mois_suivant(mois_courant)
        return creees, rafraichies, inchangees, conservees, erreurs

    @staticmethod
    def _mois_suivant(mois):
        """1er du mois suivant `mois` — sans dépendance à dateutil (même
        idiome que `souscription.campagne.facturation._default_mois`)."""
        return date(mois.year + (mois.month // 12), mois.month % 12 + 1, 1)

    def _pull_un_mois(self, souscriptions, mois, *, creer_manquantes):
        """Un seul appel de flux `meta_periodes` pour `mois`, appliqué selon
        la politique gardée par l'empreinte à toutes les souscriptions à RSC
        de `souscriptions` — brique partagée par `pull()` et `refresh()`."""
        client = self.env['souscription.electricore.client'].client()
        Periode = self.env['souscription.periode']
        par_rsc = {s.ref_situation_contractuelle: s for s in souscriptions if s.ref_situation_contractuelle}

        creees, rafraichies, inchangees, conservees, erreurs = [], [], [], [], []
        if not par_rsc:
            return creees, rafraichies, inchangees, conservees, erreurs

        # `mois_cle_requete` : le mois demandé au serveur — sert à construire
        # `mois_str` et, en repli, à chercher les Périodes déjà amorcées dont
        # la RSC n'est pas revenue dans le lot (aucune `meta` disponible pour
        # ces cas, cf. plus bas). La recherche par (souscription, mois) d'une
        # RSC **présente** dans le flux dérive plutôt son `mois_cle` de
        # `meta.debut` (dans `_appliquer_une`, même idiome que
        # `_amorcer_depuis_meta`) — défensif si jamais le serveur tronque le
        # mois différemment de ce qui a été demandé.
        mois_cle_requete = fields.Date.to_date(mois).replace(day=1)
        mois_str = fields.Date.to_string(mois_cle_requete)
        rsc_traitees = set()

        try:
            with self._ouvrir_flux(client, mois_str, list(par_rsc)) as stream:
                for meta in stream:
                    souscription = par_rsc.get(meta.ref_situation_contractuelle)
                    if souscription is None:
                        continue  # RSC hors du filtre demandé, ignorée silencieusement
                    rsc_traitees.add(meta.ref_situation_contractuelle)
                    try:
                        # Savepoint par élément (skip-and-report, ADR 0011) :
                        # un échec de mapping/contrainte sur une RSC ne doit
                        # ni écrire de résultat partiel ni casser le curseur
                        # pour les RSC suivantes du même lot.
                        with self.env.cr.savepoint():
                            self._appliquer_une(
                                Periode,
                                souscription,
                                meta,
                                creer_manquantes=creer_manquantes,
                                creees=creees,
                                rafraichies=rafraichies,
                                inchangees=inchangees,
                                conservees=conservees,
                            )
                    except Exception as exc:
                        erreurs.append(f'{souscription.name} ({mois_str}) : {exc}')
        except IngestionEnCours:
            raise UserError("L'ingestion electricore est en cours (verrou base) : réessayez plus tard.")
        except PreconditionNonRemplie as exc:
            raise UserError(f'Précondition non remplie côté electricore : {exc}')
        except ContractVersionError as exc:
            raise UserError(f'Contrat electricore obsolète : {exc}')

        # Mois absent du flux (ADR 0030 décision 1) : une Période déjà
        # amorcée dont la RSC n'est pas revenue dans ce lot est conservée et
        # signalée — « je ne sais pas » n'écrase pas « je savais ».
        rsc_absentes = [rsc for rsc in par_rsc if rsc not in rsc_traitees]
        if rsc_absentes:
            souscription_ids = [par_rsc[rsc].id for rsc in rsc_absentes]
            existantes = Periode.search(
                [
                    ('souscription_id', 'in', souscription_ids),
                    ('mois', '=', mois_cle_requete),
                    ('type_periode', '=', 'mensuelle'),
                ]
            )
            for periode in existantes:
                conservees.append(f'{periode.souscription_id.name} ({periode.mois_annee}) : mois absent du flux')

        return creees, rafraichies, inchangees, conservees, erreurs

    def _appliquer_une(
        self, Periode, souscription, meta, *, creer_manquantes, creees, rafraichies, inchangees, conservees
    ):
        """Applique la politique gardée par l'empreinte (ADR 0030 décision 1)
        à un couple `(souscription, mois)` face à une `meta` du flux — le mois
        se dérive de `meta.debut` (même idiome que `_amorcer_depuis_meta`)."""
        mois_cle = fields.Date.to_date(meta.debut).replace(day=1)
        existante = Periode.search(
            [
                ('souscription_id', '=', souscription.id),
                ('mois', '=', mois_cle),
                ('type_periode', '=', 'mensuelle'),
            ],
            limit=1,
        )

        if not existante:
            if creer_manquantes:
                Periode._amorcer_depuis_meta(souscription, meta)
                creees.append(f'{souscription.name} ({meta.mois_annee})')
            return  # scope refresh : ne crée jamais (#235 AC6)

        if existante.source_hash and existante.source_hash == meta.source_hash:
            inchangees.append(f'{souscription.name} ({meta.mois_annee})')
            return

        qualite = meta.qualite or 'incalculable'
        if qualite not in _QUALITES_FIABLES:
            conservees.append(f'{souscription.name} ({meta.mois_annee}) : qualité {qualite}')
            return

        existante._rafraichir_depuis_meta(meta)
        rafraichies.append(f'{souscription.name} ({meta.mois_annee})')

    def _ouvrir_flux(self, client, mois_str, rsc):
        """Point de transport unique : ouvre le flux `meta_periodes` (context
        manager). Seul endroit qui parle réseau — c'est la couture patchée en
        tests (réponses en boîte, rien d'autre n'est mocké)."""
        return client.meta_periodes(mois=mois_str, rsc=rsc)
