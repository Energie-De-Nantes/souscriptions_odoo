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

    # Provision d'énergie par cadran facturé (#14) — distincte du mesuré/estimé
    # (energie_*_kwh). C'est CETTE quantité qui est portée sur la facture (voir
    # _composer_lignes) :
    #  - Contrat lissé : provision contractuelle (peuplée à la création depuis la
    #    souscription) ; l'écart avec le mesuré (energie_*_kwh) est suivi par
    #    ecart_*_kwh et soldé en régularisation (ADR 0005).
    #  - Contrat non lissé : la provision vaut la consommation mesurée/estimée
    #    (alignée par electricore / le·la facturiste).
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
        [('reelle', 'Réelle'), ('estimee', 'Estimée'), ('incalculable', 'Incalculable')],
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
        '(la provision si le contrat est lissé) — le montant se calcule côté Odoo.',
    )
    puissance_moyenne_kva = fields.Float(
        string='Puissance moyenne (kVA)',
        readonly=True,
        help='Moyenne pondérée physique (C15) de la puissance sur la période — grandeur réseau, '
        'distincte de la puissance souscrite (paramètre contractuel snapshotté).',
    )

    # Métadonnées période
    type_periode = fields.Selection(
        [('mensuelle', 'Mensuelle'), ('regularisation', 'Régularisation'), ('ajustement', 'Ajustement')],
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

    @api.depends('move_ids.move_type')
    def _compute_facture_id(self):
        for periode in self:
            factures = periode.move_ids.filtered(lambda m: m.move_type == 'out_invoice')
            periode.facture_id = factures[:1]

    _unique_periode_souscription = models.Constraint(
        'UNIQUE(souscription_id, date_debut, date_fin)',
        'Une seule période par souscription et par dates début/fin.',
    )

    def init(self):
        """Unicité `(souscription, mois)` scopée aux périodes **mensuelles**
        (ADR 0020 §2) : support de la clé d'idempotence `(RSC, mois)` du pull
        electricore, sans bloquer régularisations/ajustements (libres, plusieurs
        par mois possibles). Un index unique partiel — hors du vocabulaire de
        `models.Constraint`, qui ne sait pas exprimer de clause `WHERE` — est la
        façon idiomatique Odoo d'imposer une contrainte SQL conditionnelle."""
        self.env.cr.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS souscription_periode_mois_mensuelle_unique
            ON souscription_periode (souscription_id, mois)
            WHERE type_periode = 'mensuelle'
            """
        )
        super().init()

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

    # Champs facturables figés : dès qu'une facture référence la période, les
    # réécrire désaccorderait la facture de la période. Le verrou (#14) les
    # protège ; les champs techniques/calculés (facture_id, facture_state,
    # mois_annee, jours…) restent recalculables par l'ORM (passe par _write, pas
    # par ce write public).
    _LOCKED_FIELDS = frozenset(
        {
            'date_debut',
            'date_fin',
            'pdl',
            'lisse',
            'config_cadrans',
            'type_periode',
            'energie_hph_kwh',
            'energie_hpb_kwh',
            'energie_hch_kwh',
            'energie_hcb_kwh',
            'energie_hp_kwh',
            'energie_hc_kwh',
            'energie_base_kwh',
            'provision_hp_kwh',
            'provision_hc_kwh',
            'provision_base_kwh',
            'turpe_fixe',
            'turpe_variable',
            'type_tarif_periode',
            'tarif_solidaire_periode',
            'regime_prix_periode',
            'lisse_periode',
            'puissance_souscrite_periode',
            'provision_mensuelle_kwh_periode',
            'coeff_pro_periode',
            # Identité et atterrissage v3 (#76, ADR 0020 §7) : figés au même titre
            # que le reste du snapshot dès qu'une facture référence la période.
            'ref_situation_contractuelle',
            'qualite',
            'statut_communication',
            'has_changement',
            'source_hash',
            'cta_eur',
            'taux_accise_eur_mwh',
            'puissance_moyenne_kva',
        }
    )

    def write(self, vals):
        """Verrou de facturation (#14) : la période est le brouillon de travail
        éditable *avant* facturation ; dès qu'une facture la référence (facturée,
        brouillon de facture compris), ses champs facturables sont figés et toute
        réécriture est rejetée (UserError, y compris via RPC). Pour corriger :
        supprimer la facture (ce qui dé-fige la période) ou émettre une
        régularisation."""
        if self._LOCKED_FIELDS.intersection(vals):
            for periode in self:
                if periode.facture_id:
                    raise UserError(
                        f'Période {periode.mois_annee} : déjà facturée, modification interdite. '
                        'Supprimez la facture pour corriger, ou créez une régularisation.'
                    )
        return super().write(vals)

    # Mapping cadran réseau → colonne d'index, source unique pour le justificatif
    # PDF (#55) et portail (#57) — ADR 0015. Suit le calendrier de comptage
    # (ADR 0005) ; point d'extension nommé pour Tempo/EJP (hors périmètre).
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

    def releve_colonnes(self):
        """Colonnes d'index réseau (`label`, `field`) à afficher pour le
        justificatif des relevés de cette Période, selon son calendrier de
        comptage. Itérées par les rendus PDF et portail — un seul endroit où vit
        le mapping cadran→colonne (ADR 0015)."""
        self.ensure_one()
        return self._RELEVE_COLONNES.get(self.config_cadrans, [])

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
    # fait autorité (ADR 0006). Les prix restent l'affaire de la grille (ADR 0002,
    # « référencer, pas recopier »).

    # Cadrans facturés par type de tarif (snapshot `type_tarif_periode`) : pilote
    # la boucle de composition des lignes d'énergie (#74, prefactoring en vue de
    # l'abonnement pricé sur la puissance moyenne, #78). Même partition que
    # `souscription._CADRANS_DOCUMENTS` (Conditions particulières) : Base = un
    # seul cadran ; HP/HC = toujours les deux, même à 0.
    _CADRANS_FACTURES = {
        'base': ['base'],
        'hphc': ['hp', 'hc'],
    }

    def _quantite_facturee(self, cadran):
        """Quantité d'énergie à facturer pour un cadran facturé ('base'/'hp'/'hc').

        Contrat **lissé** : la *provision* contractuelle (``provision_*_kwh``) ;
        l'écart avec le mesuré est soldé plus tard en régularisation.
        Contrat **non lissé** : le *mesuré / estimé* (``energie_*_kwh``) directement.
        Le choix s'appuie sur le snapshot figé ``lisse_periode`` (ADR 0006).
        """
        self.ensure_one()
        provision = {
            'base': self.provision_base_kwh,
            'hp': self.provision_hp_kwh,
            'hc': self.provision_hc_kwh,
        }
        mesure = {
            'base': self.energie_base_kwh,
            'hp': self.energie_hp_kwh,
            'hc': self.energie_hc_kwh,
        }
        return provision[cadran] if self.lisse_periode else mesure[cadran]

    def _composer_lignes(self, grille):
        """Compose les lignes de facture (``[(0, 0, vals)]``) de cette période.

        Lit le snapshot figé de la période et la ``grille`` passée pour les prix.
        Ne crée aucun ``account.move`` : la liste renvoyée est la surface de test
        des règles de facturation.
        """
        self.ensure_one()
        prix_dict = grille.get_prix_dict()

        # Snapshot figé typé — ADR 0006 (pas de repli sur la souscription live)
        # et #14 (valeurs typées : aucun parsing à la facturation).
        puissance_kva = self.puissance_souscrite_periode
        tarif_solidaire = self.tarif_solidaire_periode
        type_tarif = self.type_tarif_periode

        if not puissance_kva:
            raise UserError(f'Aucune puissance définie pour la période {self.mois_annee}')

        lines_vals = []

        # Section Abonnement
        lines_vals.append((0, 0, {'display_type': 'line_section', 'name': 'Abonnement'}))

        coeff_pro_historise = self.coeff_pro_periode
        # Majoration PRO appliquée à toute la fourniture — abonnement ET énergie
        # (#67, ADR 0018) ; jamais à la refacturation (pur transit Enedis).
        majoration_pro = 1 + coeff_pro_historise / 100.0
        produit_abo = self.env['souscription.produit'].produit_abonnement(tarif_solidaire)
        prix_abo_journalier = grille.get_prix_abonnement(
            puissance_kva, coeff_pro=coeff_pro_historise, is_solidaire=tarif_solidaire
        )

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
                    'price_unit': prix_abo_journalier,
                },
            )
        )

        # Note TURPE fixe sous l'abonnement
        if self.turpe_fixe > 0:
            lines_vals.append((0, 0, {'display_type': 'line_note', 'name': f'Dont turpe fixe: {self.turpe_fixe:.2f}€'}))

        # Section Énergie
        lines_vals.append((0, 0, {'display_type': 'line_section', 'name': 'Énergie'}))

        # type_tarif historisé typé (#14) : clé de sélection, comparaison directe.
        # Un seul bloc générique, piloté par les cadrans facturés du type de tarif
        # (#74) — Base : un cadran ; HP/HC : toujours les deux, même à 0.
        for cadran in self._CADRANS_FACTURES[type_tarif]:
            produit_energie = self.env['souscription.produit'].produit_energie(cadran, tarif_solidaire)
            prix_cadran = prix_dict.get(produit_energie.id)
            if prix_cadran is None:
                raise UserError(f'Prix non trouvé dans la grille pour le produit : {produit_energie.name}')
            lines_vals.append(
                (
                    0,
                    0,
                    {
                        'product_id': produit_energie.id,
                        'name': produit_energie.name,
                        'quantity': self._quantite_facturee(cadran),
                        'price_unit': prix_cadran * majoration_pro,
                    },
                )
            )

        # Note TURPE variable sous l'énergie
        if self.turpe_variable > 0:
            lines_vals.append(
                (0, 0, {'display_type': 'line_note', 'name': f'Dont turpe variable: {self.turpe_variable:.2f}€'})
            )

        return lines_vals

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
            'index_base': releve.index_base_kwh or 0.0,
            'index_hp': releve.index_hp_kwh or 0.0,
            'index_hc': releve.index_hc_kwh or 0.0,
            'index_hph': releve.index_hph_kwh or 0.0,
            'index_hpb': releve.index_hpb_kwh or 0.0,
            'index_hch': releve.index_hch_kwh or 0.0,
            'index_hcb': releve.index_hcb_kwh or 0.0,
            'releve_externe_id': releve.releve_id,
            'origine': releve.evenement or releve.origine_releve,
        }

    def _creer_facture(self):
        """Émet la facture (``account.move``) de cette période.

        Coquille fine : sélectionne la grille active à la date de fin, compose les
        lignes (``_composer_lignes``) et crée le move en posant ``periode_id``
        (source unique du lien Période ↔ Facture, ADR 0004).
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
