from babel.dates import format_date
from odoo import api, fields, models
from odoo.exceptions import UserError


class SouscriptionPeriode(models.Model):
    _name = 'souscription.periode'
    _description = 'Période de facturation énergétique'
    _order = 'date_debut'

    souscription_id = fields.Many2one(
        'souscription.souscription', required=True, readonly=True, ondelete='cascade', string='Souscription'
    )

    date_debut = fields.Date(required=True, readonly=True)
    date_fin = fields.Date(required=True, readonly=True)
    mois_annee = fields.Char(string='Mois', compute='_compute_mois_annee', store=True, readonly=True)

    # Mois canonique (ADR 0020 §2) : Date au 1er du mois, dérivé stocké de
    # `date_debut` — support local de la clé d'idempotence `(RSC, mois)` du pull
    # electricore (ADR 0011). Distinct de `mois_annee` (libellé d'affichage
    # français, inchangé) : la collision de nom avec le contrat v3 (qui nomme
    # `mois_annee` sa clé « YYYY-MM ») se résout en gardant l'existant Odoo.
    mois = fields.Date(string='Mois (canonique)', compute='_compute_mois', store=True, readonly=True)

    pdl = fields.Char(string='pdl', readonly=True)
    lisse = fields.Boolean(string='Lissé', readonly=True)  # related='souscription_id.lisse',  store=True)

    # Identité electricore (ADR 0010, ADR 0020 §3) : la Période snapshotte la RSC
    # de la Souscription à sa création — même logique que le snapshot des
    # paramètres contractuels (ADR 0006).
    ref_situation_contractuelle = fields.Char(
        string='RSC (référence situation contractuelle)',
        readonly=True,
        help='RSC de la Souscription au moment de la création de cette période '
        "(snapshot) — support de la clé d'idempotence (RSC, mois) du pull electricore.",
    )

    # Calendrier de comptage figé à la création (copie de la souscription, ADR 0005).
    # Pilote le niveau de saisie de l'énergie (voir la cascade plus bas).
    config_cadrans = fields.Selection(
        [('base', 'Base (mono-index)'), ('hp_hc', 'HP/HC'), ('4_cadrans', '4 cadrans saisonniers')],
        string='Calendrier de comptage',
        readonly=True,
    )

    # Consommations détaillées par cadrans (pour calcul TURPE)
    energie_hph_kwh = fields.Float(string='Énergie HPH (kWh)', help='Heures Pleines saison Haute')
    energie_hpb_kwh = fields.Float(string='Énergie HPB (kWh)', help='Heures Pleines saison Basse')
    energie_hch_kwh = fields.Float(string='Énergie HCH (kWh)', help='Heures Creuses saison Haute')
    energie_hcb_kwh = fields.Float(string='Énergie HCB (kWh)', help='Heures Creuses saison Basse')

    # Énergie mesurée / estimée par cadran facturé (selon contrat) — cascade
    # dérivée-mais-surchargeable (ADR 0005). Chaque niveau est dérivé du niveau
    # réseau en dessous SAUF quand le calendrier de comptage en fait le niveau de
    # saisie (alors readonly=False permet la saisie directe — mesure Enedis ou
    # estimation du·de la facturiste —, conservée par les computes config-aware).
    energie_hp_kwh = fields.Float(string='Énergie HP (kWh)', compute='_compute_hp_hc', store=True, readonly=False)
    energie_hc_kwh = fields.Float(string='Énergie HC (kWh)', compute='_compute_hp_hc', store=True, readonly=False)
    energie_base_kwh = fields.Float(string='Énergie BASE (kWh)', compute='_compute_base', store=True, readonly=False)

    # Provision d'énergie par cadran facturé (#14) — l'Énergie facturée
    # universelle (ADR 0030 décision 2, #234), distincte du mesuré/estimé
    # (energie_*_kwh). C'est CETTE quantité, et elle seule, qui est portée sur
    # la facture (voir _quantite_facturee/_composer_lignes) :
    #  - Contrat lissé : provision contractuelle (peuplée à la création depuis la
    #    souscription) ; l'écart avec le mesuré (energie_*_kwh) est suivi par
    #    ecart_*_kwh et soldé en régularisation (ADR 0005).
    #  - Contrat non lissé : tamponnée `provision := energie` à la création de
    #    la facture (_tamponner_provision, appelée par _creer_facture) — la
    #    meilleure mesure/estimation du moment, gelée dès lors comme le reste
    #    du snapshot facturé.
    provision_hp_kwh = fields.Float(string='Provision HP (kWh)')
    provision_hc_kwh = fields.Float(string='Provision HC (kWh)')
    provision_base_kwh = fields.Float(string='Provision BASE (kWh)')

    # Écart mesuré − provision, par cadran facturé (régularisation des contrats
    # lissés — ADR 0005). Calculé, non stocké ; affiché si lissé.
    ecart_hp_kwh = fields.Float(string='Écart HP (kWh)', compute='_compute_ecart')
    ecart_hc_kwh = fields.Float(string='Écart HC (kWh)', compute='_compute_ecart')
    ecart_base_kwh = fields.Float(string='Écart BASE (kWh)', compute='_compute_ecart')

    # TURPE (calculé sur tous les cadrans)
    turpe_fixe = fields.Float(string='TURPE Fixe (€)')
    turpe_variable = fields.Float(string='TURPE Variable (€)', help='Utilise HPH+HPB+HCH+HCB')

    # Atterrissage du contrat PeriodeMeta v3 electricore (ADR 0020 §4) : noms du
    # contrat repris tels quels (single-source, ADR 0019), sauf collision. Les
    # verdicts jumeaux qualite/statut_communication remplacent le drapeau
    # data_complete d'ADR 0011 ; une période incalculable est créée quand même
    # (le brouillon facturable reste la règle, CONTEXT.md).
    qualite = fields.Selection(
        [('réelle', 'Réelle'), ('estimée', 'Estimée'), ('incalculable', 'Incalculable')],
        string='Qualité',
        readonly=True,
        help="Verdict electricore sur la qualité de l'énergie de cette période.",
    )
    statut_communication = fields.Selection(
        [('communicante', 'Communicante'), ('non_communicante', 'Non communicante')],
        string='Statut de communication',
        readonly=True,
        help='Verdict electricore sur la communication du compteur (Linky) sur cette période.',
    )
    has_changement = fields.Boolean(
        string='Changement pendant la période',
        readonly=True,
        help='Un événement C15 (changement de compteur, de puissance…) a eu lieu pendant cette période.',
    )
    source_hash = fields.Char(
        string='Hash source',
        readonly=True,
        help='Empreinte electricore des données sources ayant produit cette période (traçabilité du pull).',
    )
    cta_eur = fields.Float(
        string='CTA (€)',
        readonly=True,
        help="Contribution Tarifaire d'Acheminement, montant servi tel quel par electricore.",
    )
    taux_accise_eur_mwh = fields.Float(
        string='Taux accise (€/MWh)',
        readonly=True,
        help="Taux d'accise servi par electricore ; l'assiette est l'énergie facturée par Odoo "
        '(la provision, quel que soit le lissage — ADR 0030) — le montant se calcule côté Odoo.',
    )
    puissance_moyenne_kva = fields.Float(
        string='Puissance moyenne (kVA)',
        readonly=True,
        help='Moyenne pondérée physique (C15) de la puissance sur la période — grandeur réseau, '
        'distincte de la puissance souscrite (paramètre contractuel snapshotté).',
    )

    # Métadonnées période. La Période est **purement mensuelle** (ADR 0030
    # décision 3, #239) : `regularisation`/`ajustement` n'ont jamais porté de
    # donnée (la Régularisation est un modèle propre depuis la tranche 4,
    # #236) — sélection réduite en conséquence, garde de nettoyage en
    # pre-migrate (migrations/19.0.1.15.0).
    type_periode = fields.Selection(
        [('mensuelle', 'Mensuelle')],
        default='mensuelle',
        string='Type de période',
    )
    jours = fields.Integer(compute='_compute_jours', store=True)

    # Snapshot contractuel figé à la création (historisation typée — #14).
    # Ces valeurs peuvent changer dans la souscription ; la période garde celles
    # du moment, sous une forme *typée* (clé de sélection / nombre) que la
    # facturation lit sans parsing.
    type_tarif_periode = fields.Selection(
        [('base', 'Base'), ('hphc', 'Heures Pleines / Heures Creuses')],
        string='Type tarif (période)',
        readonly=True,
        help='Type de tarif au moment de la création de cette période',
    )

    tarif_solidaire_periode = fields.Boolean(
        string='Tarif solidaire (période)',
        readonly=True,
        help='État du tarif solidaire au moment de la création de cette période',
    )

    regime_prix_periode = fields.Selection(
        [('standard', 'Standard'), ('moulin', 'Moulin')],
        string='Régime de prix (période)',
        default='standard',
        readonly=True,
        help='Régime de prix de la Souscription au moment de la création de '
        'cette période (snapshot, ADR 0006) — sélectionne la Grille de prix '
        'par (régime, date de fin de période) lors de la facturation.',
    )

    lisse_periode = fields.Boolean(
        string='Lissé (période)', readonly=True, help='État du lissage au moment de la création de cette période'
    )

    puissance_souscrite_periode = fields.Float(
        string='Puissance souscrite (période, kVA)',
        readonly=True,
        help='Puissance souscrite (kVA) au moment de la création de cette période',
    )

    provision_mensuelle_kwh_periode = fields.Float(
        string='Provision mensuelle (période)',
        readonly=True,
        help='Provision mensuelle au moment de la création de cette période',
    )

    coeff_pro_periode = fields.Float(
        string='Coefficient PRO (période)',
        readonly=True,
        help='Coefficient PRO au moment de la création de cette période',
    )

    # Relevés d'index utilisés pour le calcul d'énergie (ADR 0015). Justificatif
    # légal, figé avec le snapshot et verrouillé après facturation (#56). Saisi à
    # la main par le·la facturiste tant que le pull electricore manque (#12).
    releve_ids = fields.One2many('souscription.releve', 'periode_id', string="Relevés d'index utilisés")

    # Gating XML des colonnes du formulaire backend (#138) : `column_invisible`
    # ne peut pas appeler une méthode, et l'union des familles (_familles_relevees)
    # exige plusieurs booléens vrais simultanément — impossible avec une seule
    # Selection. Calculés, jamais stockés (source unique : releve_colonnes()).
    releve_show_base = fields.Boolean(compute='_compute_releve_show_familles')
    releve_show_hphc = fields.Boolean(compute='_compute_releve_show_familles')
    releve_show_4cadrans = fields.Boolean(compute='_compute_releve_show_familles')

    # Lien Période ↔ Facture : `account.move.periode_id` est l'unique source de
    # vérité (ADR 0004). `facture_id` en est dérivé — calculé/stocké, non écrit.
    move_ids = fields.One2many('account.move', 'periode_id', string='Documents liés', readonly=True)
    facture_id = fields.Many2one(
        'account.move',
        string='Facture associée',
        compute='_compute_facture_id',
        store=True,
        help='Facture (out_invoice) rattachée à cette période, dérivée du lien account.move.periode_id.',
    )
    # État de la facture exposé sur la période. `facture_id` inclut déjà les
    # brouillons (le compute ne filtre pas sur l'état) ; ce champ rend l'état
    # visible côté gestion pour distinguer brouillon / postée — notamment quand
    # une facture est remise en brouillon par le·la facturiste.
    facture_state = fields.Selection(related='facture_id.state', string='État facture', readonly=True)

    # Période d'ouverture (#107, ADR 0023 décision 3) : Période légitime
    # backfillée par la migration pour un mois non régularisé d'un contrat
    # lissé, portant du facturé (provision, jours — champs existants) mais
    # liée à une facture PROD (Odoo 17), hors du système — donc sans
    # account.move (facture_id/move_ids restent vides, pas de move fictif). Ce
    # champ est le seul marqueur : sa présence identifie la Période d'ouverture,
    # aucun type_periode dédié — elle reste 'mensuelle', pour rester dans le
    # même périmètre qu'une Période facturée normale (régularisation #20).
    facture_legacy_ref = fields.Char(
        string='Facture legacy (référence)',
        readonly=True,
        help='Référence de la facture prod (Odoo 17) dont cette Période est le backfill. '
        "Marque la Période comme « d'ouverture » : pas d'account.move dans ce système.",
    )

    # État « régularisée » posé par la migration (PRD #207/#208, ADR 0030
    # décision 4) : un mois déjà soldé côté prod (settled-is-settled, ADR
    # 0023 §2) avant bascule — exclu des candidats de la Régularisation,
    # silencieusement (ce n'est pas une anomalie, juste déjà réglé). Le
    # backfill qui pose ce marqueur est le chantier #208, pas celui-ci ; le
    # champ est posé ici pour que le calcul des candidats puisse déjà le
    # lire. Volontairement absent de `_LOCKED_FIELDS` : une Période legacy
    # porte déjà `facture_legacy_ref` (donc verrouillée), et le backfill
    # #208 doit pouvoir écrire ce marqueur après coup sans dé-figer le reste.
    #
    # Second auteur (ADR 0031 décision 4, #248) : à l'émission de la
    # Régularisation de CLÔTURE d'une souscription sortie (`date_fin` posé),
    # `souscription.regularisation._marquer_regularisee_si_cloture()` pose ce
    # même marqueur sur TOUS les mois de la souscription — le livre est
    # fermé, aucun candidat ne renaît même si electricore raffine encore le
    # mesuré après coup. Le champ garde son nom (pas de renommage) ; les deux
    # auteurs (migration, clôture) partagent la même sémantique d'exclusion.
    legacy_regularisee = fields.Boolean(
        string='Régularisée (legacy)',
        default=False,
        readonly=True,
        help='Mois déjà soldé — par une régularisation prod avant la bascule (PRD #207/#208), '
        'ou par la Régularisation de clôture de la souscription (ADR 0031 décision 4, #248) — '
        'exclu des candidats de la Régularisation du nouveau système.',
    )

    # Trace du tampon d'émission (ADR 0030 décision 4, tranche 6 #238) : posée
    # par `souscription.regularisation._solder_provisions()` sur CHAQUE
    # mensuelle couverte par la Régularisation émise — écart nul compris (une
    # mensuelle sans écart à ce tour-ci reçoit quand même la trace, tampon
    # +=0). « La trace pointe la dernière » : un mesuré raffiné après solde
    # fait renaître l'écart pour une régul suivante, qui écrase ce lien.
    # Jamais posée avant l'émission (brouillon régul, facture non postée).
    regularisation_id = fields.Many2one(
        'souscription.regularisation',
        string='Régularisation (dernier solde)',
        readonly=True,
        help="Dernière Régularisation dont l'émission a tamponné la provision de cette Période.",
    )

    @api.depends('move_ids.move_type')
    def _compute_facture_id(self):
        for periode in self:
            factures = periode.move_ids.filtered(lambda m: m.move_type == 'out_invoice')
            periode.facture_id = factures[:1]

    # Unicité `(souscription, mois)` (ADR 0020 §2, amendé par ADR 0030 décision
    # 3 / #239) : support de la clé d'idempotence `(RSC, mois)` du pull
    # electricore. La Période étant désormais purement mensuelle (plus de
    # `regularisation`/`ajustement`), l'unicité est **pleine** — un
    # `models.Constraint` UNIQUE ordinaire suffit, plus besoin de l'index
    # partiel `WHERE type_periode = 'mensuelle'` (raw SQL en `init()`).
    _unique_mois = models.Constraint(
        'UNIQUE(souscription_id, mois)',
        'Une période existe déjà pour cette souscription sur ce mois.',
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            sous = self.env['souscription.souscription'].browse(vals['souscription_id'])

            # Snapshot typé de l'état de la souscription au moment de la création
            # (#14) : la clé de tarif (pas le libellé) et la puissance en kVA (pas
            # "6 kVA") — la facturation les lit sans parsing.
            vals.update(
                {
                    'type_tarif_periode': sous.type_tarif,
                    'tarif_solidaire_periode': sous.tarif_solidaire,
                    'regime_prix_periode': sous.regime_prix,
                    'lisse_periode': sous.lisse,
                    'puissance_souscrite_periode': float(sous.puissance_souscrite) if sous.puissance_souscrite else 0.0,
                    'provision_mensuelle_kwh_periode': sous.provision_mensuelle_kwh,
                    'coeff_pro_periode': sous.coeff_pro,
                    'pdl': sous.pdl,  # Copie du PDL aussi
                    'lisse': sous.lisse,  # Compatibilité ancien champ
                    'config_cadrans': sous.config_cadrans or ('4_cadrans' if sous.type_tarif == 'hphc' else 'base'),
                    # Snapshot de la RSC (ADR 0010, ADR 0020 §3) : même logique que
                    # le snapshot des paramètres contractuels (ADR 0006).
                    'ref_situation_contractuelle': sous.ref_situation_contractuelle,
                }
            )

            # Provisions par cadran selon type de tarif — source unique
            # souscription._provisions_cadrans() (#73) : hp/hc explicites
            # (peuplées par le raccordement) priment, sinon répartition 70/30
            # de la mensuelle. La répartition ne vit qu'à cet unique endroit.
            # N'écrase jamais une provision déjà fournie explicitement à create()
            # (saisie manuelle d'une période, tests).
            if sous.lisse:
                provisions = sous._provisions_cadrans()
                if sous.type_tarif == 'base':
                    vals.setdefault('provision_base_kwh', provisions['base'])
                else:  # HP/HC
                    vals.setdefault('provision_hp_kwh', provisions['hp'])
                    vals.setdefault('provision_hc_kwh', provisions['hc'])

        return super().create(vals_list)

    # Champs **facturés**, gelés : dès qu'une Facture qui référence la période
    # est **émise** (postée), les réécrire désaccorderait la facture de la
    # période. Le verrou (#14, amendé #267 — ADR 0006/0007 amendés, ADR 0032)
    # les protège ; les champs techniques/calculés (facture_id, facture_state,
    # mois_annee, jours…) restent recalculables par l'ORM (passe par _write, pas
    # par ce write public).
    #
    # Le **mesuré** — l'atterrissage réseau v3 (énergies par cadran, verdicts,
    # TURPE fixe/variable, CTA, taux d'accise, puissance moyenne, empreinte) —
    # est volontairement ABSENT de cette liste (ADR 0030 décision 1, #235) :
    # exemption chirurgicale du verrou, il redevient réécrivable après
    # facturation, gardé par l'empreinte côté pull
    # (`souscription.pull.meta.periodes.service`) et à la main par le·la
    # facturiste (correction directe). Seul le **facturé** — provisions, jours
    # (dérivé de date_debut/date_fin, tous deux ici), snapshot contractuel,
    # relevés-justificatifs (verrou propre, souscription_releve.py) — reste
    # verrouillé ; aucun canal de pull n'écrit jamais `provision_*`.
    _LOCKED_FIELDS = frozenset(
        {
            'date_debut',
            'date_fin',
            'pdl',
            'lisse',
            'config_cadrans',
            'type_periode',
            'provision_hp_kwh',
            'provision_hc_kwh',
            'provision_base_kwh',
            'type_tarif_periode',
            'tarif_solidaire_periode',
            'regime_prix_periode',
            'lisse_periode',
            'puissance_souscrite_periode',
            'provision_mensuelle_kwh_periode',
            'coeff_pro_periode',
            # Identité (#76, ADR 0020 §7, ADR 0010) : snapshot au même titre
            # que le reste du contrat — jamais réécrite par le pull (la clé
            # (RSC, mois) se lit sur la Souscription courante, pas la Période).
            'ref_situation_contractuelle',
            # Référence de la facture legacy (#107) : au même titre que
            # facture_id, sa présence fige la période — l'écraser romprait le
            # lien vers la facture prod sans passer par le verrou.
            'facture_legacy_ref',
        }
    )

    def _est_facturee_emise(self):
        """Condition **dérivée** du gel (#267 — brouillon gouverné, ADR 0006/
        0007 amendés, ADR 0032) : cette Période est-elle verrouillée ?

        Oui si une Facture qui la référence est **postée** (`facture_id.state
        == 'posted'`), ou si elle porte une référence de facture legacy
        (`facture_legacy_ref`, #107) — une Période d'ouverture backfillée est
        TOUJOURS considérée émise : la facture prod qu'elle projette est hors
        de ce système, jamais en brouillon ici.

        Non si aucune Facture ne la référence, OU si la Facture qui la
        référence est encore en **brouillon** : la fenêtre brouillon reste
        vivante — c'est l'**émission**, pas l'existence de la facture, qui
        fige (avant #267 : `facture_id or facture_legacy_ref` seul, sans
        regarder l'état)."""
        self.ensure_one()
        return bool(self.facture_legacy_ref or self.facture_id.state == 'posted')

    def write(self, vals):
        """Verrou de facturation (#14, amendé #267) : la période est le
        brouillon de travail éditable *avant* et *pendant* la fenêtre
        brouillon de sa Facture ; dès qu'une Facture qui la référence est
        **émise** (postée) — ou qu'elle porte une facture legacy (#107) —,
        ses champs facturables sont figés et toute réécriture est rejetée
        (UserError, y compris via RPC). Pour corriger après émission : un
        avoir ou une régularisation (plus de « supprimer la facture », qui ne
        fige plus rien tant qu'elle est en brouillon — cf. `_est_facturee_emise`).

        Exemption ciblée : le contexte `regularisation_tampon` (posé
        uniquement par `souscription.regularisation._solder_provisions()`,
        ADR 0030 décision 4) contourne ce verrou pour `provision_*_kwh` — seul
        canal qui réécrit la provision d'une Période déjà émise, à l'émission
        d'une facture de régularisation qui la porte. Aucun autre appelant ne
        pose ce contexte ; le pull et l'édition manuelle restent bloqués une
        fois émise.

        Régénération au fil de l'eau (#267, point d'entrée (b)) : une édition
        RÉUSSIE d'un champ facturable — la Période est donc dans sa fenêtre
        brouillon, avec ou sans brouillon de Facture lié — recompose les
        lignes générées de ce brouillon, pour que le·la facturiste voie tout
        de suite l'effet de sa correction. Contexte `souscription_tampon_emission`
        (posé uniquement par `_tamponner_provision`) : la re-génération de
        `account.move._post()` suit immédiatement le tampon dans le même
        événement d'émission, inutile de la déclencher deux fois."""
        champs_geles = self._LOCKED_FIELDS.intersection(vals)
        if champs_geles and not self.env.context.get('regularisation_tampon'):
            for periode in self:
                if periode._est_facturee_emise():
                    raise UserError(
                        f'Période {periode.mois_annee} : facture émise, modification interdite. '
                        'Corrigez par un avoir ou par une régularisation.'
                    )
        resultat = super().write(vals)
        if champs_geles and not self.env.context.get('souscription_tampon_emission'):
            for periode in self:
                if periode.facture_id.state == 'draft':
                    periode.facture_id._recomposer_lignes_generees()
        return resultat

    # Mapping cadran réseau → colonne d'index, source unique pour le justificatif
    # PDF (#55), portail (#57) et formulaire backend (#138) — ADR 0015 (amendé
    # #138). Point d'extension nommé pour Tempo/EJP (hors périmètre).
    _RELEVE_COLONNES = {
        'base': [{'label': 'Base', 'field': 'index_base'}],
        'hp_hc': [{'label': 'HP', 'field': 'index_hp'}, {'label': 'HC', 'field': 'index_hc'}],
        '4_cadrans': [
            {'label': 'HPH', 'field': 'index_hph'},
            {'label': 'HPB', 'field': 'index_hpb'},
            {'label': 'HCH', 'field': 'index_hch'},
            {'label': 'HCB', 'field': 'index_hcb'},
        ],
    }

    # Ordre superficiel → profond, pour l'union ordonnée quand plusieurs
    # familles cohabitent (changement de compteur en cours de période).
    _FAMILLES = ['base', 'hp_hc', '4_cadrans']

    def _famille_non_vide(self, releve, famille):
        """Un relevé `releve` porte-t-il au moins un index non nul de `famille` ?"""
        return any(releve[champ['field']] for champ in self._RELEVE_COLONNES[famille])

    def _familles_relevees(self):
        """Familles de cadrans (`base`/`hp_hc`/`4_cadrans`) réellement portées
        par les relevés de cette Période, ordonnées superficiel → profond
        (#138). Un changement de compteur en cours de période peut faire
        cohabiter deux familles ; chaque relevé ne remplit que les registres de
        *son* compteur. Repli sur le `config_cadrans` déclaré si aucun relevé ne
        porte le moindre index (saisie manuelle #12, qui doit garder des
        colonnes où écrire)."""
        self.ensure_one()
        presentes = [f for f in self._FAMILLES if any(self._famille_non_vide(r, f) for r in self.releve_ids)]
        return presentes or [self.config_cadrans or 'base']

    def releve_colonnes(self):
        """Colonnes d'index réseau (`label`, `field`) à afficher pour le
        justificatif des relevés de cette Période : l'**union** des familles de
        cadrans réellement présentes dans `releve_ids` (#138, amende ADR 0015 —
        ne suit plus `config_cadrans` directement). Itérées par les rendus PDF,
        portail et formulaire backend — un seul endroit où vit le mapping
        cadran→colonne."""
        self.ensure_one()
        return [colonne for famille in self._familles_relevees() for colonne in self._RELEVE_COLONNES[famille]]

    @api.depends(
        'config_cadrans',
        'releve_ids.index_base',
        'releve_ids.index_hp',
        'releve_ids.index_hc',
        'releve_ids.index_hph',
        'releve_ids.index_hpb',
        'releve_ids.index_hch',
        'releve_ids.index_hcb',
    )
    def _compute_releve_show_familles(self):
        """Booléens calculés pour le gating XML du formulaire backend (#138) :
        `column_invisible` ne peut pas appeler une méthode, et l'union peut
        rendre **plusieurs** familles vraies simultanément — impossible à
        représenter par une Selection unique."""
        for periode in self:
            familles = periode._familles_relevees()
            periode.releve_show_base = 'base' in familles
            periode.releve_show_hphc = 'hp_hc' in familles
            periode.releve_show_4cadrans = '4_cadrans' in familles

    @api.depends('date_debut', 'date_fin')
    def _compute_jours(self):
        for p in self:
            if p.date_debut and p.date_fin:
                p.jours = (p.date_fin - p.date_debut).days
            else:
                p.jours = 0

    @api.depends('energie_hph_kwh', 'energie_hpb_kwh', 'energie_hch_kwh', 'energie_hcb_kwh', 'config_cadrans')
    def _compute_hp_hc(self):
        """HP/HC dérivés des 4 cadrans saisonniers en config 4_cadrans ; sinon
        saisis directement (valeur conservée).

        electricore (contrat v3, ADR 0020) sert HP/HC **déjà groupés** même en
        config ``4_cadrans`` : à la création, si HP/HC sont fournis en vals sans
        qu'aucun des 4 cadrans ne le soit, la cascade ne doit pas les remettre à
        zéro. On ne dérive donc que si au moins un cadran source est non nul —
        seule la saisie manuelle des 4 cadrans déclenche le regroupement.
        """
        for periode in self:
            cadrans_fournis = any(
                (periode.energie_hph_kwh, periode.energie_hpb_kwh, periode.energie_hch_kwh, periode.energie_hcb_kwh)
            )
            if periode.config_cadrans == '4_cadrans' and cadrans_fournis:
                periode.energie_hp_kwh = periode.energie_hph_kwh + periode.energie_hpb_kwh
                periode.energie_hc_kwh = periode.energie_hch_kwh + periode.energie_hcb_kwh
            else:
                periode.energie_hp_kwh = periode.energie_hp_kwh
                periode.energie_hc_kwh = periode.energie_hc_kwh

    @api.depends('energie_hp_kwh', 'energie_hc_kwh', 'config_cadrans')
    def _compute_base(self):
        """BASE = HP+HC sauf en config base où elle est saisie directement."""
        for periode in self:
            if periode.config_cadrans in ('4_cadrans', 'hp_hc'):
                periode.energie_base_kwh = periode.energie_hp_kwh + periode.energie_hc_kwh
            else:
                periode.energie_base_kwh = periode.energie_base_kwh

    @api.depends(
        'energie_hp_kwh',
        'energie_hc_kwh',
        'energie_base_kwh',
        'provision_hp_kwh',
        'provision_hc_kwh',
        'provision_base_kwh',
    )
    def _compute_ecart(self):
        """Écart facturé réel − provision, par cadran facturé."""
        for periode in self:
            periode.ecart_hp_kwh = periode.energie_hp_kwh - periode.provision_hp_kwh
            periode.ecart_hc_kwh = periode.energie_hc_kwh - periode.provision_hc_kwh
            periode.ecart_base_kwh = periode.energie_base_kwh - periode.provision_base_kwh

    @api.depends('date_debut')
    def _compute_mois_annee(self):
        for rec in self:
            if rec.date_debut:
                rec.mois_annee = format_date(rec.date_debut, format='MMMM yyyy', locale='fr_FR').capitalize()
            else:
                rec.mois_annee = ''

    @api.depends('date_debut')
    def _compute_mois(self):
        """Mois canonique (ADR 0020 §2) : `date_debut` tronquée au 1er du mois —
        support de la clé d'idempotence `(RSC, mois)` du pull electricore."""
        for rec in self:
            rec.mois = rec.date_debut.replace(day=1) if rec.date_debut else False

    # === Composition de la facture (candidate A / ADR 0006) ===
    # La Période compose ses lignes de facture à partir de son snapshot figé
    # (puissance, tarif, coeff PRO, solidaire, quantités) et de la grille passée
    # en paramètre. Aucun repli sur l'état live de la souscription : le snapshot
    # fait autorité (ADR 0006). Les prix restent l'affaire de la grille — la
    # règle d'assemblage vit dans grille.composants(), la Période n'en est
    # qu'une projection (ADR 0002 « référencer, pas recopier », ADR 0029).

    def _quantite_facturee(self, cadran):
        """Quantité d'énergie à facturer pour un cadran facturé ('base'/'hp'/'hc').

        Énergie facturée universelle (ADR 0030 décision 2, #234) : la
        *provision* (``provision_*_kwh``) fait foi, lissé ou non — MAIS
        seulement une fois **tamponnée** (#267). Le tampon
        ``provision := energie`` a migré de la création de la facture à son
        **émission** (``_tamponner_provision``, appelée par
        ``account.move._post()``, AVANT la re-génération) : pendant toute la
        fenêtre brouillon, une Période qui doit recevoir ce tampon
        (``_a_tamponner``) porte encore une provision **vide** — la lire
        montrerait 0 kWh, alors qu'electricore connaît déjà mieux.

        **Choix documenté (#267)** : tant que non tamponnée (facture pas
        encore émise), cette méthode lit le **mesuré** (``energie_*_kwh``)
        directement — le brouillon montre la meilleure connaissance du
        moment, cohérent avec « rien ne gèle au brouillon » (CONTEXT.md
        « Facture »). Une fois tamponnée (facture émise, ou contrat lissé
        hors clôture dont la provision contractuelle est fixée dès la
        création), la provision fait foi, gelée contre le mesuré qui continue
        de vivre à côté (ADR 0030). L'alternative écartée — un second
        mécanisme de calcul dédié au brouillon — aurait dupliqué la logique
        que le tampon applique déjà ; lire le mesuré en repli est la même
        Énergie facturée universelle, simplement pas-encore-gelée.
        """
        self.ensure_one()
        if self._a_tamponner() and not self._est_facturee_emise():
            mesure = {
                'base': self.energie_base_kwh,
                'hp': self.energie_hp_kwh,
                'hc': self.energie_hc_kwh,
            }
            return mesure[cadran]
        provision = {
            'base': self.provision_base_kwh,
            'hp': self.provision_hp_kwh,
            'hc': self.provision_hc_kwh,
        }
        return provision[cadran]

    def _composer_lignes(self, grille):
        """Compose les lignes de facture (``[(0, 0, vals)]``) de cette période.

        Lit le snapshot figé de la période, résout les prix via
        ``grille.composants()`` — l'unique règle d'assemblage (ADR 0029) — et
        ne garde que la projection : quantités du snapshot, sections, notes.
        Ne crée aucun ``account.move``.

        Chaque ligne porte ``souscription_ligne_generee = True`` (#266, ADR
        0014 amendé) : c'est cette méthode — pas un appelant — qui pose le
        flag de provenance, pour que TOUT chemin qui compose des lignes
        depuis une Période (création, re-génération à l'émission) le porte
        sans avoir à y penser.
        """
        self.ensure_one()

        # Snapshot figé typé — ADR 0006 (pas de repli sur la souscription live)
        # et #14 (valeurs typées : aucun parsing à la facturation).
        puissance_kva = self.puissance_souscrite_periode
        coeff_pro_historise = self.coeff_pro_periode

        if not puissance_kva:
            raise UserError(f'Aucune puissance définie pour la période {self.mois_annee}')

        composants = grille.composants(
            self.type_tarif_periode,
            puissance_kva,
            coeff_pro=coeff_pro_historise,
            tarif_solidaire=self.tarif_solidaire_periode,
        )

        lines_vals = []

        # Section Abonnement
        lines_vals.append((0, 0, {'display_type': 'line_section', 'name': 'Abonnement'}))

        produit_abo = composants['abonnement']['produit']
        type_client = 'PRO' if coeff_pro_historise > 0 else 'PART'
        puissance_desc = f'{puissance_kva:g} kVA'  # :g supprime les .0 inutiles

        lines_vals.append(
            (
                0,
                0,
                {
                    'product_id': produit_abo.id,
                    'name': f'{produit_abo.name} {puissance_desc} {type_client}',
                    'quantity': self.jours,
                    'price_unit': composants['abonnement']['prix_jour'],
                },
            )
        )

        # Note TURPE fixe sous l'abonnement
        if self.turpe_fixe > 0:
            lines_vals.append((0, 0, {'display_type': 'line_note', 'name': f'Dont turpe fixe: {self.turpe_fixe:.2f}€'}))

        # Section Énergie
        lines_vals.append((0, 0, {'display_type': 'line_section', 'name': 'Énergie'}))

        for composant in composants['energies']:
            lines_vals.append(
                (
                    0,
                    0,
                    {
                        'product_id': composant['produit'].id,
                        'name': composant['produit'].name,
                        'quantity': self._quantite_facturee(composant['cadran']),
                        'price_unit': composant['prix_kwh'],
                    },
                )
            )

        # Note TURPE variable sous l'énergie
        if self.turpe_variable > 0:
            lines_vals.append(
                (0, 0, {'display_type': 'line_note', 'name': f'Dont turpe variable: {self.turpe_variable:.2f}€'})
            )

        return [(cmd, id_, dict(vals, souscription_ligne_generee=True)) for cmd, id_, vals in lines_vals]

    # === Amorçage depuis le pull electricore (#77, ADR 0011/0019/0020) ===

    # Nature du contrat (`nature_index` de l'ObjetReleve) → nature Odoo du
    # Relevé (ADR 0020 §6) : réel/corrigé sont tous deux une mesure Enedis
    # (le "corrigé" est un réel révisé) ; le reste est une estimation.
    _NATURE_RELEVE = {'reel': 'reel', 'corrige': 'reel'}

    @api.model
    def _amorcer_depuis_meta(self, souscription, meta):
        """Mappe une `PeriodeMeta` (contrat v3, duck-typée) vers `create()`.

        Aucune table de traduction (ADR 0020) : les champs du contrat
        atterrissent sous leur nom. N'écrit rien de son propre chef — construit
        les vals et délègue à `create()`, qui applique le snapshot contractuel
        habituel (type_tarif, puissance…) par-dessus. `meta` n'a besoin que des
        attributs de `PeriodeMeta` (tests : un stub/namedtuple suffit).

        Une période `qualite='incalculable'` est créée quand même, énergies
        nulles (le brouillon facturable reste la règle, CONTEXT.md).
        """
        vals = {
            'souscription_id': souscription.id,
            'date_debut': fields.Date.to_date(meta.debut),
            'date_fin': fields.Date.to_date(meta.fin),
            'type_periode': 'mensuelle',
            **self._vals_atterrissage_v3(meta),
            'releve_ids': [(0, 0, self._releve_vals_depuis_objet(releve)) for releve in (meta.releves_utilises or [])],
        }
        return self.create(vals)

    def _releve_vals_depuis_objet(self, releve):
        """Mappe un `ObjetReleve` (contrat v3) vers les vals d'un
        `souscription.releve` enfant (ADR 0020 §6) : provenance conservée
        (`releve_externe_id`, `origine`), nature réel/corrigé → `reel`,
        estimé → `estime`."""
        return {
            'date': fields.Date.to_date(releve.date_releve),
            'nature': self._NATURE_RELEVE.get(releve.nature_index, 'estime'),
            'index_base': releve.index_base_kwh or 0,
            'index_hp': releve.index_hp_kwh or 0,
            'index_hc': releve.index_hc_kwh or 0,
            'index_hph': releve.index_hph_kwh or 0,
            'index_hpb': releve.index_hpb_kwh or 0,
            'index_hch': releve.index_hch_kwh or 0,
            'index_hcb': releve.index_hcb_kwh or 0,
            'releve_externe_id': releve.releve_id,
            'origine': releve.evenement or releve.origine_releve,
        }

    # Champs de l'atterrissage v3 rafraîchis EN BLOC par le pull (ADR 0030
    # décision 1, #235) — jamais d'énergie fraîche sur TURPE périmé : un seul
    # `write()`. Volontairement absents : `date_debut`/`date_fin`/
    # `type_periode`/`ref_situation_contractuelle` (identité, jamais réécrite
    # par le pull) et `provision_*` (le facturé, jamais écrit par aucun canal
    # de pull).
    def _vals_atterrissage_v3(self, meta):
        return {
            'puissance_moyenne_kva': meta.puissance_moyenne_kva or 0.0,
            'energie_base_kwh': meta.energie_base_kwh or 0.0,
            'energie_hp_kwh': meta.energie_hp_kwh or 0.0,
            'energie_hc_kwh': meta.energie_hc_kwh or 0.0,
            'turpe_fixe': meta.turpe_fixe_eur or 0.0,
            'turpe_variable': meta.turpe_variable_eur or 0.0,
            'cta_eur': meta.cta_eur or 0.0,
            'taux_accise_eur_mwh': meta.taux_accise_eur_mwh or 0.0,
            'has_changement': bool(meta.has_changement),
            'qualite': meta.qualite or 'incalculable',
            'statut_communication': meta.statut_communication or False,
            'source_hash': meta.source_hash,
        }

    def _rafraichir_depuis_meta(self, meta):
        """Rafraîchit une Période **déjà amorcée** depuis une nouvelle `meta`
        (#235, ADR 0030 décision 1) : appelée par
        `souscription.pull.meta.periodes.service` une fois l'empreinte jugée
        nouvelle et le verdict fiable (`réelle`/`estimée`) — cette méthode
        écrit **inconditionnellement**, la garde vit chez l'appelant.

        Écrase l'atterrissage réseau v3 **en bloc** (`_vals_atterrissage_v3`) —
        un seul `write()`, jamais d'énergie fraîche sur TURPE périmé. Passe
        par `write()` (pas d'écriture directe) : l'exemption ciblée du verrou
        de facturation (#14, cf. `_LOCKED_FIELDS`) rend cette écriture valide
        même sur une Période émise — c'est précisément ce qui réalise « le
        mesuré vivant » d'ADR 0030.

        Relevés : remplacés **en bloc** (`releve_ids`, le re-pull promis par
        ADR 0015) **seulement si la Période n'est pas encore émise**
        (`_est_facturee_emise`, #267) — pendant la fenêtre brouillon, le
        re-pull rafraîchit les relevés comme le reste du mesuré ; une fois
        émise, le relevé-justificatif reste figé (verrou propre de
        `souscription.releve`, jamais contourné ici) et `releve_ids` est
        absent des vals, donc intact.

        Régénération au fil de l'eau (#267, point d'entrée (a)) : si cette
        Période porte un brouillon de Facture, il est recomposé après le
        write — le facturiste voit tout de suite le mesuré rafraîchi reflété
        dans les lignes (énergie non tamponnée encore lue en direct par
        `_quantite_facturee`, tant que le brouillon n'a pas été émis)."""
        self.ensure_one()
        vals = self._vals_atterrissage_v3(meta)
        if not self._est_facturee_emise():
            vals['releve_ids'] = [(5, 0, 0)] + [
                (0, 0, self._releve_vals_depuis_objet(releve)) for releve in (meta.releves_utilises or [])
            ]
        self.write(vals)
        if self.facture_id.state == 'draft':
            self.facture_id._recomposer_lignes_generees()

    def _est_periode_cloture(self):
        """Cette Période est-elle la Période de clôture de sa Souscription —
        celle qui contient `date_fin` (dernier jour servi, ADR 0031 décision
        2) ? Même prédicat de bornes que
        `souscription.souscription._periode_cloture()` (demi-ouvertes, bornes
        v3 brutes), vu côté Période plutôt que côté Souscription — évite d'y
        aller-retour pour une simple comparaison de bornes."""
        self.ensure_one()
        sous = self.souscription_id
        return bool(
            sous.date_fin and self.date_debut and self.date_fin and self.date_debut <= sous.date_fin < self.date_fin
        )

    def _a_tamponner(self):
        """Cette Période reçoit-elle le tampon ``provision := energie`` à
        l'émission (#267, ADR 0030 décision 2) ? Contrat **non lissé** :
        toujours. Contrat **lissé** : jamais, SAUF pour la Période de
        **clôture** d'une souscription sortie (`date_fin` posé, ADR 0031
        décision 4, #248) — la dernière mensuelle d'un lissé se facture **au
        réel** comme n'importe quelle non-lissée. Factorisé hors de
        ``_tamponner_provision`` : ``_quantite_facturee`` partage exactement
        ce prédicat pour savoir si le brouillon doit lire le mesuré ou la
        provision (#267)."""
        self.ensure_one()
        return not self.lisse_periode or self._est_periode_cloture()

    def _tamponner_provision(self):
        """Tamponne ``provision_* := energie_*`` (par cadran facturé) sur une
        Période éligible (``_a_tamponner``), à l'**émission** de sa Facture —
        Énergie facturée universelle (ADR 0030 décision 2, #234) : la
        provision devient le facturé pour tout contrat, la branche
        lissé/non-lissé de ``_quantite_facturee`` reste mais bascule sur
        « tamponnée ou non », pas sur le lissage seul (#267). Contrat
        **lissé** hors clôture : no-op, la provision contractuelle est déjà
        fixée à la création. Non éligible (``_a_tamponner`` faux) : rien à
        faire, ``_quantite_facturee`` lit déjà la provision contractuelle.

        **Déplacement (#267, tranche 3 du PRD #264)** : appelée depuis
        ``account.move._post()``, AVANT la re-génération des lignes et AVANT
        ``super()._post()`` — plus depuis ``_creer_facture()`` (qui ne
        produit plus qu'un brouillon non tamponné). Pendant toute la fenêtre
        brouillon, ``provision_*`` reste donc vide pour une Période non
        tamponnée ; c'est ``_quantite_facturee`` qui compense en lisant le
        mesuré en direct jusqu'à ce tampon (voir son docstring). Passe par
        ``write()`` (pas d'écriture directe) : au moment de l'appel, la
        Facture qui référence CETTE Période est encore en état ``draft``
        (``super()._post()`` n'a pas encore tourné) — le verrou (#14,
        ``_est_facturee_emise``) ne bloque donc pas cette écriture,
        exactement comme avant #267 où le tampon précédait la création du
        move. Contexte `souscription_tampon_emission` : la re-génération de
        `_post()` suit immédiatement dans le même événement d'émission,
        inutile de la déclencher une seconde fois depuis `write()`.

        Garde-fou : no-op si la Période est déjà **émise**
        (``_est_facturee_emise``) — défense en profondeur (ne devrait pas se
        produire, une Période n'a qu'une Facture par construction, ADR 0004)
        et cas de la Période legacy (``facture_legacy_ref``, jamais de move
        dans ce système, donc jamais atteinte par ``account.move._post()``
        de toute façon).

        Rejoué : réouvrir la Facture en brouillon (``button_draft()``) puis
        la ré-émettre rejoue ce tampon aux valeurs courantes de ``energie_*``
        — la future « régularisation des réels » d'un non-lissé rééditée par
        Enedis emprunte le même mécanisme.
        """
        self.ensure_one()
        if not self._a_tamponner():
            return
        if self._est_facturee_emise():
            # Le facturé gelé (ADR 0030) : une Période déjà émise garde sa
            # provision scellée — même condition que le verrou de write().
            return
        self.with_context(souscription_tampon_emission=True).write(
            {
                'provision_hp_kwh': self.energie_hp_kwh,
                'provision_hc_kwh': self.energie_hc_kwh,
                'provision_base_kwh': self.energie_base_kwh,
            }
        )

    # Underscore délibéré : ferme la porte RPC externe, même idiome que
    # `sale.order._create_invoices` (décision du grill, amende la revue d'architecture).
    def _creer_facture(self):
        """Crée la facture (``account.move``) de cette période, en **brouillon**.

        Sélectionne la grille active à la date de fin, compose les lignes
        (``_composer_lignes``) et crée le move en posant ``periode_id``
        (source unique du lien Période ↔ Facture, ADR 0004). Ne tamponne
        PLUS la provision ici (``_tamponner_provision`` a migré à
        l'**émission**, appelée par ``account.move._post()`` — #267, tranche
        3 du PRD #264) : le brouillon créé ici porte donc, pour une Période
        éligible (``_a_tamponner``), le **mesuré** en lecture directe
        (``_quantite_facturee``), pas encore la provision tamponnée. Ne poste
        jamais le move : l'émission (``action_post`` / ``account.move._post``)
        reste un geste distinct — c'est elle, pas la création, qui tamponne,
        re-génère, verrouille et impute le chèque énergie (tranche 1 du PRD
        #264, #265 ; tranche 3, #267).
        """
        self.ensure_one()
        grille = self.env['grille.prix'].get_grille_active(self.date_fin, regime=self.regime_prix_periode)
        return self.env['account.move'].create(
            {
                'move_type': 'out_invoice',
                'partner_id': self.souscription_id.partner_id.id,
                'invoice_date': self.date_fin,
                'periode_id': self.id,
                'invoice_line_ids': self._composer_lignes(grille),
            }
        )
