import logging
import re

from odoo import api, fields, models
from odoo.addons.base_iban.models.res_partner_bank import validate_iban
from odoo.exceptions import UserError, ValidationError

# Trio ré-exporté par la fabrique (#222/#360, ADR 0024) : la garde de version
# vit désormais dans le client (ContractVersionError), IngestionEnCours et
# PreconditionNonRemplie couvrent le flux R67 absent (typé upstream, #229).
# Importés ici (pas `traduire_exceptions_electricore()`) : ce bouton a un
# mapping propre, distinct de celui des quatre appelants frères — les deux
# premières deviennent une notification non bloquante plutôt qu'une
# UserError, cf. action_estimer_provisions.
from ..core.electricore_client_fabrique import ContractVersionError, IngestionEnCours, PreconditionNonRemplie

_logger = logging.getLogger(__name__)


class RaccordementDemande(models.Model):
    _name = 'raccordement.demande'
    _description = 'Demande de raccordement'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    name = fields.Char(string='Référence', required=True, copy=False, readonly=True, default='Nouveau')

    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', string='Société', required=True, default=lambda self: self.env.company)

    # État kanban
    stage_id = fields.Many2one(
        'raccordement.stage',
        string='Étape',
        group_expand='_read_group_stage_ids',
        tracking=True,
        copy=False,
        ondelete='restrict',
        index=True,
    )
    color = fields.Integer(string='Couleur', related='stage_id.color')
    kanban_state = fields.Selection(
        [('normal', 'En cours'), ('blocked', 'Bloqué'), ('done', 'Prêt')], string='État kanban', default='normal'
    )
    # Visibilité du bouton « Estimer les provisions » (#121) : calculée plutôt
    # que comparée en XML (un many2one ne se compare pas à un xmlid dans une
    # expression de vue) — même idiome que les autres gardes par étape
    # (env.ref) du module, cf. _avancer_demande_valide_sge.
    en_calcul_mensualites = fields.Boolean(
        string="À l'étape « Calcul de mensualités »",
        compute='_compute_en_calcul_mensualites',
        help="Vrai à l'étape « Calcul de mensualités en cours » (#121).",
    )

    # Informations souscription
    pro = fields.Boolean(
        string='Professionnel',
        default=False,
        tracking=True,
        help="Cocher si c'est une demande professionnelle (création d'une société)",
    )
    siret = fields.Char(string='N° SIRET', tracking=True, help="Numéro SIRET de l'entreprise (14 chiffres)")
    # Majoration négociée par le Collège pendant « PRO à valider » (#101,
    # ADR 0022 §7) ; recopiée sur la Souscription à la naissance.
    coeff_pro = fields.Float(
        string='Majoration PRO (%)',
        default=0.0,
        digits=(5, 2),
        tracking=True,
        help='Majoration en % négociée par le Collège pour cette demande PRO — recopiée sur la '
        'Souscription à sa naissance (0% pour les particuliers).',
    )
    pdl = fields.Char(string='PDL', required=True, tracking=True)
    date_debut_souhaitee = fields.Date(string='Date de début souhaitée', required=True, tracking=True)
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
        string='Puissance souscrite',
        required=True,
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

    # Provisions mensuelles
    provision_mensuelle_kwh = fields.Float(
        string='Provision mensuelle (kWh)', help='Énergie estimée mensuelle (tarif Base)', tracking=True
    )
    provision_hp_kwh = fields.Float(
        string='Provision HP mensuelle (kWh)',
        help='Énergie estimée mensuelle Heures Pleines (tarif HP/HC)',
        tracking=True,
    )
    provision_hc_kwh = fields.Float(
        string='Provision HC mensuelle (kWh)',
        help='Énergie estimée mensuelle Heures Creuses (tarif HP/HC)',
        tracking=True,
    )

    # Déclarations contractuelles captées à l'adhésion (équivalent LSD prod),
    # recopiées sur la Souscription à la clôture (ADR 0016).
    cotitulaires = fields.Many2many(
        'res.partner',
        'raccordement_cotitulaire_rel',
        'demande_id',
        'partner_id',
        string='Cotitulaires',
        tracking=True,
        help='Co-titulaires du contrat, au-delà du contact principal.',
    )
    date_validation = fields.Date(
        string='Date de signature',
        tracking=True,
        help="Date de l'acte d'adhésion (signature électronique) sur support durable.",
    )
    renonce_retractation = fields.Boolean(
        string='Renonce au délai de rétractation',
        default=False,
        tracking=True,
        help='Le·la souscripteur·rice demande une exécution avant la fin du délai '
        'de rétractation de 14 jours et y renonce expressément.',
    )

    # Consentement RGPD à la collecte de données fines chez Enedis, par finalité
    # (cases NON pré-cochées, ADR 0017). Saisie back-office = preuve faible :
    # l'acte réel viendra du formulaire public (#62). Une finalité cochée crée une
    # ligne 'donné' dans le journal à la création de la Souscription.
    consent_conso_quotidienne = fields.Boolean(
        string='Consentement — consommations quotidiennes',
        default=False,
        tracking=True,
    )
    consent_courbe_charge = fields.Boolean(
        string='Consentement — courbe de charge',
        default=False,
        tracking=True,
    )

    # Informations contact
    contact_nom = fields.Char(string='Nom', required=True, tracking=True)
    contact_prenom = fields.Char(string='Prénom', tracking=True)
    contact_email = fields.Char(string='Email', required=True, tracking=True)
    contact_telephone = fields.Char(string='Téléphone', tracking=True)
    contact_mobile = fields.Char(string='Mobile', tracking=True)

    # Adresse
    contact_street = fields.Char(string='Rue', required=True)
    contact_street2 = fields.Char(string='Rue 2')
    contact_zip = fields.Char(string='Code postal', required=True)
    contact_city = fields.Char(string='Ville', required=True)
    contact_country_id = fields.Many2one('res.country', string='Pays', default=lambda self: self.env.ref('base.fr'))

    # Informations bancaires
    bank_acc_holder_name = fields.Char(string='Titulaire du compte', tracking=True)
    bank_iban = fields.Char(string='IBAN', tracking=True)
    bank_bic = fields.Char(string='BIC', tracking=True)
    iban_valide = fields.Boolean(string='IBAN validé', compute='_compute_iban_valide', store=True, tracking=True)

    # Mandat SEPA
    sepa_mandate_date = fields.Date(string='Date du mandat SEPA', tracking=True)
    sepa_mandate_ref = fields.Char(string='Référence mandat SEPA', tracking=True)

    # Mode de paiement
    mode_paiement = fields.Selection(
        [
            ('prelevement', 'Prélèvement'),
            ('monnaie_locale', 'Monnaie locale'),
            ('especes', 'Espèces'),
            ('virement', 'Virement'),
            ('cheque', 'Chèque'),
        ],
        string='Mode de paiement',
        default='prelevement',
        tracking=True,
    )

    # Dates de suivi
    date_demande_sge = fields.Date(string='Date demande SGE', tracking=True)
    date_demande_mesures = fields.Date(string='Date demande mesures', tracking=True)
    date_estimation = fields.Date(string='Date estimation', tracking=True)

    # Suivi de l'affaire Enedis (#87, ADR 0021). id_affaire est la référence
    # d'affaire SGE, connue tôt et non ambiguë (ADR 0010) ; sa date de saisie
    # amorce le délai de grâce du poll quotidien (#89) et est recopiée sur la
    # Souscription à la création, comme id_affaire lui-même (ADR 0016).
    id_affaire = fields.Char(string="N° d'affaire Enedis", tracking=True, help='Référence renvoyée dès la demande SGE.')
    id_affaire_date_saisie = fields.Date(
        string="Date de saisie de l'id_Affaire",
        tracking=True,
        help="Date à laquelle l'id_Affaire a été renseigné — amorce le délai de grâce "
        'du poll quotidien des affaires Enedis (#89).',
    )

    # Situation d'entrée (#100, ADR 0021 §4 / ADR 0022 §1 & §4) : voie SGE par
    # laquelle la demande entre dans le périmètre. Requise à la saisie de
    # l'id_Affaire (elle route l'auto-move vers la bonne branche ⏳) ;
    # éditable par l'accueilliste — sa correction re-route une carte déjà en
    # branche vers l'autre branche, jamais de recul.
    situation_entree = fields.Selection(
        [('mes', 'Mise en service (F120)'), ('cfne', 'Changement de fournisseur (F130)')],
        string="Situation d'entrée",
        tracking=True,
        help="Voie SGE d'entrée dans le périmètre : mise en service (F120, PDL hors service) "
        'ou changement de fournisseur (CFNE F130, PDL déjà alimenté). Requise à la saisie de '
        "l'id_Affaire ; sa correction re-route la carte déjà en branche vers l'autre branche.",
    )

    # Champs liés après création
    partner_id = fields.Many2one('res.partner', string='Contact créé', readonly=True, tracking=True)
    partner_bank_id = fields.Many2one('res.partner.bank', string='Compte bancaire créé', readonly=True, tracking=True)
    souscription_id = fields.Many2one(
        'souscription.souscription', string='Souscription créée', readonly=True, tracking=True
    )

    # Notes
    notes = fields.Text(string='Notes')

    _MESSAGE_SITUATION_ENTREE_REQUISE = (
        "La situation d'entrée (mise en service F120 ou changement de fournisseur F130) est "
        "requise pour saisir l'id_Affaire."
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nouveau') == 'Nouveau':
                vals['name'] = self.env['ir.sequence'].next_by_code('raccordement.demande.sequence') or 'Nouveau'
            if vals.get('id_affaire') and not vals.get('situation_entree'):
                raise UserError(self._MESSAGE_SITUATION_ENTREE_REQUISE)
            if vals.get('id_affaire') and not vals.get('id_affaire_date_saisie'):
                vals['id_affaire_date_saisie'] = fields.Date.context_today(self)
        records = super().create(vals_list)
        # Définir l'étape initiale si non définie : routage à la création
        # (#100, ADR 0022 §1) — PRO coché -> « PRO à valider », sinon
        # « Nouveau ».
        for record in records:
            if not record.stage_id:
                record.stage_id = record._get_default_stage_id()
        # id_Affaire déjà renseigné à la création (rare, mais cohérent avec
        # l'auto-move de write(), #90/#100) : avance la carte si elle est en amont.
        records.filtered('id_affaire')._router_situation_entree()
        return records

    def _get_default_stage_id(self):
        """Étape de routage à la création (#100, ADR 0022 §1) : une demande
        PRO naît en « PRO à valider » (décision du Collège) ; une demande
        particulière naît en « Nouveau »."""
        self.ensure_one()
        xmlid = 'souscriptions_odoo.stage_pro_a_valider' if self.pro else 'souscriptions_odoo.stage_nouveau'
        stage = self.env.ref(xmlid, raise_if_not_found=False)
        return stage or self.env['raccordement.stage'].search([], order='sequence', limit=1)

    @api.model
    def _read_group_stage_ids(self, stages, domain):
        """Retourne toutes les étapes pour la vue kanban"""
        # Retourne toutes les étapes dans l'ordre défini
        return stages.search([], order='sequence')

    @api.depends('stage_id')
    def _compute_en_calcul_mensualites(self):
        """Vrai à l'étape « Calcul de mensualités en cours » (#121) — pilote
        la visibilité du bouton « Estimer les provisions »."""
        stage = self.env.ref('souscriptions_odoo.stage_calcul_mensualites', raise_if_not_found=False)
        for record in self:
            record.en_calcul_mensualites = bool(stage) and record.stage_id == stage

    @api.depends('bank_iban')
    def _compute_iban_valide(self):
        """IBAN validé au sens de base_iban (#216, ADR 0022 §2) : même
        vérité que la création du compte bancaire à l'acceptation — plus
        d'algorithme maison susceptible de diverger."""
        for record in self:
            record.iban_valide = self._validate_iban(record.bank_iban)

    def _validate_iban(self, iban):
        """Enveloppe base_iban.validate_iban (ValidationError -> faux) :
        seul point de vérité de l'IBAN, utilisé par le champ calculé et par
        la garde bloquante d'acceptation (#216)."""
        try:
            validate_iban(iban)
            return True
        except ValidationError:
            return False

    @api.constrains('pro', 'siret')
    def _check_siret_required_for_pro(self):
        """Vérifie que le SIRET est renseigné pour les demandes professionnelles"""
        for record in self:
            if record.pro and not record.siret:
                raise ValidationError('Le numéro SIRET est obligatoire pour les demandes professionnelles.')

    @api.constrains('siret')
    def _check_siret_format(self):
        """Valide le format du SIRET (14 chiffres)"""
        for record in self:
            if record.siret:
                # Nettoyer le SIRET (supprimer espaces et caractères non numériques)
                siret_clean = re.sub(r'[^\d]', '', record.siret)
                if len(siret_clean) != 14 or not siret_clean.isdigit():
                    raise ValidationError('Le numéro SIRET doit contenir exactement 14 chiffres.')

    @api.onchange('stage_id')
    def _onchange_stage_id(self):
        """Actions lors du changement d'étape"""
        if self.stage_id:
            # Étape finale (naissance de la Souscription, is_close) : vérifie
            # que les informations nécessaires sont présentes. L'ancienne
            # heuristique par nom (« IBAN validé ») a disparu avec l'étape :
            # la garde IBAN devient un blocage dur au drag d'acceptation
            # (#101), plus un avertissement non bloquant ici.
            if self.stage_id.is_close:
                # Vérifier que toutes les infos nécessaires sont présentes
                missing = []
                if not self.pdl:
                    missing.append('PDL')
                if not self.contact_email:
                    missing.append('Email')
                if not self.bank_iban and self.mode_paiement == 'prelevement':
                    missing.append('IBAN')

                if missing:
                    return {
                        'warning': {
                            'title': 'Informations manquantes',
                            'message': f'Les informations suivantes sont manquantes : {", ".join(missing)}',
                        }
                    }

    def write(self, vals):
        """Override write pour les actions automatiques de base"""
        # Étapes pilotées par les faits (#90, ADR 0021 §5) : le drag-in
        # manuel y est refusé, sauf pour les automatismes du module
        # (contournement de contexte `raccordement_automove`).
        if 'stage_id' in vals and not self.env.context.get('raccordement_automove'):
            self._verifier_pas_de_drag_in_factuel(vals['stage_id'])
        if 'stage_id' in vals:
            self._verifier_garde_iban_acceptation(vals['stage_id'])

        # id_Affaire saisi/corrigé : la situation d'entrée est requise (#100,
        # ADR 0022 §4) — elle route l'auto-move vers la bonne branche ⏳.
        if vals.get('id_affaire'):
            for record in self:
                if not vals.get('situation_entree', record.situation_entree):
                    raise UserError(self._MESSAGE_SITUATION_ENTREE_REQUISE)

        # id_Affaire saisi/corrigé (#87) : date de saisie auto-stampée, sauf
        # si le vals la fixe explicitement (rattrapage de typo, tests
        # antidatant la grâce du poll #89).
        if vals.get('id_affaire') and 'id_affaire_date_saisie' not in vals:
            vals = dict(vals, id_affaire_date_saisie=fields.Date.context_today(self))

        # Stage avant écriture (#103) : seule une transition *effective* vers
        # « Abonnement Validé » envoie le pack de bienvenue — une
        # ré-écriture sans changement n'en envoie pas un second.
        stage_avant = {r.id: r.stage_id.id for r in self} if 'stage_id' in vals else None

        res = super().write(vals)

        # Si on change l'étape
        if 'stage_id' in vals:
            for record in self:
                # Si on passe à l'étape finale et qu'on n'a pas encore créé les entrées
                if record.stage_id.is_close and not record.souscription_id:
                    record._create_odoo_entries()

            stage_abonnement_valide = self.env.ref(
                'souscriptions_odoo.stage_abonnement_valide', raise_if_not_found=False
            )
            if stage_abonnement_valide:
                for record in self:
                    if (
                        record.stage_id == stage_abonnement_valide
                        and stage_avant.get(record.id) != stage_abonnement_valide.id
                    ):
                        record._envoyer_pack_bienvenue()

        # id_Affaire saisi ou situation_entree corrigée (#90/#100) : la carte
        # avance seule vers la branche ⏳ désignée, ou re-route latéralement
        # une carte déjà en branche — jamais en aval (pas de recul).
        if 'id_affaire' in vals or 'situation_entree' in vals:
            self._router_situation_entree()

        # Write-through post-naissance (#101, ADR 0022 §2) : une fois la
        # Souscription née, la saisie ou correction de l'id_Affaire sur la
        # demande se propage à la Souscription liée, avec sa date de saisie
        # (elle amorce la grâce du poll #89). La RSC et l'état restent portés
        # par la Souscription — la carte ne fait que refléter.
        if 'id_affaire' in vals:
            for record in self:
                if record.souscription_id and record.id_affaire:
                    record.souscription_id.write(
                        {
                            'id_affaire': record.id_affaire,
                            'id_affaire_date_saisie': record.id_affaire_date_saisie,
                        }
                    )

        return res

    def _verifier_pas_de_drag_in_factuel(self, nouveau_stage_id):
        """Refuse le drag-in manuel vers une étape pilotée par un fait
        (#90) : on corrige le fait, la carte suit — jamais l'inverse. Ne
        s'applique qu'aux demandes qui *changent* réellement d'étape : une
        ré-écriture sans changement (resync des données, module upgrade) ne
        déclenche pas la garde."""
        nouveau_stage = self.env['raccordement.stage'].browse(nouveau_stage_id)
        if not nouveau_stage.entree_factuelle:
            return
        deplacees = self.filtered(lambda r: r.stage_id.id != nouveau_stage_id)
        if deplacees:
            raise UserError(
                f'« {nouveau_stage.name} » est une étape pilotée par un fait : elle ne se force pas à la '
                'main. Corrigez le fait (id_Affaire saisi, RSC acquise) — la carte suivra automatiquement.'
            )

    def _verifier_garde_iban_acceptation(self, nouveau_stage_id):
        """Garde bloquante IBAN (#101, ADR 0022 §2) : le drag vers l'étape de
        naissance (is_close) est refusé si le mode de paiement est le
        prélèvement et l'IBAN invalide — la colonne « IBAN vérifié » ne ment
        jamais. Remplace l'ancien avertissement non bloquant (onchange),
        disparu avec l'étape qui le portait (#100). Vérifiée avant l'écriture
        (comme la garde factuelle) pour qu'un refus n'altère pas l'étape."""
        nouveau_stage = self.env['raccordement.stage'].browse(nouveau_stage_id)
        if not nouveau_stage.is_close:
            return
        cible = self.filtered(lambda r: not r.souscription_id and r.stage_id.id != nouveau_stage_id)
        for record in cible:
            if record.mode_paiement == 'prelevement' and not record._validate_iban(record.bank_iban):
                raise UserError(
                    "Impossible d'accepter la demande : le mode de paiement est le prélèvement et "
                    "l'IBAN est invalide. Corrigez l'IBAN avant d'accepter."
                )

    # Branches ⏳ ciblées par situation_entree (#100, ADR 0022 §1/§4), et
    # leur mail de rassurage associé (#102, ADR 0022 §6).
    _STAGE_XMLID_PAR_SITUATION = {
        'mes': 'souscriptions_odoo.stage_f120_mes',
        'cfne': 'souscriptions_odoo.stage_f130_cfne',
    }
    _TEMPLATE_XMLID_PAR_SITUATION = {
        'mes': 'souscriptions_odoo.mail_template_raccordement_f120',
        'cfne': 'souscriptions_odoo.mail_template_raccordement_f130',
    }

    def _stage_branche_cible(self):
        """L'étape ⏳ désignée par situation_entree, ou vide si absente/non
        configurée."""
        self.ensure_one()
        xmlid = self._STAGE_XMLID_PAR_SITUATION.get(self.situation_entree)
        return self.env.ref(xmlid, raise_if_not_found=False) if xmlid else self.env['raccordement.stage']

    def _stages_branches_sge(self):
        """Les deux étapes ⏳ (branches F120/F130), pour distinguer un
        re-routage latéral d'un avancement amont->branche."""
        stage_f120 = self.env.ref('souscriptions_odoo.stage_f120_mes', raise_if_not_found=False)
        stage_f130 = self.env.ref('souscriptions_odoo.stage_f130_cfne', raise_if_not_found=False)
        return (stage_f120 or self.env['raccordement.stage']) | (stage_f130 or self.env['raccordement.stage'])

    def _router_situation_entree(self):
        """Route la carte vers la branche ⏳ désignée par situation_entree
        (#100, ADR 0021 §5 / ADR 0022 §1 & §4) :

        - en amont des branches (id_Affaire tout juste saisi) : avance seule
          vers la branche demandée ;
        - déjà dans une branche : une correction de situation_entree bascule
          latéralement vers l'autre branche (ni avancement, ni recul) ;
        - en aval des branches (Validé sur SGE et au-delà) : aucun effet — on
          ne recule jamais une carte déjà instruite côté Enedis.

        Chaque entrée effective (initiale ou re-routée) envoie le mail de
        rassurage (#102) de la branche d'arrivée : c'est le moment où la
        demande SGE part réellement chez Enedis.
        """
        branches = self._stages_branches_sge()
        for record in self:
            if not record.id_affaire or not record.situation_entree:
                continue
            cible = record._stage_branche_cible()
            if not cible or record.stage_id == cible:
                continue
            en_branche = record.stage_id in branches
            en_amont = record.stage_id.sequence < cible.sequence
            if en_branche or en_amont:
                record.with_context(raccordement_automove=True).stage_id = cible.id
                record._envoyer_mail_rassurage()

    def _envoyer_mail_rassurage(self):
        """Mail de rassurage (#102, ADR 0022 §6) à l'entrée effective d'une
        branche ⏳ — accusé de prise en compte, un template par situation
        d'entrée. Le re-routage F120<->F130 envoie le mail de la branche
        d'arrivée (même seuil d'appel que l'avancement initial,
        `_router_situation_entree`)."""
        self.ensure_one()
        xmlid = self._TEMPLATE_XMLID_PAR_SITUATION.get(self.situation_entree)
        template = self.env.ref(xmlid, raise_if_not_found=False) if xmlid else False
        if template:
            template.send_mail(self.id, force_send=False)

    # Variante du pack de bienvenue (#103, ADR 0022 §6) par faits de la
    # demande : PRO, sinon solidaire, sinon particulier.
    _TEMPLATE_XMLID_BIENVENUE_PRO = 'souscriptions_odoo.mail_template_bienvenue_pro'
    _TEMPLATE_XMLID_BIENVENUE_SOLIDAIRE = 'souscriptions_odoo.mail_template_bienvenue_solidaire'
    _TEMPLATE_XMLID_BIENVENUE_PARTICULIER = 'souscriptions_odoo.mail_template_bienvenue_particulier'

    def _envoyer_pack_bienvenue(self):
        """Pack de bienvenue (#103, ADR 0022 §6) à l'entrée effective en
        « Abonnement Validé » : conditions particulières complètes (RSC +
        mensualités réelles) en pièce jointe (`report_template_ids` du
        template, rendu pour la Souscription) + documents d'accueil
        statiques configurables (`attachment_ids` du template). Variante
        choisie par les faits de la demande ; no-op si la Souscription
        n'existe pas (rien à joindre, rien à notifier)."""
        self.ensure_one()
        if not self.souscription_id:
            return
        if self.pro:
            xmlid = self._TEMPLATE_XMLID_BIENVENUE_PRO
        elif self.tarif_solidaire:
            xmlid = self._TEMPLATE_XMLID_BIENVENUE_SOLIDAIRE
        else:
            xmlid = self._TEMPLATE_XMLID_BIENVENUE_PARTICULIER
        template = self.env.ref(xmlid, raise_if_not_found=False)
        if template:
            template.send_mail(self.souscription_id.id, force_send=False)

    def _create_odoo_entries(self):
        """Orchestration mince de l'acceptation (#218, PRD #215 tranche 3/3) :
        crée le contact (dédup email inchangée), la banque et le mandat SEPA
        en prélèvement, fait naître la Souscription — tous les invariants de
        naissance (mapping, provisions, actes...) vivent désormais sur
        `souscription.souscription.naitre_depuis_demande` — puis lie et trace
        au chatter.

        Plus de `try/except` nu : une erreur (journal SDD absent, IBAN
        refusé, échec de naissance...) remonte **typée, avec son message
        d'origine** — la transaction du write qui a déclenché cette méthode
        annule tout, la carte ne bouge pas, rien de semi-né.
        """
        self.ensure_one()

        # 1. Créer le contact
        partner = self._create_partner()
        self.partner_id = partner

        # 2. Créer le compte bancaire si nécessaire, puis le mandat SEPA
        # (#187) : la garde IBAN (_verifier_garde_iban_acceptation,
        # exécutée avant l'écriture qui déclenche _create_odoo_entries)
        # garantit déjà un IBAN valide ici en mode prélèvement.
        if self.bank_iban and self.mode_paiement == 'prelevement':
            partner_bank = self._create_partner_bank(partner)
            self.partner_bank_id = partner_bank
            self._creer_mandat_sepa(partner_bank)

        # 3. Faire naître la souscription (#218)
        souscription = self.env['souscription.souscription'].naitre_depuis_demande(self)
        self.souscription_id = souscription

        # Message de succès
        self.message_post(
            body=f"""Entrées Odoo créées avec succès :
            - Contact : {partner.name} (ID: {partner.id})
            - Souscription : {souscription.name} (ID: {souscription.id})
            """
        )

    def _create_partner(self):
        """Crée un contact res.partner (particulier ou société selon le champ pro)"""
        if self.pro:
            # Demande professionnelle : créer une société
            partner_vals = {
                'name': self.contact_nom,  # Nom de la société
                'email': self.contact_email,
                'phone': self.contact_telephone or self.contact_mobile,
                'street': self.contact_street,
                'street2': self.contact_street2,
                'zip': self.contact_zip,
                'city': self.contact_city,
                'country_id': self.contact_country_id.id,
                'is_company': True,  # C'est une société
            }

            # Ajouter le SIRET si renseigné et si le champ existe sur res.partner
            if self.siret:
                if 'siret' in self.env['res.partner']._fields:
                    partner_vals['siret'] = self.siret
                else:
                    _logger.warning(
                        'Champ SIRET non disponible sur res.partner. Installez le module l10n_fr pour activer cette fonctionnalité.'
                    )
        else:
            # Demande particulière : créer un contact individuel
            partner_vals = {
                'name': f'{self.contact_prenom} {self.contact_nom}' if self.contact_prenom else self.contact_nom,
                'email': self.contact_email,
                'phone': self.contact_telephone or self.contact_mobile,
                'street': self.contact_street,
                'street2': self.contact_street2,
                'zip': self.contact_zip,
                'city': self.contact_city,
                'country_id': self.contact_country_id.id,
                'is_company': False,  # C'est un particulier
            }

        # Vérifier si un contact existe déjà avec cet email : recherche
        # insensible à la casse (=ilike), restreinte aux partners actifs et de
        # même nature (société/particulier) que la demande. Sans ce filtre sur
        # is_company, une demande PRO pourrait retomber sur un particulier
        # existant et écraser son identité (et inversement).
        existing_partner = self.env['res.partner'].search(
            [('email', '=ilike', self.contact_email), ('is_company', '=', self.pro)], limit=1
        )

        if existing_partner:
            # Réutiliser le contact existant sans écraser son identité (nom,
            # adresse, is_company...) : seule la demande est tracée, le
            # contact n'est pas modifié.
            self.message_post(
                body=f'Contact existant réutilisé : {existing_partner.name} (ID: {existing_partner.id}), '
                'identité non modifiée.'
            )
            return existing_partner
        else:
            # Créer un nouveau contact
            return self.env['res.partner'].create(partner_vals)

    def _create_partner_bank(self, partner):
        """Crée un compte bancaire res.partner.bank"""
        bank_vals = {
            'partner_id': partner.id,
            'acc_number': self.bank_iban,
            'acc_holder_name': self.bank_acc_holder_name or partner.name,
        }

        # Chercher la banque par BIC si fourni
        if self.bank_bic:
            bank = self.env['res.bank'].search([('bic', '=', self.bank_bic)], limit=1)
            if bank:
                bank_vals['bank_id'] = bank.id

        return self.env['res.partner.bank'].create(bank_vals)

    # --- Pont vers le mandat SEPA (#217, PRD #215 tranche 2/3) ---
    #
    # La création du mandat (garde registre `sdd.mandate`, résolution du
    # journal SDD, construction des valeurs) vit désormais dans le service
    # `souscription.sepa.mandat` (models/core/souscription_sepa_mandat.py,
    # ex-#187) : la demande n'a plus de logique mandat propre, elle appelle,
    # recopie le RUM retourné et trace au chatter.

    def _creer_mandat_sepa(self, partner_bank):
        """Appelle le service SEPA mandat (#217) à l'acceptation d'une
        demande en mode prélèvement — l'acceptation est la porte humaine
        (IBAN vérifié par _verifier_garde_iban_acceptation, mandat signé
        exigé côté saisie) : pas de second circuit de validation (CONTEXT.md
        « Mandat de prélèvement »). No-op silencieux si le service retourne
        `None` (`sdd.mandate` absent du registre, Community/CI) : le reste
        de l'acceptation se déroule à l'identique."""
        self.ensure_one()
        mandat = self.env['souscription.sepa.mandat'].creer(
            partner_bank, date_signature=self.sepa_mandate_date, rum=self.sepa_mandate_ref
        )
        if not mandat:
            return
        # Traçable depuis la demande sans nouveau champ relationnel vers un
        # modèle absent en Community (un Many2one déclaré ici casserait
        # l'install Community à l'_auto_init) : on recopie la référence
        # (RUM, saisie ou générée par l'outillage) sur le champ existant, et
        # on trace le rattachement au chatter.
        self.sepa_mandate_ref = mandat.name
        self.message_post(body=f'Mandat SEPA créé et actif (RUM : {mandat.name}).')

    # --- Estimation des provisions (#121, `provision_estimation`, #229) ---
    #
    # Bouton seulement, pas d'auto-déclenchement au drag kanban : un appel
    # réseau dans write() bloquerait la transaction du drag-and-drop — le
    # bouton suffit (l'AC de l'issue accepte « bouton, et/ou auto »).

    def action_estimer_provisions(self):
        """Bouton « Estimer les provisions » (visible à l'étape « Calcul de
        mensualités en cours ») : interroge electricore
        (`client.provision_estimation(pdl)`) et pré-remplit les provisions
        selon le tarif. L'humain garde la main — les champs restent éditables
        — et l'absence de données (trouve=False, flux R67 indisponible)
        n'empêche jamais la saisie manuelle : c'est le chemin normal.

        Mapping d'exceptions (#229, trio ré-exporté par la fabrique) :
        `IngestionEnCours`/`PreconditionNonRemplie` (flux R67 absent, typé
        upstream) -> notification non bloquante + chatter (même
        comportement que l'ancien 503, plus précis) ; `ContractVersionError`
        -> `UserError` (la garde de version vit dans le client) ; tout le
        reste (réseau coupé, 500 inattendu) remonte tel quel — plus
        d'enveloppe `UserError` générique."""
        self.ensure_one()
        client = self.env['souscription.electricore.client'].client()  # fast-fail paquet+config (ADR 0024)
        try:
            reponse = self._appeler_estimation(client, self.pdl)
        except (IngestionEnCours, PreconditionNonRemplie) as exc:
            return self._notifier_estimation_indisponible(exc)
        except ContractVersionError as exc:
            raise UserError(
                f"Version de contrat electricore inattendue pour l'estimation des provisions : {exc}"
            ) from exc

        if not reponse.get('trouve'):
            self.message_post(
                body='Aucune mesure R67 dans la fenêtre de 12 mois : estimation impossible, saisie manuelle.'
            )
            return

        self._appliquer_estimation(reponse['estimation'])

    def _appeler_estimation(self, client, pdl):
        """Point de transport unique : passe-plat vers
        `client.provision_estimation(pdl)` (`electricore-client` 0.5.0,
        #229) — couture patchée en tests, réponse en boîte, rien d'autre
        n'est mocké."""
        return client.provision_estimation(pdl)

    def _notifier_estimation_indisponible(self, exc):
        """`IngestionEnCours`/`PreconditionNonRemplie` (#229) = état
        opérationnel attendu (flux R67 non matérialisé — M023 pas encore
        ingérée sur le portail SGE — ou ingestion en cours) : jamais une
        UserError. Tracé au chatter comme information opérationnelle, et
        notification non bloquante côté utilisateur."""
        self.ensure_one()
        message = str(exc) or (
            'Flux R67 non disponible pour ce PDL (mesures pas encore ingérées, ou ingestion en cours) : '
            'réessayez plus tard, ou saisissez les provisions à la main.'
        )
        self.message_post(body=f'Estimation des provisions indisponible : {message}')
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Estimation des provisions indisponible',
                'message': message,
                'type': 'warning',
                'sticky': False,
            },
        }

    def _appliquer_estimation(self, estimation):
        """Pré-remplit les provisions selon le tarif à partir de l'estimation
        electricore — en kWh, zéro € (la valorisation reste côté grille de
        prix) — puis trace un unique message chatter récapitulatif (pas de
        spam). Profondeur HP/HC insuffisante (champs null, ou
        `profondeur_cadran == 'base'`) sur un tarif HP/HC : ne remplit rien,
        repli manuel signalé au chatter."""
        self.ensure_one()
        if self.type_tarif == 'base':
            vals = {'provision_mensuelle_kwh': estimation.get('energie_base_mensuel_kwh') or 0.0}
        else:  # hphc
            hp = estimation.get('energie_hp_mensuel_kwh')
            hc = estimation.get('energie_hc_mensuel_kwh')
            if hp is None or hc is None or estimation.get('profondeur_cadran') == 'base':
                self.message_post(
                    body='Estimation electricore insuffisamment détaillée (profondeur HP/HC absente) : '
                    'aucune provision pré-remplie, saisie manuelle nécessaire.'
                )
                return
            vals = {'provision_hp_kwh': hp, 'provision_hc_kwh': hc}

        self.write(vals)
        self.message_post(body=self._message_recapitulatif_estimation(estimation, vals))

    @staticmethod
    def _message_recapitulatif_estimation(estimation, vals):
        """Résumé chatter (un seul post par clic, pas de spam) : valeurs
        pré-remplies, couverture, profondeur, qualité, alerte éventuelle."""
        lignes = ['Estimation des provisions (electricore) :']
        if 'provision_mensuelle_kwh' in vals:
            lignes.append(f'- Provision mensuelle (Base) : {vals["provision_mensuelle_kwh"]:.1f} kWh')
        if 'provision_hp_kwh' in vals:
            lignes.append(f'- Provision HP mensuelle : {vals["provision_hp_kwh"]:.1f} kWh')
            lignes.append(f'- Provision HC mensuelle : {vals["provision_hc_kwh"]:.1f} kWh')
        suffisante = 'suffisante' if estimation.get('couverture_suffisante') else 'insuffisante'
        lignes.append(
            f'- Couverture : {estimation.get("couverture_mois")} mois, '
            f'{estimation.get("couverture_debut")} → {estimation.get("couverture_fin")} ({suffisante})'
        )
        lignes.append(f'- Profondeur : {estimation.get("profondeur_cadran")}')
        lignes.append(f'- Qualité : {estimation.get("qualite")}')
        if estimation.get('signal_alertable'):
            lignes.append('⚠️ Signal alertable : estimation à vérifier avant validation.')
        return '\n'.join(lignes)
