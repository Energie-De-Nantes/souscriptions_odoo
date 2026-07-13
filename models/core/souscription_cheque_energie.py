from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class SouscriptionChequeEnergie(models.Model):
    """Chèque énergie : tiers-payeur de l'État, jamais une remise (ADR 0026).

    **Nature** : aide versée au fournisseur *à la place* du·de la
    souscripteur·rice — le chiffre d'affaires et la TVA des *Factures*
    qu'il paie restent intacts (CONTEXT.md « Chèque énergie »).

    **Propriété** : ce modèle possède l'identité (numéro, montant,
    expiration) et le cycle de vie (reçu → validé → rejeté/expiré). Le
    **gate** est `action_valider()` : il crée et poste l'`account.payment`
    qui porte seul le solde et le lettrage — jamais réimplémentés ici
    (ADR 0026 §3, alternative écartée : « modèle propre réimplémentant
    solde + imputation »). L'imputation FIFO automatique à l'ÉMISSION (pas la
    création, tranche 1 du PRD #264, #265) vit côté
    `account.move._imputer_cheques_energie()`, appelée depuis `_post()`
    (#172) — mécanique partagée par la mensuelle et la facture de
    régularisation (tranche 5, #237).
    """

    _name = 'souscription.cheque_energie'
    _description = 'Chèque énergie'
    _order = 'date_expiration'

    numero = fields.Char(string='Numéro', required=True, copy=False)

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

    @api.constrains('numero')
    def _check_numero_unique(self):
        for cheque in self:
            if cheque.numero and self.search_count([('numero', '=', cheque.numero), ('id', '!=', cheque.id)]):
                raise ValidationError(_('Ce numéro de chèque énergie (%s) est déjà saisi.', cheque.numero))

    def action_valider(self):
        """Le **gate** (ADR 0026) : reçu → validé, crée et poste l'`account.payment`
        entrant (journal « Chèques énergie », #170) qui portera seul le solde et
        le lettrage. Un chèque qui n'est pas à l'état `reçu` (déjà validé,
        rejeté ou expiré) ne peut pas être (re)validé — erreur explicite plutôt
        qu'un second paiement fantôme."""
        # get-or-create par code (auto-réparation) : la config #170 n'a pas
        # d'xmlid — cf. hooks.py, un record xmlid'é posé en post_init est purgé
        # par le nettoyage de fin d'install. On (re)pose le journal au besoin.
        from ...hooks import setup_cheque_energie_compta

        journal = setup_cheque_energie_compta(self.env)
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
