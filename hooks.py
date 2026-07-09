"""Setup comptable du chèque énergie (#170, ADR 0026).

Le journal « Chèques énergie » et le compte « à recevoir de l'État » sont
posés ici plutôt qu'en `data/*.xml` statique : `account.account.company_ids`
est un many2many *requis* (variante multi-société) et l'outstanding receipts
account d'une méthode de paiement entrante (`account.payment.method.line`,
compute stocké auto-créé par le journal) n'est pas assignable proprement en
`<record>` déclaratif.

**Sans xmlid, exprès.** On crée en `search`-or-`create` par *code*, pas via
`_load_records` + xmlid : un record xmlid'é créé en `post_init_hook` est
*purgé* par le nettoyage de fin d'install d'Odoo (il n'est pas dans le jeu
d'xmlids « vus » pendant le chargement des data → considéré orphelin →
supprimé, cascade sur le journal). Un record sans ir.model.data n'y est pas
soumis : il survit. C'est aussi ce qui rend la fonction sûre à appeler *à la
volée* depuis `action_valider` (auto-réparation si l'install ne l'a pas posé).

ponytail : une seule société (`env.company`), pas de boucle multi-société —
ni ce module ni le reste du repo ne gèrent le multi-company aujourd'hui.
Ajouter la boucle sur `res.company.search([])` si ça change.

Idempotent : recherche par code avant de créer, et le correctif de
`payment_account_id` ne réécrit que si nécessaire — rejouable sans doublon.
"""

CODE_COMPTE_CHEQUE_ENERGIE = '467100'
CODE_JOURNAL_CHEQUE_ENERGIE = 'CHEN'


def setup_cheque_energie_compta(env):
    """Crée (ou retrouve) le compte + le journal chèque énergie et renvoie le
    journal. Idempotent, sans xmlid (cf. docstring du module)."""
    company = env.company

    # ponytail : classe 4 générique (« autres comptes débiteurs »), pas un
    # code PCG spécifique État (44x) — paramétrage à préciser par la compta,
    # au même niveau que la neutralisation des produits 331/332 (cf.
    # migrations/19.0.1.8.0/post-migrate.py). `asset_receivable` (et non
    # `asset_current`) est requis : c'est ce qui rend le compte `reconcile`
    # et compatible avec `_get_valid_payment_account_types()` côté
    # `account.payment` (ADR 0026 §2).
    compte = env['account.account'].search(
        [('code', '=', CODE_COMPTE_CHEQUE_ENERGIE), ('company_ids', 'in', company.id)], limit=1
    )
    if not compte:
        compte = env['account.account'].create(
            {
                'name': "Chèques énergie à recevoir de l'État",
                'code': CODE_COMPTE_CHEQUE_ENERGIE,
                'account_type': 'asset_receivable',
                'company_ids': [(6, 0, [company.id])],
            }
        )

    journal = env['account.journal'].search(
        [('code', '=', CODE_JOURNAL_CHEQUE_ENERGIE), ('company_id', '=', company.id)], limit=1
    )
    if not journal:
        journal = env['account.journal'].create(
            {
                'name': 'Chèques énergie',
                'code': CODE_JOURNAL_CHEQUE_ENERGIE,
                'type': 'cash',
                'company_id': company.id,
                'default_account_id': compte.id,
            }
        )

    # La ligne de méthode de paiement entrante manuelle est auto-créée par le
    # journal (compute stocké, ADR 0026) : sans son outstanding account
    # explicite, `action_post()` sur le paiement échoue dès que la
    # comptabilité complète est installée ("outstanding payments/receipts
    # account" manquant, cf. account_payment.py:_prepare_move_line_default_vals).
    journal.inbound_payment_method_line_ids.filtered(lambda l: l.payment_account_id != compte).write(
        {'payment_account_id': compte.id}
    )
    return journal
