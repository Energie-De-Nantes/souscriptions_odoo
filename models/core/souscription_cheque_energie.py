from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SouscriptionChequeEnergie(models.Model):
    """Chèque énergie : tiers-payeur de l'État, jamais une remise (ADR 0026).

    **Nature** : aide versée au fournisseur *à la place* du·de la
    souscripteur·rice — le chiffre d'affaires et la TVA des *Factures*
    qu'il paie restent intacts (CONTEXT.md « Chèque énergie »).

    **Propriété** : ce modèle possède toute son histoire (revue
    d'architecture #255) — identité (numéro, montant, expiration), cycle de
    vie (reçu → validé → rejeté/expiré), **imputation** (`imputer()`,
    appelée depuis `account.move._post()` — #172, tranche 1 du PRD #264,
    #265) et **setup comptable** (`_setup_compta()`, #170). Le **gate** du
    cycle de vie est `action_valider()` : il crée et poste l'`account.payment`
    qui porte seul le solde et le lettrage — jamais réimplémentés ici
    (ADR 0026 §3, alternative écartée : « modèle propre réimplémentant
    solde + imputation »). L'imputation FIFO automatique à l'ÉMISSION (pas la
    création) est partagée par la mensuelle et la facture de régularisation
    (tranche 5, #237), toutes deux résolues au seul point de couture commun :
    `account.move._post()`.
    """

    _name = 'souscription.cheque_energie'
    _description = 'Chèque énergie'
    _order = 'date_expiration'

    # ponytail : une seule société (`env.company`), pas de boucle
    # multi-société — ni ce module ni le reste du repo ne gèrent le
    # multi-company aujourd'hui. Ajouter la boucle sur `res.company.search([])`
    # si ça change.
    _CODE_COMPTE_CHEQUE_ENERGIE = '467100'
    _CODE_JOURNAL_CHEQUE_ENERGIE = 'CHEN'

    numero = fields.Char(string='Numéro', required=True, copy=False)

    _numero_unique = models.Constraint(
        'UNIQUE(numero)',
        'Ce numéro de chèque énergie est déjà saisi.',
    )

    # Nominatif à la personne, pas au contrat (ADR 0026) : un chèque s'impute
    # sur toutes les Factures de l'usager·ère, tous contrats confondus.
    partner_id = fields.Many2one('res.partner', string='Souscripteur·rice', required=True)

    montant = fields.Float(string='Montant (€)', required=True)
    date_reception = fields.Date(string='Date de réception', default=fields.Date.context_today)
    date_expiration = fields.Date(
        string="Date d'expiration",
        required=True,
        help="Pilote l'ordre FIFO d'imputation entre plusieurs chèques du même usager·ère (#172).",
    )

    state = fields.Selection(
        [
            ('recu', 'Reçu'),
            ('valide', 'Validé'),
            ('rejete', 'Rejeté'),
            ('expire', 'Expiré'),
        ],
        string='État',
        default='recu',
        required=True,
        copy=False,
    )

    # Généré et posté par le gate `action_valider()` — jamais créé/modifié
    # ailleurs. Un chèque non `validé` (payment_id vide) est par construction
    # exclu de toute imputation (#172 : la recherche FIFO filtre state='valide').
    payment_id = fields.Many2one('account.payment', string='Paiement', readonly=True, copy=False)

    currency_id = fields.Many2one('res.currency', string='Devise', compute='_compute_currency_id')

    # Pas un `related` (ADR 0026 le visait, mais `account.payment` n'a pas de
    # champ `amount_residual` en Odoo 19 Community — il vit sur les lignes
    # d'écriture du paiement). On délègue quand même : `_seek_for_lines()`
    # (natif, account_payment.py:232) sépare la ligne de liquidité (compte
    # « à recevoir », #170) de la ligne contrepartie tiers (411 usager·ère,
    # celle lettrée contre les Factures, #172) — c'est le residual natif de
    # cette dernière qui est le solde. Aucune arithmétique de lettrage
    # réimplémentée ici.
    solde = fields.Monetary(
        string='Solde restant',
        compute='_compute_solde',
        currency_field='currency_id',
        help='Portion du chèque non encore imputée sur une Facture — dérivé, jamais saisi.',
    )

    # Projection lecture seule du solde pour la vue facturiste, à côté du
    # `state` saisi à la main (reçu/validé/rejeté/expiré).
    etat_solde = fields.Selection(
        [
            ('non_entame', 'Non entamé'),
            ('en_cours', 'En cours'),
            ('epuise', 'Épuisé'),
        ],
        string='État du solde',
        compute='_compute_etat_solde',
    )

    @api.depends('payment_id.currency_id')
    def _compute_currency_id(self):
        for cheque in self:
            cheque.currency_id = cheque.payment_id.currency_id or cheque.env.company.currency_id

    @api.depends(
        'payment_id.state', 'payment_id.move_id.line_ids.amount_residual', 'payment_id.move_id.line_ids.account_id'
    )
    def _compute_solde(self):
        for cheque in self:
            pay = cheque.payment_id
            # Un paiement non posté (draft/canceled/rejected) n'a rien lettré :
            # solde nul plutôt qu'une erreur ou un résidu périmé.
            if not pay or pay.state not in ('paid', 'in_process'):
                cheque.solde = 0.0
                continue
            _liquidity, counterpart, writeoff = pay._seek_for_lines()
            reconcile_lines = (counterpart + writeoff).filtered(lambda l: l.account_id.reconcile)
            cheque.solde = abs(sum(reconcile_lines.mapped('amount_residual')))

    @api.depends('payment_id', 'solde', 'montant')
    def _compute_etat_solde(self):
        for cheque in self:
            if not cheque.payment_id:
                cheque.etat_solde = False
            elif cheque.currency_id.is_zero(cheque.solde):
                cheque.etat_solde = 'epuise'
            elif cheque.currency_id.is_zero(cheque.solde - cheque.montant):
                cheque.etat_solde = 'non_entame'
            else:
                cheque.etat_solde = 'en_cours'

    def action_valider(self):
        """Le **gate** (ADR 0026) : reçu → validé, crée et poste l'`account.payment`
        entrant (journal « Chèques énergie », #170) qui portera seul le solde et
        le lettrage. Un chèque qui n'est pas à l'état `reçu` (déjà validé,
        rejeté ou expiré) ne peut pas être (re)validé — erreur explicite plutôt
        qu'un second paiement fantôme."""
        # get-or-create par code (auto-réparation) : la config #170 n'a pas
        # d'xmlid — cf. `_setup_compta()`, un record xmlid'é posé en
        # post_init est purgé par le nettoyage de fin d'install. On (re)pose
        # le journal au besoin.
        journal = self._setup_compta()
        for cheque in self:
            if cheque.state != 'recu':
                label = dict(cheque._fields['state'].selection).get(cheque.state, cheque.state)
                raise UserError(_('Seul un chèque « reçu » peut être validé (état actuel : %s).', label))

            payment = self.env['account.payment'].create(
                {
                    'payment_type': 'inbound',
                    'partner_type': 'customer',
                    'partner_id': cheque.partner_id.id,
                    'amount': cheque.montant,
                    'journal_id': journal.id,
                    'date': cheque.date_reception or fields.Date.context_today(cheque),
                    'memo': cheque.numero,
                }
            )
            payment.action_post()
            cheque.write({'payment_id': payment.id, 'state': 'valide'})
        # None n'est pas marshallable en XML-RPC (Odoo 19, allow_none=False) —
        # la migration appelle ce gate via execute_kw.
        return True

    @api.model
    def _setup_compta(self):
        """Crée (ou retrouve) le journal « Chèques énergie » + le compte
        « à recevoir de l'État » (467100) et renvoie le journal (#170,
        ADR 0026 ; rapatrié depuis `hooks.setup_cheque_energie_compta` par
        #255, revue d'architecture — sémantique strictement inchangée).

        Posé en Python plutôt qu'en `data/*.xml` statique :
        `account.account.company_ids` est un many2many *requis* (variante
        multi-société) et l'outstanding receipts account d'une méthode de
        paiement entrante (`account.payment.method.line`, compute stocké
        auto-créé par le journal) n'est pas assignable proprement en
        `<record>` déclaratif.

        **Sans xmlid, exprès.** On crée en `search`-or-`create` par *code*,
        pas via `_load_records` + xmlid : un record xmlid'é créé en
        `post_init_hook` est *purgé* par le nettoyage de fin d'install
        d'Odoo (il n'est pas dans le jeu d'xmlids « vus » pendant le
        chargement des data → considéré orphelin → supprimé, cascade sur le
        journal). Un record sans ir.model.data n'y est pas soumis : il
        survit. C'est aussi ce qui rend cette méthode sûre à appeler *à la
        volée* depuis `action_valider()` (auto-réparation si l'install ne
        l'a pas posée).

        Appelée par le shim `hooks.setup_cheque_energie_compta(env)` — le
        manifeste (`post_init_hook`) et la migration `19.0.1.8.0` l'appellent
        par ce nom, ils ne bougent pas.

        Idempotent : recherche par code avant de créer, et le correctif de
        `payment_account_id` ne réécrit que si nécessaire — rejouable sans
        doublon.
        """
        company = self.env.company

        # ponytail : classe 4 générique (« autres comptes débiteurs »), pas
        # un code PCG spécifique État (44x) — paramétrage à préciser par la
        # compta, au même niveau que la neutralisation des produits 331/332
        # (cf. migrations/19.0.1.8.0/post-migrate.py). `asset_receivable`
        # (et non `asset_current`) est requis : c'est ce qui rend le compte
        # `reconcile` et compatible avec `_get_valid_payment_account_types()`
        # côté `account.payment` (ADR 0026 §2).
        compte = self.env['account.account'].search(
            [('code', '=', self._CODE_COMPTE_CHEQUE_ENERGIE), ('company_ids', 'in', company.id)], limit=1
        )
        if not compte:
            compte = self.env['account.account'].create(
                {
                    'name': "Chèques énergie à recevoir de l'État",
                    'code': self._CODE_COMPTE_CHEQUE_ENERGIE,
                    'account_type': 'asset_receivable',
                    'company_ids': [(6, 0, [company.id])],
                }
            )

        journal = self.env['account.journal'].search(
            [('code', '=', self._CODE_JOURNAL_CHEQUE_ENERGIE), ('company_id', '=', company.id)], limit=1
        )
        if not journal:
            journal = self.env['account.journal'].create(
                {
                    'name': 'Chèques énergie',
                    'code': self._CODE_JOURNAL_CHEQUE_ENERGIE,
                    'type': 'cash',
                    'company_id': company.id,
                    'default_account_id': compte.id,
                }
            )

        # La ligne de méthode de paiement entrante manuelle est auto-créée
        # par le journal (compute stocké, ADR 0026) : sans son outstanding
        # account explicite, `action_post()` sur le paiement échoue dès que
        # la comptabilité complète est installée ("outstanding
        # payments/receipts account" manquant, cf.
        # account_payment.py:_prepare_move_line_default_vals).
        journal.inbound_payment_method_line_ids.filtered(lambda l: l.payment_account_id != compte).write(
            {'payment_account_id': compte.id}
        )
        return journal

    @api.model
    def imputer(self, facture):
        """Impute en FIFO (par date d'expiration) les *outstanding credits*
        des chèques énergie **validés** de l'usager·ère sur ``facture``
        (#172, ADR 0026 ; rapatriée depuis `account.move._imputer_cheques_energie()`
        par #255, revue d'architecture — sémantique strictement inchangée).
        Appelée depuis `account.move._post()` — jamais au brouillon — pour
        toute facture d'énergie réellement postée : la mécanique est
        partagée entre la mensuelle (`souscription.periode._creer_facture`)
        et la facture de régularisation
        (`souscription.regularisation._creer_facture`, tranche 5, #237),
        toutes deux créées en **brouillon** — cette méthode ne dépend que de
        ``facture`` et de son partenaire, jamais de sa source (Période ou
        Régularisation). Retourne les chèques effectivement consommés (au
        moins une ligne lettrée), recordset vide si aucun.

        **Contrat figé (#255, décision du grill 2026-07-13) : l'état est la
        seule porte, l'expiration ne sert qu'au FIFO.** Le filtre porte
        uniquement sur `state = 'valide'` — un chèque **validé** est une
        créance acquise sur l'État et reste imputable après sa date
        d'expiration (celle-ci borne la **validation**, la porte étatique,
        jamais l'imputation). `date_expiration` n'intervient qu'au tri, pour
        ordonner le FIFO entre plusieurs chèques valides d'un même
        usager·ère. Aucun effet si l'usager·ère ne détient aucun chèque
        validé à solde positif : la Facture postée reste sans imputation,
        comportement de facturation inchangé (#170, non-régression).

        Le lettrage **natif** d'Odoo fait tout le travail — même mécanique que
        le widget « Outstanding credits »/``js_assign_outstanding_line`` : seul
        l'ordre FIFO par expiration est du code métier ici. Le plafonnement
        (``min(solde, total)``, jamais de ligne/solde négatif) et le report du
        reliquat sur la Facture suivante sont natifs à
        ``account.move.line.reconcile()``, jamais réimplémentés — la
        réconciliation exige des écritures **postées** des deux côtés :
        cette méthode n'appelle jamais ``action_post()`` elle-même, c'est la
        responsabilité de l'appelant (``_post()``) de ne l'invoquer qu'une
        fois ``facture`` réellement postée.
        """
        facture.ensure_one()
        cheques = self.search([('partner_id', '=', facture.partner_id.id), ('state', '=', 'valide')]).sorted(
            'date_expiration'
        )
        cheques = cheques.filtered(lambda c: c.solde > 0.0)
        consommes = self.browse()
        if not cheques:
            return consommes

        compte_tiers = ('asset_receivable', 'liability_payable')
        for cheque in cheques:
            if facture.currency_id.is_zero(facture.amount_residual):
                break
            # `_seek_for_lines()` (natif) plutôt qu'un filtre par account_type
            # brut : le compte « à recevoir de l'État » est lui-même typé
            # asset_receivable (#170 FIX 4), donc un filtre account_type seul
            # matcherait aussi la ligne de liquidité du paiement — on veut
            # uniquement la ligne contrepartie tiers (411 usager·ère).
            _liquidite, contrepartie, ecart = cheque.payment_id._seek_for_lines()
            ligne_paiement = (contrepartie + ecart).filtered(lambda l: l.account_id.reconcile and not l.reconciled)
            ligne_facture = facture.line_ids.filtered(
                lambda l: l.account_id.account_type in compte_tiers and not l.reconciled
            )
            if not ligne_paiement or not ligne_facture:
                continue
            (ligne_paiement + ligne_facture).reconcile()
            consommes += cheque
        return consommes
