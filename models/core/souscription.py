import logging
from datetime import date, timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError

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
    _inherit = ['mail.thread']

    name = fields.Char(string='Référence', required=True, copy=False, readonly=True, default='Nouveau')
    partner_id = fields.Many2one('res.partner', string='Souscripteur·trice')
    active = fields.Boolean(string='Active', default=True)

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
    presta_ids = fields.One2many('souscription.presta', 'souscription_id', string='Prestations à refacturer')
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

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nouveau') == 'Nouveau':
                vals['name'] = self.env['ir.sequence'].next_by_code('souscription.sequence') or 'Nouveau'
            # Amorçage du calendrier de comptage tant qu'electricore ne l'alimente
            # pas (#12) : par défaut aligné sur le type de tarif.
            if not vals.get('config_cadrans'):
                vals['config_cadrans'] = '4_cadrans' if vals.get('type_tarif') == 'hphc' else 'base'
        return super().create(vals_list)

    @api.depends('periode_ids.facture_id')
    def _compute_factures_via_periodes(self):
        for sous in self:
            sous.facture_ids = sous.periode_ids.mapped('facture_id')

    def creer_factures(self):
        """Émet les factures des périodes non encore facturées.

        Orchestrateur : pour chaque souscription, boucle sur ses périodes sans
        facture (garde anti-doublon) et délègue l'émission à la période
        (``periode._creer_facture``). La composition des lignes et la création du
        ``account.move`` vivent désormais sur la Période (ADR 0006).
        """
        _logger.info(f'Créer factures appelé pour {len(self)} souscriptions')

        for souscription in self:
            if not souscription.partner_id:
                _logger.warning(f'Souscription {souscription.name} sans partenaire, ignorée')
                continue

            premiere_facture = self.env['account.move']
            for periode in souscription.periode_ids.filtered(lambda p: not p.facture_id):
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
                souscription._facturer_prestations_en_attente(premiere_facture)

    def _facturer_prestations_en_attente(self, facture):
        """Ajoute les prestations en attente (`facture_id` NULL) comme lignes de
        `facture` et pose leur `facture_id`. Responsabilité de la Souscription,
        pas de la Période (ADR 0009)."""
        self.ensure_one()
        prestas = self.presta_ids.filtered(lambda p: not p.facture_id)
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

    # === API POUR PONT EXTERNE ===

    @api.model
    def get_souscriptions_by_pdl(self, pdl_list):
        """Récupère les souscriptions par liste de PDL - API pour pont externe"""
        return self.search([('pdl', 'in', pdl_list)]).read(
            [
                'name',
                'pdl',
                'partner_id',
                'date_debut',
                'date_fin',
                'puissance_souscrite',
                'type_tarif',
                'lisse',
                'provision_mensuelle_kwh',
                'tarif_solidaire',
                'mode_paiement',
            ]
        )

    def get_billing_periods(self, date_start=None, date_end=None):
        """Récupère les périodes de facturation pour cette souscription"""
        domain = [('souscription_id', '=', self.id)]
        if date_start:
            domain.append(('date_debut', '>=', date_start))
        if date_end:
            domain.append(('date_fin', '<=', date_end))

        periods = self.env['souscription.periode'].search(domain)
        return periods.read(
            [
                'date_debut',
                'date_fin',
                'type_periode',
                'energie_base_kwh',
                'provision_base_kwh',
                'turpe_fixe',
                'turpe_variable',
                'facture_id',
            ]
        )

    @api.model
    def create_billing_period(self, vals):
        """Crée une période de facturation - API pour pont externe"""
        return self.env['souscription.periode'].create(vals)

    def update_consumption_data(self, period_data):
        """Met à jour les données de consommation - API pour pont externe"""
        for period_vals in period_data:
            period_id = period_vals.pop('id')
            period = self.env['souscription.periode'].browse(period_id)
            period.write(period_vals)
        return True

    @api.model
    def generer_lot_prelevement_mensuel(self):
        """Génère un lot de prélèvement pour les souscriptions en prélèvement automatique"""
        # Fonctionnalité à implémenter dans une version ultérieure
        # Pour l'instant, on retourne un message d'information
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Génération de lot de prélèvement',
                'message': 'Fonctionnalité en cours de développement - Version minimale',
                'type': 'info',
                'sticky': False,
            },
        }
