"""Retrait de `cheque_energie` du Mode de paiement (#184, #183).

Le chèque énergie est un tiers-payeur (ADR 0026, CONTEXT.md « Chèque
énergie ») : il s'impute sur les Factures avant règlement, il ne règle pas
le solde. Le proposer comme Mode de paiement contredisait le modèle — la
valeur est retirée des deux Selections (souscription.souscription,
raccordement.demande).

Les enregistrements existants portant cette valeur sont vidés (pas de mode
devinable, à renseigner à la main) ; les autres valeurs ne sont pas
touchées. Idempotent, no-op sur install neuve ou base sans occurrence.
"""


def migrate(cr, version):
    cr.execute("UPDATE souscription_souscription SET mode_paiement = NULL WHERE mode_paiement = 'cheque_energie'")
    cr.execute("UPDATE raccordement_demande SET mode_paiement = NULL WHERE mode_paiement = 'cheque_energie'")
