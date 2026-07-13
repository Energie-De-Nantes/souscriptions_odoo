"""Garde de nettoyage avant suppression des types morts de `type_periode`
(#239, ADR 0030 décision 3 — la Période redevient purement mensuelle).

`regularisation` et `ajustement` n'ont **jamais été portés par une donnée** :
la Régularisation est un modèle propre (`souscription.regularisation`) depuis
la tranche 4 (#236), et ces valeurs de sélection n'ont jamais été écrites par
le système en place. La sélection Python passe à `mensuelle` seul dans cette
même version — si une ligne existe malgré tout avec l'un de ces types, c'est
une anomalie qui doit être nettoyée à la main *avant* l'upgrade, pas absorbée
silencieusement. Échec bruyant : on lève avant que le schéma ne change, pour
que l'anomalie remonte plutôt que de laisser une donnée orpheline hors
sélection.
"""


def migrate(cr, version):
    cr.execute("SELECT COUNT(*) FROM souscription_periode WHERE type_periode IN ('regularisation', 'ajustement')")
    (nb,) = cr.fetchone()
    if nb:
        raise Exception(
            f'{nb} souscription.periode porte(nt) encore un type_periode mort '
            "('regularisation'/'ajustement') — nettoyage manuel requis avant l'upgrade "
            'vers 19.0.1.15.0 (#239, ADR 0030 décision 3).'
        )
