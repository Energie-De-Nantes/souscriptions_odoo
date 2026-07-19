"""Campagne de facturation (#153/#156, ADR 0025) : tableau de bord mensuel du·de
la *Facturiste* — matrice à prérequis (DAG-rollup) au-dessus d'états qui vivent
ailleurs (périodes, factures, refacturations). 0 champ de vérification ajouté sur
`souscription.periode`/`souscription.refacturation` (ADR 0025 §2) : le seul état
vraiment persisté ici est la validation des portes manuelles (et les notes
reportées, #159) — tout le reste est dérivé à la volée depuis les données
existantes (#157).

Le catalogue `ETAPES_CAMPAGNE` est l'**interface complète du DAG** (#342, ADR
0036 décision 9 — le « grand A ») : chaque entrée déclare tout ce qu'est son
étape en clés plates, méthodes nommées par chaîne (résolues par `getattr`), clé
absente = défaut — le moteur ci-dessous est générique, zéro branche
`if self.code == ...`. Les six tables satellites que cette tranche absorbe :
cible de statut (`cible_statut`), action du bouton (`action`), cible du
drill-down (`drill_down`), stratégie de vidange (`vidange`), et le fait que
« Préparer les prélèvements » lise un reste-à-faire qui n'est pas la
cumulative-amont (`reste_a_faire`). Le test structurel (`tests/
test_campagne_catalogue.py`) verrouille ce contrat : prérequis existants, ordre
topologique, méthodes présentes, clés inconnues refusées.
"""

import time

from babel.dates import format_date
from dateutil.relativedelta import relativedelta
from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import is_html_empty

# Catalogue des étapes (#156, ADR 0025 §1 ; #342, ADR 0036 décision 9) : le DAG
# est déclaré en code, pas de modèle de configuration ni de moteur de workflow.
# L'ordre d'insertion EST un ordre topologique valide (chaque étape apparaît
# après tous ses prérequis) — sert à la fois de source de vérité du DAG et
# d'ordre d'affichage/seed.
#
# type d'étape :
#  - 'porte'  : validation manuelle (case à cocher, validé_par/validé_le persistés) ;
#  - 'derive' : signal dérivé des données (#157) — un reste-à-faire existe,
#               l'étape est faite quand il vaut 0 ;
#  - 'action' : étape déclenchée par bouton (#158) sans backlog mensuel
#               dérivable — le pull F15 tire TOUT (pas de fenêtre temporelle,
#               ADR 0009 §2), donc pas de reste-à-faire mensuel. Elle est
#               « faite » dès qu'elle a été demandée sans erreur pour la
#               campagne (champ `demande` persisté, posé par action_executer) :
#               c'est ce qui lui permet de gater sa vérif au même titre que le
#               pull des périodes. Revirement assumé du PRD #153 (« validation
#               manuelle ») décidé au rebase de cette branche : la demande
#               suffit, plus de coche (#163 est remplacé).
#
# phase (#342, ADR 0036 décision 14) : tirer / verifier / facturer / solder —
# lue telle quelle par le champ compute stocké `souscription.campagne.etape.
# phase` (même idiome que `type_etape`). Aucune vue modifiée dans cette
# tranche (#344 s'en chargera).
#
# gate (#342, ADR 0036 décision 11) : dureté de la porte que l'action de
# l'étape fait respecter — 'dure' (l'action lève `UserError` via
# `_verifier_gate` tant que `etat_prerequis != 'prete'`) ou absente (« douce » :
# l'action s'exécute même si un prérequis n'est pas satisfait — auto-
# cicatrisation, jamais un verrou pour l'humain). Statu quo comportemental,
# déclaré ici avec le pourquoi par entrée plutôt que du folklore lisible
# seulement en cherchant les appels à `_verifier_gate` dans le corps du
# moteur.
#
# cible_statut : pour une étape 'derive', le statut de `_STATUTS_ORDONNES`
# qu'une souscription doit avoir atteint pour compter « faite » — lu par
# `_reste_a_faire` (#157). reste_a_faire : nom d'une méthode de la Campagne
# qui rend directement le recordset reste-à-faire, pour les étapes dont le
# signal n'est pas la cumulative-amont des statuts (« Préparer les
# prélèvements », #186).
#
# action : nom de la méthode de la Campagne que le bouton générique
# (`action_executer`) délègue. Absent sur les portes (validées via la case
# `valide`, jamais un bouton).
#
# drill_down : nom d'une méthode de la ligne d'étape qui construit l'action
# « Voir » ; absente = dispatch par défaut (reste-à-faire souscriptions pour
# une étape 'derive', périmètre facturable sinon).
#
# vidange : présente seulement sur les deux étapes en tâche de fond (#326/
# #327, ADR 0035) — stratégie (liste de travail, action unitaire — le même nom
# de méthode que le lot appelle sur N enregistrements ou sur 1, idiome
# recordset natif —, libellé d'échec, libellé de réussite, source des
# réussites pour la notification de fin) lue par
# `SouscriptionCampagneEtape._vidanger_un_paquet` (générique, ADR 0036
# décision 9).
#
# amorcage (#342, ADR 0036 décisions 3-4 et 9) : nom de la méthode-données du
# pull, portée par la Campagne — présence de la clé = étape machine-runnable.
# Consommée par la tranche suivante (#343, l'automate d'amorçage à la
# création) ; cette tranche ne fait que la déclarer.
#
# Les deux « vrais pulls » (méta-périodes + F15) gatent chacun leur porte de
# vérif. Les relevés d'index NE sont PAS une étape : ils arrivent avec le pull
# des périodes (enfants souscription.releve, cf. _amorcer_depuis_meta).
#
# « Pull sorties C15 » et « Régulariser les clôtures » (#248, ADR 0031
# décision 4) : câblent l'ordre de campagne de la clôture — pull des sorties
# -> date_fin -> périmètre -> pull des méta-périodes -> mensuelles -> réguls
# de clôture. `pull_sorties_c15` devient la troisième racine du DAG (aucun
# prérequis, comme sync F15 : tire tout, auto-cicatrisant, ADR 0031 décision
# 1) ; `pull_meta_periodes` en dépend désormais — le prérequis documente
# l'ordre voulu (`date_fin` doit être à jour avant que le périmètre du mois
# soit tiré) mais n'est PAS un verrou dur (gate douce, même idiome que les
# autres pulls-racines : l'auto-cicatrisation du pull des sorties absorbe un
# passage dans le désordre).
ETAPES_CAMPAGNE = {
    'pull_sorties_c15': {
        'label': 'Pull sorties C15',
        'type': 'action',
        'prerequis': (),
        'phase': 'tirer',
        # gate absente = douce : aucun prérequis de toute façon (racine).
        'action': 'action_pull_sorties_c15',
        'amorcage': '_pull_sorties_c15_donnees',
    },
    'pull_meta_periodes': {
        'label': 'Pull méta-périodes',
        'type': 'derive',
        'prerequis': ('pull_sorties_c15',),
        'phase': 'tirer',
        # gate absente = douce (auto-cicatrisation, ADR 0031 décision 1) : un
        # passage dans le désordre se rattrape au pull suivant, jamais bloqué
        # pour l'humain.
        'cible_statut': 'a_facturer',
        'action': 'action_pull_meta_periodes',
        'amorcage': '_pull_meta_periodes_donnees',
    },
    'sync_f15': {
        'label': 'Sync F15',
        'type': 'action',
        'prerequis': (),
        'phase': 'tirer',
        # gate absente = douce : aucun prérequis (racine indépendante).
        'action': 'action_sync_f15',
        'amorcage': '_sync_f15_donnees',
    },
    'verif_periodes': {
        'label': 'Vérif périodes',
        'type': 'porte',
        'prerequis': ('pull_meta_periodes',),
        'phase': 'verifier',
        'drill_down': '_drill_down_periodes_du_mois',
    },
    'verif_refacturations': {
        'label': 'Vérif refacturations',
        'type': 'porte',
        'prerequis': ('sync_f15',),
        'phase': 'verifier',
        'drill_down': '_drill_down_ecran_refacturations',
    },
    # Tâche de fond (#327, ADR 0035 — second client du harnais posé en #326
    # pour `emettre_factures`) : le bouton POSE l'intention (`demande`) et
    # déclenche son propre `ir.cron` — il ne crée plus les factures
    # lui-même. Même lecture de `fait` que les autres étapes 'derive'
    # (`nb_reste_a_faire == 0`, inchangé) : `demande` ne sert PAS à lire
    # « fait », il sert à la vidange (cf.
    # SouscriptionCampagneEtape._vidanger_un_paquet, partagée avec
    # `emettre_factures`).
    'creer_factures': {
        'label': 'Créer factures',
        'type': 'derive',
        'prerequis': ('verif_periodes', 'verif_refacturations'),
        'phase': 'facturer',
        # gate dure (#342, ADR 0036 décision 11) : objet même des deux vérifs
        # qui la précèdent — les franchir SANS avoir vérifié romprait le sens
        # de la porte.
        'gate': 'dure',
        'cible_statut': 'facturee',
        'action': 'action_creer_factures',
        'drill_down': '_drill_down_factures_du_mois',
        'vidange': {
            'liste_travail': '_souscriptions_a_facturer_du_mois',
            'action': 'creer_factures',
            'ok': '_souscriptions_facturees_ou_emises_du_mois',
            'message_echec': 'Création de facture impossible',
            'libelle_reussite': 'Créées',
        },
    },
    # Porte manuelle (#287, ADR 0025 §2 — même grain que les vérifs) : la
    # fenêtre du geste commercial (CONTEXT.md « Geste commercial », ADR 0032)
    # se referme consciemment ici, AVANT le gel irréversible de l'émission —
    # aucun reste-à-faire (pas de signal dérivé), aucune action, son « Voir »
    # ouvre les mêmes factures du mois que Créer/Émettre (#282).
    'gestes_commerciaux': {
        'label': 'Gestes commerciaux',
        'type': 'porte',
        'prerequis': ('creer_factures',),
        'phase': 'facturer',
        'drill_down': '_drill_down_factures_du_mois',
    },
    # Tâche de fond (#326, ADR 0035 — premier client du harnais, rejoint par
    # `creer_factures` en #327) : le bouton POSE l'intention (`demande` sur
    # la ligne d'étape) et déclenche `ir.cron` — il ne poste plus les
    # factures lui-même. `fait` reste dérivé de `nb_reste_a_faire == 0`
    # (type 'derive', inchangé) : `demande` ne sert PAS à lire « fait », il
    # sert à la vidange à savoir qu'il reste un travail à reprendre (cf.
    # SouscriptionCampagneEtape._vidanger_un_paquet).
    'emettre_factures': {
        'label': 'Émettre factures',
        'type': 'derive',
        'prerequis': ('creer_factures', 'gestes_commerciaux'),
        'phase': 'facturer',
        # gate dure (#342, ADR 0036 décision 11) : objet même de la vérif —
        # émettre gèle définitivement, jamais sans porte franchie.
        'gate': 'dure',
        'cible_statut': 'emise',
        'action': 'action_emettre_factures',
        'drill_down': '_drill_down_factures_du_mois',
        'vidange': {
            'liste_travail': '_factures_brouillon_du_mois',
            'action': 'action_post',
            'ok': '_factures_postees_du_mois',
            'message_echec': 'Émission impossible',
            'libelle_reussite': 'Émises',
        },
    },
    'regulariser_clotures': {
        'label': 'Régulariser les clôtures',
        'type': 'action',
        'prerequis': ('emettre_factures',),
        'phase': 'solder',
        # gate absente = douce (#342, ADR 0036 décision 11) : le garde-fou
        # par unité (une clôture pas encore facturée est ignorée ce passage,
        # cf. action_regulariser_clotures) est plus fin que l'arête — la
        # durcir bloquerait les clôtures saines sur un échec d'émission
        # tiers.
        'action': 'action_regulariser_clotures',
    },
    'preparer_prelevements': {
        'label': 'Préparer les prélèvements',
        'type': 'action',
        'prerequis': ('emettre_factures',),
        'phase': 'solder',
        # gate dure (#342, ADR 0036 décision 11) : protège d'un batch SEPA
        # incomplet lancé avant que les factures du mois ne soient toutes
        # émises.
        'gate': 'dure',
        'reste_a_faire': '_factures_prelevement_dues_du_mois',
        'action': 'action_preparer_prelevements',
    },
}

# Clés reconnues du catalogue (#342, ADR 0036 décision 12) : toute clé absente
# de cet ensemble est un typo silencieux qui bloquerait une étape à vie sans
# jamais lever — le test structurel (tests/test_campagne_catalogue.py) refuse
# toute entrée qui en porte une autre.
CLES_CATALOGUE_CONNUES = frozenset(
    {
        'label',
        'type',
        'prerequis',
        'phase',
        'gate',
        'cible_statut',
        'reste_a_faire',
        'action',
        'drill_down',
        'vidange',
        'amorcage',
    }
)

# Étapes machine-runnable (#343, ADR 0036 décisions 3-4) : les trois pulls,
# dans l'ordre du catalogue (topologique) — l'ordre d'itération EST l'ordre
# de la passe séquentielle de l'automate (pull sorties C15 avant pull
# méta-périodes, cf. le prérequis douce qui les relie).
CODES_AMORCAGE = tuple(code for code, info in ETAPES_CAMPAGNE.items() if 'amorcage' in info)


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

    # Lettre du mois (#313, ADR 0034) : TOUT l'éditorial du mail de facture —
    # dates du mois, evergreen (tarif solidaire, permanences, bénévoles),
    # rappels — jamais un encart. Reportée depuis la campagne précédente à la
    # création (_reporter_lettre_precedente, même idiome que les notes) : la
    # facture TIRE cette lettre via son propre mois (account.move,
    # _compute_lettre_du_mois) — la campagne ne pousse rien.
    lettre_mois = fields.Html(string='Lettre du mois')

    # Décompte factures créées/émises du mois (#157) : dérivé, non stocké — cf.
    # _factures_du_mois().
    nb_factures_creees = fields.Integer(string='Factures créées', compute='_compute_stats_factures')
    nb_factures_emises = fields.Integer(string='Factures émises', compute='_compute_stats_factures')

    # --- Bandeau de stats natif (#301) : buckets EXACTS du statut de
    # facturation par souscription — Périmètre = somme des quatre buckets, une
    # souscription dans EXACTEMENT un bucket (cf. _souscriptions_par_bucket),
    # à l'inverse du reste-à-faire CUMULATIF amont de la matrice des étapes
    # (#157, _reste_a_faire), qui garde sa sémantique propre et n'est pas
    # touché ici. Tout dérivé, store=False (esprit ADR 0025). ---
    currency_id = fields.Many2one('res.currency', string='Devise', compute='_compute_currency_id')
    nb_perimetre = fields.Integer(string='Périmètre', compute='_compute_stats_bandeau')
    nb_a_tirer = fields.Integer(string='À tirer', compute='_compute_stats_bandeau')
    nb_a_facturer = fields.Integer(string='À facturer', compute='_compute_stats_bandeau')
    nb_facturees_brouillon = fields.Integer(string='Facturées', compute='_compute_stats_bandeau')
    nb_emises_bucket = fields.Integer(string='Émises', compute='_compute_stats_bandeau')
    total_emis_ttc = fields.Monetary(
        string='Total émis TTC', compute='_compute_stats_bandeau', currency_field='currency_id'
    )

    # Colonne « Étapes faites (X/Y) » de la liste des campagnes (#301) :
    # lecture de l'historique sans ouvrir chaque mois — Char plutôt que deux
    # Integer, plus simple à afficher tel quel dans la liste.
    etapes_faites = fields.Char(string='Étapes faites', compute='_compute_etapes_faites')

    _unique_mois = models.Constraint(
        'UNIQUE(mois)',
        'Une campagne de facturation existe déjà pour ce mois.',
    )

    @api.model
    def _default_mois(self):
        """1er du mois précédent (on ferme le mois qui vient de s'écouler)."""
        premier_mois_courant = fields.Date.context_today(self).replace(day=1)
        return premier_mois_courant - relativedelta(months=1)

    @api.depends('mois')
    def _compute_name(self):
        for campagne in self:
            campagne.name = (
                format_date(campagne.mois, format='MMMM yyyy', locale='fr_FR').capitalize() if campagne.mois else ''
            )

    @api.model_create_multi
    def create(self, vals_list):
        # Garde « mois révolu » (#343, ADR 0036 décisions 2-3) : l'invariant
        # qui rend l'amorçage automatique sûr — un mois pas encore terminé
        # tirerait un périmètre et des relevés incomplets. Vérifiée AVANT
        # tout `super().create()` (aucune ligne n'existe encore, aucun
        # réseau) : la création reste instantanée, la garde ne fait que lire
        # l'horloge.
        premier_mois_courant = fields.Date.context_today(self).replace(day=1)
        for vals in vals_list:
            if vals.get('mois'):
                vals['mois'] = fields.Date.to_date(vals['mois']).replace(day=1)
                mois = vals['mois']
            else:
                mois = self._default_mois()
            if mois >= premier_mois_courant:
                raise UserError(
                    _(
                        'Impossible de créer une campagne pour %(mois)s : le mois doit être strictement '
                        "révolu — sinon la campagne, qui s'amorce seule à sa création, tirerait un "
                        'périmètre et des relevés incomplets (ADR 0036).',
                        mois=format_date(mois, format='MMMM yyyy', locale='fr_FR'),
                    )
                )
        campagnes = super().create(vals_list)
        campagnes._seed_etapes()
        campagnes._reporter_notes_precedentes()
        campagnes._reporter_lettre_precedente()
        campagnes._declencher_amorcage()
        return campagnes

    def _declencher_amorcage(self):
        """Déclenche le cron d'amorçage dédié (#343, ADR 0036 décision 3) —
        `_trigger()` ne fait que planifier une exécution proche (ligne
        `ir.cron.trigger`), aucun appel réseau : la création reste
        instantanée. Le cron (`_cron_amorcer`) se charge lui-même de
        retrouver quoi amorcer — aucun identifiant de campagne à lui
        transmettre."""
        if self:
            self.env.ref('souscriptions_odoo.ir_cron_amorcage_campagne')._trigger()

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
            mois_precedent = campagne.mois - relativedelta(months=1)
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

    def _reporter_lettre_precedente(self):
        """Pré-remplit la lettre du mois M avec celle de M-1 à la création
        (#313, ADR 0034 « Le second détour ») — même idiome que
        `_reporter_notes_precedentes` : c'est ce report qui rend l'evergreen
        (permanences, tarif solidaire, bénévoles) viable sans retype ni
        déploiement, seules les dates changent d'un mois sur l'autre.

        Chaîne naturellement (N -> N+1 -> N+2…) : la lettre copiée redevient
        elle-même la source du report suivant. Chaîne rompue (pas de
        campagne pour le mois précédent) : rien à reporter, aucune erreur —
        même contrat que les notes.

        Ne PRÉ-remplit que : une lettre passée à la création est la volonté du·
        de la Facturiste et prime sur le report. Contrairement aux notes (des
        enfants qu'on ajoute), la lettre est un champ scalaire — la réassigner
        sans garde écraserait la valeur explicite. `is_html_empty` et non
        `not` : l'éditeur HTML envoie `<p><br></p>` pour un champ vidé."""
        for campagne in self:
            if not is_html_empty(campagne.lettre_mois):
                continue
            mois_precedent = campagne.mois - relativedelta(months=1)
            precedente = self.search([('mois', '=', mois_precedent)], limit=1)
            if precedente:
                campagne.lettre_mois = precedente.lettre_mois

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
        # Période d'ouverture (#107, ADR 0023 décision 3) : facture legacy déjà
        # créée ET émise dans l'ancien système (Odoo 17), sans account.move ici
        # (`facture_id` restera vide, ADR 0004). Statut terminal — sinon elle
        # reste comptée « à facturer » à vie, comme `creer_factures()` le sait
        # déjà côté action (#284) mais le compteur dérivé l'ignorait.
        if periode.facture_legacy_ref:
            return 'emise'
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

    def _reste_a_faire(self, code):
        """Souscriptions restantes pour l'étape dérivée `code` (#157) — toutes
        celles pas encore parvenues au statut cible de l'étape (`cible_statut`
        du catalogue, #342 — remplace l'ancienne table satellite
        `_CIBLE_PAR_ETAPE_DERIVEE`). Feed aussi bien le compteur affiché
        (`nb_reste_a_faire`) que le drill-down.

        ponytail: une requête par souscription facturable (échelle facturiste —
        dizaines/centaines, pas un flux temps réel) ; upgrade en une seule
        requête SQL groupée si ça devient lent un jour."""
        self.ensure_one()
        cible = ETAPES_CAMPAGNE.get(code, {}).get('cible_statut')
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

    @api.depends('mois')
    def _compute_currency_id(self):
        for campagne in self:
            campagne.currency_id = self.env.company.currency_id

    @api.depends('etape_ids.fait')
    def _compute_etapes_faites(self):
        for campagne in self:
            total = len(campagne.etape_ids)
            faites = len(campagne.etape_ids.filtered('fait'))
            campagne.etapes_faites = f'{faites}/{total}'

    def _souscriptions_par_bucket(self):
        """Partitionne le Périmètre de campagne en buckets EXACTS du statut de
        facturation (#301) — une souscription dans exactement un bucket,
        contrairement au reste-à-faire cumulatif (#157, `_reste_a_faire`).

        ponytail: une requête par souscription facturable, même échelle que
        `_reste_a_faire` — upgrade en une seule requête groupée si ça devient
        lent un jour."""
        self.ensure_one()
        buckets = {statut: self.env['souscription.souscription'] for statut in self._STATUTS_ORDONNES}
        for souscription in self._souscriptions_facturables():
            buckets[self._statut_facturation(souscription)] |= souscription
        return buckets

    # --- Listes de travail de la vidange (#342, ADR 0036 décision 9 — clé
    # `vidange.liste_travail`/`vidange.ok` du catalogue) : nommées par la
    # Campagne, lues génériquement par `SouscriptionCampagneEtape` (liste
    # complète, non limitée — l'appelant tranche `[:limit]`). Remplacent les
    # anciennes branches `if self.code == 'creer_factures'` de
    # `_liste_de_travail`/`_compter_liste_de_travail`/`_notifier_fin`. ---

    def _souscriptions_a_facturer_du_mois(self):
        """Travail restant pour « Créer factures » : le bucket EXACT « à
        facturer » (#301) — pas le reste-à-faire cumulatif (une souscription
        encore « à tirer », sans Période, n'est pas du travail pour CETTE
        étape)."""
        self.ensure_one()
        return self._souscriptions_par_bucket()['a_facturer']

    def _souscriptions_facturees_ou_emises_du_mois(self):
        """Réussites de « Créer factures » pour la notification de fin :
        toute souscription déjà parvenue à « facturée » ou « émise »."""
        self.ensure_one()
        buckets = self._souscriptions_par_bucket()
        return buckets['facturee'] | buckets['emise']

    def _factures_brouillon_du_mois(self):
        """Travail restant pour « Émettre factures » : les brouillons du
        mois."""
        self.ensure_one()
        return self._factures_du_mois().filtered(lambda f: f.state == 'draft')

    def _factures_postees_du_mois(self):
        """Réussites de « Émettre factures » pour la notification de fin :
        les factures du mois déjà postées."""
        self.ensure_one()
        return self._factures_du_mois().filtered(lambda f: f.state == 'posted')

    @api.depends('mois')
    def _compute_stats_bandeau(self):
        for campagne in self:
            buckets = campagne._souscriptions_par_bucket()
            campagne.nb_a_tirer = len(buckets['a_tirer'])
            campagne.nb_a_facturer = len(buckets['a_facturer'])
            campagne.nb_facturees_brouillon = len(buckets['facturee'])
            campagne.nb_emises_bucket = len(buckets['emise'])
            campagne.nb_perimetre = sum(len(bucket) for bucket in buckets.values())
            factures_emises = campagne._factures_du_mois().filtered(lambda f: f.state == 'posted')
            campagne.total_emis_ttc = sum(factures_emises.mapped('amount_total'))

    # --- Drill-down des tuiles du bandeau (#301) : chaque tuile ouvre la
    # liste filtrée exacte qu'elle affiche — un helper générique par nature de
    # cible (souscriptions / factures), aucune logique de bucket dupliquée
    # (délègue à _souscriptions_par_bucket / _factures_du_mois). ---

    def _action_liste_souscriptions(self, souscriptions, label):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': label,
            'res_model': 'souscription.souscription',
            'view_mode': 'list,form',
            'domain': [('id', 'in', souscriptions.ids)],
        }

    def action_drill_down_perimetre(self):
        self.ensure_one()
        return self._action_liste_souscriptions(self._souscriptions_facturables(), _('Périmètre de campagne'))

    def action_drill_down_a_tirer(self):
        self.ensure_one()
        return self._action_liste_souscriptions(self._souscriptions_par_bucket()['a_tirer'], _('À tirer'))

    def action_drill_down_a_facturer(self):
        self.ensure_one()
        return self._action_liste_souscriptions(self._souscriptions_par_bucket()['a_facturer'], _('À facturer'))

    def action_drill_down_facturees(self):
        self.ensure_one()
        return self._action_liste_souscriptions(self._souscriptions_par_bucket()['facturee'], _('Facturées'))

    def action_drill_down_emises(self):
        self.ensure_one()
        return self._action_liste_souscriptions(self._souscriptions_par_bucket()['emise'], _('Émises'))

    def action_drill_down_total_emis(self):
        self.ensure_one()
        factures = self._factures_du_mois().filtered(lambda f: f.state == 'posted')
        return {
            'type': 'ir.actions.act_window',
            'name': _('Total émis'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', factures.ids)],
        }

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
        # Cohérence déclaration/enforcement (review #350) : un appel ici sans
        # `gate: 'dure'` au catalogue est un mensonge de documentation — le
        # sens inverse (déclarée dure, appel oublié) est verrouillé par
        # test_campagne_catalogue.test_toute_gate_dure_est_reellement_appliquee.
        assert ETAPES_CAMPAGNE[code].get('gate') == 'dure', (
            f"_verifier_gate({code!r}) : appel présent mais gate non déclarée 'dure' au catalogue"
        )
        etape = self._etape(code)
        if etape.etat_prerequis != 'prete':
            raise UserError(_('Étape « %s » bloquée : prérequis non satisfaits.', ETAPES_CAMPAGNE[code]['label']))

    def action_pull_sorties_c15(self):
        """Étape racine du DAG (#248, ADR 0031 décision 4) : pull des sorties
        C15 en tête de campagne — ordre voulu « pull des sorties -> date_fin
        -> périmètre -> pull des méta-périodes ». Délègue intégralement au
        bouton autonome déjà couvert
        (`souscription.souscription.action_tirer_sorties_c15`, #246), même
        périmètre toutes-souscriptions-non-résiliées (auto-cicatrisant, pas
        de fenêtre mensuelle, ADR 0031 décision 1) : aucune nouvelle couture
        réseau, aucun scope par mois de campagne — la file des sorties n'en a
        pas besoin."""
        self.ensure_one()
        return self.env['souscription.souscription'].action_tirer_sorties_c15()

    def action_regulariser_clotures(self):
        """Étape de fin de campagne (#248, ADR 0031 décision 4) : émet la
        Régularisation de clôture — une Régularisation **ordinaire** (mêmes
        candidats, ADR 0030) — de chaque Souscription actuellement
        `en_attente_cloture`. Cible la file d'ATTENTE (l'état, CONTEXT.md
        « En instance / En service / En attente de clôture / Résiliée »),
        pas le seul périmètre de ce mois : la file est auto-cicatrisante,
        comme le pull des sorties — une clôture ratée un mois ressort au
        passage suivant.

        Skip-and-report par souscription (ADR 0011) : une Période de clôture
        pas encore facturée (mensuelles pas encore émises) est ignorée ce
        passage, retentée au suivant ; une Régularisation sans écart (rien à
        solder ce tour-ci) est laissée en brouillon vide, jamais facturée
        (`_creer_facture` refuserait une Régularisation sans ligne) — ni
        erreur, ni notification bloquante, l'état `en_attente_cloture`
        persiste jusqu'à ce qu'un écart apparaisse. Une erreur de calcul sur
        une souscription n'interrompt pas le lot."""
        self.ensure_one()
        cibles = self.env['souscription.souscription'].search([('etat', '=', 'en_attente_cloture')])
        emises, ignorees, erreurs = [], [], []
        for souscription in cibles:
            periode_cloture = souscription._periode_cloture()
            if not periode_cloture or not (periode_cloture.facture_id or periode_cloture.facture_legacy_ref):
                ignorees.append(souscription.name)
                continue
            try:
                with self.env.cr.savepoint():
                    regularisation = souscription._regularisation_brouillon()
                    regularisation._recalculer()
                    if not regularisation.ligne_ids:
                        ignorees.append(souscription.name)
                        continue
                    facture = regularisation._creer_facture()
                    facture.action_post()
                    emises.append(souscription.name)
            except Exception as exc:
                erreurs.append(f'{souscription.name} : {exc}')
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Régulariser les clôtures'),
                'message': _(
                    'Émises : %(emises)s · Ignorées (rien à solder pour le moment) : %(ignorees)s · '
                    'Erreurs : %(erreurs)s',
                    emises=len(emises),
                    ignorees=len(ignorees),
                    erreurs=len(erreurs),
                ),
                'type': 'warning' if erreurs else 'success',
                'sticky': bool(erreurs),
            },
        }

    def _pull_meta_periodes_donnees(self):
        """Méthode-données du pull des méta-périodes (#341, ADR 0036 décision
        13) : cible le Périmètre de campagne (#175) pour `self.mois` — aucun
        mois re-proposé, le scope est déjà celle de la campagne — et délègue
        au propriétaire durable du pull, `souscription.pull.meta.periodes.
        service` (#233, scope facturation `pull()`, même couture réseau
        `_ouvrir_flux`/fabrique client, ADR 0024).

        Returns:
            tuple[list[str], list[str], list[str], list[str], list[str]] :
            `(creees, rafraichies, inchangees, conservees, erreurs)`, même
            gabarit que les deux autres pulls (sorties C15, sync F15) —
            consommé par le bouton `action_pull_meta_periodes` (toast) et par
            tout appelant non-UI (automate d'amorçage, tests)."""
        self.ensure_one()
        cibles = self._souscriptions_facturables()
        return self.env['souscription.pull.meta.periodes.service'].pull(cibles, self.mois)

    def action_pull_meta_periodes(self):
        """Lance le tirage en un clic (#176), sans fenêtre intermédiaire :
        emballe `_pull_meta_periodes_donnees` en toast (#341, ADR 0036
        décision 13) résumant créées/rafraîchies/conservées/erreurs
        (politique gardée par l'empreinte, ADR 0030 décision 1, #235) —
        sticky si des erreurs, auto-dismiss sinon — aucun résumé persisté."""
        self.ensure_one()
        creees, rafraichies, inchangees, conservees, erreurs = self._pull_meta_periodes_donnees()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Pull méta-périodes'),
                'message': _(
                    'Créées : %(creees)s · Rafraîchies : %(rafraichies)s · Conservées : %(conservees)s · '
                    'Erreurs : %(erreurs)s',
                    creees=len(creees),
                    rafraichies=len(rafraichies),
                    conservees=len(conservees),
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

    # --- Méthodes-données de l'amorçage (#342, ADR 0036 décision 9 — clé
    # `amorcage` du catalogue), consommées par la tranche suivante (#343).
    # `_pull_meta_periodes_donnees` (ci-dessus) vit déjà nativement sur la
    # Campagne (#341) ; les deux wrappers ci-dessous existent pour que les
    # TROIS méthodes nommées par `amorcage` vivent sur le même modèle, lu
    # uniformément par le futur automate — aucune nouvelle couture réseau,
    # délégation pure aux méthodes-données durables (#341) déjà couvertes. ---

    def _pull_sorties_c15_donnees(self):
        """Vue Campagne de la méthode-données du pull des sorties C15 (#341)
        — même délégation que `action_pull_sorties_c15` ci-dessus, sans le
        toast."""
        self.ensure_one()
        return self.env['souscription.souscription']._pull_sorties_c15_donnees()

    def _sync_f15_donnees(self):
        """Vue Campagne de la méthode-données de la sync F15 (#341) — même
        délégation que `action_sync_f15` ci-dessus, sans le toast."""
        self.ensure_one()
        return self.env['souscription.refacturation']._synchroniser_depuis_electricore_donnees()

    # --- Amorçage automatique à la création (#343, ADR 0036 décisions 3-8) ---
    #
    # `_cron_amorcer` est le point d'entrée du cron dédié (déclenché par
    # `_declencher_amorcage` ci-dessus) : il cherche lui-même UNE campagne
    # dont au moins un pull n'a encore jamais été demandé — `demande` (déjà
    # persisté, ADR 0035) suffit, aucun marqueur d'état nouveau (décision 4).
    # `_amorcer` fait la passe séquentielle proprement dite, sous l'identité
    # du créateur (décision 7) : au plus une tentative par étape d'amorçage,
    # dans l'ordre du catalogue — jamais de boucle (« la passe ne boucle
    # pas », décision 4). Un échec transport (UserError, cf.
    # `traduire_exceptions_electricore`) laisse l'étape « à lancer » ; ses
    # avals ne la verront jamais « prête » (`etat_prerequis`, décision 5) —
    # aucune logique de propagation dédiée, la lecture normale du DAG
    # suffit. Erreurs par souscription (skip-and-report) : déjà au chatter
    # de la souscription fautive, DANS le service (#341/#360) — la méthode-
    # données réussit quand même (tuple avec des erreurs dedans), `demande`
    # est donc posée normalement (décision 8a).

    def _amorcer(self):
        """Passe séquentielle d'amorçage pour CETTE campagne (#343). Committe
        après chaque étape réussie (API de progression `ir.cron`, ADR 0035) :
        un échec à l'étape suivante ne perd pas le succès déjà acquis."""
        self.ensure_one()
        cron = self.env['ir.cron']
        mesures = []
        for code in CODES_AMORCAGE:
            etape = self._etape(code)
            if etape.etat_prerequis != 'prete' or etape.fait:
                continue
            methode = ETAPES_CAMPAGNE[code]['amorcage']
            debut = time.monotonic()
            try:
                resultat = getattr(self, methode)()
            except UserError as exc:
                mesures.append((ETAPES_CAMPAGNE[code]['label'], None, None, time.monotonic() - debut, str(exc)))
                continue
            duree = time.monotonic() - debut
            etape.write({'demande': True})
            cron._commit_progress(1)
            nb_erreurs = len(resultat[-1])
            nb_total = sum(len(lot) for lot in resultat)
            mesures.append((ETAPES_CAMPAGNE[code]['label'], nb_total, nb_erreurs, duree, None))
        self._notifier_fin_amorcage(mesures)

    @api.model
    def _cron_amorcer(self):
        """Point d'entrée du cron d'amorçage (`ir_cron_amorcage_campagne`,
        #343) : cherche UNE campagne portant encore un pull jamais demandé
        et lui délègue sa passe, sous l'identité de sa créatrice/son
        créateur — jamais l'utilisateur technique du cron (décision 7). Ne
        boucle pas (décision 4) : une campagne par appel, aucun
        re-déclenchement — le filet de sécurité quotidien du cron
        (`interval_type`, même idiome que la vidange, ADR 0035) suffit à
        rattraper une campagne encore en attente."""
        etape = self.env['souscription.campagne.etape'].search(
            [('code', 'in', list(CODES_AMORCAGE)), ('demande', '=', False)], limit=1
        )
        if etape:
            campagne = etape.campagne_id
            campagne.with_user(campagne.create_uid.id or self.env.user.id)._amorcer()
        self.env['ir.cron']._commit_progress(remaining=0)

    def _notifier_fin_amorcage(self, mesures):
        """Notification bus récapitulative de fin de passe (#343, ADR 0036
        décision 8c) : comptes et durée par étape tentée, erreur transport le
        cas échéant — même idiome que `_notifier_fin` de la vidange
        (`bus.bus._sendone`, natif, zéro JS), chez le créateur de la
        campagne. Best effort (décision 8b) : aucune exception ne doit faire
        perdre le travail déjà committé si l'envoi échoue — non gardé
        explicitement, `_sendone` est un simple INSERT natif."""
        self.ensure_one()
        if not mesures:
            return
        demandeur = self.create_uid
        if not demandeur:
            return
        self.env['bus.bus']._sendone(
            demandeur.partner_id, 'simple_notification', self._construire_notification_amorcage(mesures)
        )

    def _construire_notification_amorcage(self, mesures):
        self.ensure_one()
        lignes = []
        une_erreur = False
        for label, nb_total, nb_erreurs, duree, erreur_transport in mesures:
            if erreur_transport is not None:
                une_erreur = True
                lignes.append(
                    _(
                        '%(label)s : échec transport (%(duree).1fs) — %(erreur)s',
                        label=label,
                        duree=duree,
                        erreur=erreur_transport,
                    )
                )
            else:
                if nb_erreurs:
                    une_erreur = True
                lignes.append(
                    _(
                        '%(label)s : %(nb)s traité(s), %(erreurs)s en erreur (%(duree).1fs)',
                        label=label,
                        nb=nb_total,
                        erreurs=nb_erreurs,
                        duree=duree,
                    )
                )
        return {
            'title': _('Amorçage de la campagne %s', self.name),
            'message': '\n'.join(lignes),
            'type': 'warning' if une_erreur else 'success',
            'sticky': une_erreur,
        }

    def action_creer_factures(self):
        """Gated sur les deux portes de vérif (#158) : pose l'intention et
        déclenche le cron de vidange dédié — elle ne crée plus les factures
        elle-même (#327, ADR 0035 : second client du harnais posé en #326,
        même bascule « le bouton demande, il ne fait plus »). Rend la main
        immédiatement ; la vidange vit dans
        ``SouscriptionCampagneEtape._vidanger_un_paquet`` (partagée avec
        « émettre factures »), sous l'identité du·de la Facturiste
        demandeur·se (``with_user(demande_par_id)``).

        Idempotent par construction, sans état de retry dédié : l'anti-
        doublon par période déjà présent dans `creer_factures()` (une
        souscription déjà facturée pour le mois n'est jamais refacturée)
        fait l'idempotence — rien n'est ajouté ici, comme pour l'émission."""
        self.ensure_one()
        self._verifier_gate('creer_factures')
        self._etape('creer_factures').write({'demande': True})
        self.env.ref('souscriptions_odoo.ir_cron_vidange_creer_factures')._trigger()

    def action_emettre_factures(self):
        """Gated sur créer factures + gestes commerciaux (#158) : pose
        l'intention et déclenche le cron de vidange — elle ne poste plus
        les factures elle-même (#326, ADR 0035 : « le bouton demande, il ne
        fait plus »). Rend la main immédiatement ; la vidange (paquets,
        repli par facture #268, règle « pas de progrès », notification de
        fin) vit dans ``SouscriptionCampagneEtape._vidanger_un_paquet``,
        sous l'identité du·de la Facturiste qui clique
        (``with_user(demande_par_id)``) — jamais l'utilisateur technique du
        cron, pour que les écritures comptables restent signées par un
        humain (ADR 0025 décision 3, amendée ADR 0035).

        Idempotent par construction, sans état de retry dédié : le filtre
        ``state == 'draft'`` (dans la vidange) exclut déjà les factures
        émises — un reclic après correction de la cause d'un échec ne
        reprend que les échecs ; un reclic sur une étape déjà terminée ne
        trouve rien à faire. Le reste-à-faire de l'étape (#157,
        ``_reste_a_faire``) reflète l'état réel tout seul — aucun champ de
        progression ajouté (esprit ADR 0025)."""
        self.ensure_one()
        self._verifier_gate('emettre_factures')
        self._etape('emettre_factures').write({'demande': True})
        self.env.ref('souscriptions_odoo.ir_cron_vidange_emettre_factures')._trigger()

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

    # Phase (#342, ADR 0036 décision 14) : fonction pure de `code`, même
    # idiome que `type_etape` — aucune vue modifiée dans cette tranche (#344
    # rendra les quatre sections).
    phase = fields.Selection(
        [('tirer', 'Tirer'), ('verifier', 'Vérifier'), ('facturer', 'Facturer'), ('solder', 'Solder')],
        compute='_compute_phase',
        store=True,
        string='Phase',
    )

    # Porte manuelle (#156, ADR 0025 §2) : état persisté du DAG avec `demande`
    # ci-dessous et les notes (#159). validé_par/validé_le sont estampillés au
    # write (jamais saisis à la main) — cf. write() ci-dessous.
    valide = fields.Boolean(string='Validé')
    valide_par_id = fields.Many2one('res.users', string='Validé par', readonly=True)
    valide_le = fields.Datetime(string='Validé le', readonly=True)

    # Intention posée AVANT le travail, jamais un accompli posé après (#326,
    # ADR 0035 amendant ADR 0025) — renommé depuis `lance` (migration
    # `migrations/19.0.1.19.0`). Pour une étape 'action' restante (sync F15,
    # pull sorties C15...) qui tire tout d'un coup, sans backlog mensuel
    # dérivable (ADR 0009 §2), « demandée » reste équivalent à « faite »
    # (posé par action_executer, jamais saisi à la main — cf. _compute_fait).
    # Pour « émettre factures » (type 'derive'), `demande` ne pilote PAS
    # `fait` (qui reste `nb_reste_a_faire == 0`) : il pilote la vidange en
    # tâche de fond (cf. _vidanger_un_paquet) — une intention encore posée
    # veut dire « il reste un paquet à reprendre ».
    demande = fields.Boolean(string='Demandé', readonly=True)
    demande_par_id = fields.Many2one(
        'res.users',
        string='Demandé par',
        readonly=True,
        help=(
            "La personne qui a cliqué — le travail de fond s'exécute sous son "
            "identité (with_user), jamais sous l'utilisateur technique du cron."
        ),
    )

    etat_prerequis = fields.Selection(
        [('prete', 'Prête'), ('bloquee', 'Bloquée')],
        string='Prérequis',
        compute='_compute_etat_prerequis',
    )
    # « Fait » : pour une porte manuelle, la validation ; pour une étape à
    # signal dérivé, son reste-à-faire (#157 : fait quand nb_reste_a_faire == 0) ;
    # pour une action (sync F15), sa demande (`demande`). Cf. le catalogue.
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

    @api.depends('code')
    def _compute_phase(self):
        for etape in self:
            etape.phase = ETAPES_CAMPAGNE.get(etape.code, {}).get('phase')

    def write(self, vals):
        if vals.get('valide'):
            vals = dict(vals)
            vals.setdefault('valide_par_id', self.env.user.id)
            vals.setdefault('valide_le', fields.Datetime.now())
        if vals.get('demande'):
            vals = dict(vals)
            vals.setdefault('demande_par_id', self.env.user.id)
        return super().write(vals)

    @api.depends('type_etape', 'code', 'campagne_id.mois')
    def _compute_nb_reste_a_faire(self):
        """#157 : lit la stratégie de reste-à-faire au catalogue (#342) —
        `reste_a_faire` (méthode dédiée, ex. « Préparer les prélèvements »,
        #186) prime sur `cible_statut` (délègue alors à
        `campagne_id._reste_a_faire(code)`, la cumulative-amont). Ni l'un ni
        l'autre : pas de signal dérivé (portes, actions sans backlog), reste
        à 0. Recompté à chaque lecture (pas de relation ORM déclarée vers
        période/facture, donc pas d'invalidation de cache automatique
        inter-modèles, ADR 0025)."""
        for etape in self:
            info = ETAPES_CAMPAGNE.get(etape.code, {})
            methode = info.get('reste_a_faire')
            if methode and etape.campagne_id:
                etape.nb_reste_a_faire = len(getattr(etape.campagne_id, methode)())
            elif info.get('cible_statut') and etape.campagne_id:
                etape.nb_reste_a_faire = len(etape.campagne_id._reste_a_faire(etape.code))
            else:
                etape.nb_reste_a_faire = 0

    @api.depends('valide', 'type_etape', 'code', 'nb_reste_a_faire', 'demande')
    def _compute_fait(self):
        for etape in self:
            info = ETAPES_CAMPAGNE.get(etape.code, {})
            if etape.type_etape == 'porte':
                etape.fait = etape.valide
            elif info.get('cible_statut') or info.get('reste_a_faire'):
                etape.fait = etape.nb_reste_a_faire == 0
            else:
                # 'action' restante (sync F15, pull sorties C15, régulariser
                # les clôtures) : pas de backlog dérivable (tire tout, ADR
                # 0009 §2) — « faite » une fois demandée pour la campagne.
                etape.fait = etape.demande

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

    # --- Drill-down (#157 ; générique #342, ADR 0036 décision 9) : la clé
    # `drill_down` du catalogue nomme une méthode de CETTE classe qui
    # construit l'action « Voir » — absente = dispatch par défaut (liste
    # filtrée des souscriptions concernées par cette étape, pour les étapes à
    # signal dérivé, ou à défaut toutes les souscriptions facturables du
    # mois). Exception #282 (« Créer factures »/« Émettre factures ») et #336
    # (les deux portes de vérif) : nommées explicitement au catalogue,
    # `_drill_down_factures_du_mois`/`_drill_down_periodes_du_mois`/
    # `_drill_down_ecran_refacturations` ci-dessous — plus aucune branche
    # `if self.code == ...` ici. ---

    def _drill_down_periodes_du_mois(self):
        """#336 : « Vérif périodes » ouvre les périodes mensuelles du mois de
        la campagne — pas le fallback souscriptions."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': ETAPES_CAMPAGNE.get(self.code, {}).get('label', self.code),
            'res_model': 'souscription.periode',
            'view_mode': 'list,form',
            'domain': [('mois', '=', self.campagne_id.mois), ('type_periode', '=', 'mensuelle')],
        }

    def _drill_down_ecran_refacturations(self):
        """#336 : « Vérif refacturations » réutilise l'écran de vérification
        des prestations existant (ADR 0012, groupé par état) par référence à
        son XML id — aucune vue ni domaine dupliqués ici."""
        self.ensure_one()
        return self.env['ir.actions.act_window']._for_xml_id('souscriptions_odoo.action_souscription_refacturation')

    def _drill_down_factures_du_mois(self):
        """#282 : « Créer factures »/« Émettre factures » affichent un
        reste-à-faire côté souscriptions, mais la facturiste y travaille sur
        des FACTURES — ouvre les factures du mois, groupées par statut
        (brouillon à émettre / comptabilisé déjà émis). #287 : « Gestes
        commerciaux » partage ce même drill-down — la porte n'a pas de
        reste-à-faire propre, c'est sur CES factures du mois que se pose la
        ligne € manuelle avant que l'émission ne gèle le brouillon."""
        self.ensure_one()
        factures = self.campagne_id._factures_du_mois()
        return {
            'type': 'ir.actions.act_window',
            'name': ETAPES_CAMPAGNE.get(self.code, {}).get('label', self.code),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', factures.ids)],
            'context': {'group_by': 'state'},
        }

    def action_drill_down(self):
        self.ensure_one()
        methode = ETAPES_CAMPAGNE.get(self.code, {}).get('drill_down')
        if methode:
            return getattr(self, methode)()
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

    # --- Bouton d'étape (#158 ; générique #342) : un seul bouton générique
    # par ligne, qui dispatche vers la méthode de la Campagne nommée par la
    # clé `action` du catalogue — jamais de logique dupliquée entre la vue et
    # ETAPES_CAMPAGNE. Les portes manuelles n'ont pas de clé `action` : elles
    # se valident via le champ `valide`. ---

    def action_executer(self):
        self.ensure_one()
        methode = ETAPES_CAMPAGNE.get(self.code, {}).get('action')
        if not methode:
            raise UserError(
                _("Pas d'action pour l'étape « %s ».", ETAPES_CAMPAGNE.get(self.code, {}).get('label', self.code))
            )
        resultat = getattr(self.campagne_id, methode)()
        # Étape 'action' réussie (pas d'exception) = « pull effectué » pour la
        # campagne : débloque sa vérif (cf. champ `demande`). Pour
        # « émettre factures » (type 'derive'), c'est
        # `action_emettre_factures` elle-même qui pose `demande` — cette
        # branche ne la concerne pas (#326).
        if self.type_etape == 'action':
            self.demande = True
        return resultat

    # --- Vidange en tâche de fond (#326/#327, ADR 0035 ; générique #342, ADR
    # 0036 décision 9) : deux clients, « émettre factures » (#326) et « créer
    # factures » (#327), tous deux nommés par la clé `vidange` du catalogue.
    #
    # Le bouton d'étape (`action_emettre_factures`/`action_creer_factures`,
    # ci-dessus sur la Campagne) pose l'intention (`demande`) et déclenche le
    # cron dédié à SON étape ; ce qui suit VIDE cette intention par paquets,
    # sous l'identité du·de la Facturiste demandeur·se (jamais l'utilisateur
    # technique du cron). Une étape, un paquet, pas de boucle : c'est
    # `ir.cron._run_job` qui rappelle ce code tant qu'une passe progresse
    # (API de progression native, Odoo 17+ — aucune dépendance ajoutée).
    # `_vidanger_un_paquet` est UNE seule méthode pour les deux étapes — la
    # stratégie (liste de travail, action unitaire, libellés) vient du
    # catalogue, zéro branche `if self.code == ...` ; la mécanique de paquet
    # (verrouillage, tentative en lot, repli unitaire sous savepoint, règle
    # « pas de progrès », notification) est strictement la même pour les
    # deux (cf. note de généricité dans la PR #327).
    #
    # Taille de paquet dérivée de `MIN_RUNS_PER_JOB = 10` (plancher de passes
    # par exécution du worker) : `10 × 50 × 88 ms` (mesure ADR 0035, sur
    # l'émission) reste sous `limit_time_real` (120 s), ~44 s de marge.
    # Réglage de performance pur — aucun test ne s'y accroche. Réutilisée
    # telle quelle pour la création (81 s / 810 factures mesurés, ADR 0035 —
    # même ordre de grandeur par facture).
    _TAILLE_PAQUET_VIDANGE = 50

    def _strategie_vidange(self):
        self.ensure_one()
        return ETAPES_CAMPAGNE[self.code]['vidange']

    def _liste_de_travail(self, limit):
        """Prochain paquet de travail du mois de la campagne — distinct de
        `_reste_a_faire` (ADR 0035 décision 4) : celui-ci répond « combien de
        souscriptions restent, pour la porte du DAG », celui-là « quelles
        unités traiter au prochain paquet, pour le cron ». La liste complète
        vient de la méthode de Campagne nommée par `vidange.liste_travail`
        (#342) — brouillons du mois à émettre, ou souscriptions du mois
        encore à facturer (bucket EXACT « à facturer », #301 — pas le
        reste-à-faire cumulatif : une souscription encore « à tirer », sans
        Période, n'est pas du travail pour CETTE étape)."""
        self.ensure_one()
        methode = self._strategie_vidange()['liste_travail']
        return getattr(self.campagne_id, methode)()[:limit]

    def _compter_liste_de_travail(self):
        self.ensure_one()
        methode = self._strategie_vidange()['liste_travail']
        return len(getattr(self.campagne_id, methode)())

    def _traiter_le_paquet(self, travail):
        """Tentative en lot : `vidange.action` (#342) est le nom d'UNE
        méthode recordset, appelée identiquement qu'elle porte sur le lot
        entier ou une seule unité (idiome natif) — `action_post()` pour
        l'émission (7,7 ms/facture pièce, mesure ADR 0035, bien moins cher
        qu'un repli facture par facture quand le lot est sain),
        `creer_factures()` pour la création (#158, déjà idempotent par
        période). Même levée `UserError` sur un échec, qui fait retomber sur
        le repli unitaire ci-dessous."""
        methode = self._strategie_vidange()['action']
        getattr(travail, methode)()
        return len(travail)

    def _traiter_une_unite(self, unite):
        """Repli unitaire (#268/#327) : la MÊME action (`vidange.action`)
        tentée sur UNE unité du paquet, sous savepoint individuel — cf.
        `_vidanger_un_paquet`. Le type de `unite` varie avec l'étape (une
        facture pour l'émission, une souscription pour la création) ; c'est
        pour ça que le chatter de l'échec (`_message_echec`) atterrit
        naturellement sur le bon enregistrement : la facture pour l'émission,
        la SOUSCRIPTION pour la création — qui n'a pas encore de facture à ce
        stade (#327)."""
        methode = self._strategie_vidange()['action']
        getattr(unite, methode)()

    def _message_echec(self, exc):
        libelle = self._strategie_vidange()['message_echec']
        return _('%(libelle)s : %(erreur)s', libelle=libelle, erreur=exc)

    def _vidanger_un_paquet(self):
        """Vide UN paquet de l'étape courante (« émettre factures », #326,
        ou « créer factures », #327) — appelée par le point d'entrée cron
        paramétré (`_cron_vidanger(code)`, #342), sous `with_user
        (demande_par_id)`. Ne boucle pas : cf. le bloc de commentaire
        ci-dessus. Un seul corps pour les deux étapes — seule la stratégie
        du catalogue (`vidange`) varie avec `self.code`.

        Isolation d'erreur par unité (#268/#327) : tente le lot entier ; si
        une grille incapable de prixer (`UserError`, ADR 0029) ou toute
        autre donnée manquante sur UNE unité fait échouer le lot, réessaie
        unité par unité sous savepoint individuel, cause au chatter de
        l'unité fautive — une facture pour l'émission, une SOUSCRIPTION pour
        la création, qui n'a pas encore de facture à ce stade (idiome natif,
        `account.move._autopost_draft_entries`).

        Règle d'arrêt « pas de progrès » (ADR 0035 décision 3) : une passe
        qui n'a RIEN traité (zéro succès) retombe l'intention — sinon une
        Grille de prix manquante ferait retourner le cron en boucle serrée
        sur un travail qui ne peut pas aboutir avant qu'un humain n'ait
        corrigé la donnée en cause."""
        self.ensure_one()
        cron = self.env['ir.cron']
        travail = self._liste_de_travail(limit=self._TAILLE_PAQUET_VIDANGE)
        restants = len(travail) if len(travail) < self._TAILLE_PAQUET_VIDANGE else self._compter_liste_de_travail()
        cron._commit_progress(remaining=restants)

        if not travail:
            self.demande = False
            self._notifier_fin()
            return

        # Verrou avant traitement (comme le natif) : évite qu'un deuxième
        # worker ne reprenne les mêmes unités en parallèle.
        travail.try_lock_for_update()

        try:
            traites = self._traiter_le_paquet(travail)
            cron._commit_progress(traites)
            if not self._compter_liste_de_travail():
                self.demande = False
                self._notifier_fin()
            return
        except UserError:
            self.env.cr.rollback()

        aucun_progres = True
        for unite in travail:
            try:
                with self.env.cr.savepoint():
                    self._traiter_une_unite(unite)
                aucun_progres = False
            except UserError as exc:
                unite.message_post(body=self._message_echec(exc))
            finally:
                cron._commit_progress(1)

        if aucun_progres:
            self.demande = False
            self._notifier_fin()

    def _notifier_fin(self):
        """Notification de fin (#326, généralisée #327 ; générique #342) :
        compteurs réussites/échecs uniquement — le drill-down existant
        (`action_drill_down`) dit LESQUELLES, le chatter de l'unité fautive
        dit POURQUOI (posé ci-dessus). Émise par `bus.bus._sendone` (natif,
        `simple_notification`) chez le·la demandeur·se — zéro JS.

        `nb_echecs` = `_compter_liste_de_travail()` (même liste que la
        vidange : le travail restant EST l'échec restant) ; `nb_ok` = la
        méthode de Campagne nommée par `vidange.ok` (#342) — les factures du
        mois postées pour l'émission, les souscriptions du mois déjà
        « facturée » ou « émise » pour la création (ce dernier bucket exclut
        volontairement « à tirer » : une souscription sans Période n'a
        jamais été du travail pour cette étape)."""
        self.ensure_one()
        demandeur = self.demande_par_id
        if not demandeur:
            return
        strategie = self._strategie_vidange()
        nb_ok = len(getattr(self.campagne_id, strategie['ok'])())
        nb_echecs = self._compter_liste_de_travail()
        libelle_ok = strategie['libelle_reussite']
        self.env['bus.bus']._sendone(
            demandeur.partner_id, 'simple_notification', self._construire_notification(nb_ok, nb_echecs, libelle_ok)
        )

    def _construire_notification(self, nb_ok, nb_echecs, libelle_ok):
        titre = ETAPES_CAMPAGNE[self.code]['label']
        if not nb_echecs:
            return {
                'title': titre,
                'message': _('%(libelle)s : %(nb)s.', libelle=libelle_ok, nb=nb_ok),
                'type': 'success',
                'sticky': False,
            }
        return {
            'title': titre,
            'message': _(
                '%(libelle)s : %(nb_ok)s · Échecs : %(nb_echecs)s', libelle=libelle_ok, nb_ok=nb_ok, nb_echecs=nb_echecs
            ),
            'type': 'warning',
            'sticky': True,
        }

    @api.model
    def _cron_vidanger(self, code):
        """Point d'entrée paramétré (#342, ADR 0036 décision 10) — fusionne
        les deux points d'entrée jumeaux `_cron_vidanger_emettre_factures`/
        `_cron_vidanger_creer_factures` en UNE méthode, appelée par CHAQUE
        cron avec SON code en dur dans le champ `code` XML (les deux
        enregistrements `ir.cron`, xml_ids stables, restent — seul leur
        champ `code` change, cf. `data/ir_cron_vidange_*.xml` — parallélisme
        préservé : deux workers peuvent vidanger « créer » et « émettre »
        en même temps).

        Cherche l'étape `code` actuellement demandée (recliquer une étape
        déjà terminée ne trouve rien : `demande` est retombée) et lui
        délègue UN paquet, sous l'identité du·de la Facturiste demandeur·se
        — jamais celle, technique, du cron."""
        etape = self.search([('code', '=', code), ('demande', '=', True)], limit=1)
        if not etape:
            self.env['ir.cron']._commit_progress(remaining=0)
            return
        etape.with_user(etape.demande_par_id.id or self.env.user.id)._vidanger_un_paquet()


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
