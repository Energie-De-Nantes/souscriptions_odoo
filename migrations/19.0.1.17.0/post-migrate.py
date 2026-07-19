"""Heal des campagnes en vol : porte « Gestes commerciaux » (#287, ADR 0025).

`gestes_commerciaux` s'insère entre `creer_factures` et `emettre_factures`
dans `ETAPES_CAMPAGNE` (souscription_campagne.py) — `emettre_factures` gagne
`gestes_commerciaux` comme second prérequis. Mais `_seed_etapes` n'amorce les
lignes d'étape qu'à la CRÉATION de la campagne : une campagne déjà ouverte
avant cette version n'a pas de ligne `souscription.campagne.etape` pour ce
code. `_compute_etat_prerequis` d'`emettre_factures` lit alors
`freres.get('gestes_commerciaux')` -> None (absent du dict, pas juste
« pas fait ») -> `all(...)` False -> bloquée à vie : les factures en attente
ne partent plus, sans script pour réparer.

`sequence=65`, volontairement entre `creer_factures` (60) et
`emettre_factures` (70) — les séquences qu'une campagne en vol tient déjà
depuis SA création, avec l'ancien catalogue à 9 étapes. On n'y touche PAS
(pas de re-séquençage des lignes existantes) : seule la ligne manquante est
insérée, à la bonne place visuelle entre les deux.

SQL direct (comme 19.0.1.14.0/19.0.1.16.0/post-migrate.py) : `type_etape` est
posé à la valeur que `_compute_type_etape` calculerait de toute façon pour ce
code ('porte', cf. ETAPES_CAMPAGNE) — un backfill SQL brut d'un champ stocké
compute n'est jamais recalculé tout seul par un simple accès ORM ultérieur.
Même motif pour `phase` (#342, ADR 0036 décision 14, champ ajouté après ce
script mais rejoué par tout `-u` multi-versions partant d'une base plus
ancienne) : 'facturer', la valeur que `_compute_phase` calculerait pour
`gestes_commerciaux`.
`valide` + le drapeau de lancement à FALSE (porte non validée, jamais
lancée) : l'état de départ normal d'une porte fraîchement seedée. Idempotent :
n'insère que pour les campagnes qui n'ont pas encore la ligne.

Nom de colonne détecté à l'exécution (`lance` OU `demande`) : dans un `-u`
multi-versions, Odoo exécute TOUS les pre-migrate applicables (par ordre de
version) AVANT le moindre post-migrate — sur une base < 1.17.0, le pre-1.19.0
(#326, renommage `lance` -> `demande`) tourne donc avant CE script, dont
l'INSERT à liste de colonnes explicite planterait sur `lance`. Même idiome
de garde `information_schema.columns` que le pre-1.19.0.
"""


def migrate(cr, version):
    cr.execute(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'souscription_campagne_etape' AND column_name IN ('lance', 'demande')
        """
    )
    (colonne_lancement,) = cr.fetchone()
    cr.execute(
        f"""
        INSERT INTO souscription_campagne_etape
            (campagne_id, code, sequence, type_etape, phase, valide, {colonne_lancement},
             create_uid, write_uid, create_date, write_date)
        SELECT c.id, 'gestes_commerciaux', 65, 'porte', 'facturer', FALSE, FALSE, 1, 1, NOW(), NOW()
        FROM souscription_campagne_facturation c
        WHERE NOT EXISTS (
            SELECT 1 FROM souscription_campagne_etape e
            WHERE e.campagne_id = c.id AND e.code = 'gestes_commerciaux'
        )
        """
    )
