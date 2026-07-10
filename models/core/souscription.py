import logging
from datetime import date, timedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

_logger = logging.getLogger(__name__)


class SouscriptionEtat(models.Model):
    _name = 'souscription.etat'
    _description = 'États de facturation'
    _order = 'sequence'

    name = fields.Char('Nom', required=True)
    sequence = fields.Integer('Ordre', default=10)
    color = fields.Integer('Couleur')


class Souscription(models.Model):
    _name = 'souscription.souscription'
    _description = 'Souscription Électricité'
    # mail.activity.mixin (#89) : porte l'alerte du poll quotidien des affaires
    # Enedis quand la Souscription n'a pas de demande de raccordement liée
    # (saisie manuelle) — sinon l'alerte est portée par la demande.
    _inherit = ['mail.thread', 'mail.activity.mixin', 'portal.mixin']

    name = fields.Char(string='Référence', required=True, copy=False, readonly=True, default='Nouveau')
    partner_id = fields.Many2one('res.partner', string='Souscripteur·trice')
    cotitulaires = fields.Many2many(
        'res.partner',
        'souscription_cotitulaire_rel',
        'souscription_id',
        'partner_id',
        string='Cotitulaires',
        help='Co-titulaires du contrat, au-delà du·de la souscripteur·rice principal·e.',
    )
    active = fields.Boolean(string='Active', default=True)

    # Déclarations contractuelles captées au Raccordement puis recopiées ici à la
    # création (ADR 0016) : la Souscription en est propriétaire, les rapports les
    # lisent sur elle, jamais sur la demande.
    date_validation = fields.Date(
        string='Date de signature',
        help="Date de l'acte d'adhésion (signature électronique) sur support durable.",
    )
    renonce_retractation = fields.Boolean(
        string='Renonce au délai de rétractation',
        default=False,
        help='Le·la souscripteur·rice a demandé une exécution avant la fin du délai '
        'de rétractation de 14 jours et y renonce expressément.',
    )

    date_debut = fields.Date(string='Début de la souscription')
    date_fin = fields.Date(string='Fin de la souscription')
    etat_facturation_id = fields.Many2one('souscription.etat', string='État de facturation', required=True)
    # facture_ids = fields.One2many(
    #     'account.move',
    #     'souscription_id',
    #     string='Factures')
    facture_ids = fields.One2many(
        'account.move', compute='_compute_factures_via_periodes', string='Factures', store=False
    )
    periode_ids = fields.One2many('souscription.periode', 'souscription_id', string='Périodes de facturation')
    refacturation_ids = fields.One2many('souscription.refacturation', 'souscription_id', string='Refacturations')
    consentement_ids = fields.One2many('souscription.consentement', 'souscription_id', string='Journal de consentement')
    # Données métier

    ## Utiles facturation
    pdl = fields.Char(string='pdl')
    lisse = fields.Boolean(string='Lissé', default=False)
    puissance_souscrite = fields.Selection(
        selection=[
            ('3', '3 kVA'),
            ('6', '6 kVA'),
            ('9', '9 kVA'),
            ('12', '12 kVA'),
            ('15', '15 kVA'),
            ('18', '18 kVA'),
            ('24', '24 kVA'),
            ('30', '30 kVA'),
            ('36', '36 kVA'),
        ],
        string='Puissance souscrite (kVA)',
        required=True,
        tracking=True,
    )
    provision_mensuelle_kwh = fields.Float(
        string='Provision mensuelle (kWh)',
        help='Énergie estimée mensuelle à facturer si lissage activé (tarif Base).',
        tracking=True,
    )
    provision_hp_kwh = fields.Float(
        string='Provision HP mensuelle (kWh)',
        help='Énergie estimée mensuelle Heures Pleines si lissage activé (tarif HP/HC).',
        tracking=True,
    )
    provision_hc_kwh = fields.Float(
        string='Provision HC mensuelle (kWh)',
        help='Énergie estimée mensuelle Heures Creuses si lissage activé (tarif HP/HC).',
        tracking=True,
    )
    type_tarif = fields.Selection(
        [('base', 'Base'), ('hphc', 'Heures Pleines / Heures Creuses')],
        default='base',
        string='Type de tarif',
        required=True,
        tracking=True,
    )
    tarif_solidaire = fields.Boolean(string='Tarif solidaire', default=False, tracking=True)

    # Régime de prix (CONTEXT.md « Régime de prix », « Tarif Moulin ») : quel
    # barème s'applique. Orthogonal au Tarif solidaire (isolation comptable) et
    # à la Majoration PRO (surcoût %) : les trois axes se composent librement
    # jusqu'à la ligne de facture. Le Moulin ne change QUE le prix via la
    # Grille — fiscalité et comptes restent ceux du standard (le solidaire, lui,
    # isole comptablement — ADR 0013).
    regime_prix = fields.Selection(
        [('standard', 'Standard'), ('moulin', 'Moulin')],
        string='Régime de prix',
        default='standard',
        required=True,
        tracking=True,
        help='Barème appliqué à cette Souscription. Sélectionne la Grille de '
        'prix par (régime, date) — aucun produit dédié : seul le prix change.',
    )

    # Calendrier de comptage du compteur (cadrans réseau mesurés) — source
    # Configuration Enedis / electricore. Orthogonal au type de tarif facturé
    # (ADR 0005). Détermine le niveau de saisie de l'énergie sur les périodes.
    config_cadrans = fields.Selection(
        [('base', 'Base (mono-index)'), ('hp_hc', 'HP/HC'), ('4_cadrans', '4 cadrans saisonniers')],
        string='Calendrier de comptage',
        help='Cadrans réseau mesurés par le compteur (Configuration Enedis). '
        "Détermine la granularité saisissable de l'énergie, indépendamment "
        'du type de tarif facturé.',
    )

    ## Utiles paiement

    mode_paiement = fields.Selection(
        [
            ('prelevement', 'Prélèvement'),
            ('cheque_energie', 'Chèque énergie'),
            ('monnaie_locale', 'Monnaie locale'),
            ('especes', 'Espèces'),
            ('virement', 'Virement'),
            ('cheque', 'Chèque'),
        ],
        string='Mode de paiement',
        tracking=True,
    )

    # Coefficient PRO personnalisé
    coeff_pro = fields.Float(
        'Majoration PRO (%)',
        default=0.0,
        digits=(5, 2),
        help='Majoration en % appliquée au tarif de base (0% pour les particuliers)',
        tracking=True,
    )
    ## Informations
    ref_compteur = fields.Char(string='Référence compteur')
    numero_depannage = fields.Char(string='Numéro de dépannage')
    # Champ d'atterrissage migration (#106, ADR 0023) : adresse du point de
    # livraison, distincte de l'adresse du·de la souscripteur·rice
    # (`partner_id`) — le PDL peut être ailleurs (locatif, second logement...).
    adresse_pdl = fields.Text(
        string='Adresse du PDL',
        help="Adresse du point de livraison, distincte de l'adresse du·de la souscripteur·rice.",
    )

    # Identité électricore (ADR 0010, ADR 0020 §3, ADR 0021). `ref_situation_contractuelle`
    # est la clé d'articulation du pull de méta-périodes (RSC, unique par couple
    # PDL/usager·ère) ; `id_affaire` est l'amorce de réconciliation (référence
    # d'affaire Enedis, connue tôt et non ambiguë). `id_affaire` est recopié depuis
    # raccordement.demande à la création (#87) ; la RSC est acquise par le poll
    # quotidien ou l'action manuelle (#88/#89) — écriture restreinte au groupe
    # gestionnaire (ADR 0021 §5), c'est l'échappatoire quand Enedis/electricore
    # déraille.
    ref_situation_contractuelle = fields.Char(
        string='RSC (référence situation contractuelle)',
        tracking=True,
        help="Clé d'articulation du pull de méta-périodes electricore, unique par "
        'couple PDL/usager·ère. Non affichée dans SGE : acquise par le poll quotidien '
        'des affaires Enedis, ou saisissable à la main (groupe gestionnaire) quand '
        'le suivi automatique déraille.',
    )
    id_affaire = fields.Char(
        string="N° d'affaire Enedis",
        tracking=True,
        help="Référence d'affaire Enedis, renvoyée dès la demande de raccordement. "
        'Amorce de réconciliation (audit + ré-résolution de la RSC) — recopiée '
        'depuis raccordement.demande à la création, corrigeable ensuite (rattrapage de typo).',
    )
    id_affaire_date_saisie = fields.Date(
        string="Date de saisie de l'id_Affaire",
        help="Date de saisie de l'id_Affaire — recopiée depuis raccordement.demande à la "
        'création, ré-amorcée à chaque correction. Amorce le délai de grâce du poll '
        'quotidien des affaires Enedis (#89).',
    )
    etat = fields.Selection(
        [('en_instance', 'En instance'), ('en_service', 'En service'), ('resiliee', 'Résiliée')],
        string='État',
        compute='_compute_etat',
        store=True,
        tracking=True,
        help='Cycle de vie calculé depuis les faits (ADR 0021), jamais saisi : '
        '*en instance* (RSC absente, non facturable), *en service* (RSC acquise, '
        'facturable), *résiliée* (date de fin passée — logique minimale, chantier '
        'dédié ultérieur). Se corrige par le fait (la RSC), jamais par ce champ.',
    )
    motif_resolution_rsc = fields.Char(
        string='Motif dernière résolution RSC',
        help='Motif renvoyé par electricore (contrat RSC) quand la dernière tentative '
        "de résolution (poll ou manuelle, #88/#89) n'a pas renvoyé de RSC. Effacé dès "
        'que la RSC est résolue.',
    )
    date_derniere_resolution_rsc = fields.Date(
        string='Date de dernière résolution RSC',
        help='Date de la dernière tentative de résolution RSC (#88/#89), succès ou échec.',
    )

    # Une RSC identifie un contrat unique (#15, ADR 0010) : deux souscriptions
    # successives sur un même PDL portent des RSC différentes, et le pull clé
    # sur RSC ne peut pas être ambigu. Les NULL (en instance) ne se gênent pas
    # entre eux (sémantique UNIQUE de Postgres).
    _rsc_unique = models.Constraint(
        'UNIQUE(ref_situation_contractuelle)',
        'Cette RSC est déjà portée par une autre souscription — une RSC identifie un contrat unique.',
    )

    @api.depends('ref_situation_contractuelle', 'date_fin')
    def _compute_etat(self):
        today = fields.Date.context_today(self)
        for sous in self:
            if sous.date_fin and sous.date_fin < today:
                sous.etat = 'resiliee'
            elif sous.ref_situation_contractuelle:
                sous.etat = 'en_service'
            else:
                sous.etat = 'en_instance'

    @api.model
    def souscriptions_concernees(self, mois):
        """Périmètre de campagne (CONTEXT.md « Périmètre de campagne ») : les
        Souscriptions concernées par le mois `M`, par recouvrement de
        l'intervalle de service avec `M` sur les dates propres de la
        Souscription — RSC acquise ET `date_debut <= dernier jour de M` ET
        (`date_fin` vide OU `date_fin >= premier jour de M`).

        Point unique du prédicat : la Campagne (`_souscriptions_facturables`)
        et le wizard ad-hoc de pull le consomment tous les deux, pour ne
        jamais diverger. Historique et figé par le mois — à distinguer de
        `etat == 'en_service'`, un instantané vivant (aujourd'hui), qui
        sur-compte les Souscriptions entrées après `M` et sous-compte celles
        résiliées depuis (ADR 0025)."""
        premier_jour = fields.Date.to_date(mois).replace(day=1)
        premier_jour_suivant = (premier_jour + timedelta(days=31)).replace(day=1)
        dernier_jour = premier_jour_suivant - timedelta(days=1)
        return self.search(
            [
                ('ref_situation_contractuelle', '!=', False),
                ('date_debut', '<=', dernier_jour),
                '|',
                ('date_fin', '=', False),
                ('date_fin', '>=', premier_jour),
            ]
        )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('ref_situation_contractuelle') and not self._peut_ecrire_rsc():
                raise AccessError(self._MESSAGE_RSC_RESTREINTE)
            if vals.get('name', 'Nouveau') == 'Nouveau':
                vals['name'] = self.env['ir.sequence'].next_by_code('souscription.sequence') or 'Nouveau'
            # Amorçage du calendrier de comptage tant qu'electricore ne l'alimente
            # pas (#12) : par défaut aligné sur le type de tarif.
            if not vals.get('config_cadrans'):
                vals['config_cadrans'] = '4_cadrans' if vals.get('type_tarif') == 'hphc' else 'base'
            # id_Affaire saisi/corrigé (#87) : date de saisie auto-stampée, sauf
            # si le vals la fixe explicitement (recopie depuis la demande, tests
            # antidatant la grâce du poll #89).
            if vals.get('id_affaire') and not vals.get('id_affaire_date_saisie'):
                vals['id_affaire_date_saisie'] = fields.Date.context_today(self)
        return super().create(vals_list)

    def _octroyer_acces_portail(self):
        """Donne l'accès portail au·à la souscripteur·trice.

        Odoo ne le fait pas par défaut : un contact n'a aucun login. On réutilise
        le wizard standard « Grant portal access » (crée le user portail + envoie
        l'email d'invitation). Appelé depuis l'onboarding raccordement uniquement
        (`_create_souscription`), pas depuis `create()` — sinon tests, imports et
        synchro electricore déclencheraient des invitations en masse.
        Idempotent : partenaires déjà portail/interne ignorés (`is_portal`/
        `is_internal`), user portail archivé réactivé, sans email ignoré. Un échec
        (email en doublon…) n'annule pas la souscription.
        """
        partners = self.partner_id.filtered('email')
        if not partners:
            return
        wizard = self.env['portal.wizard'].with_context(active_ids=partners.ids).sudo().create({})
        for wu in wizard.user_ids:
            if wu.is_portal or wu.is_internal:
                continue
            try:
                wu.action_grant_access()
            except Exception as e:  # noqa: BLE001 — un souci portail ne bloque pas la souscription
                _logger.warning('Accès portail non octroyé pour %s : %s', wu.partner_id.display_name, e)

    def _compute_access_url(self):
        """URL portail de la souscription (portal.mixin) → route custom."""
        super()._compute_access_url()
        for souscription in self:
            souscription.access_url = f'/my/souscription/{souscription.id}'

    def action_apercu_portail(self):
        """Bouton « Aperçu » : ouvre la page portail du·de la souscripteur·rice
        (URL signée par access_token) sans se connecter en tant que client."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': self.get_portal_url(),
            'target': 'new',
        }

    _MESSAGE_RSC_RESTREINTE = (
        'La RSC (référence situation contractuelle) ne peut être modifiée que par '
        'un·e gestionnaire Souscriptions, ou par la résolution automatique (#88/#89).'
    )

    def _peut_ecrire_rsc(self):
        """Écriture RSC restreinte (#87, ADR 0021 §5) : gestionnaire, ou
        résolution automatique (poll/bouton, #88/#89) via la clé de contexte
        `rsc_automatisme` — la RSC vient alors d'electricore, pas d'une saisie
        manuelle."""
        return bool(self.env.context.get('rsc_automatisme')) or self.env.user.has_group(
            'souscriptions_odoo.group_souscriptions_manager'
        )

    def write(self, vals):
        if 'ref_situation_contractuelle' in vals and not self._peut_ecrire_rsc():
            raise AccessError(self._MESSAGE_RSC_RESTREINTE)
        if vals.get('id_affaire') and 'id_affaire_date_saisie' not in vals:
            vals = dict(vals, id_affaire_date_saisie=fields.Date.context_today(self))

        # RSC nouvellement acquise (#90) : la demande liée avance à « En
        # service » — que la RSC vienne du poll (#89) ou d'une saisie
        # manuelle (#87), l'automatisme s'accroche au fait, pas au canal.
        rsc_avant = (
            {s.id: s.ref_situation_contractuelle for s in self} if 'ref_situation_contractuelle' in vals else None
        )

        res = super().write(vals)

        if rsc_avant is not None:
            nouvellement_resolues = self.filtered(lambda s: s.ref_situation_contractuelle and not rsc_avant.get(s.id))
            nouvellement_resolues._avancer_demande_valide_sge()

        return res

    def _avancer_demande_valide_sge(self):
        """Auto-move (#90, reciblé #100 ADR 0022 §3 — pas de RSC sans C15
        d'effectivité, RSC résolue ≡ validé sur SGE) : la demande liée avance
        à « Validé sur SGE », seulement si elle est encore en amont (jamais
        de recul), avec trace au chatter de la demande."""
        stage = self.env.ref('souscriptions_odoo.stage_valide_sge', raise_if_not_found=False)
        if not stage:
            return
        for sous in self:
            demande = sous._demande_liee()
            if not demande or demande.stage_id.sequence >= stage.sequence:
                continue
            demande.with_context(raccordement_automove=True).stage_id = stage.id
            demande.message_post(
                body=f'Étape avancée automatiquement à « Validé sur SGE » (RSC {sous.ref_situation_contractuelle} acquise).'
            )

    def action_resoudre_rsc_maintenant(self):
        """Bouton « résoudre la RSC maintenant » (#88) : résout la RSC des
        Souscriptions sélectionnées via le service electricore, en un seul
        appel batch même pour une seule Souscription. Idempotent : une
        Souscription déjà *en service* n'est jamais re-ciblée — aucun appel
        si le lot filtré est vide."""
        cibles = self.filtered(lambda s: s.etat != 'en_service')
        if not cibles:
            return
        sans_affaire = cibles.filtered(lambda s: not s.id_affaire)
        if sans_affaire:
            raise UserError(
                f'Impossible de résoudre la RSC : id_Affaire manquant sur : {", ".join(sans_affaire.mapped("name"))}.'
            )
        cibles._resoudre_rsc()

    def _resoudre_rsc(self):
        """Résout `self` en un seul appel batch via le service electricore
        (#88) et applique le mapping des motifs du contrat RSC (xor
        `ref_situation_contractuelle`/`error`) : succès -> RSC écrite
        (bascule *en service* + trace au chatter, #87) ; motif -> stocké
        avec la date de tentative, visible sur la Souscription. Ne filtre
        pas `self` : à l'appelant de ne cibler que ce qui doit l'être
        (idempotence du bouton, ciblage du poll #89)."""
        if not self:
            return
        resultats = self.env['souscription.rsc.service'].resoudre(self.mapped('id_affaire'))
        today = fields.Date.context_today(self)
        for sous in self:
            resultat = resultats.get(sous.id_affaire)
            if resultat is None:
                continue  # ne devrait pas arriver (contrat : une réponse par entrée)
            if resultat.ref_situation_contractuelle:
                sous.with_context(rsc_automatisme=True).write(
                    {'ref_situation_contractuelle': resultat.ref_situation_contractuelle}
                )
                sous.write({'motif_resolution_rsc': False, 'date_derniere_resolution_rsc': today})
                sous.message_post(body=f'RSC résolue par electricore : {resultat.ref_situation_contractuelle}')
            else:
                sous.write({'motif_resolution_rsc': resultat.error, 'date_derniere_resolution_rsc': today})

    # --- Poll quotidien des affaires Enedis (#89, ADR 0021 §3-4) ---

    _DELAI_GRACE_INCONNUE_JOURS = 3
    _ACTIVITY_SUMMARY_RSC = 'Anomalie affaire Enedis (RSC)'

    @api.model
    def _cron_poll_affaires_enedis(self):
        """Cron quotidien : cible les Souscriptions en instance à id_Affaire
        renseigné, non archivées — indépendamment de l'existence d'une
        demande, donc les Souscriptions saisies à la main sont couvertes.
        Un seul appel batch. Échec réseau/service : skip silencieux total
        (aucun état modifié, aucune activité), nouvel essai au poll suivant."""
        cibles = self.search([('etat', '=', 'en_instance'), ('id_affaire', '!=', False), ('active', '=', True)])
        if not cibles:
            return
        try:
            cibles._resoudre_rsc()
        except Exception:
            _logger.warning('Poll RSC : échec réseau/service, nouvel essai au poll suivant.', exc_info=True)
            return
        cibles._appliquer_alertes_rsc()

    def _appliquer_alertes_rsc(self):
        """Mapping des motifs -> alerte (#89, ADR 0021 §4) pour les
        Souscriptions venant d'être poll-ées. *Résolue* : lève toute alerte
        (attente silencieuse). *Connue sans C15* : attente silencieuse,
        c'est l'état normal du suivi. *Inconnue* : tolérée
        `_DELAI_GRACE_INCONNUE_JOURS` jours depuis la saisie de l'id_Affaire,
        puis alerte. *Ambiguë* : alerte immédiate. Une alerte n'est jamais
        recréée tant qu'elle persiste ; elle se lève dès que le motif
        disparaît."""
        today = fields.Date.context_today(self)
        for sous in self:
            if sous.etat == 'en_service':
                sous._lever_alerte_rsc()
                continue
            motif = sous.motif_resolution_rsc or ''
            if motif.startswith('Résolution ambiguë'):
                sous._signaler_alerte_rsc()
            elif motif.startswith('Affaire inconnue'):
                saisie = sous.id_affaire_date_saisie
                en_grace = bool(saisie) and (today - saisie).days <= sous._DELAI_GRACE_INCONNUE_JOURS
                if en_grace:
                    sous._lever_alerte_rsc()
                else:
                    sous._signaler_alerte_rsc()
            else:  # « connue sans C15 » ou motif inattendu : attente silencieuse
                sous._lever_alerte_rsc()

    def _demande_liee(self):
        """La demande de raccordement ayant engendré `self`, s'il y en a une
        (les Souscriptions saisies à la main n'en ont pas)."""
        self.ensure_one()
        return self.env['raccordement.demande'].search([('souscription_id', '=', self.id)], limit=1)

    def _signaler_alerte_rsc(self):
        """Alerte : carte bloquée (demande liée) + une activité unique pour
        l'accueilliste, jamais recréée tant que l'anomalie persiste.
        Souscription sans demande liée -> activité portée par elle-même."""
        self.ensure_one()
        demande = self._demande_liee()
        cible = demande or self
        if demande and demande.kanban_state != 'blocked':
            demande.kanban_state = 'blocked'
        deja_signalee = cible.activity_ids.filtered(lambda a: a.summary == self._ACTIVITY_SUMMARY_RSC)
        if not deja_signalee:
            cible.activity_schedule(
                'mail.mail_activity_data_todo',
                summary=self._ACTIVITY_SUMMARY_RSC,
                note=f"Suivi de l'affaire {self.id_affaire} bloqué : {self.motif_resolution_rsc}",
            )

    def _lever_alerte_rsc(self):
        """Lève l'alerte #89 : débloque la carte de la demande liée et
        retire l'activité de suivi si elles existent (no-op sinon)."""
        self.ensure_one()
        demande = self._demande_liee()
        cible = demande or self
        if demande and demande.kanban_state == 'blocked':
            demande.kanban_state = 'normal'
        cible.activity_ids.filtered(lambda a: a.summary == self._ACTIVITY_SUMMARY_RSC).unlink()

    @api.depends('periode_ids.facture_id')
    def _compute_factures_via_periodes(self):
        for sous in self:
            sous.facture_ids = sous.periode_ids.mapped('facture_id')

    # Cadrans facturés par type de tarif : (code grille, libellé document).
    _CADRANS_DOCUMENTS = {
        'base': [('base', 'Base')],
        'hphc': [('hp', 'Heures pleines'), ('hc', 'Heures creuses')],
    }

    def _provisions_cadrans(self):
        """Provision mensuelle par cadran facturé ('base'/'hp'/'hc') — source
        unique (#73). HP/HC explicites (`provision_hp_kwh`/`provision_hc_kwh`)
        si renseignées, tel que peuplé par le raccordement ; sinon répartition
        70% HP / 30% HC de `provision_mensuelle_kwh`. Consommée par la création
        de Période (snapshot figé, ADR 0006) et par la projection documents
        (ADR 0016) : la règle de répartition ne vit qu'ici.
        """
        self.ensure_one()
        if self.provision_hp_kwh or self.provision_hc_kwh:
            hp, hc = self.provision_hp_kwh, self.provision_hc_kwh
        else:
            hp, hc = self.provision_mensuelle_kwh * 0.7, self.provision_mensuelle_kwh * 0.3
        return {
            'base': self.provision_mensuelle_kwh,
            'hp': hp,
            'hc': hc,
        }

    def _prix_documents(self, a_date=None):
        """Prix engagés à projeter sur les *Conditions particulières* (ADR 0016).

        Résout les tarifs depuis la *Grille de prix* en vigueur à ``a_date``
        (défaut : ``date_debut``) : abonnement de la puissance souscrite et
        énergie des cadrans facturés. Rendus **TTC pour un particulier** (la TVA
        est portée par le *Produit de facturation*), **HT pour une société** —
        choix piloté par ``partner_id.is_company``. Pour un contrat lissé, calcule
        la mensualité estimée. Le rapport ne fait que projeter ce dict, il ne
        recalcule aucun prix (module profond, interface étroite).
        """
        self.ensure_one()
        produit = self.env['souscription.produit']
        a_date = a_date or self.date_debut or fields.Date.today()
        grille = self.env['grille.prix'].get_grille_active(a_date, regime=self.regime_prix)
        is_company = bool(self.partner_id.is_company)
        is_sol = self.tarif_solidaire
        prix_grille = grille.get_prix_dict()

        def affiche(product, montant_ht):
            """HT tel quel pour une société ; TTC via la TVA du produit sinon."""
            if is_company or not product.taxes_id:
                return montant_ht
            taxes = product.taxes_id.compute_all(
                montant_ht,
                currency=self.env.company.currency_id,
                quantity=1.0,
                product=product,
                partner=self.partner_id,
            )
            return taxes['total_included']

        # Majoration PRO appliquée à toute la fourniture — abonnement ET énergie
        # (#67, ADR 0018) ; même facteur que la facture (souscription_periode.py),
        # jamais à la refacturation. L'abonnement l'absorbe via get_prix_abonnement.
        majoration_pro = 1 + self.coeff_pro / 100.0

        # Abonnement (€/an et €/mois) pour la puissance souscrite.
        abo_product = produit.produit_abonnement(is_sol)
        abo_jour_ht = grille.get_prix_abonnement(self.puissance_souscrite, self.coeff_pro, is_sol)
        abo_an = affiche(abo_product, abo_jour_ht * 365.0)
        abo_mois = affiche(abo_product, abo_jour_ht * 365.0 / 12.0)

        # Provision mensuelle par cadran facturé (utilisée pour la mensualité) —
        # source unique _provisions_cadrans() (#73).
        provisions = self._provisions_cadrans()

        energies = []
        mensualite = abo_mois
        for code, libelle in self._CADRANS_DOCUMENTS[self.type_tarif]:
            energie_product = produit.produit_energie(code, is_sol)
            prix_kwh = affiche(energie_product, prix_grille.get(energie_product.id, 0.0) * majoration_pro)
            energies.append({'code': code, 'label': libelle, 'prix_kwh': prix_kwh})
            mensualite += provisions.get(code, 0.0) * prix_kwh

        return {
            'grille': grille,
            'taxe_incluse': not is_company,
            'mention_taxe': 'HT' if is_company else 'TTC',
            'abonnement': {
                'puissance': self.puissance_souscrite,
                'prix_an': abo_an,
                'prix_mois': abo_mois,
            },
            'energies': energies,
            'mensualite': mensualite if self.lisse else 0.0,
        }

    def etat_consentement(self, finalite):
        """État courant d'une finalité de *Consentement* = état de sa **dernière**
        ligne de journal (ADR 0017). Retourne ``'donne'`` / ``'retire'`` / ``False``
        si la finalité n'a jamais été tracée. Source unique pour les rapports et le
        portail (le retrait n'écrase pas, il ajoute une ligne)."""
        self.ensure_one()
        ligne = self.env['souscription.consentement'].search(
            [('souscription_id', '=', self.id), ('finalite', '=', finalite)],
            order='date_consentement desc, id desc',
            limit=1,
        )
        return ligne.etat if ligne else False

    def enregistrer_consentement(self, finalite, etat='donne', source=None, date_retrait=None):
        """Ajoute une ligne au journal de consentement append-only (ne réécrit
        jamais une ligne existante). La version du texte est figée par défaut du
        modèle (intégrité texte ↔ preuve, ADR 0017)."""
        self.ensure_one()
        vals = {
            'souscription_id': self.id,
            'finalite': finalite,
            'etat': etat,
            'source': source,
        }
        if date_retrait:
            vals['date_retrait'] = date_retrait
        return self.env['souscription.consentement'].create(vals)

    def creer_factures(self):
        """Émet les factures des périodes non encore facturées.

        Orchestrateur : pour chaque souscription, boucle sur ses périodes sans
        facture (garde anti-doublon) et délègue l'émission à la période
        (``periode._creer_facture``). La composition des lignes et la création du
        ``account.move`` vivent désormais sur la Période (ADR 0006).

        Une Période d'ouverture (#107) est déjà facturée côté legacy
        (``facture_legacy_ref``) même si elle n'a pas de ``facture_id`` (pas de
        move dans ce système) : l'anti-doublon l'exclut aussi, pour ne jamais
        émettre une seconde facture sur un mois déjà réglé en prod.
        """
        _logger.info(f'Créer factures appelé pour {len(self)} souscriptions')

        for souscription in self:
            if not souscription.partner_id:
                _logger.warning(f'Souscription {souscription.name} sans partenaire, ignorée')
                continue

            premiere_facture = self.env['account.move']
            a_facturer = souscription.periode_ids.filtered(lambda p: not p.facture_id and not p.facture_legacy_ref)
            for periode in a_facturer:
                try:
                    facture = periode._creer_facture()
                    premiere_facture = premiere_facture or facture
                    _logger.info(f'Facture {facture.name} créée pour période {periode.mois_annee}')
                except Exception as e:
                    _logger.error(f'Erreur création facture pour période {periode.mois_annee}: {e}')
                    raise UserError(f'Erreur création facture pour {periode.mois_annee}: {e}')

            # Rassemble les prestations en attente sur la première facture émise
            # ce run, puis les flague (ADR 0009). Le flag les retire de la file,
            # donc les périodes suivantes ne les re-facturent pas.
            if premiere_facture:
                souscription._facturer_refacturations(premiere_facture)

    def _facturer_refacturations(self, facture):
        """Ajoute les prestations *à refacturer* comme lignes de `facture` et
        pose leur `facture_id`. Responsabilité de la Souscription, pas de la
        Période (ADR 0009). Sont *à refacturer* les prestations sans facture et
        non mises en attente : la mise en attente est un opt-out de la
        facturation automatique (ADR 0012)."""
        self.ensure_one()
        prestas = self.refacturation_ids.filtered(lambda p: not p.facture_id and not p.en_attente)
        if not prestas:
            return
        facture.write({'invoice_line_ids': [p._composer_ligne() for p in prestas]})
        prestas.facture_id = facture

    @api.model
    def ajouter_periodes_mensuelles(self):
        """
        Crée une période de facturation (du 1er au dernier jour du mois précédent)
        pour chaque souscription active.
        L'historisation des paramètres se fait automatiquement dans create().
        """
        # Calcul du 1er jour du mois en cours
        premier_mois_courant = date.today().replace(day=1)

        # 1er jour du mois précédent
        premier_mois_precedent = (premier_mois_courant - timedelta(days=1)).replace(day=1)

        souscriptions = self.search([('active', '=', True)])
        periodes_creees = 0

        for souscription in souscriptions:
            # Vérifier qu'une période n'existe pas déjà pour ce mois
            periode_existante = self.env['souscription.periode'].search(
                [
                    ('souscription_id', '=', souscription.id),
                    ('date_debut', '=', premier_mois_precedent),
                    ('date_fin', '=', premier_mois_courant),
                ]
            )

            if not periode_existante:
                self.env['souscription.periode'].create(
                    {
                        'souscription_id': souscription.id,
                        'date_debut': premier_mois_precedent,
                        'date_fin': premier_mois_courant,
                        'type_periode': 'mensuelle',
                        # Les cadrans énergétiques restent à 0 (à remplir via pont externe)
                        'energie_hph_kwh': 0,
                        'energie_hpb_kwh': 0,
                        'energie_hch_kwh': 0,
                        'energie_hcb_kwh': 0,
                        'turpe_fixe': 0,
                        'turpe_variable': 0,
                        # L'historisation se fait automatiquement dans create()
                    }
                )
                periodes_creees += 1

        _logger.info(f'{periodes_creees} périodes créées pour {len(souscriptions)} souscriptions actives')
