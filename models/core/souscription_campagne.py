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
from odoo import api, fields, models

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
#               dérivable — la refacturation Enedis n'est pas rattachée à un
#               mois (CONTEXT.md « Refacturation »), donc « sync F15 » n'a pas
#               de reste-à-faire naturel. ponytail: elle reste donc
#               structurellement « non faite » — ça ne bloque rien de dur
#               (« créer factures » ne dépend que des deux portes de vérif,
#               jamais de « sync F15 » directement) ; upgrade path si un vrai
#               signal (ou une porte manuelle dédiée) devient nécessaire.
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
    'releves_index': {
        'label': "Relevés d'index",
        'type': 'porte',
        'prerequis': (),
    },
    'verif_periodes': {
        'label': 'Vérif périodes',
        'type': 'porte',
        'prerequis': ('pull_meta_periodes', 'releves_index'),
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

    # Porte manuelle (#156, ADR 0025 §2) : seul état vraiment persisté du DAG
    # avec les notes (#159). validé_par/validé_le sont estampillés au write
    # (jamais saisis à la main) — cf. write() ci-dessous.
    valide = fields.Boolean(string='Validé')
    valide_par_id = fields.Many2one('res.users', string='Validé par', readonly=True)
    valide_le = fields.Datetime(string='Validé le', readonly=True)

    etat_prerequis = fields.Selection(
        [('prete', 'Prête'), ('bloquee', 'Bloquée')],
        string='Prérequis',
        compute='_compute_etat_prerequis',
    )
    # « Fait » : pour une porte manuelle, la validation ; pour une étape à
    # signal dérivé, son reste-à-faire (#157, pas encore câblé dans cette
    # tranche — cf. ETAPES_CAMPAGNE) ; pour une action sans signal (sync F15),
    # jamais fait automatiquement (cf. commentaire sur le catalogue).
    fait = fields.Boolean(string='Fait', compute='_compute_fait')

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

    @api.depends('valide', 'type_etape')
    def _compute_fait(self):
        for etape in self:
            if etape.type_etape == 'porte':
                etape.fait = etape.valide
            else:
                # 'derive' : signal câblé en #157 (0 reste-à-faire -> fait).
                # 'action' : jamais de signal dérivé (cf. ETAPES_CAMPAGNE).
                etape.fait = False

    @api.depends('code', 'campagne_id.etape_ids.fait')
    def _compute_etat_prerequis(self):
        for etape in self:
            prerequis = ETAPES_CAMPAGNE.get(etape.code, {}).get('prerequis', ())
            if not prerequis:
                etape.etat_prerequis = 'prete'
                continue
            freres = {e.code: e.fait for e in etape.campagne_id.etape_ids}
            etape.etat_prerequis = 'prete' if all(freres.get(p) for p in prerequis) else 'bloquee'
