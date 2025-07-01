from odoo import models, fields, api
from odoo.exceptions import UserError
import re
from datetime import date

import logging
_logger = logging.getLogger(__name__)

class RaccordementDemande(models.Model):
    _name = 'raccordement.demande'
    _description = 'Demande de raccordement'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'
    
    name = fields.Char(
        string='Référence',
        required=True,
        copy=False,
        readonly=True,
        default='Nouveau'
    )
    
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company',
        string='Société',
        required=True,
        default=lambda self: self.env.company
    )
    
    # État kanban
    stage_id = fields.Many2one(
        'raccordement.stage',
        string='Étape',
        group_expand='_read_group_stage_ids',
        tracking=True,
        copy=False,
        ondelete='restrict',
        index=True
    )
    color = fields.Integer(string='Couleur', related='stage_id.color')
    kanban_state = fields.Selection([
        ('normal', 'En cours'),
        ('blocked', 'Bloqué'),
        ('done', 'Prêt')
    ], string='État kanban', default='normal')
    
    # Informations souscription
    pdl = fields.Char(string='PDL', required=True, tracking=True)
    date_debut_souhaitee = fields.Date(
        string='Date de début souhaitée',
        required=True,
        tracking=True
    )
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
        tracking=True
    )
    type_tarif = fields.Selection(
        [('base', 'Base'), ('hphc', 'Heures Pleines / Heures Creuses')],
        default='base',
        string='Type de tarif',
        required=True,
        tracking=True
    )
    tarif_solidaire = fields.Boolean(
        string='Tarif solidaire',
        default=False,
        tracking=True
    )
    
    # Provisions mensuelles
    provision_mensuelle_kwh = fields.Float(
        string="Provision mensuelle (kWh)",
        help="Énergie estimée mensuelle (tarif Base)",
        tracking=True
    )
    provision_hp_kwh = fields.Float(
        string="Provision HP mensuelle (kWh)",
        help="Énergie estimée mensuelle Heures Pleines (tarif HP/HC)",
        tracking=True
    )
    provision_hc_kwh = fields.Float(
        string="Provision HC mensuelle (kWh)",
        help="Énergie estimée mensuelle Heures Creuses (tarif HP/HC)",
        tracking=True
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
    contact_country_id = fields.Many2one(
        'res.country',
        string='Pays',
        default=lambda self: self.env.ref('base.fr')
    )
    
    # Informations bancaires
    bank_acc_holder_name = fields.Char(
        string='Titulaire du compte',
        tracking=True
    )
    bank_iban = fields.Char(string='IBAN', tracking=True)
    bank_bic = fields.Char(string='BIC', tracking=True)
    iban_valide = fields.Boolean(
        string='IBAN validé',
        compute='_compute_iban_valide',
        store=True,
        tracking=True
    )
    
    # Mandat SEPA
    sepa_mandate_date = fields.Date(string='Date du mandat SEPA', tracking=True)
    sepa_mandate_ref = fields.Char(string='Référence mandat SEPA', tracking=True)
    
    # Mode de paiement
    mode_paiement = fields.Selection([
        ('prelevement', 'Prélèvement'),
        ('cheque_energie', 'Chèque énergie'),
        ('monnaie_locale', 'Monnaie locale'),
        ('especes', 'Espèces'),
        ('virement', 'Virement'),
        ('cheque', 'Chèque'),
    ], string="Mode de paiement", default='prelevement', tracking=True)
    
    # Dates de suivi
    date_demande_sge = fields.Date(string='Date demande SGE', tracking=True)
    date_demande_mesures = fields.Date(string='Date demande mesures', tracking=True)
    date_estimation = fields.Date(string='Date estimation', tracking=True)
    
    # Champs liés après création
    partner_id = fields.Many2one(
        'res.partner',
        string='Contact créé',
        readonly=True,
        tracking=True
    )
    partner_bank_id = fields.Many2one(
        'res.partner.bank',
        string='Compte bancaire créé',
        readonly=True,
        tracking=True
    )
    souscription_id = fields.Many2one(
        'souscription.souscription',
        string='Souscription créée',
        readonly=True,
        tracking=True
    )
    
    # Notes
    notes = fields.Text(string='Notes')
    
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nouveau') == 'Nouveau':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'raccordement.demande.sequence'
                ) or 'Nouveau'
        records = super().create(vals_list)
        # Définir l'étape initiale si non définie
        for record in records:
            if not record.stage_id:
                record.stage_id = self._get_default_stage_id()
        return records
    
    @api.model
    def _get_default_stage_id(self):
        """Retourne la première étape par défaut"""
        return self.env['raccordement.stage'].search([], order='sequence', limit=1)
    
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
    
    @api.onchange('stage_id')
    def _onchange_stage_id(self):
        """Actions lors du changement d'étape"""
        if self.stage_id:
            # Si on passe à l'étape "IBAN validé"
            if 'iban' in self.stage_id.name.lower() and 'valid' in self.stage_id.name.lower():
                if not self.iban_valide:
                    return {
                        'warning': {
                            'title': 'IBAN non valide',
                            'message': "L'IBAN n'est pas valide. Veuillez le vérifier avant de passer à cette étape."
                        }
                    }
            
            # Si on passe à l'étape finale "Souscrit"
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
                            'message': f"Les informations suivantes sont manquantes : {', '.join(missing)}"
                        }
                    }
    
    def write(self, vals):
        """Override write pour les actions automatiques de base"""
        res = super().write(vals)
        
        # Si on change l'étape
        if 'stage_id' in vals:
            for record in self:
                # Si on passe à l'étape finale et qu'on n'a pas encore créé les entrées
                if record.stage_id.is_close and not record.souscription_id:
                    record._create_odoo_entries()
        
        return res
    
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
            _logger.error(f"Erreur lors de la création des entrées Odoo : {e}")
            raise UserError(f"Erreur lors de la création des entrées : {str(e)}")
    
    def _create_partner(self):
        """Crée un contact res.partner"""
        partner_vals = {
            'name': f"{self.contact_prenom} {self.contact_nom}" if self.contact_prenom else self.contact_nom,
            'email': self.contact_email,
            'phone': self.contact_telephone,
            'mobile': self.contact_mobile,
            'street': self.contact_street,
            'street2': self.contact_street2,
            'zip': self.contact_zip,
            'city': self.contact_city,
            'country_id': self.contact_country_id.id,
            'is_company': False,
        }
        
        # Vérifier si un contact existe déjà avec cet email
        existing_partner = self.env['res.partner'].search([
            ('email', '=', self.contact_email)
        ], limit=1)
        
        if existing_partner:
            # Mettre à jour le contact existant
            existing_partner.write(partner_vals)
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
            bank = self.env['res.bank'].search([
                ('bic', '=', self.bank_bic)
            ], limit=1)
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
        
        return self.env['souscription.souscription'].create(souscription_vals)
    
