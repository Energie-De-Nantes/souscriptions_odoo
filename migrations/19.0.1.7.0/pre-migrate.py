"""Convertit les 7 colonnes index_* de souscription_releve en integer (#132).

Odoo ne convertit pas une colonne `double precision` en `integer` au simple
changement de type de champ (Float -> Integer) : sur `-u`, l'ORM renomme
l'ancienne colonne (ex. `index_hph_moved0`) et recrée une colonne integer
vide -> perte silencieuse des valeurs saisies. Ce script convertit les
colonnes *avant* la synchronisation de schéma (pre-migrate), pour qu'Odoo les
trouve déjà au bon type et n'ait rien à renommer.

Les valeurs en base sont déjà des entiers (kWh, contrat electricore
ADR-0034) : `round(...)::integer` est sans perte, pas une troncature réelle.
Idempotent — ne touche que les colonnes encore en `double precision`/`real`/
`numeric` (guard via `information_schema`), no-op si déjà migré ou si la
colonne/table n'existe pas.
"""

COLONNES_INDEX = (
    'index_hph',
    'index_hpb',
    'index_hch',
    'index_hcb',
    'index_hp',
    'index_hc',
    'index_base',
)

_TYPES_A_CONVERTIR = ('double precision', 'real', 'numeric')


def _colonnes_a_convertir(types_actuels):
    """Sous-ensemble de COLONNES_INDEX encore à convertir, d'après les types
    lus en base (information_schema). Colonne absente ou déjà integer :
    exclue — c'est ce qui rend le script idempotent. Fonction pure, isolée
    pour être testable sans base de données (voir tests/test_releve.py)."""
    return [c for c in COLONNES_INDEX if types_actuels.get(c) in _TYPES_A_CONVERTIR]


def migrate(cr, version):
    cr.execute(
        'SELECT column_name, data_type FROM information_schema.columns '
        "WHERE table_name = 'souscription_releve' AND column_name = ANY(%s)",
        (list(COLONNES_INDEX),),
    )
    types_actuels = dict(cr.fetchall())

    for colonne in _colonnes_a_convertir(types_actuels):
        cr.execute(
            f'ALTER TABLE souscription_releve ALTER COLUMN {colonne} TYPE integer USING round({colonne})::integer'
        )
