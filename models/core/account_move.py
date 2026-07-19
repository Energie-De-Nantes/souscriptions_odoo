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

    # Lettre du mois (#313, ADR 0034) : compute NON stocké — la facture
    # TIRE la lettre via son propre mois (`periode_id.mois` -> campagne du
    # même mois, `UNIQUE(mois)` rend la résolution non ambiguë), la campagne
    # ne pousse jamais rien. Pas de période (régularisation) -> pas de
    # campagne -> lettre vide, sans cas particulier : la source
    # `souscription.campagne.facturation.lettre_mois` porte l'éditorial,
    # jamais la Facture.
    lettre_du_mois = fields.Html(string='Lettre du mois', compute='_compute_lettre_du_mois')

    @api.depends('periode_id.mois')
    def _compute_lettre_du_mois(self):
        Campagne = self.env['souscription.campagne.facturation']
        for move in self:
            mois = move.periode_id.mois
            campagne = Campagne.search([('mois', '=', mois)], limit=1) if mois else Campagne
            move.lettre_du_mois = campagne.lettre_mois

    # QR-code Moneko (#313, ADR 0034 « Conséquences non évidentes ») :
    # compute NON stocké, même idiome que `lettre_du_mois` — le template
    # reste bête (un `t-if` + un `t-att-src`, aucun `search`), la résolution
    # vit ici. Pas de `@api.depends` porteur : la source n'est pas un champ
    # de CE move mais la config globale du module (`souscription.mail.
    # config`), donc pas de champ à déclarer en dépendance — recalculé à
    # chaque nouvel accès (cache par recordset fraîchement browsé), comme
    # `lettre_du_mois` recalcule à chaque facture nouvellement composée.
    # `sudo()` : la config n'accorde la lecture qu'au groupe manager
    # (ADR 0034) — un envoi déclenché par un compte qui n'a que
    # `group_souscriptions_user` ne doit jamais planter sur cette
    # résolution annexe (pas plus qu'une absence de QR ne doit être une
    # erreur : « pas de donnée -> pas de bloc »).
    # ponytail: `@api.depends()` vide -> pas d'invalidation automatique si
    # le QR change APRÈS un premier accès sur le même recordset, dans le
    # même environnement (cache ORM). Sans ceiling pratique aujourd'hui : un
    # envoi de mail browse une facture fraîche. Si un jour un long-vécu
    # (cron, session) lit ce champ avant ET après un changement de QR,
    # invalider explicitement (`move.invalidate_recordset(['qr_moneko_image_url'])`).
    qr_moneko_image_url = fields.Char(string='URL du QR-code Moneko', compute='_compute_qr_moneko_image_url')

    @api.depends()
    def _compute_qr_moneko_image_url(self):
        config = self.env['souscription.mail.config'].sudo().search([], limit=1)
        url = config._qr_moneko_image_url() if config else False
        for move in self:
            move.qr_moneko_image_url = url

    @api.depends('periode_id', 'regularisation_id', 'souscription_id')
    def _compute_is_facture_energie(self):
        """Détermine si c'est une facture d'énergie (souscription électricité) —
        source Période (mensuelle) OU Régularisation (tranche 5, #237)."""
        for move in self:
            move.is_facture_energie = bool((move.periode_id or move.regularisation_id) and move.souscription_id)

    def _facture_de_la_source(self):
        """LA facture de ma source — autorité unique (celle du gel,
        `souscription.periode._est_facturee_emise` / `regularisation.
        facture_id`), jamais le lien brut `periode_id`/`regularisation_id`
        (#318). Un avoir PORTE sa source (`periode_id` n'a pas `copy=False`
        — CONTEXT.md « Avoir » : traçabilité, Souscription, Mode de
        paiement) mais n'est jamais SA facture : `facture_id` ne désigne que
        l'`out_invoice` (`souscription.periode._compute_facture_id` filtre
        sur `move_type == 'out_invoice'`). `_post()` s'appuie là-dessus pour
        ne régénérer que la vraie facture de la source, jamais un avoir qui
        la reverse.

        Asymétrie porteuse côté Régularisation : son `_compute_facture_id`
        retient `out_invoice` **et** `out_refund` — une Régularisation à net
        négatif s'émet EN TANT QU'avoir et reste SA facture, donc régénérée
        et tamponnée normalement (CONTEXT.md « Avoir »). Un avoir de
        CORRECTION, lui, n'atteint jamais cette branche : `regularisation_id`
        est `copy=False` (#259)."""
        self.ensure_one()
        return (self.periode_id or self.regularisation_id).facture_id

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
        de couture ne fait plus que l'appeler (#255, revue d'architecture).

        Le filtre de régénération passe par `_facture_de_la_source()`, pas
        par le lien brut (#318) : un avoir (`out_refund`) émis sur une
        Facture d'énergie porte `periode_id`/`regularisation_id` (pas
        `copy=False`, CONTEXT.md « Avoir ») mais n'est jamais *la* facture
        de sa source — sans ce filtre il serait recomposé depuis la Période
        (lignes doublées) et raflerait les Refacturations en file.

        Filet final de la régénération au fil de l'eau : carte complète (5
        points d'entrée, 4 clés de contexte) dans la bannière ci-dessous."""
        a_regenerer = self.filtered(
            lambda m: m.is_facture_energie and m.state == 'draft' and m._facture_de_la_source() == m
        )
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
        ici.

        Producteur de la clé de contexte `souscription_move_unlink` : carte
        complète dans la bannière « Régénération au fil de l'eau » ci-dessous."""
        self = self.with_context(souscription_move_unlink=True)
        return super().unlink()

    # === Régénération au fil de l'eau (#267, carte #364) ===
    #
    # Invariant : le brouillon = sa source à l'instant T + les lignes
    # manuelles (#266). Tout converge vers `_recomposer_lignes_generees`
    # ci-dessous, DÉCLENCHÉ par 5 points d'entrée dans 4 fichiers — l'ORM
    # impose cet éparpillement (verrou ici, dédup là), le mécanisme central
    # reste unique. Carte, pas refactor : les lettres (a)-(d) citées par les
    # docstrings des sites sont définies UNIQUEMENT ici.
    #
    # Points d'entrée :
    #   (a) pull méta-périodes -> `souscription.periode._rafraichir_depuis_meta`
    #   (b) édition facturable  -> `souscription.periode.write()`
    #   (c) insertion F15       -> `souscription.refacturation._recomposer_brouillons_mensuels`
    #   (d) recalcul régul      -> `souscription.regularisation.action_recalculer`
    #   + filet final à l'émission : `_post()` ci-dessus (ordre : cf. sa docstring)
    #
    # Clés de contexte (produite par -> consommée par : effet) :
    #   regularisation_tampon        `regularisation._solder_provisions` -> `periode.write` : lève le verrou #14
    #   souscription_tampon_emission `periode._tamponner_provision` -> `periode.write` : évite une double recomposition
    #   souscription_regenere_lignes `_recomposer_lignes_generees` -> `account.move.line.ondelete` : lève la garde #266
    #   souscription_move_unlink     `unlink()` ci-dessus -> `account.move.line.ondelete` : lève la garde #266
    #
    # Risque connu (PR #259, non résolu) : re-poster un move de Régularisation
    # (post -> button_draft -> re-post) rejoue `_solder_provisions` (+=) —
    # gardé par `_verifier_regularisation_emise_immuable` ci-dessous, qui
    # interdit le `button_draft`/`button_cancel` d'une régularisation ÉMISE.

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
        grille qu'à la création : ``get_grille_active`` sur ``date_debut``/
        ``regime_prix_periode`` — la grille engagée, en lockstep avec la
        création, ADR 0032) + les Refacturations actuellement *à
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
            grille = self.env['grille.prix'].get_grille_active(periode.date_debut, regime=periode.regime_prix_periode)
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
        seule cette méthode (et `unlink()`, cascade) pose ce contexte.

        Mécanisme central de la régénération au fil de l'eau (#267) : les 5
        points d'entrée et le protocole de contexte sont cartographiés dans
        la bannière « Régénération au fil de l'eau », plus haut dans ce
        fichier."""
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

    def _get_mail_template(self):
        """Racine UNIQUE de résolution du modèle d'envoi (#313, ADR 0034) :
        consommée aussi bien par le bouton unitaire que par l'envoi en masse
        (`account.move.send._get_default_mail_template_id`), donc un renvoi
        manuel produit exactement le même mail que la première émission —
        jamais un mail Odoo nu, sans la Lettre du mois.

        Scopé sur facture CLIENT d'énergie (`move_type == 'out_invoice'` ET
        `is_facture_energie`) : le test sur `move_type` est **porteur**, pas un
        garde-fou redondant — un avoir de Régularisation porte bien
        `regularisation_id` et une `souscription_id`
        (`souscription_regularisation._creer_facture`, `move_type='out_refund'`),
        donc `is_facture_energie` y vaut **True**. C'est `move_type` seul qui
        renvoie les avoirs sur `super()` — le modèle standard d'Odoo. Toute
        facture hors énergie y retombe aussi.

        `all(...)` sur `self`, jamais `self.is_facture_energie` nu (grill
        2026-07-15, 3e passage) : le core appelle ce hook sur un recordset
        potentiellement multi-facture (envoi en masse), et lire un champ
        scalaire sur un `self` de plusieurs enregistrements lève `Expected
        singleton` — un renvoi groupé de plusieurs factures d'énergie
        plantait avant même d'atteindre l'envoi. `all(...)` rend le même
        verdict qu'avant pour un singleton, et ne casse plus sur un lot."""
        if all(m.is_facture_energie and m.move_type == 'out_invoice' for m in self):
            return self.env.ref('souscriptions_odoo.mail_template_facture_energie')
        return super()._get_mail_template()

    # === Encaissement une-clic pour les modes attestation-pure (#290, ADR 0033) ===
    #
    # `monnaie_locale` et `especes` n'ont **aucune** trace bancaire, jamais
    # (CONTEXT.md « Mode de paiement ») : la facturiste est l'unique source de
    # vérité de l'encaissement. Prélèvement, virement et chèque restent 100 %
    # natifs — pas de bouton, pas de résolveur pour eux.

    def _resoudre_journal_encaissement(self):
        """Résout le journal cible de l'encaissement une-clic selon
        `mode_paiement` — jamais par `type` (même idiome que
        `souscription.sepa.mandat._resoudre_journal_sdd`, gravé par ADR 0033
        amendé : un rôle de journal possédé par la société est un pointeur
        `res.company`, `type` n'est jamais un discriminateur de rôle) :
        - `monnaie_locale` -> pointeur société `journal_monnaie_locale_id`
          (calqué sur `res.company.currency_exchange_journal_id`) ;
        - `especes` -> pointeur société `journal_especes_id` (#298, calqué
          sur le même idiome — robuste au journal CHEN du chèque énergie,
          un autre journal `type='cash'` posé par le `post_init_hook` à
          chaque install, qui cassait la résolution « cash unique »
          précédente).
        Erreur explicite si le journal est absent — jamais de journal
        deviné sur un chemin monétaire."""
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
            journal = self.company_id.journal_especes_id
            if not journal:
                raise UserError(
                    _(
                        'Aucun journal « espèces » configuré pour %(societe)s : renseignez le champ '
                        "Journal espèces de la société avant d'encaisser.",
                        societe=self.company_id.name,
                    )
                )
            return journal
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
