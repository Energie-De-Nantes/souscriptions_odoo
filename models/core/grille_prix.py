from dateutil.relativedelta import relativedelta
from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

# Puissance de référence (kVA) du tarif d'abonnement affine : base à 3 kVA,
# coefficient appliqué au-delà (ADR 0018).
PUISSANCE_BASE_KVA = 3.0

# Nombre de jours servant de base au prorata journalier de l'abonnement.
# Convention TURPE : le prix annuel est divisé par 365 quelle que soit l'année.
JOURS_PAR_AN = 365.0


class GrillePrix(models.Model):
    _name = 'grille.prix'
    _description = 'Grille de prix énergétique'
    _order = 'date_debut desc'

    name = fields.Char('Nom de la grille', required=True)
    date_debut = fields.Date('Valable à partir du', required=True)
    date_fin = fields.Date(
        "Valable jusqu'au (exclu)",
        compute='_compute_date_fin',
        help='Dérivée, jamais saisie : le début de la grille suivante du même '
        'régime, vide si aucune (grille encore ouverte). Borne EXCLUE — '
        'demi-ouverte comme la Période (CONTEXT.md « Grille de prix ») : la '
        'grille se termine le jour où la suivante commence.',
    )
    active = fields.Boolean('Active', default=True)

    # Régime de prix (CONTEXT.md « Régime de prix ») : quel barème s'applique.
    # Chaque régime versionne ses grilles indépendamment — la sélection
    # (get_grille_active) et la dérivation de date_fin jouent PAR régime, jamais
    # tous régimes confondus. Le Tarif Moulin n'introduit aucun produit dédié :
    # seul ce prix change, le catalogue (souscription.produit) reste inchangé.
    regime_prix = fields.Selection(
        [('standard', 'Standard'), ('moulin', 'Moulin')],
        string='Régime de prix',
        default='standard',
        required=True,
        help='Barème appliqué par cette grille. Chaque régime versionne ses '
        'grilles indépendamment : une grille Moulin ouverte coexiste avec une '
        'grille standard ouverte (sélection et fin dérivée scopées par '
        'régime).',
    )

    ligne_ids = fields.One2many('grille.prix.ligne', 'grille_id', string='Lignes de prix')

    # Champs calculés pour info
    nb_lignes = fields.Integer('Nombre de lignes', compute='_compute_nb_lignes')

    @api.depends('ligne_ids')
    def _compute_nb_lignes(self):
        for grille in self:
            grille.nb_lignes = len(grille.ligne_ids)

    @api.depends('date_debut', 'regime_prix')
    def _compute_date_fin(self):
        """Dérivée : le `date_debut` de la grille suivante du même régime, vide
        si aucune (grille encore ouverte). Rien n'est stocké ni fermé par un
        effet de bord (cf. CONTEXT.md « Grille de prix ») — supprimer ou
        corriger une grille ne laisse donc jamais de trou de période ni de
        grille périmée à retenir à jour."""
        for grille in self:
            if not grille.date_debut:
                grille.date_fin = False
                continue
            suivante = self.search(
                [
                    ('regime_prix', '=', grille.regime_prix),
                    ('date_debut', '>', grille.date_debut),
                    ('id', '!=', grille._origin.id),
                ],
                order='date_debut asc',
                limit=1,
            )
            grille.date_fin = suivante.date_debut if suivante else False

    @api.model
    def get_grille_active(self, date_facture=None, regime='standard'):
        """Récupère la grille du régime donné en vigueur à la date donnée.

        La grille en vigueur est simplement la plus récente à avoir commencé
        (CONTEXT.md « Grille de prix ») : sélection sur la seule
        ``date_debut``, jamais sur ``date_fin`` (dérivée, non filtrable en
        SQL) — une facturation rétroactive utilise ainsi la grille en vigueur
        à la date concernée, pour le régime de la Souscription/Période
        facturée.
        """
        if date_facture is None:
            date_facture = fields.Date.today()

        grille = self.search(
            [
                ('regime_prix', '=', regime),
                ('date_debut', '<=', date_facture),
            ],
            order='date_debut desc',
            limit=1,
        )

        if not grille:
            raise UserError(
                f'Aucune grille de prix ({regime}) ne couvre la date {date_facture}. '
                f'Vérifiez la couverture des grilles (trou de période ?).'
            )

        return grille

    @api.constrains('date_debut')
    def _check_date_debut_premier_du_mois(self):
        """Un changement de grille tombe toujours un 1er du mois (CONTEXT.md
        « Grille de prix ») : aucune Période ne peut alors enjamber deux
        grilles, sa seule date de début suffisant à la désigner — il n'existe
        pas de prix au prorata. Non rétroactif par nature (``@api.constrains``
        ne revalide que les grilles créées ou modifiées) : les grilles
        existantes démarrant en cours de mois ne sont pas requalifiées ici,
        c'est voulu (cf. issue #309, hors périmètre inter-dépôt)."""
        for grille in self:
            if grille.date_debut and grille.date_debut.day != 1:
                raise ValidationError(
                    f"La grille '{grille.name}' doit débuter un 1er du mois "
                    f"({grille.date_debut} ne l'est pas) : un changement de "
                    f'grille ne tombe jamais en cours de mois.'
                )

    # Cadrans facturés par type de tarif : (code, libellé). Carte unique de la
    # partition (ADR 0029) — Base : un seul cadran ; HP/HC : toujours les deux,
    # même à 0. Pilote la Facture (periode._composer_lignes) comme les documents
    # (souscription._prix_documents).
    _CADRANS_FACTURES = {
        'base': [('base', 'Base')],
        'hphc': [('hp', 'Heures pleines'), ('hc', 'Heures creuses')],
    }

    def composants(self, type_tarif, puissance_kva, coeff_pro=0.0, tarif_solidaire=False):
        """Composants prixés de la grille pour une configuration (ADR 0029).

        L'unique implémentation de la règle d'assemblage : partition en cadrans
        facturés, prix de l'énergie par cadran, abonnement affine (ADR 0018 —
        l'appelant décide de la puissance à prixer ; la Période privilégie la
        moyenne mesurée sur le snapshot souscrit, #78), majoration PRO (#67,
        toute la fourniture, jamais la Refacturation — pur transit Enedis),
        résolution du Produit de facturation standard /
        solidaire (ADR 0013). Rend des données pures HT — produits résolus et
        prix unitaires. Quantités, TVA d'affichage et mise en page restent aux
        projections (Facture, conditions particulières), qui appellent chacune
        avec **sa** grille (historique à la fin de Période ↔ engagée à la date
        de début) : les valeurs divergent dans le temps, la règle jamais.
        Prix manquant → ``UserError`` — jamais un prix nul par défaut sur un
        document.
        """
        self.ensure_one()
        produit = self.env['souscription.produit']
        majoration_pro = 1 + coeff_pro / 100.0
        prix_dict = self._get_prix_dict()

        abonnement = {
            'produit': produit.produit_abonnement(tarif_solidaire),
            'prix_jour': self._get_prix_abonnement(puissance_kva, tarif_solidaire) * majoration_pro,
        }

        energies = []
        for cadran, libelle in self._CADRANS_FACTURES[type_tarif]:
            produit_energie = produit.produit_energie(cadran, tarif_solidaire)
            prix_kwh = prix_dict.get(produit_energie.id)
            if prix_kwh is None:
                raise UserError(f'Prix non trouvé dans la grille {self.name} pour le produit : {produit_energie.name}')
            energies.append(
                {
                    'cadran': cadran,
                    'libelle': libelle,
                    'produit': produit_energie,
                    'prix_kwh': prix_kwh * majoration_pro,
                }
            )

        return {'abonnement': abonnement, 'energies': energies}

    def prix_energie_cadran(self, cadran, tarif_solidaire=False, coeff_pro=0.0):
        """Prix unitaire (€/kWh) du cadran facturé pour cette grille, univers et
        majoration PRO donnés — même moteur que ``composants()`` (ADR 0029),
        sans nécessiter de puissance (aucun abonnement en jeu). Consommé par
        la Régularisation (ADR 0030 décision 4) pour valoriser un écart aux
        prix historiques de sa grille. Prix manquant -> ``UserError``, jamais
        un prix nul par défaut (même garde que ``composants()``)."""
        self.ensure_one()
        produit = self.env['souscription.produit'].produit_energie(cadran, tarif_solidaire)
        prix = self._get_prix_dict().get(produit.id)
        if prix is None:
            raise UserError(f'Prix non trouvé dans la grille {self.name} pour le produit : {produit.name}')
        return prix * (1 + coeff_pro / 100.0)

    def _get_prix_dict(self):
        """{product_id: prix_interne} pour toute la grille — interne, servi via
        ``composants()`` (ADR 0029)."""
        self.ensure_one()
        return {ligne.product_id.id: ligne.prix_interne for ligne in self.ligne_ids if ligne.product_id}

    def _get_prix_abonnement(self, puissance_kva, tarif_solidaire=False):
        """Prix d'abonnement journalier (€/jour) pour une puissance — interne.

        Tarif affine (ADR 0018) : la grille porte deux paramètres par univers,
        ``prix_base_3kva`` (€/an à 3 kVA) et ``coef_kva`` (€/an par kVA
        supplémentaire). Le prix journalier vaut
        ``(prix_base_3kva + coef_kva x (puissance_kva - 3)) / 365``. La
        majoration PRO est l'affaire de ``composants()`` — un seul site
        (ADR 0029). L'univers (standard / solidaire) est porté par le produit
        du catalogue (ADR 0013), jamais ré-encodé dans la grille.
        """
        self.ensure_one()

        product = self.env['souscription.produit'].produit_abonnement(tarif_solidaire)

        ligne_abo = self.ligne_ids.filtered(lambda l: l.product_id == product and l.type_produit == 'abonnement')
        if not ligne_abo:
            type_abo = 'solidaire' if tarif_solidaire else 'standard'
            raise UserError(f"Aucun tarif d'abonnement {type_abo} dans la grille {self.name}.")

        ligne = ligne_abo[0]
        prix_annuel = ligne.prix_base_3kva + ligne.coef_kva * (float(puissance_kva) - PUISSANCE_BASE_KVA)
        return prix_annuel / JOURS_PAR_AN

    def dupliquer_cette_grille(self):
        """Action pour dupliquer cette grille avec toutes ses lignes.

        La copie est créée en **brouillon (inactive)** : dupliquer sert à
        amorcer une nouvelle grille (ex. une grille Moulin) sans perturber la
        timeline en cours. Tant qu'elle est inactive elle reste hors timeline :
        `get_grille_active` et la dérivation de `date_fin` l'ignorent
        (`active_test`). L'utilisateur ajuste régime/dates puis l'active.
        """
        self.ensure_one()

        # Date de départ indicative : le 1er du mois suivant, seule date qui ne
        # viole jamais la contrainte « 1er du mois » (contrairement à `today`,
        # qui la viole tout jour sauf le 1er) — l'utilisateur l'ajuste avant
        # activation si besoin.
        date_debut_suggeree = fields.Date.today() + relativedelta(months=1, day=1)

        # copy() recopie nativement le One2many ligne_ids et le regime_prix ;
        # seules name/date_debut/active ont besoin d'être surchargées.
        nouvelle_grille = self.copy(
            {
                'name': f'Copie de {self.name}',
                'date_debut': date_debut_suggeree,
                'active': False,
            }
        )

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'grille.prix',
            'res_id': nouvelle_grille.id,
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'form_view_initial_mode': 'edit',
            },
        }


class GrillePrixLigne(models.Model):
    _name = 'grille.prix.ligne'
    _description = 'Ligne de prix énergétique'
    _order = 'type_produit, product_id'

    grille_id = fields.Many2one('grille.prix', string='Grille', required=True, ondelete='cascade')

    product_id = fields.Many2one(
        'product.product',
        string='Produit',
        required=True,
        domain=[('type', '=', 'service')],
        help='Produit de service pour la facturation énergétique',
    )

    # Rôle de la ligne. L'univers (standard / solidaire) est porté par le
    # produit du catalogue (ADR 0013), jamais par ce champ.
    type_produit = fields.Selection(
        [('abonnement', 'Tarifs abonnement'), ('energie', 'Énergie (€/kWh)')],
        string='Type',
        required=True,
        default='energie',
    )

    # Pour les abonnements : tarif affine (ADR 0018) — base à 3 kVA + coef/kVA.
    prix_base_3kva = fields.Float(
        'Abonnement base 3 kVA (€/an)',
        digits=(16, 6),
        help="Prix annuel de l'abonnement à 3 kVA, proratisé au jour (÷365) lors de la facturation.",
    )
    coef_kva = fields.Float(
        'Coefficient par kVA (€/an)',
        digits=(16, 6),
        help='Prix annuel ajouté par kVA souscrit au-delà de 3 kVA.',
    )

    # Pour les énergies : prix unitaire classique
    prix_unitaire = fields.Float('Prix unitaire (€/kWh)', digits=(16, 6), help='Prix unitaire pour les énergies')

    # Prix interne calculé
    prix_interne = fields.Float(
        'Prix interne', compute='_compute_prix_interne', store=True, help='Prix utilisé pour les calculs de facturation'
    )

    # Champs informatifs
    unite_saisie = fields.Char('Unité saisie', compute='_compute_unites', store=False)
    unite_calcul = fields.Char('Unité calcul', compute='_compute_unites', store=False)

    @api.depends('type_produit')
    def _compute_unites(self):
        for ligne in self:
            if ligne.type_produit == 'abonnement':
                ligne.unite_saisie = '€/an'
                ligne.unite_calcul = '€/jour'
            else:
                ligne.unite_saisie = '€/kWh'
                ligne.unite_calcul = '€/kWh'

    @api.depends('type_produit', 'prix_unitaire', 'prix_base_3kva')
    def _compute_prix_interne(self):
        for ligne in self:
            if ligne.type_produit == 'abonnement':
                # Prix indicatif (€/jour) à la puissance de base ; le prix facturé
                # est calculé par _get_prix_abonnement (affine, ADR 0018).
                ligne.prix_interne = ligne.prix_base_3kva / JOURS_PAR_AN if ligne.prix_base_3kva else 0.0
            else:
                # Énergies : prix interne = prix saisi.
                ligne.prix_interne = ligne.prix_unitaire or 0.0

    _unique_produit_grille = models.Constraint(
        'UNIQUE(grille_id, product_id)',
        "Un produit ne peut apparaître qu'une seule fois par grille.",
    )
