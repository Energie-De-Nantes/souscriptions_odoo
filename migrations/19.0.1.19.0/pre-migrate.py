"""Renomme `lance` -> `demande` sur `souscription.campagne.etape` (#326, ADR
0035 amendement ADR 0025) : le champ n'est plus un constat de succès posé
APRÈS le travail, mais une intention posée AVANT — le bouton « Émettre
factures » demande, il ne fait plus (le travail part en tâche de fond, cf.
`SouscriptionCampagneEtape._vidanger_un_paquet`).

Aucune perte de valeur pour les étapes 'action' déjà en vol (sync F15, pull
sorties C15, régulariser les clôtures...) : leur `lance` devient `demande`
avec la MÊME valeur — pour elles, la demande est toujours équivalente au
lancement (elles tirent tout d'un coup, aucune n'a rejoint le harnais de
tâche de fond dans cette tranche). Aucune campagne en vol n'avait `lance =
True` pour `emettre_factures` avant cette version (le champ n'était jamais
posé pour cette étape, de type 'derive' — son « fait » a toujours été
`nb_reste_a_faire == 0`, cf. ADR 0025 amendée) : les lignes migrées démarrent
donc `demande = False`, ce qui est exactement l'état réel (rien n'est en
cours de vidange au moment de la migration).

RENAME COLUMN plutôt que ADD + backfill + DROP : pas de perte, et évite
qu'Odoo ne recrée une colonne `demande` vide au chargement du module (la
colonne existe déjà, remplie, avant que l'ORM ne compare son schéma).
Pré-migration (pas post) : le renommage doit précéder la synchronisation de
schéma normale du module, qui verrait sinon deux champs distincts (`lance`
disparu du modèle, `demande` absent de la table) et laisserait la donnée
orpheline plutôt que migrée.

`demande_par_id` (nouveau champ, sans équivalent historique) n'a rien à
migrer : l'ORM la crée vide au chargement normal du module, comme n'importe
quel nouveau champ.

Idempotent : la garde sur `information_schema.columns` rend un rejeu sans
effet (colonne déjà renommée -> plus de `lance` à trouver).
"""


def migrate(cr, version):
    cr.execute(
        """
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'souscription_campagne_etape' AND column_name = 'lance'
        """
    )
    if cr.fetchone():
        cr.execute('ALTER TABLE souscription_campagne_etape RENAME COLUMN lance TO demande')
