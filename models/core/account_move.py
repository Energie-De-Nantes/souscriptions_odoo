from odoo import api, fields, models
from odoo.exceptions import ValidationError


class AccountMove(models.Model):
    _inherit = 'account.move'

    periode_id = fields.Many2one('souscription.periode', string='Période facturée')

    # Parallèle à periode_id (ADR 0030 décision 5, amende ADR-0004 en « toute
    # facture d'énergie référence sa source : une Période OU une
    # Régularisation »). Pas encore posé par aucun code de ce système dans
    # cette tranche — la génération de facture de régularisation est la
    # tranche 5 (#237) ; seul le lien et sa contrainte d'exclusivité existent
    # déjà.
    regularisation_id = fields.Many2one('souscription.regularisation', string='Régularisation liée')

    @api.constrains('periode_id', 'regularisation_id')
    def _check_source_exclusive(self):
        for move in self:
            if move.periode_id and move.regularisation_id:
                raise ValidationError(
                    'Une facture référence sa source : une Période ou une Régularisation, jamais les deux.'
                )

    # Compute (pas `related`, qui ne sait suivre qu'un seul chemin) : la
    # Souscription se lit via la Période OU la Régularisation, jamais les
    # deux (ADR 0030 décision 5, amende ADR-0004).
    souscription_id = fields.Many2one(
        'souscription.souscription',
        string='Souscription',
        compute='_compute_souscription_id',
        store=True,
        readonly=True,
    )

    is_facture_energie = fields.Boolean(string="Facture d'énergie", compute='_compute_is_facture_energie', store=True)

    @api.depends('periode_id.souscription_id', 'regularisation_id.souscription_id')
    def _compute_souscription_id(self):
        for move in self:
            move.souscription_id = move.periode_id.souscription_id or move.regularisation_id.souscription_id

    # Plomberie dérivée (#185, PRD #183) : la Souscription est l'unique source
    # de vérité du Mode de paiement (CONTEXT.md) — jamais saisi sur la
    # Facture. related stocké pour rester filtrable/groupable (vue
    # « Règlements en attente ») ; se recalcule quand la Souscription change.
    mode_paiement = fields.Selection(
        related='souscription_id.mode_paiement',
        string='Mode de paiement',
        store=True,
        readonly=True,
    )

    @api.depends('periode_id', 'regularisation_id', 'souscription_id')
    def _compute_is_facture_energie(self):
        """Détermine si c'est une facture d'énergie (souscription électricité) —
        source Période (mensuelle) OU Régularisation (tranche 5, #237)."""
        for move in self:
            move.is_facture_energie = bool((move.periode_id or move.regularisation_id) and move.souscription_id)

    def _get_report_base_filename(self):
        """Nom de fichier personnalisé pour les factures d'énergie"""
        self.ensure_one()
        if self.is_facture_energie and self.souscription_id:
            return f'Facture_Energie_{self.souscription_id.name}_{self.name}'
        return super()._get_report_base_filename()

    def _imputer_cheques_energie(self):
        """Impute en FIFO (par date d'expiration) les *outstanding credits* des
        chèques énergie **validés** de l'usager·ère sur **cette** Facture qui
        vient d'être créée (#172, ADR 0026). Mécanique partagée entre la
        mensuelle (``souscription.periode._creer_facture``) et la facture de
        régularisation (``souscription.regularisation._creer_facture``,
        tranche 5, #237) : le point de couture ne dépend que de la Facture et
        de son partenaire, jamais de sa source (Période ou Régularisation).
        Aucun effet si l'usager·ère ne détient aucun chèque validé à solde
        positif : la Facture reste ``draft``, comportement de facturation
        inchangé (#170, non-régression).

        Le lettrage **natif** d'Odoo fait tout le travail — même mécanique que
        le widget « Outstanding credits »/``js_assign_outstanding_line`` : seul
        l'ordre FIFO par expiration est du code métier ici. Le plafonnement
        (``min(solde, total)``, jamais de ligne/solde négatif) et le report du
        reliquat sur la Facture suivante sont natifs à
        ``account.move.line.reconcile()``, jamais réimplémentés — la
        réconciliation exige des écritures **postées** des deux côtés, d'où le
        ``action_post()`` déclenché ici quand un chèque est disponible.
        """
        self.ensure_one()
        Cheque = self.env['souscription.cheque_energie']
        cheques = Cheque.search([('partner_id', '=', self.partner_id.id), ('state', '=', 'valide')]).sorted(
            'date_expiration'
        )
        cheques = cheques.filtered(lambda c: c.solde > 0.0)
        if not cheques:
            return

        if self.state == 'draft':
            self.action_post()

        compte_tiers = ('asset_receivable', 'liability_payable')
        for cheque in cheques:
            if self.currency_id.is_zero(self.amount_residual):
                break
            # `_seek_for_lines()` (natif) plutôt qu'un filtre par account_type
            # brut : le compte « à recevoir de l'État » est lui-même typé
            # asset_receivable (#170 FIX 4), donc un filtre account_type seul
            # matcherait aussi la ligne de liquidité du paiement — on veut
            # uniquement la ligne contrepartie tiers (411 usager·ère).
            _liquidite, contrepartie, ecart = cheque.payment_id._seek_for_lines()
            ligne_paiement = (contrepartie + ecart).filtered(lambda l: l.account_id.reconcile and not l.reconciled)
            ligne_facture = self.line_ids.filtered(
                lambda l: l.account_id.account_type in compte_tiers and not l.reconciled
            )
            if not ligne_paiement or not ligne_facture:
                continue
            (ligne_paiement + ligne_facture).reconcile()
