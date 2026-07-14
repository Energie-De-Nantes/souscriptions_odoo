from odoo import _, api, fields, models
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
        """Point de couture de l'émission — **unique événement de gel** (ADR
        0032) : tampon de provision Période (ADR 0030 décision 2, #234,
        déplacé de la création à l'émission par la tranche 3 du PRD #264,
        #267), re-génération préservante des lignes (#266, tranche 2 du PRD
        #264), tampon de Régularisation (ADR 0030 décision 4, tranche 6 du
        PRD #231, #238) **et** imputation du chèque énergie (ADR 0026, #172,
        déplacée de la création à l'émission par la tranche 1 du PRD #264,
        #265).

        Ordre gravé (#267, AC « effets observables dans cet ordre ») :
        **tampon -> re-génération finale -> post -> verrou (dérivé) -> solde
        régul -> imputation chèque**. Le tampon doit précéder la
        re-génération : ``_quantite_facturee`` lit le mesuré tant que la
        provision n'est pas tamponnée (#267), donc composer les lignes AVANT
        le tampon figerait une quantité pas encore gelée sur les lignes qui,
        elles, ne seront plus jamais recomposées après ce ``_post()``. Le
        verrou de la Période/des Relevés n'a besoin d'aucun appel : il est
        **dérivé** de ``facture_id.state == 'posted'``
        (``souscription.periode._est_facturee_emise``) — il s'active tout
        seul dès que ``super()._post()`` a tourné.

        Tampon et re-génération se déclenchent AVANT ``super()._post()`` — le
        move est encore brouillon, sa Période pas encore verrouillée, ses
        lignes flaguées éditables — sur ``self`` (pas sur le résultat
        filtré) : même un move programmé dans le futur (``soft=True``, qui
        restera en brouillon) doit voir sa provision tamponnée et ses lignes
        rafraîchies. Le solde régul et l'imputation, eux, ne se déclenchent
        qu'à l'émission RÉELLE : filtrer sur le résultat de
        ``super()._post()``, pas sur ``self``, exclut naturellement les
        moves soft-programmés sans logique dédiée.

        L'imputation elle-même (recherche FIFO des chèques validés,
        lettrage) vit sur `souscription.cheque_energie.imputer()` — ce point
        de couture ne fait plus que l'appeler (#255, revue d'architecture)."""
        a_regenerer = self.filtered(lambda m: m.is_facture_energie and m.state == 'draft')
        for move in a_regenerer:
            if move.periode_id:
                move.periode_id._tamponner_provision()
            move._recomposer_lignes_generees()

        posted = super()._post(soft=soft)
        for move in posted.filtered(lambda m: m.regularisation_id):
            move.regularisation_id._solder_provisions()
        for move in posted.filtered(lambda m: m.is_facture_energie):
            self.env['souscription.cheque_energie'].imputer(move)
        return posted

    def unlink(self):
        """Autorise la suppression EN CASCADE des lignes générées (#266) : le
        contexte `souscription_move_unlink` lève la garde `ondelete` de
        `account.move.line` (`_empecher_suppression_directe_ligne_generee`)
        pour les lignes de CE move — la cascade ORM (`account.move.line.
        move_id`, `ondelete='cascade'`) ne doit jamais être bloquée par cette
        garde.

        Supprimer un brouillon est ANODIN depuis #267 (ADR 0006/0007 amendés,
        ADR 0032) : rien n'est figé avant l'émission, donc rien à
        « dé-figer ». `souscription.refacturation.facture_id` (ondelete='set
        null') remet les Refacturations rassemblées en file, et le statut de
        facturation de la Souscription (dérivé, ADR 0025 §2) retombe tout
        seul à « à facturer » — la cascade native suffit, aucun code dédié
        ici."""
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
            return lignes + prestas._composer_lignes_groupees()
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

    def _get_name_invoice_report(self):
        """Point d'extension natif d'Odoo — porte UNIQUE du design de facture
        d'énergie (#289). `account.report_invoice` (héritée dans
        reports/facture_energie_template.xml) lit ce hook pour choisir entre
        le document standard et `souscriptions_odoo.report_facture_energie` ;
        CE report est ce que le portail client (`get_portal_url`), le PDF
        envoyé par email et Imprimer/Télécharger par défaut traversent tous
        — un seul branchement couvre les trois surfaces.

        Les factures hors énergie (mobilier, etc.) retombent sur `super()`
        automatiquement, sans liste d'exclusion à maintenir. Les avoirs de
        régularisation aussi (hors périmètre #289) : `is_facture_energie` est
        False par conception dessus (`regularisation_id` est `copy=False`,
        cf. `account_move.py` plus haut)."""
        self.ensure_one()
        if self.is_facture_energie:
            return 'souscriptions_odoo.report_facture_energie'
        return super()._get_name_invoice_report()

    # === Encaissement une-clic pour les modes attestation-pure (#290, ADR 0033) ===
    #
    # `monnaie_locale` et `especes` n'ont **aucune** trace bancaire, jamais
    # (CONTEXT.md « Mode de paiement ») : la facturiste est l'unique source de
    # vérité de l'encaissement. Prélèvement, virement et chèque restent 100 %
    # natifs — pas de bouton, pas de résolveur pour eux.

    def _resoudre_journal_encaissement(self):
        """Résout le journal cible de l'encaissement une-clic selon
        `mode_paiement` — jamais par nom (même idiome que
        `souscription.sepa.mandat._resoudre_journal_sdd`) :
        - `monnaie_locale` -> pointeur société `journal_monnaie_locale_id`
          (calqué sur `res.company.currency_exchange_journal_id`) ;
        - `especes` -> journal `type='cash'` unique de la société, résolu à
          la volée (pas de champ stocké, idiome de
          `account.move._search_default_journal`).
        Erreur explicite si le journal est absent ou ambigu — jamais de
        journal deviné sur un chemin monétaire."""
        self.ensure_one()
        if self.mode_paiement == 'monnaie_locale':
            journal = self.company_id.journal_monnaie_locale_id
            if not journal:
                raise UserError(
                    _(
                        'Aucun journal « monnaie locale » configuré pour %(societe)s : renseignez le champ '
                        "Journal monnaie locale de la société avant d'encaisser.",
                        societe=self.company_id.name,
                    )
                )
            return journal
        if self.mode_paiement == 'especes':
            journaux = self.env['account.journal'].search(
                [('type', '=', 'cash'), ('company_id', '=', self.company_id.id)]
            )
            if not journaux:
                raise UserError(
                    _(
                        'Aucun journal de caisse (type « Espèces ») configuré pour %(societe)s : '
                        "configurez-en un avant d'encaisser.",
                        societe=self.company_id.name,
                    )
                )
            if len(journaux) > 1:
                raise UserError(
                    _(
                        'Plusieurs journaux de caisse existent pour %(societe)s, ambiguïté à résoudre avant '
                        "d'encaisser : %(journaux)s.",
                        societe=self.company_id.name,
                        journaux=', '.join(journaux.mapped('name')),
                    )
                )
            return journaux
        raise UserError(
            _(
                'Encaissement une-clic indisponible pour le mode de paiement « %(mode)s ».',
                mode=self.mode_paiement,
            )
        )

    def action_encaisser(self):
        """Le bouton une-clic de la vue « Règlements en attente » (#290, ADR
        0033) : crée, poste et lettre un `account.payment` entrant du
        reste-à-payer intégral sur le journal résolu — même gate que
        `action_valider()` du chèque énergie (ADR 0026), en déléguant le
        lettrage au wizard natif `account.payment.register._create_payments()`
        plutôt qu'en le réimplémentant. Le paiement naît ICI, au clic —
        jamais pré-créé à l'émission (ADR 0033) : sans l'Enterprise
        `account_accountant`, l'enregistrer fait passer la facture
        directement à `paid`, donc le créer c'est affirmer « encaissé »."""
        self.ensure_one()
        journal = self._resoudre_journal_encaissement()
        self.env['account.payment.register'].with_context(active_model='account.move', active_ids=self.ids).create(
            {'journal_id': journal.id, 'amount': self.amount_residual}
        )._create_payments()
