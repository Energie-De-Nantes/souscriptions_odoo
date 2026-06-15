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

    pdl = fields.Char(string='pdl', readonly=True)
    lisse = fields.Boolean(string='Lissé', readonly=True)  # related='souscription_id.lisse',  store=True)

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
                    'lisse_periode': sous.lisse,
                    'puissance_souscrite_periode': float(sous.puissance_souscrite) if sous.puissance_souscrite else 0.0,
                    'provision_mensuelle_kwh_periode': sous.provision_mensuelle_kwh,
                    'coeff_pro_periode': sous.coeff_pro,
                    'pdl': sous.pdl,  # Copie du PDL aussi
                    'lisse': sous.lisse,  # Compatibilité ancien champ
                    'config_cadrans': sous.config_cadrans or ('4_cadrans' if sous.type_tarif == 'hphc' else 'base'),
                }
            )

            # Gestion des provisions selon type de tarif
            if sous.lisse and sous.provision_mensuelle_kwh:
                if sous.type_tarif == 'base':
                    vals['provision_base_kwh'] = sous.provision_mensuelle_kwh
                else:  # HP/HC - répartition temporaire 70% HP / 30% HC
                    vals['provision_hp_kwh'] = sous.provision_mensuelle_kwh * 0.7
                    vals['provision_hc_kwh'] = sous.provision_mensuelle_kwh * 0.3

        return super().create(vals_list)

    # Champs facturables figés : une fois la facture émise, les réécrire
    # changerait une facture opposable. Le verrou (#14) les protège ; les champs
    # techniques/calculés (facture_id, facture_state, mois_annee, jours…) restent
    # recalculables par l'ORM (passe par _write, pas par ce write public).
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
            'lisse_periode',
            'puissance_souscrite_periode',
            'provision_mensuelle_kwh_periode',
            'coeff_pro_periode',
        }
    )

    def write(self, vals):
        """Verrou de facturation (#14) : une période dont la facture est *émise*
        (postée) est en lecture seule sur ses champs facturables, y compris via
        RPC. La correction se fait *avant* l'émission (facture en brouillon)."""
        if self._LOCKED_FIELDS.intersection(vals):
            for periode in self:
                if periode.facture_id.state == 'posted':
                    raise UserError(
                        f'Période {periode.mois_annee} : facture émise, modification interdite. '
                        'Repassez la facture en brouillon pour corriger, ou créez une régularisation.'
                    )
        return super().write(vals)

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
        saisis directement (valeur conservée)."""
        for periode in self:
            if periode.config_cadrans == '4_cadrans':
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

    # === Composition de la facture (candidate A / ADR 0006) ===
    # La Période compose ses lignes de facture à partir de son snapshot figé
    # (puissance, tarif, coeff PRO, solidaire, quantités) et de la grille passée
    # en paramètre. Aucun repli sur l'état live de la souscription : le snapshot
    # fait autorité (ADR 0006). Les prix restent l'affaire de la grille (ADR 0002,
    # « référencer, pas recopier »).

    def _get_produit_abonnement(self, tarif_solidaire):
        """Produit d'abonnement (standard ou solidaire)."""
        product_ref = (
            'souscriptions_product_abonnement_solidaire'
            if tarif_solidaire
            else 'souscriptions_product_abonnement_standard'
        )
        try:
            return self.env.ref(f'souscriptions_odoo.{product_ref}')
        except Exception:
            type_abo = 'solidaire' if tarif_solidaire else 'standard'
            raise UserError(f"Produit d'abonnement {type_abo} non trouvé")

    def _get_produit_energie(self, type_energie):
        """Produit d'énergie correspondant au cadran facturé (base, hp, hc)."""
        xmlid_map = {
            'base': 'souscriptions_odoo.souscriptions_product_energie_base',
            'hp': 'souscriptions_odoo.souscriptions_product_energie_hp',
            'hc': 'souscriptions_odoo.souscriptions_product_energie_hc',
        }
        xmlid = xmlid_map.get(type_energie.lower())
        if not xmlid:
            raise UserError(f"Type d'énergie non reconnu : {type_energie}")
        produit = self.env.ref(xmlid, raise_if_not_found=False)
        if not produit:
            raise UserError(f"Produit d'énergie {type_energie} non trouvé")
        return produit

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
        produit_abo = self._get_produit_abonnement(tarif_solidaire)
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
        is_base_tarif = type_tarif == 'base'

        if is_base_tarif:
            produit_base = self._get_produit_energie('base')
            prix_base = prix_dict.get(produit_base.id)
            if prix_base is None:
                raise UserError(f'Prix non trouvé dans la grille pour le produit : {produit_base.name}')
            lines_vals.append(
                (
                    0,
                    0,
                    {
                        'product_id': produit_base.id,
                        'name': produit_base.name,
                        'quantity': self._quantite_facturee('base'),
                        'price_unit': prix_base,
                    },
                )
            )
        else:  # HP/HC : toujours les deux lignes (même à 0)
            produit_hp = self._get_produit_energie('hp')
            prix_hp = prix_dict.get(produit_hp.id)
            if prix_hp is None:
                raise UserError(f'Prix non trouvé dans la grille pour le produit : {produit_hp.name}')
            lines_vals.append(
                (
                    0,
                    0,
                    {
                        'product_id': produit_hp.id,
                        'name': produit_hp.name,
                        'quantity': self._quantite_facturee('hp'),
                        'price_unit': prix_hp,
                    },
                )
            )

            produit_hc = self._get_produit_energie('hc')
            prix_hc = prix_dict.get(produit_hc.id)
            if prix_hc is None:
                raise UserError(f'Prix non trouvé dans la grille pour le produit : {produit_hc.name}')
            lines_vals.append(
                (
                    0,
                    0,
                    {
                        'product_id': produit_hc.id,
                        'name': produit_hc.name,
                        'quantity': self._quantite_facturee('hc'),
                        'price_unit': prix_hc,
                    },
                )
            )

        # Note TURPE variable sous l'énergie
        if self.turpe_variable > 0:
            lines_vals.append(
                (0, 0, {'display_type': 'line_note', 'name': f'Dont turpe variable: {self.turpe_variable:.2f}€'})
            )

        return lines_vals

    def _creer_facture(self):
        """Émet la facture (``account.move``) de cette période.

        Coquille fine : sélectionne la grille active à la date de fin, compose les
        lignes (``_composer_lignes``) et crée le move en posant ``periode_id``
        (source unique du lien Période ↔ Facture, ADR 0004).
        """
        self.ensure_one()
        grille = self.env['grille.prix'].get_grille_active(self.date_fin)
        return self.env['account.move'].create(
            {
                'move_type': 'out_invoice',
                'partner_id': self.souscription_id.partner_id.id,
                'invoice_date': self.date_fin,
                'periode_id': self.id,
                'invoice_line_ids': self._composer_lignes(grille),
            }
        )
