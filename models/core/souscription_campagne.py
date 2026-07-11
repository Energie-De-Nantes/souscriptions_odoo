"""Campagne de facturation (#153/#156, ADR 0025) : tableau de bord mensuel du·de
la *Facturiste* — matrice à prérequis (DAG-rollup) au-dessus d'états qui vivent
ailleurs (périodes, factures, refacturations). 0 champ de vérification ajouté sur
`souscription.periode`/`souscription.refacturation` (ADR 0025 §2) : le seul état
vraiment persisté ici est la validation des portes manuelles (et les notes
reportées, #159) — tout le reste est dérivé à la volée depuis les données
existantes (#157).
"""

from datetime import timedelta

from babel.dates import format_date
from odoo import _, api, fields, models
from odoo.exceptions import UserError

# Catalogue des étapes (#156, ADR 0025 §1) : le DAG est déclaré en code, pas de
# modèle de configuration ni de moteur de workflow. L'ordre d'insertion EST un
# ordre topologique valide (chaque étape apparaît après tous ses prérequis) —
# sert à la fois de source de vérité du DAG et d'ordre d'affichage/seed.
#
# type d'étape :
#  - 'porte'  : validation manuelle (case à cocher, validé_par/validé_le persistés) ;
#  - 'derive' : signal dérivé des données (#157) — un reste-à-faire existe,
#               l'étape est faite quand il vaut 0 ;
#  - 'action' : étape déclenchée par bouton (#158) sans backlog mensuel
#               dérivable — le pull F15 tire TOUT (pas de fenêtre temporelle,
#               ADR 0009 §2), donc pas de reste-à-faire mensuel. Elle est
#               « faite » dès qu'elle a été lancée sans erreur pour la
#               campagne (champ `lance` persisté, posé par action_executer) :
#               c'est ce qui lui permet de gater sa vérif au même titre que le
#               pull des périodes. Revirement assumé du PRD #153 (« validation
#               manuelle ») décidé au rebase de cette branche : le lancement
#               suffit, plus de coche (#163 est remplacé).
#
# Les deux « vrais pulls » (méta-périodes + F15) gatent chacun leur porte de
# vérif. Les relevés d'index NE sont PAS une étape : ils arrivent avec le pull
# des périodes (enfants souscription.releve, cf. _amorcer_depuis_meta).
#
# « Préparer les prélèvements » (#186, PRD #183) : étape 'action' dont le
# bouton ouvre une liste (SDD, préparation seulement — aucun paiement/batch/
# fichier créé par le module, cf. action_preparer_prelevements). Contrairement
# à sync F15, son « fait » n'est PAS le lancement (`lance`) mais un signal
# dérivé (cf. _compute_fait/_compute_nb_reste_a_faire) — aucun champ de
# verrou ajouté sur Période/Facture (esprit ADR 0025).
ETAPES_CAMPAGNE = {
    'pull_meta_periodes': {
        'label': 'Pull méta-périodes',
        'type': 'derive',
        'prerequis': (),
    },
    'sync_f15': {
        'label': 'Sync F15',
        'type': 'action',
        'prerequis': (),
    },
    'verif_periodes': {
        'label': 'Vérif périodes',
        'type': 'porte',
        'prerequis': ('pull_meta_periodes',),
    },
    'verif_refacturations': {
        'label': 'Vérif refacturations',
        'type': 'porte',
        'prerequis': ('sync_f15',),
    },
    'creer_factures': {
        'label': 'Créer factures',
        'type': 'derive',
        'prerequis': ('verif_periodes', 'verif_refacturations'),
    },
    'emettre_factures': {
        'label': 'Émettre factures',
        'type': 'derive',
        'prerequis': ('creer_factures',),
    },
    'preparer_prelevements': {
        'label': 'Préparer les prélèvements',
        'type': 'action',
        'prerequis': ('emettre_factures',),
    },
}


class SouscriptionCampagneFacturation(models.Model):
    """Campagne de facturation (`souscription.campagne.facturation`, ADR 0025).

    Un enregistrement par mois : orchestre les étapes de la facturation du mois
    sous forme de matrice à prérequis (CONTEXT.md « Campagne de facturation »).
    Créée par un bouton manuel (pas de cron) ; l'historique est simplement la
    liste des campagnes, triée mois décroissant (`_order`).
    """

    _name = 'souscription.campagne.facturation'
    _description = 'Campagne de facturation'
    _order = 'mois desc'

    name = fields.Char(string='Nom', compute='_compute_name', store=True)

    # Même type que souscription.periode.mois (Date, snapshotté au 1er du mois,
    # ADR 0020 §2) pour que le rapprochement (campagne, période) se fasse par
    # égalité directe, sans conversion (#157).
    mois = fields.Date(
        string='Mois',
        required=True,
        default=lambda self: self._default_mois(),
        help="Mois facturé — n'importe quelle date du mois convient, seuls l'année et le mois comptent.",
    )

    etape_ids = fields.One2many('souscription.campagne.etape', 'campagne_id', string='Étapes')
    note_ids = fields.One2many('souscription.campagne.note', 'campagne_id', string='Notes')

    # Décompte factures créées/émises du mois (#157) : dérivé, non stocké — cf.
    # _factures_du_mois().
    nb_factures_creees = fields.Integer(string='Factures créées', compute='_compute_stats_factures')
    nb_factures_emises = fields.Integer(string='Factures émises', compute='_compute_stats_factures')

    _unique_mois = models.Constraint(
        'UNIQUE(mois)',
        'Une campagne de facturation existe déjà pour ce mois.',
    )

    @api.model
    def _default_mois(self):
        """1er du mois précédent — même calcul que le wizard de pull (on ferme
        le mois qui vient de s'écouler), sans dépendance à dateutil."""
        premier_mois_courant = fields.Date.context_today(self).replace(day=1)
        return (premier_mois_courant - timedelta(days=1)).replace(day=1)

    @api.depends('mois')
    def _compute_name(self):
        for campagne in self:
            campagne.name = (
                format_date(campagne.mois, format='MMMM yyyy', locale='fr_FR').capitalize() if campagne.mois else ''
            )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('mois'):
                vals['mois'] = fields.Date.to_date(vals['mois']).replace(day=1)
        campagnes = super().create(vals_list)
        campagnes._seed_etapes()
        campagnes._reporter_notes_precedentes()
        return campagnes

    def write(self, vals):
        if vals.get('mois'):
            vals = dict(vals, mois=fields.Date.to_date(vals['mois']).replace(day=1))
        return super().write(vals)

    def _seed_etapes(self):
        """Amorce les étapes du catalogue à la création (#156) : une ligne
        d'état par étape du DAG, dans l'ordre du catalogue (ordre topologique)."""
        Etape = self.env['souscription.campagne.etape']
        for campagne in self:
            Etape.create(
                [
                    {'campagne_id': campagne.id, 'code': code, 'sequence': (i + 1) * 10}
                    for i, code in enumerate(ETAPES_CAMPAGNE)
                ]
            )

    # --- Notes reportées (#159) : rappel doux, jamais bloquant — aucune étape
    # ne lit note_ids, donc une note ne peut jamais gater le DAG. ---

    def _reporter_notes_precedentes(self):
        """Reprend les notes « à reporter, non traitées » de la campagne du
        mois précédent, comme prérequis repris (rappel doux, non bloquant).

        Chaîne naturellement (N -> N+1 -> N+2…) : la note copiée conserve
        `à_reporter=True` et repart `traité=False`, donc redevient elle-même
        éligible à la reprise lors de la création de la campagne suivante —
        jusqu'à ce qu'elle soit marquée traitée. Chaîne rompue (pas de
        campagne pour le mois précédent) : rien à reporter, aucune erreur."""
        Note = self.env['souscription.campagne.note']
        for campagne in self:
            mois_precedent = (campagne.mois - timedelta(days=1)).replace(day=1)
            precedente = self.search([('mois', '=', mois_precedent)], limit=1)
            if not precedente:
                continue
            a_reporter = precedente.note_ids.filtered(lambda n: n.a_reporter and not n.traite)
            for note in a_reporter:
                Note.create(
                    {
                        'campagne_id': campagne.id,
                        'texte': note.texte,
                        'a_reporter': True,
                        'traite': False,
                        'origine_note_id': note.id,
                    }
                )

    # --- Signaux dérivés (#157) : 0 champ ajouté sur souscription.souscription.
    # Statut de facturation par (souscription, mois de la campagne) et
    # compteurs reste-à-faire, tous recalculés à la volée depuis
    # souscription.periode / account.move (ADR 0025 §2). ---

    def _souscriptions_facturables(self):
        """Souscriptions concernées par la campagne : le Périmètre de
        campagne du mois (CONTEXT.md « Périmètre de campagne ») — recouvrement
        de l'intervalle de service avec `self.mois`, jamais l'instantané vivant
        `etat == 'en_service'` (#175)."""
        self.ensure_one()
        return self.env['souscription.souscription'].souscriptions_concernees(self.mois)

    def _statut_facturation(self, souscription):
        """Statut de facturation dérivé de `(souscription, mois de la
        campagne)` — à tirer / à facturer / facturée / émise (#157). Aucun
        champ stocké : rejoué à chaque appel depuis
        `souscription.periode.mois`/`facture_id`/`facture_state`.

        ponytail: vocabulaire PRD tel quel (à tirer/à facturer/facturée/
        émise) — l'alignement avec le vocabulaire prod sale_order.invoice_status
        demande l'inspection via l'odoo MCP (indisponible en sandbox) ;
        follow-up possible si besoin de convergence de vocabulaire un jour.
        """
        self.ensure_one()
        periode = self.env['souscription.periode'].search(
            [
                ('souscription_id', '=', souscription.id),
                ('mois', '=', self.mois),
                ('type_periode', '=', 'mensuelle'),
            ],
            limit=1,
        )
        if not periode:
            return 'a_tirer'
        if not periode.facture_id:
            return 'a_facturer'
        return 'emise' if periode.facture_state == 'posted' else 'facturee'

    # Statuts de facturation, dans l'ordre du cycle (#157). Le reste-à-faire
    # d'une étape dérivée = toutes les souscriptions pas encore parvenues au
    # statut *cible* de l'étape (cumulatif amont), pas seulement celles dans le
    # bucket juste avant : sinon une étape aval lit « fait » (reste 0) tant que
    # rien n'a atteint sa file — « émettre » se marquait faite alors que
    # « créer » avait encore tout son backlog (aucune facture créée => 0
    # souscription en « facturée » => reste 0).
    _STATUTS_ORDONNES = ('a_tirer', 'a_facturer', 'facturee', 'emise')

    # Étape à signal dérivé -> statut cible atteint = étape faite pour cette
    # souscription. Les étapes absentes (portes, action) n'ont pas de signal
    # dérivé (cf. ETAPES_CAMPAGNE) : reste-à-faire vide par construction.
    _CIBLE_PAR_ETAPE_DERIVEE = {
        'pull_meta_periodes': 'a_facturer',
        'creer_factures': 'facturee',
        'emettre_factures': 'emise',
    }

    def _reste_a_faire(self, code):
        """Souscriptions restantes pour l'étape dérivée `code` (#157) — toutes
        celles pas encore parvenues au statut cible de l'étape. Feed aussi bien
        le compteur affiché (`nb_reste_a_faire`) que le drill-down.

        ponytail: une requête par souscription facturable (échelle facturiste —
        dizaines/centaines, pas un flux temps réel) ; upgrade en une seule
        requête SQL groupée si ça devient lent un jour."""
        self.ensure_one()
        cible = self._CIBLE_PAR_ETAPE_DERIVEE.get(code)
        if not cible:
            return self.env['souscription.souscription']
        pas_encore = set(self._STATUTS_ORDONNES[: self._STATUTS_ORDONNES.index(cible)])
        cibles = self._souscriptions_facturables()
        return cibles.filtered(lambda s: self._statut_facturation(s) in pas_encore)

    def _factures_du_mois(self):
        """Factures (account.move) des périodes du mois de la campagne."""
        self.ensure_one()
        periodes = self.env['souscription.periode'].search([('mois', '=', self.mois), ('facture_id', '!=', False)])
        return periodes.facture_id

    @api.depends('mois')
    def _compute_stats_factures(self):
        for campagne in self:
            factures = campagne._factures_du_mois()
            campagne.nb_factures_creees = len(factures)
            campagne.nb_factures_emises = len(factures.filtered(lambda f: f.state == 'posted'))

    # --- Préparer les prélèvements (#186, PRD #183) : domaine partagé entre
    # le bouton (toutes périodes) et le signal dérivé « fait » (mois de la
    # campagne seulement) — mode explicitement `prelevement` uniquement,
    # jamais le mode vide (qui relève de la vue « Règlements en attente »,
    # #185). ---

    _DOMAINE_FACTURES_PRELEVEMENT_DUES = [
        ('is_facture_energie', '=', True),
        ('state', '=', 'posted'),
        ('amount_residual', '>', 0),
        ('mode_paiement', '=', 'prelevement'),
    ]

    def _factures_prelevement_dues_du_mois(self):
        """Factures prélèvement du mois de la campagne encore dues (#186) —
        `amount_residual > 0` encode déjà « aucun paiement (complet) en
        face » : pas de champ de verrou dédié, recalculé à chaque lecture
        (esprit ADR 0025)."""
        self.ensure_one()
        return self._factures_du_mois().filtered_domain(self._DOMAINE_FACTURES_PRELEVEMENT_DUES)

    def action_preparer_prelevements(self):
        """Bouton (#158) : ouvre la liste de TOUTES les factures prélèvement
        dues, toutes périodes confondues (le batch mensuel embarque les
        rattrapages, comme en prod) — pas seulement le mois de la campagne.
        Le module ne crée ni paiement, ni batch, ni fichier (décision PRD
        #183) : de là, le geste reste l'outillage comptable (sélection ->
        « Enregistrer un paiement » SDD -> batch -> pain.008)."""
        self.ensure_one()
        self._verifier_gate('preparer_prelevements')
        return {
            'type': 'ir.actions.act_window',
            'name': _('Préparer les prélèvements'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': self._DOMAINE_FACTURES_PRELEVEMENT_DUES,
        }

    # --- Boutons d'étape (#158) : délèguent aux actions déjà couvertes par
    # ailleurs (test_pull_meta_periodes.py, test_periode_facture.py...) —
    # aucune nouvelle couture réseau, `_ouvrir_flux`/`_tirer_prestations`
    # inchangées. ---

    def _etape(self, code):
        self.ensure_one()
        etape = self.etape_ids.filtered(lambda e: e.code == code)
        if not etape:
            raise UserError(_('Étape « %s » introuvable sur cette campagne.', code))
        return etape

    def _verifier_gate(self, code):
        """Garde-fou dur (#158) : bloque l'action tant que le DAG ne montre
        pas l'étape `code` prête — réutilise `etat_prerequis` (donc le
        catalogue ETAPES_CAMPAGNE), aucune logique de gate dupliquée."""
        self.ensure_one()
        etape = self._etape(code)
        if etape.etat_prerequis != 'prete':
            raise UserError(_('Étape « %s » bloquée : prérequis non satisfaits.', ETAPES_CAMPAGNE[code]['label']))

    def action_pull_meta_periodes(self):
        """Lance le tirage en un clic (#176), sans fenêtre intermédiaire :
        cible le Périmètre de campagne (#175) pour `self.mois` — aucun mois
        re-proposé, la scope est déjà celle de la campagne — et délègue la
        boucle de tirage au point partagé avec le wizard ad-hoc
        (`souscription.pull.meta.periodes.wizard._tirer_meta_periodes`, même
        couture réseau `_ouvrir_flux`/fabrique client, ADR 0024). Retourne une
        notification résumant créées/déjà présentes/erreurs — sticky si des
        erreurs, auto-dismiss sinon — aucun résumé persisté."""
        self.ensure_one()
        cibles = self._souscriptions_facturables()
        creees, existantes, erreurs = self.env['souscription.pull.meta.periodes.wizard']._tirer_meta_periodes(
            cibles, self.mois
        )
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Pull méta-périodes'),
                'message': _(
                    'Créées : %(creees)s · Déjà présentes : %(existantes)s · Erreurs : %(erreurs)s',
                    creees=len(creees),
                    existantes=len(existantes),
                    erreurs=len(erreurs),
                ),
                'type': 'warning' if erreurs else 'success',
                'sticky': bool(erreurs),
            },
        }

    def action_sync_f15(self):
        """Délègue directement à la sync F15 déjà couverte (#147),
        indépendante du pull (#158 — les deux racines du DAG n'ont aucune
        dépendance entre elles)."""
        self.ensure_one()
        return self.env['souscription.refacturation'].synchroniser_depuis_electricore()

    def action_creer_factures(self):
        """Gated sur les deux portes de vérif (#158) ; délègue à
        `creer_factures()`, déjà idempotent (anti-doublon par période,
        test_periode_facture.py)."""
        self.ensure_one()
        self._verifier_gate('creer_factures')
        self._souscriptions_facturables().creer_factures()

    def action_emettre_factures(self):
        """Gated sur créer factures (#158) : poste les factures brouillon du
        mois de la campagne (accounting standard, `action_post`)."""
        self.ensure_one()
        self._verifier_gate('emettre_factures')
        self._factures_du_mois().filtered(lambda f: f.state == 'draft').action_post()

    # action_preparer_prelevements (#186) : déclarée plus haut, aux côtés du
    # domaine partagé avec le signal dérivé « fait ».


class SouscriptionCampagneEtape(models.Model):
    """Ligne d'état par étape de campagne (#156, ADR 0025) : le seul état
    vraiment persisté du DAG — la validation des portes manuelles. Le reste
    (libellé, prérequis, type d'étape) vient du catalogue `ETAPES_CAMPAGNE`,
    source unique — aucune configuration n'est stockée en base.
    """

    _name = 'souscription.campagne.etape'
    _description = 'Étape de campagne de facturation'
    _order = 'sequence, id'

    campagne_id = fields.Many2one(
        'souscription.campagne.facturation', required=True, ondelete='cascade', string='Campagne'
    )
    sequence = fields.Integer(default=10)

    code = fields.Selection(selection=lambda self: self._selection_code(), required=True, string='Étape')

    # Type d'étape (porte/dérivée/action) : fonction pure de `code`, jamais
    # saisi — stocké uniquement pour piloter simplement les vues (invisible=)
    # sans recalcul.
    type_etape = fields.Selection(
        [('porte', 'Porte manuelle'), ('derive', 'Signal dérivé'), ('action', 'Action')],
        compute='_compute_type_etape',
        store=True,
        string='Type',
    )

    # Porte manuelle (#156, ADR 0025 §2) : état persisté du DAG avec `lance`
    # ci-dessous et les notes (#159). validé_par/validé_le sont estampillés au
    # write (jamais saisis à la main) — cf. write() ci-dessous.
    valide = fields.Boolean(string='Validé')
    valide_par_id = fields.Many2one('res.users', string='Validé par', readonly=True)
    valide_le = fields.Datetime(string='Validé le', readonly=True)

    # Étape 'action' (sync F15) : « faite » = lancée au moins une fois pour
    # cette campagne. Le pull F15 tire tout, sans signal mensuel dérivable
    # (ADR 0009 §2) ; ce drapeau persisté joue le rôle de « pull effectué »
    # pour gater « vérif refacturations », comme le reste-à-faire gate « vérif
    # périodes ». Posé par action_executer, jamais saisi à la main.
    lance = fields.Boolean(string='Lancé', readonly=True)

    etat_prerequis = fields.Selection(
        [('prete', 'Prête'), ('bloquee', 'Bloquée')],
        string='Prérequis',
        compute='_compute_etat_prerequis',
    )
    # « Fait » : pour une porte manuelle, la validation ; pour une étape à
    # signal dérivé, son reste-à-faire (#157 : fait quand nb_reste_a_faire == 0) ;
    # pour une action (sync F15), son lancement (`lance`). Cf. le catalogue.
    fait = fields.Boolean(string='Fait', compute='_compute_fait')

    # Reste-à-faire dérivé (#157) : nombre de souscriptions que cette étape
    # concerne encore. Vide (0) pour les portes/actions, qui n'ont pas de
    # signal dérivé (cf. ETAPES_CAMPAGNE et campagne_id._reste_a_faire()).
    nb_reste_a_faire = fields.Integer(string='Reste à faire', compute='_compute_nb_reste_a_faire')

    @api.model
    def _selection_code(self):
        return [(code, info['label']) for code, info in ETAPES_CAMPAGNE.items()]

    @api.depends('code')
    def _compute_type_etape(self):
        for etape in self:
            etape.type_etape = ETAPES_CAMPAGNE.get(etape.code, {}).get('type')

    def write(self, vals):
        if vals.get('valide'):
            vals = dict(vals)
            vals.setdefault('valide_par_id', self.env.user.id)
            vals.setdefault('valide_le', fields.Datetime.now())
        return super().write(vals)

    @api.depends('type_etape', 'code', 'campagne_id.mois')
    def _compute_nb_reste_a_faire(self):
        """#157 : délègue à `campagne_id._reste_a_faire(code)` — recompté à
        chaque lecture (pas de relation ORM déclarée vers période/facture,
        donc pas d'invalidation de cache automatique inter-modèles, ADR 0025).

        « Préparer les prélèvements » (#186) : même esprit dérivé, mais sur
        les factures du mois plutôt que sur les souscriptions
        (`_factures_prelevement_dues_du_mois`, pas `_reste_a_faire`)."""
        for etape in self:
            if etape.code == 'preparer_prelevements' and etape.campagne_id:
                etape.nb_reste_a_faire = len(etape.campagne_id._factures_prelevement_dues_du_mois())
            elif etape.type_etape == 'derive' and etape.campagne_id:
                etape.nb_reste_a_faire = len(etape.campagne_id._reste_a_faire(etape.code))
            else:
                etape.nb_reste_a_faire = 0

    @api.depends('valide', 'type_etape', 'code', 'nb_reste_a_faire', 'lance')
    def _compute_fait(self):
        for etape in self:
            if etape.type_etape == 'porte':
                etape.fait = etape.valide
            elif etape.type_etape == 'derive' or etape.code in self._CODES_ACTION_DERIVEE:
                etape.fait = etape.nb_reste_a_faire == 0
            else:
                # 'action' restante (sync F15) : pas de backlog dérivable
                # (tire tout, ADR 0009 §2) — « faite » une fois lancée pour
                # la campagne.
                etape.fait = etape.lance

    @api.depends('code', 'valide', 'type_etape', 'campagne_id.etape_ids.fait')
    def _compute_etat_prerequis(self):
        for etape in self:
            prerequis = ETAPES_CAMPAGNE.get(etape.code, {}).get('prerequis', ())
            # Une porte validée n'est jamais « bloquée » : la validation
            # manuelle EST l'override du·de la facturiste — Bloquée veut dire
            # « pas encore le moment », pas « déjà accompli ». Sans ça une porte
            # validée hors-séquence s'affiche Bloquée ET Faite (incohérent).
            if not prerequis or (etape.type_etape == 'porte' and etape.valide):
                etape.etat_prerequis = 'prete'
                continue
            freres = {e.code: e.fait for e in etape.campagne_id.etape_ids}
            etape.etat_prerequis = 'prete' if all(freres.get(p) for p in prerequis) else 'bloquee'

    # --- Drill-down (#157) : la liste filtrée des souscriptions concernées
    # par cette étape (pour les étapes à signal dérivé) ou, à défaut, toutes
    # les souscriptions facturables du mois. ---

    def action_drill_down(self):
        self.ensure_one()
        if self.type_etape == 'derive':
            souscriptions = self.campagne_id._reste_a_faire(self.code)
        else:
            souscriptions = self.campagne_id._souscriptions_facturables()
        return {
            'type': 'ir.actions.act_window',
            'name': ETAPES_CAMPAGNE.get(self.code, {}).get('label', self.code),
            'res_model': 'souscription.souscription',
            'view_mode': 'list,form',
            'domain': [('id', 'in', souscriptions.ids)],
        }

    # --- Bouton d'étape (#158) : un seul bouton générique par ligne, qui
    # dispatche vers la méthode de la Campagne nommée par ce code — jamais de
    # logique dupliquée entre la vue et ETAPES_CAMPAGNE. Les portes manuelles
    # n'ont pas d'entrée ici : elles se valident via le champ `valide`.
    _ACTIONS_PAR_ETAPE = {
        'pull_meta_periodes': 'action_pull_meta_periodes',
        'sync_f15': 'action_sync_f15',
        'creer_factures': 'action_creer_factures',
        'emettre_factures': 'action_emettre_factures',
        'preparer_prelevements': 'action_preparer_prelevements',
    }

    # Étapes 'action' dont le « fait » est un signal dérivé (#186) plutôt que
    # le lancement (`lance`, cf. sync F15) — cf. _compute_fait/
    # _compute_nb_reste_a_faire.
    _CODES_ACTION_DERIVEE = ('preparer_prelevements',)

    def action_executer(self):
        self.ensure_one()
        methode = self._ACTIONS_PAR_ETAPE.get(self.code)
        if not methode:
            raise UserError(
                _("Pas d'action pour l'étape « %s ».", ETAPES_CAMPAGNE.get(self.code, {}).get('label', self.code))
            )
        resultat = getattr(self.campagne_id, methode)()
        # Étape 'action' réussie (pas d'exception) = « pull effectué » pour la
        # campagne : débloque sa vérif (cf. champ `lance`).
        if self.type_etape == 'action':
            self.lance = True
        return resultat


class SouscriptionCampagneNote(models.Model):
    """Note de campagne (#159, ADR 0025) : modèle dédié, pas le chatter — le
    chatter ne sait ni flaguer « à reporter » ni se chaîner d'un mois à
    l'autre. Une note « à reporter » non traitée renaît comme **prérequis
    repris** (rappel doux, non bloquant) dans la campagne suivante tant
    qu'elle reste non traitée (chaînage N→N+1→N+2…, cf.
    `SouscriptionCampagneFacturation._reporter_notes_precedentes`).
    """

    _name = 'souscription.campagne.note'
    _description = 'Note de campagne de facturation'
    _order = 'id'

    campagne_id = fields.Many2one(
        'souscription.campagne.facturation', required=True, ondelete='cascade', string='Campagne'
    )
    texte = fields.Text(required=True, string='Note')
    a_reporter = fields.Boolean(string='À reporter')
    traite = fields.Boolean(string='Traité')

    # Prérequis repris (#159) : pointeur vers la note du mois précédent dont
    # celle-ci est la reprise — truthy = rappel doux à mettre en avant côté
    # vue. Jamais un prérequis DAG : aucune étape ne lit note_ids/reprise.
    origine_note_id = fields.Many2one(
        'souscription.campagne.note', string='Reprise de', readonly=True, ondelete='set null'
    )
    reprise = fields.Boolean(string='Prérequis repris', compute='_compute_reprise', store=True)

    @api.depends('origine_note_id')
    def _compute_reprise(self):
        for note in self:
            note.reprise = bool(note.origine_note_id)
