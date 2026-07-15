# Encaissement une-clic pour les modes attestation-pure : réouverture bornée de l'option B (PRD #183)

Instruit le chantier « Bouton de validation d'encaissement manuel » (grillé le 2026-07-14,
prolongement du PRD #183, chantier #290). Le
[PRD #183](https://github.com/Energie-De-Nantes/souscriptions_odoo/issues/183) avait tranché que
**le module ne crée ni paiement, ni batch, ni fichier pain** — *« le module prépare, l'outillage
comptable exécute »* — et avait **explicitement écarté** la génération programmatique des
paiements (« option B du grill »), *« à reconsidérer seulement si les clics mensuels deviennent
une friction avérée »*. Cet ADR **rouvre cette option, de façon bornée**, pour les seuls modes
**attestation-pure**.

## Le déclencheur : une friction *permanente*, pas passagère

La clause de réouverture du PRD #183 parlait d'une friction *avérée*. Le grill a montré qu'elle
n'est pas seulement avérée, elle est **structurelle et permanente** — mais uniquement pour deux
modes. La [refonte du vocabulaire « Mode de paiement »](../../CONTEXT.md) scinde la *saisie
manuelle* selon **ce qui fait foi de l'encaissement** :

- **bancaire-rapprochable** (virement, chèque) — l'argent atterrit sur un **relevé bancaire** ;
  le **rapprochement** fait foi. L'automatisation existe (import de relevé) : la saisie au wizard
  n'est qu'un pis-aller, la friction est *transitoire*.
- **attestation-pure** (monnaie locale / Moneko, espèces) — **aucune trace bancaire, jamais**.
  Aucun relevé ne rapprochera jamais ces encaissements ; l'**attestation à la main** du·de la
  facturiste est l'**unique** source de vérité possible. Ici la friction du wizard natif
  (ouvrir, choisir le journal, valider, par ligne) ne disparaîtra **jamais** d'elle-même.

Prélèvement (batch SEPA → `pain.008`, ~700 paiements/mois vérifiés en prod) et
bancaire-rapprochable (rapprochement de relevé) **restent 100 % natifs** : la séparation
*préparer / exécuter* du PRD #183 tient pour eux. On ne rouvre l'option B que là où elle n'a
structurellement pas d'alternative.

## La décision

Un **bouton une-clic** sur la vue « Règlements en attente », **actif uniquement** pour
`mode_paiement ∈ {monnaie_locale, especes}` et `amount_residual > 0`. Un clic **crée, poste et
lettre** un `account.payment` entrant du **reste-à-payer intégral** sur le journal du mode → la
facture sort de la liste. C'est le **gate** de l'encaissement, calqué sur `action_valider()` du
chèque énergie ([ADR 0026](0026-cheque-energie-tiers-payeur-modele-propre-delegue-paiement.md)),
en délégant le lettrage au wizard natif `account.payment.register._create_payments()` plutôt
qu'en le réimplémentant.

**Le paiement naît au clic, jamais à l'émission.** Sans l'Enterprise `account_accountant`, une
facture n'a pas d'état `in_payment` : enregistrer un paiement la fait passer *directement* à
`paid` (gotcha déjà noté au PRD #183). Dans ce module, **créer un paiement, c'est affirmer
« encaissé »** — on ne peut donc pas le pré-créer à l'émission sans mentir sur la réception des
fonds. L'émission gèle la facture ([ADR 0032](0032-brouillon-gouverne-gel-a-lemission.md)) ;
l'encaissement est un acte aval, daté du jour où l'argent arrive.

**Résolution du journal** (jamais par nom — non-idiome Odoo confirmé en source) :
- `monnaie_locale` → pointeur **`res.company.journal_monnaie_locale_id`**
  (`Many2one('account.journal', domain=[('type','=','bank')], check_company=True)`), calqué sur
  `res.company.currency_exchange_journal_id` du core — car « Moneko » est un rôle nommé parmi
  plusieurs journaux `bank` que `type` ne sait pas distinguer.
- `especes` → **journal `type='cash'` unique** résolu à la volée (idiome de
  `account.move._search_default_journal`), sans champ stocké.
- Garde explicite si le journal est absent ou ambigu — jamais de journal deviné sur un chemin
  monétaire (même idiome que `_resoudre_journal_sdd`).

## Considérées puis rejetées

- **Statu quo (wizard natif)** — la réponse du PRD #183. Correcte pour les modes rapprochables,
  mais laisse la friction *permanente* des modes attestation-pure sans réponse.
- **Pré-création du paiement à l'émission** (brouillon ou posté) — un brouillon ne lettre pas
  (la facture reste dans la liste jusqu'au post : aucun gain, et il faut le ramasser à
  l'annulation/avoir) ; un posté affirme la réception avant que l'argent n'existe. Rejeté.
- **Toggle booléen** (le mot du croquis d'origine) — « encaissé » n'est pas un booléen sur la
  facture mais l'**existence d'un paiement posté et lettré**. Une case qui, décochée, devrait
  **annuler et dé-lettrer** une écriture comptable postée est un piège. Le **bouton une-sens**
  nomme l'acte honnêtement ; la correction d'une erreur passe par l'annulation native du
  paiement (comme le chèque énergie). Rejeté.
- **Marqueur de rôle sur `account.journal`** — non-idiomatique pour un rôle singulier possédé
  par la société ; le pointeur vit sur le modèle qui porte le rôle (`res.company`). Rejeté.

## Conséquences

- Le module crée désormais des `account.payment` **au-delà du seul chèque énergie** ; l'énoncé
  du PRD #183 « le module ne crée aucun paiement » devient « **sauf l'encaissement
  attestation-pure** ». Cet ADR est la trace de cette exception délibérée.
- **Hors périmètre, chantiers propres** : (1) la page **`res.config.settings` « Souscriptions »**
  qui exposera `journal_monnaie_locale_id` (via `related='company_id.…'`) et le reste de la
  configuration — les champs société posés ici la préparent sans rework (#291) ; (2) le bug
  latent de `_resoudre_journal_sdd`, qui lève dès que **plusieurs** journaux exposent la méthode
  `sdd` (le cas de la prod réelle : 4 journaux, mais un seul mandaté) (#292) ; (3) une action
  groupée « Encaisser » multi-sélection, seulement si le clic ligne-à-ligne devient une gêne.

## Amendement (#298) — espèces résout aussi par pointeur société, jamais par `type`

La décision initiale (section « Résolution du journal ») traitait `especes` différemment de
`monnaie_locale` : un journal `type='cash'` **unique**, résolu **à la volée** par recherche,
sans champ stocké. Ce raisonnement s'est révélé faux en pratique : le journal **CHEN** du
chèque énergie ([ADR 0026](0026-cheque-energie-tiers-payeur-modele-propre-delegue-paiement.md))
est **lui aussi** `type='cash'`, posé par le `post_init_hook` à **chaque** install. Dès qu'une
caisse espèces réelle est configurée à côté de CHEN, la recherche « cash unique » cesse d'être
unique et lève une ambiguïté sur un chemin qui n'en a, du point de vue métier, **aucune** — la
facturiste sait parfaitement quelle est *sa* caisse.

**Ce qui change.** `especes` résout désormais par le même idiome que `monnaie_locale` : un
pointeur **`res.company.journal_especes_id`**
(`Many2one('account.journal', domain=[('type','=','cash')], check_company=True)`). Le `search`
« cash unique » et ses deux `UserError` (absence, ambiguïté) sont **supprimés** — remplacés par
la seule garde « pointeur non renseigné ». `monnaie_locale` et le journal CHEN sont inchangés.

**Le principe, gravé pour ne plus être redécouvert au prix d'un bug** : un rôle de journal
**possédé par la société** est **toujours** un pointeur `Many2one` sur `res.company`, **jamais**
résolu par `type` — `type` classe une **famille** de journaux (`bank`, `cash`, `sale`…), il ne
nomme **jamais** un rôle singulier au sein de cette famille. C'était déjà l'idiome de
`monnaie_locale` (calqué sur `res.company.currency_exchange_journal_id` du core) ; ce n'était,
à tort, pas encore celui d'`especes`. Deux précédents core le confirment sans ambiguïté :
`res.company.currency_exchange_journal_id` (`type='bank'` groupe des journaux bancaires, un
seul est *le* journal d'écart de change) et `res.company.tax_cash_basis_journal_id` (`type` ne
distingue pas non plus *le* journal de la comptabilité d'engagement). Toute future extension
d'un rôle de journal société (prélèvement compris, #292) suit ce même principe — jamais une
résolution ad hoc par `type`.
