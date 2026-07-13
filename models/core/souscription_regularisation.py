from odoo import api, fields, models
from odoo.exceptions import UserError


class SouscriptionRegularisation(models.Model):
    """Régularisation (solde) — CONTEXT.md, ADR 0030 décisions 3-4, tranches 4
    et 5 du PRD #231. Même motif que la Refacturation (ADR 0009) : modèle
    indépendant de la Période, rassemblé sur une Facture.

    En-tête par Souscription : dates couvertes **informatives** (dérivées des
    lignes, jamais une fenêtre stockée — les candidats se sélectionnent par
    l'écart et le verdict, ADR 0030 décision 4) + lignes **typées** (une par
    grille × cadran). `_recalculer()` (re)construit les lignes, à volonté —
    mais refuse dès qu'une Facture existe (``facture_id``, tranche 5, #237) :
    l'« état facturée » dérivé du lien **verrouille** le recalcul, faute de
    quoi la Facture divergerait silencieusement des lignes qui l'ont projetée.
    Le tampon de l'énergie facturée (tranche 6, #238) reste hors périmètre.
    """

    _name = 'souscription.regularisation'
    _description = 'Régularisation (solde)'

    souscription_id = fields.Many2one(
        'souscription.souscription', required=True, ondelete='cascade', string='Souscription'
    )

    # Dates couvertes, purement informatives (ADR 0030 décision 4) : posées
    # par `_recalculer()` sur le span des mois EXAMINÉS (verdict connu, non
    # legacy), écarts nuls compris — le solde couvre tout le span, pas
    # seulement les mois à écart. Jamais une borne des candidats du prochain
    # recalcul.
    date_debut = fields.Date(string='Début couvert', readonly=True)
    date_fin = fields.Date(string='Fin couverte', readonly=True)

    ligne_ids = fields.One2many('souscription.regularisation.ligne', 'regularisation_id', string='Lignes')

    montant_total = fields.Float(string='Montant total (€)', compute='_compute_montant_total', store=True)

    # Relevés frais en justificatif (décision 5 : bi-parent, `periode_id`
    # devient optionnel sur `souscription.releve`) — pas encore alimenté par
    # `_recalculer()` dans cette tranche (aucune AC ne le requiert) ; le champ
    # existe pour que le lien et sa contrainte « exactement un » soient posés.
    releve_ids = fields.One2many('souscription.releve', 'regularisation_id', string="Relevés d'index (justificatif)")

    # Signalements de la dernière exécution de `_recalculer()` (mois hors
    # candidats, souscription non communicante écartée…) — surface de review
    # du·de la facturiste, même idiome que `wizard.resultat`.
    signalements = fields.Text(string='Signalements', readonly=True)

    # Lien Régularisation ↔ Facture (ADR 0030 décision 5) : `account.move.
    # regularisation_id` est l'unique source de vérité (même motif que
    # `souscription.periode.facture_id`/`move_ids`, ADR 0004) ; `facture_id`
    # en est dérivé. La Facture peut être un avoir (`out_refund`, net négatif,
    # tranche 5 #237) — les deux types comptent comme « facturée ».
    move_ids = fields.One2many('account.move', 'regularisation_id', string='Documents liés', readonly=True)
    facture_id = fields.Many2one(
        'account.move',
        string='Facture (ou avoir)',
        compute='_compute_facture_id',
        store=True,
        help='Facture (out_invoice) ou avoir (out_refund) projeté depuis cette Régularisation.',
    )

    # État dérivé du lien (aucun champ saisi, CONTEXT.md « Régularisation
    # (solde) ») : « facturée » dès qu'une Facture référence cette
    # Régularisation — verrouille alors `_recalculer()` (tranche 5, #237).
    etat = fields.Selection(
        [('brouillon', 'Brouillon'), ('facturee', 'Facturée')],
        string='État',
        compute='_compute_etat',
        store=True,
    )

    @api.depends('ligne_ids.montant')
    def _compute_montant_total(self):
        for regul in self:
            regul.montant_total = sum(regul.ligne_ids.mapped('montant'))

    @api.depends('move_ids.move_type')
    def _compute_facture_id(self):
        for regul in self:
            factures = regul.move_ids.filtered(lambda m: m.move_type in ('out_invoice', 'out_refund'))
            regul.facture_id = factures[:1]

    @api.depends('facture_id')
    def _compute_etat(self):
        for regul in self:
            regul.etat = 'facturee' if regul.facture_id else 'brouillon'

    def action_recalculer(self):
        self.ensure_one()
        self._recalculer()

    # === Calcul des candidats (ADR 0030 décision 4) ===
    #
    # Candidats : mois FACTURÉS (facture_id ou facture_legacy_ref, même
    # convention que `creer_factures`) à écart non nul, dont le mesuré est
    # connu (verdict réelle/estimée), non soldés en legacy
    # (`legacy_regularisee`, PRD #207/#208) et de compteur communicant. Aucune
    # fenêtre stockée : chaque appel repart de zéro sur TOUTES les Périodes
    # facturées de la Souscription — recalculable à volonté, idempotent à
    # données constantes.

    def _recalculer(self):
        """(Re)construit les lignes depuis les mois candidats — supprime les
        lignes existantes puis reconstruit entièrement (idempotent à données
        constantes, AC #236).

        Refuse dès qu'une Facture existe (``facture_id``, tranche 5, #237) :
        une Régularisation facturée est verrouillée, au même titre qu'une
        Période facturée (#14) — recalculer romprait silencieusement le lien
        entre les lignes projetées et le document légal déjà émis. Pour
        corriger : supprimer la Facture (ce qui dé-fige la Régularisation) ou
        émettre une nouvelle Régularisation.
        """
        self.ensure_one()
        if self.facture_id:
            raise UserError(
                f'{self.souscription_id.name} : régularisation déjà facturée, recalcul interdit. '
                'Supprimez la facture pour corriger, ou créez une nouvelle régularisation.'
            )
        souscription = self.souscription_id
        self.ligne_ids.unlink()

        facturees = souscription.periode_ids.filtered(
            lambda p: p.type_periode == 'mensuelle' and (p.facture_id or p.facture_legacy_ref)
        )
        if not facturees:
            self.write({'signalements': False, 'date_debut': False, 'date_fin': False})
            return

        signalements = []

        # Compteur communicant (ADR 0030 décision 4, v1 scopée) : vérifié sur
        # la Période facturée la plus récente — un statut vide (donnée
        # ancienne, jamais atterrie en v3) ne bloque pas, seul un statut
        # explicitement non communicant écarte toute la Souscription.
        derniere = facturees.sorted('mois')[-1]
        if derniere.statut_communication and derniere.statut_communication != 'communicante':
            signalements.append(
                f'{souscription.name} : compteur non communicant, régularisation écartée (hors périmètre v1, ADR 0030).'
            )
            self.write({'signalements': '\n'.join(signalements), 'date_debut': False, 'date_fin': False})
            return

        # Rafraîchit le mesuré (scope régul de la tranche 2, #235) avant de
        # lire les verdicts — un appel par mois représenté, jamais une plage :
        # chaque appel rend son propre rapport (conservées/rafraîchies…),
        # corrélé sans ambiguïté au mois qui vient d'être demandé (pas de
        # parsing de libellés à travers deux conventions de format).
        Service = self.env['souscription.pull.meta.periodes.service']
        fraiches = set()
        for mois in sorted(set(facturees.mapped('mois'))):
            _creees, _rafraichies, _inchangees, conservees, _erreurs = Service.refresh(souscription, mois, mois)
            if not conservees:
                fraiches.add(mois)

        groupes = {}
        couvertes = self.env['souscription.periode']
        Grille = self.env['grille.prix']
        for periode in facturees.sorted('mois'):
            if periode.qualite not in ('réelle', 'estimée'):
                signalements.append(f'{periode.mois_annee} : verdict {periode.qualite or "absent"}, hors candidats.')
                continue
            if periode.legacy_regularisee:
                continue  # déjà soldée en legacy : exclusion silencieuse, pas une anomalie
            couvertes |= periode  # examiné = couvert, écart nul compris

            cadrans = Grille._CADRANS_FACTURES.get(periode.type_tarif_periode, [])
            ecarts = {cadran: getattr(periode, f'ecart_{cadran}_kwh') for cadran, _label in cadrans}
            if not any(ecarts.values()):
                continue  # écart nul ce mois-ci : rien à régulariser

            grille = Grille.get_grille_active(periode.date_fin, regime=periode.regime_prix_periode)
            note = '' if periode.mois in fraiches else ' (estimation locale)'
            for cadran, ecart in ecarts.items():
                if not ecart:
                    continue
                cle = (grille.id, cadran)
                groupe = groupes.get(cle)
                if groupe is None:
                    groupe = groupes[cle] = {
                        'grille': grille,
                        'cadran': cadran,
                        'debut': periode.date_debut,
                        'fin': periode.date_fin,
                        'ecart': 0.0,
                        'periode_ids': [],
                        'detail': [],
                        # Snapshot du premier mois du groupe (ADR 0006) : le
                        # solidaire est structurel à la Souscription (ne
                        # change pas en cours de route), figé ici pour que la
                        # projection facture (tranche 5, #237) choisisse le
                        # bon produit du catalogue sans relire les Périodes.
                        'tarif_solidaire': periode.tarif_solidaire_periode,
                        'coeff_pro': periode.coeff_pro_periode,
                    }
                groupe['debut'] = min(groupe['debut'], periode.date_debut)
                groupe['fin'] = max(groupe['fin'], periode.date_fin)
                groupe['ecart'] += ecart
                groupe['periode_ids'].append(periode.id)
                groupe['detail'].append(f'{periode.mois_annee} : {ecart:.2f} kWh{note}')

        lignes_vals = []
        for (grille_id, cadran), groupe in groupes.items():
            prix = groupe['grille'].prix_energie_cadran(cadran, groupe['tarif_solidaire'], groupe['coeff_pro'])
            lignes_vals.append(
                (
                    0,
                    0,
                    {
                        'grille_id': grille_id,
                        'cadran': cadran,
                        'date_debut': groupe['debut'],
                        'date_fin': groupe['fin'],
                        'ecart_kwh': groupe['ecart'],
                        'prix_kwh': prix,
                        'periode_ids': [(6, 0, groupe['periode_ids'])],
                        'detail': '\n'.join(groupe['detail']),
                        'tarif_solidaire': groupe['tarif_solidaire'],
                    },
                )
            )

        self.write(
            {
                'ligne_ids': lignes_vals,
                'signalements': '\n'.join(signalements),
                'date_debut': min(couvertes.mapped('date_debut')) if couvertes else False,
                'date_fin': max(couvertes.mapped('date_fin')) if couvertes else False,
            }
        )


class SouscriptionRegularisationLigne(models.Model):
    """Ligne typée de la Régularisation : une par grille × cadran (CONTEXT.md
    « Régularisation (solde) »). Porte la sous-période couverte, la Σ écart
    kWh et le prix historique de sa grille — la facture (tranche 5, #237) en
    sera la projection, notes par mois sous la ligne (`detail`)."""

    _name = 'souscription.regularisation.ligne'
    _description = 'Ligne de régularisation (grille × cadran)'
    _order = 'date_debut'

    regularisation_id = fields.Many2one(
        'souscription.regularisation', required=True, ondelete='cascade', string='Régularisation'
    )

    grille_id = fields.Many2one('grille.prix', required=True, string='Grille de prix')
    cadran = fields.Selection(
        [('base', 'Base'), ('hp', 'Heures pleines'), ('hc', 'Heures creuses')],
        string='Cadran facturé',
        required=True,
    )

    date_debut = fields.Date(string='Début de la sous-période')
    date_fin = fields.Date(string='Fin de la sous-période')

    ecart_kwh = fields.Float(string='Écart (kWh)')
    prix_kwh = fields.Float(string='Prix (€/kWh)', digits=(16, 6))
    montant = fields.Float(string='Montant (€)', compute='_compute_montant', store=True)

    # Snapshot du tarif solidaire (ADR 0013) au moment du calcul des
    # candidats — le solidaire choisit le *Produit de facturation* (compte +
    # TVA isolés) à la projection facture (tranche 5, #237) ; figé ici plutôt
    # que relu sur la Souscription live, même logique de snapshot que la
    # Période (ADR 0006).
    tarif_solidaire = fields.Boolean(string='Tarif solidaire (snapshot)', readonly=True)

    # Mois agrégés dans cette ligne — support du détail et du signalement
    # « estimation locale » (mois conservé au refresh, ADR 0030 décision 1).
    periode_ids = fields.Many2many('souscription.periode', string='Périodes couvertes')
    detail = fields.Text(string='Détail par mois', readonly=True)

    @api.depends('ecart_kwh', 'prix_kwh')
    def _compute_montant(self):
        for ligne in self:
            ligne.montant = ligne.ecart_kwh * ligne.prix_kwh
