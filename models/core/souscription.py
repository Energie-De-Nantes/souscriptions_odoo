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

    # Cadrans facturés par type de tarif : (code grille, libellé document).
    _CADRANS_DOCUMENTS = {
        'base': [('base', 'Base')],
        'hphc': [('hp', 'Heures pleines'), ('hc', 'Heures creuses')],
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
        grille = self.env['grille.prix'].get_grille_active(a_date)
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

        # Abonnement (€/an et €/mois) pour la puissance souscrite.
        abo_product = produit.produit_abonnement(is_sol)
        abo_jour_ht = grille.get_prix_abonnement(self.puissance_souscrite, self.coeff_pro, is_sol)
        abo_an = affiche(abo_product, abo_jour_ht * 365.0)
        abo_mois = affiche(abo_product, abo_jour_ht * 365.0 / 12.0)

        # Provision mensuelle par cadran facturé (utilisée pour la mensualité).
        provisions = {
            'base': self.provision_mensuelle_kwh,
            'hp': self.provision_hp_kwh,
            'hc': self.provision_hc_kwh,
        }

        energies = []
        mensualite = abo_mois
        for code, libelle in self._CADRANS_DOCUMENTS[self.type_tarif]:
            energie_product = produit.produit_energie(code, is_sol)
            prix_kwh = affiche(energie_product, prix_grille.get(energie_product.id, 0.0))
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
