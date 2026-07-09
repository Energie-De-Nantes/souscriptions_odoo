"""Setup comptable post-install/upgrade (#170, ADR 0026).

Le journal « Chèques énergie » et le compte « à recevoir de l'État » sont
posés ici plutôt qu'en `data/*.xml` statique : `account.account.company_ids`
est un many2many *requis* (variante multi-société) et l'outstanding receipts
account d'une méthode de paiement entrante (`account.payment.method.line`,
compute stocké auto-créé par le journal) n'est pas assignable proprement en
`<record>` déclaratif. `_load_records` est le même primitif que le loader XML
d'Odoo (assignation d'xmlid + respect du `noupdate`) — juste appelé depuis
Python pour pouvoir composer les deux étapes.

ponytail : une seule société (`env.company`), pas de boucle multi-société —
ni ce module ni le reste du repo ne gèrent le multi-company aujourd'hui.
Ajouter la boucle sur `res.company.search([])` si ça change.

Idempotent : `_load_records` recherche l'xmlid avant de créer, et le
correctif de `payment_account_id` ne réécrit que si nécessaire — rejouable à
chaque upgrade sans doublon.
"""

CODE_COMPTE_CHEQUE_ENERGIE = '511800'
CODE_JOURNAL_CHEQUE_ENERGIE = 'CHEN'


def setup_cheque_energie_compta(env):
    company = env.company

    compte = env['account.account']._load_records(
        [
            {
                'xml_id': 'souscriptions_odoo.souscriptions_account_cheque_energie_a_recevoir',
                'noupdate': True,
                'values': {
                    'name': "Chèques énergie à recevoir de l'État",
                    'code': CODE_COMPTE_CHEQUE_ENERGIE,
                    'account_type': 'asset_current',
                    'company_ids': [(6, 0, [company.id])],
                },
            }
        ]
    )

    journal = env['account.journal']._load_records(
        [
            {
                'xml_id': 'souscriptions_odoo.souscriptions_journal_cheque_energie',
                'noupdate': True,
                'values': {
                    'name': 'Chèques énergie',
                    'code': CODE_JOURNAL_CHEQUE_ENERGIE,
                    'type': 'cash',
                    'company_id': company.id,
                    'default_account_id': compte.id,
                },
            }
        ]
    )

    # La ligne de méthode de paiement entrante manuelle est auto-créée par le
    # journal (compute stocké, ADR 0026) : sans son outstanding account
    # explicite, `action_post()` sur le paiement échoue dès que la
    # comptabilité complète est installée ("outstanding payments/receipts
    # account" manquant, cf. account_payment.py:_prepare_move_line_default_vals).
    journal.inbound_payment_method_line_ids.filtered(lambda l: l.payment_account_id != compte).write(
        {'payment_account_id': compte.id}
    )
