from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class AccountMove(models.Model):
    _inherit = 'account.move'

    periode_id = fields.Many2one('souscription.periode', string='Période facturée')

    # Parallèle à periode_id (ADR 0030 décision 5, amende ADR-0004 en « toute
    # facture d'énergie référence sa source : une Période OU une
    # Régularisation »). Posé par `souscription.regularisation._creer_facture`
    # (tranche 5, #237). `copy=False` : un duplicate ou un avoir (Odoo passe
    # par `copy_data`) ne doit JAMAIS porter le lien — son post
    # re-consommerait les écarts figés (double-tampon, grill #259).
    regularisation_id = fields.Many2one('souscription.regularisation', string='Régularisation liée', copy=False)

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

    def _post(self, soft=True):
        """Point de couture de l'émission — re-génération préservante des
        lignes (#266, tranche 2 du PRD #264), tampon de Régularisation (ADR
        0030 décision 4, tranche 6 du PRD #231, #238) **et** imputation du
        chèque énergie (ADR 0026, #172, déplacée de la création à l'émission
        par la tranche 1 du PRD #264, #265).

        La re-génération se déclenche AVANT ``super()._post()`` — le move est
        encore brouillon, ses lignes flaguées éditables — sur ``self`` (pas
        sur le résultat filtré) : même un move programmé dans le futur
        (``soft=True``, qui restera en brouillon) doit voir ses lignes
        rafraîchies. Le tampon et l'imputation, eux, ne se déclenchent qu'à
        l'émission RÉELLE : filtrer sur le résultat de ``super()._post()``,
        pas sur ``self``, exclut naturellement les moves soft-programmés sans
        logique dédiée."""
        a_regenerer = self.filtered(lambda m: m.is_facture_energie and m.state == 'draft')
        for move in a_regenerer:
            move._recomposer_lignes_generees()

        posted = super()._post(soft=soft)
        for move in posted.filtered(lambda m: m.regularisation_id):
            move.regularisation_id._solder_provisions()
        for move in posted.filtered(lambda m: m.is_facture_energie):
            move._imputer_cheques_energie()
        return posted

    def unlink(self):
        """Autorise la suppression EN CASCADE des lignes générées (#266) : le
        contexte `souscription_move_unlink` lève la garde `ondelete` de
        `account.move.line` (`_empecher_suppression_directe_ligne_generee`)
        pour les lignes de CE move — supprimer la facture reste le geste de
        correction documenté (dé-fige la Période, ADR 0014/0007), la cascade
        ORM (`account.move.line.move_id`, `ondelete='cascade'`) ne doit jamais
        être bloquée par cette garde."""
        self = self.with_context(souscription_move_unlink=True)
        return super().unlink()

    # === Provenance des lignes (#266, tranche 2 du PRD #264, ADR 0014 amendé) ===
    #
    # Point d'entrée unique : composer les lignes GÉNÉRÉES de CE move, résolu
    # par sa source (periode_id / regularisation_id, jamais les deux —
    # `_check_source_exclusive`). Chaque composeur par source
    # (`periode._composer_lignes`, `refacturation._composer_ligne`,
    # `regularisation._composer_lignes`) pose lui-même le flag de provenance
    # — ce point d'entrée ne fait qu'agréger, résolu par la source.

    def _composer_lignes_generees(self):
        """Compose les lignes GÉNÉRÉES de ce move, résolu par sa source.

        Source Période (mensuelle) : ses lignes propres (sections,
        abonnement, énergie, notes TURPE — snapshot figé, ADR 0006, même
        grille qu'à la création : ``get_grille_active`` sur ``date_fin``/
        ``regime_prix_periode``) + les Refacturations actuellement *à
        refacturer* de la Souscription (ADR 0009) — même règle qu'à la
        création (`souscription._facturer_refacturations`) : une Refacturation
        entrée en file après la création du brouillon est donc rassemblée ici
        si ce move est régénéré à l'émission.

        Source Régularisation : ses lignes projetées (grille × cadran + notes
        par mois, ADR 0030 décision 3) — pas de rassemblage de Refacturations
        sur ce chemin (jamais fait aujourd'hui, inchangé).

        Vide si ni l'un ni l'autre (facture hors énergie) : n'est jamais
        appelée dans ce cas (cf. `_post`/`_recomposer_lignes_generees`, filtre
        `is_facture_energie`)."""
        self.ensure_one()
        if self.periode_id:
            periode = self.periode_id
            grille = self.env['grille.prix'].get_grille_active(periode.date_fin, regime=periode.regime_prix_periode)
            lignes = periode._composer_lignes(grille)
            prestas = periode.souscription_id._refacturations_a_rassembler(self)
            return lignes + [presta._composer_ligne() for presta in prestas]
        if self.regularisation_id:
            return self.regularisation_id._composer_lignes()
        return []

    def _recomposer_lignes_generees(self):
        """Recompose PRÉSERVANTE (#266) : supprime les lignes flaguées
        existantes de CE move puis les remplace par une composition fraîche
        depuis la source (`_composer_lignes_generees`) — toute ligne NON
        flaguée (geste commercial en euros, ligne posée par un autre module :
        arrondi, escompte…) survit intacte. La facture émise = la source à
        l'instant T + les lignes manuelles (AC #266).

        Source Période : rassemble aussi les Refacturations fraîches (voir
        `_composer_lignes_generees`) et pose leur lien (`facture_id`) —
        même geste que le chemin de création
        (`souscription._facturer_refacturations`), rejoué ici. Ré-interroger
        la file *après* avoir recomposé les lignes est correct : composer et
        rassembler lisent la même file (`_refacturations_a_rassembler`), et
        rien ne la modifie entre les deux appels dans ce flux synchrone.

        Contexte `souscription_regenere_lignes` : lève la garde `ondelete`
        (#266) pour la suppression, ici, des lignes flaguées qu'on remplace —
        seule cette méthode (et `unlink()`, cascade) pose ce contexte."""
        self.ensure_one()
        self.invoice_line_ids.filtered('souscription_ligne_generee').with_context(
            souscription_regenere_lignes=True
        ).unlink()
        self.write({'invoice_line_ids': self._composer_lignes_generees()})
        if self.periode_id:
            self.periode_id.souscription_id._refacturations_a_rassembler(self).facture_id = self

    def _verifier_regularisation_emise_immuable(self):
        """Une facture de régularisation ÉMISE est immuable (grill #259) : le
        tampon d'émission a déjà soldé les mensuelles couvertes, et ni sa
        réversion ni celle du marqueur de clôture (#248) ne sont des gestes du
        métier — un re-post re-consommerait les écarts figés (double-tampon).
        La correction vit ailleurs : nouvelle Régularisation (le mesuré
        raffiné fait renaître l'écart) ou avoir (l'avoir ne porte pas le lien,
        `copy=False`)."""
        for move in self:
            if move.regularisation_id and move.state == 'posted':
                raise UserError(
                    'Une facture de régularisation émise est immuable : corrigez par une '
                    "nouvelle régularisation (un mesuré raffiné fait renaître l'écart) "
                    'ou par un avoir — jamais par remise en brouillon ou annulation.'
                )

    def button_draft(self):
        self._verifier_regularisation_emise_immuable()
        return super().button_draft()

    def button_cancel(self):
        self._verifier_regularisation_emise_immuable()
        return super().button_cancel()

    def _get_report_base_filename(self):
        """Nom de fichier personnalisé pour les factures d'énergie"""
        self.ensure_one()
        if self.is_facture_energie and self.souscription_id:
            return f'Facture_Energie_{self.souscription_id.name}_{self.name}'
        return super()._get_report_base_filename()

    def _imputer_cheques_energie(self):
        """Impute en FIFO (par date d'expiration) les *outstanding credits* des
        chèques énergie **validés** de l'usager·ère sur **cette** Facture qui
        vient d'être **émise** (#172, ADR 0026 ; déplacé de la création à
        l'émission par la tranche 1 du PRD #264, #265). Appelée depuis
        ``_post()`` — jamais au brouillon — pour toute facture d'énergie
        (``is_facture_energie``) réellement postée : la mécanique est
        partagée entre la mensuelle (``souscription.periode._creer_facture``)
        et la facture de régularisation
        (``souscription.regularisation._creer_facture``, tranche 5, #237),
        toutes deux créées en **brouillon** — le point de couture ne dépend
        que de la Facture et de son partenaire, jamais de sa source (Période
        ou Régularisation). Aucun effet si l'usager·ère ne détient aucun
        chèque validé à solde positif : la Facture postée reste sans
        imputation, comportement de facturation inchangé (#170,
        non-régression).

        Le lettrage **natif** d'Odoo fait tout le travail — même mécanique que
        le widget « Outstanding credits »/``js_assign_outstanding_line`` : seul
        l'ordre FIFO par expiration est du code métier ici. Le plafonnement
        (``min(solde, total)``, jamais de ligne/solde négatif) et le report du
        reliquat sur la Facture suivante sont natifs à
        ``account.move.line.reconcile()``, jamais réimplémentés — la
        réconciliation exige des écritures **postées** des deux côtés, déjà
        garanti par l'appel depuis ``_post()`` (plus de ``action_post()``
        interne ici).
        """
        self.ensure_one()
        Cheque = self.env['souscription.cheque_energie']
        cheques = Cheque.search([('partner_id', '=', self.partner_id.id), ('state', '=', 'valide')]).sorted(
            'date_expiration'
        )
        cheques = cheques.filtered(lambda c: c.solde > 0.0)
        if not cheques:
            return

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
