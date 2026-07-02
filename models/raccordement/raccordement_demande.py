import logging
import re

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

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
            ('cheque_energie', 'Chèque énergie'),
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

    @api.depends('bank_iban')
    def _compute_iban_valide(self):
        """Valide le format de l'IBAN"""
        for record in self:
            record.iban_valide = self._validate_iban(record.bank_iban)

    def _validate_iban(self, iban):
        """Validation complète du format IBAN avec vérification modulo 97"""
        if not iban:
            return False

        # Nettoyer l'IBAN
        iban = re.sub(r'\s', '', iban.upper())

        # Vérifier la longueur minimale
        if len(iban) < 15:
            return False

        # Vérifier le format de base (2 lettres + 2 chiffres + reste)
        if not re.match(r'^[A-Z]{2}[0-9]{2}[A-Z0-9]+$', iban):
            return False

        # Vérification modulo 97 (norme ISO 13616)
        return self._check_iban_modulo(iban)

    def _check_iban_modulo(self, iban):
        """Vérifie la validité IBAN selon l'algorithme modulo 97"""
        # Déplacer les 4 premiers caractères à la fin
        rearranged = iban[4:] + iban[:4]

        # Convertir les lettres en chiffres (A=10, B=11, ..., Z=35)
        numeric_string = ''
        for char in rearranged:
            if char.isdigit():
                numeric_string += char
            else:
                # A=10, B=11, ..., Z=35
                numeric_string += str(ord(char) - ord('A') + 10)

        # Calculer le modulo 97
        try:
            remainder = int(numeric_string) % 97
            return remainder == 1
        except ValueError:
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

        res = super().write(vals)

        # Si on change l'étape
        if 'stage_id' in vals:
            for record in self:
                # Si on passe à l'étape finale et qu'on n'a pas encore créé les entrées
                if record.stage_id.is_close and not record.souscription_id:
                    record._create_odoo_entries()

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

    # Branches ⏳ ciblées par situation_entree (#100, ADR 0022 §1/§4).
    _STAGE_XMLID_PAR_SITUATION = {
        'mes': 'souscriptions_odoo.stage_f120_mes',
        'cfne': 'souscriptions_odoo.stage_f130_cfne',
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

    def _create_odoo_entries(self):
        """Crée automatiquement les entrées Odoo (contact, banque, souscription)"""
        self.ensure_one()

        try:
            # 1. Créer le contact
            partner = self._create_partner()
            self.partner_id = partner

            # 2. Créer le compte bancaire si nécessaire
            if self.bank_iban and self.mode_paiement == 'prelevement':
                partner_bank = self._create_partner_bank(partner)
                self.partner_bank_id = partner_bank

            # 3. Créer la souscription
            souscription = self._create_souscription(partner)
            self.souscription_id = souscription

            # Message de succès
            self.message_post(
                body=f"""Entrées Odoo créées avec succès :
                - Contact : {partner.name} (ID: {partner.id})
                - Souscription : {souscription.name} (ID: {souscription.id})
                """
            )

        except Exception as e:
            _logger.error(f'Erreur lors de la création des entrées Odoo : {e}')
            raise UserError(f'Erreur lors de la création des entrées : {str(e)}')

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

    def _create_souscription(self, partner):
        """Crée une souscription"""
        souscription_vals = {
            'partner_id': partner.id,
            'pdl': self.pdl,
            'date_debut': self.date_debut_souhaitee,
            'puissance_souscrite': self.puissance_souscrite,
            'type_tarif': self.type_tarif,
            'tarif_solidaire': self.tarif_solidaire,
            'mode_paiement': self.mode_paiement,
            'lisse': True,  # Activer le lissage par défaut
            # Déclarations contractuelles captées à l'adhésion → la Souscription
            # en devient propriétaire (ADR 0016).
            'date_validation': self.date_validation,
            'renonce_retractation': self.renonce_retractation,
            'cotitulaires': [(6, 0, self.cotitulaires.ids)],
            # Identité electricore (ADR 0010/0021) : id_Affaire recopié comme
            # amorce de réconciliation, avec sa date de saisie (grâce du poll #89).
            'id_affaire': self.id_affaire,
            'id_affaire_date_saisie': self.id_affaire_date_saisie,
            # Majoration PRO négociée par le Collège (#101, ADR 0022 §7).
            'coeff_pro': self.coeff_pro,
        }

        # Ajouter les provisions selon le type de tarif
        if self.type_tarif == 'base':
            souscription_vals['provision_mensuelle_kwh'] = self.provision_mensuelle_kwh
        else:  # HP/HC
            souscription_vals['provision_hp_kwh'] = self.provision_hp_kwh
            souscription_vals['provision_hc_kwh'] = self.provision_hc_kwh

        # Définir l'état de facturation initial
        etat_initial = self.env['souscription.etat'].search([], order='sequence', limit=1)
        if etat_initial:
            souscription_vals['etat_facturation_id'] = etat_initial.id

        souscription = self.env['souscription.souscription'].create(souscription_vals)

        # Journal de consentement (ADR 0017) : une finalité cochée = un acte
        # 'donné'. Capture back-office (preuve faible), tracée comme telle ; l'acte
        # réel du·de la souscripteur·rice viendra du formulaire public (#62).
        source = f'Raccordement {self.name} (back-office)'
        if self.consent_conso_quotidienne:
            souscription.enregistrer_consentement('conso_quotidienne', source=source)
        if self.consent_courbe_charge:
            souscription.enregistrer_consentement('courbe_charge', source=source)

        return souscription
