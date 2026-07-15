# Grille de prix = moteur de prix unique : composants prixés, projetés par la Facture et les Conditions particulières

*Statut : accepté (2026-07-11). Issu de la revue d'architecture de juillet 2026 : la règle
« prixer une configuration » était implémentée deux fois — `_composer_lignes` (Facture) et
`_prix_documents` (Conditions particulières) — avec le facteur de *Majoration PRO* en trois
exemplaires et deux cartes de cadrans parallèles. Ne re-décide ni la grille **tout-compris**
([ADR-0002](0002-deux-sources-de-verite-marge-en-analytique.md)), ni le snapshot de la
*Période* ([ADR-0006](0006-snapshot-periode-fait-autorite-facturation.md)), ni la CP comme
**projection** ([ADR-0016](0016-documents-contractuels-projection-souscription-consentements-raccordement.md)),
ni l'abonnement **affine** ([ADR-0018](0018-abonnement-affine-base-3kva-plus-coefficient-kva.md)) :
il fixe **où vit la règle d'assemblage des prix** et **ce qui a le droit de diverger**.
CONTEXT.md (« Grille de prix ») porte déjà le vocabulaire.*

## Décision

1. **Une seule implémentation de la règle d'assemblage, portée par la grille.**
   `grille.prix` expose `composants(type_tarif, puissance, coeff_pro, tarif_solidaire)` :
   partition du tarif en cadrans **facturés** (codes + libellés), prix de l'énergie par
   cadran, abonnement **affine**, application de la *Majoration PRO*, résolution du *Produit
   de facturation* (standard / solidaire). Sortie en **données pures** — produits résolus et
   prix unitaires HT — sans effet de bord.

2. **La grille est un paramètre de l'appelant, jamais résolue dans le moteur.** La *Facture*
   prixe avec la grille **historique** (active à `date_fin` de la *Période*) ; les
   *Conditions particulières* avec la grille **engagée** (active à `date_debut`). Les
   **valeurs divergent donc dans le temps — c'est le domaine** (régularisation aux prix
   historiques) ; l'invariant défendu est l'unicité de la **règle**, pas l'égalité des
   montants.

3. **Entrées en valeurs plates, jamais un recordset `souscription`.** Le chemin Facture
   nourrit le moteur avec les valeurs **figées** du snapshot de la Période (ADR-0006), la CP
   avec la Souscription vivante : une interface en valeurs rend le re-couplage de la facture
   aux données vivantes impossible par construction.

4. **Prix manquant : échec bruyant dans le moteur.** Une grille incapable de prixer une
   configuration lève une `UserError` actionnable (produit + grille nommés). Le défaut
   silencieux `0,0` du chemin CP disparaît : un prix nul sur un document opposable est pire
   que l'erreur qu'il évitait.

5. **L'interface publique de la grille rétrécit.** `get_prix_dict` et `get_prix_abonnement`
   deviennent internes ; `get_prix_abonnement` **perd son paramètre `coeff_pro`** — la
   Majoration PRO n'a plus qu'un site (dans `composants`). Les deux cartes parallèles
   `_CADRANS_FACTURES` (periode) et `_CADRANS_DOCUMENTS` (souscription) fusionnent en une
   carte unique dans le moteur.

6. **Les appelants gardent leur présentation.** Quantités (jours, kWh mesurés ou provision —
   déjà locales, ADR-0008), TVA d'affichage (HT société / TTC particulier via le produit),
   sections, notes TURPE et mensualité estimée restent chez chaque projection.

## Conséquences

- **Localité** : le facteur PRO passe de 3 sites à 1 ; la partition des cadrans de 2 cartes
  à 1 ; un nouveau type de tarif (p. ex. Tempo) s'ajoute dans **un** fichier.
- **Testabilité** : la règle PRO × solidaire × cadrans × affine se teste sur l'interface du
  moteur, en données, sans facture postée ni `compute_all`.
- **Changement de comportement assumé** : générer une CP sur une grille incomplète échoue au
  lieu d'imprimer 0,0000 €/kWh — l'erreur arrive à la génération, là où la grille se complète.
- **Uniformisation du coefficient négatif** : l'ancienne garde `if coeff_pro > 0` de l'abonnement
  ignorait un coefficient négatif, que l'énergie appliquait déjà sans garde ; `composants()`
  applique le facteur uniformément. `coeff_pro < 0` n'est pas un cas métier (la *Majoration PRO*
  est un surcoût) — l'incohérence disparaît avec la duplication.
- **Garde-fou pour une future revue** : constater que la CP et les factures affichent des
  prix différents n'est **pas** un bug à corriger (relire §2) ; « aligner » les valeurs ou
  adoucir l'échec bruyant en défaut régresserait cet ADR.

## Options écartées

- **Statu quo (deux implémentations).** La convention seule gardait les règles égales ; la
  dérive était silencieuse — le 0,0 de la CP en était déjà un symptôme.
- **Lignes prêtes-à-facturer en sortie.** Élargit l'interface pour absorber les quantités,
  qui ne sont pas dupliquées ; la CP re-décomposerait des lignes qu'elle n'affiche pas.
- **Nouveau modèle « moteur de prix ».** Au deletion test, il coordonnerait grille +
  catalogue sans rien posséder ; la grille resterait à moitié vidée à côté.
- **Défaut (0 / None) sur prix manquant, au choix de l'appelant.** Re-duplique une politique
  par appelant — exactement la dérive que l'ADR ferme.
- **Passer la Souscription en entrée.** Recouple silencieusement la facture aux données
  vivantes, contre le snapshot (ADR-0006).

## Raison

Deux documents opposables projetaient chacun leur propre assemblage de prix ; rien d'autre
que la discipline ne les gardait sous la même règle. Concentrer la règle dans le module qui
possède déjà les prix — la grille — et paramétrer par la grille rend la divergence *voulue*
(valeurs, dans le temps) structurellement distincte de la divergence *interdite* (règle).

## Amendement (#309) — borne demi-ouverte, sélection sur le début, fin dérivée

Décision §2 corrigée : elle décrivait la Facture prixant « avec la grille historique (active à
`date_fin` de la Période) ». C'était le bug — pas la règle. Une *Période* est bornée en
**demi-ouvert** (`[date_debut, date_fin)`), donc `date_fin` est le 1er du mois **suivant** :
sélectionner dessus prixait juin à la grille de juillet dès qu'un changement de grille tombait
entre les deux. `souscription.py` (`_prix_documents`, grille **engagée**) portait déjà la bonne
réponse ; seuls les chemins Période (composition des lignes, régénération à l'émission,
régularisation) avaient dérivé. CONTEXT.md « Grille de prix » (#308) porte déjà la correction ;
cet amendement aligne l'ADR.

1. **Borne demi-ouverte partout.** La *Grille de prix* adopte la même convention que la
   *Période* : `[date_debut, date_fin)`, la fin exclue. Une grille se termine le jour où la
   suivante commence, jamais la veille — supprime la question « inclusif ou exclusif » qui
   permettait au bug de passer inaperçu.

2. **Sélection sur la date de DÉBUT, dans les deux projections.** La Facture prixe avec la
   grille en vigueur à `date_debut` de la Période (historique — une régularisation rejoue
   ainsi les prix de son mois) ; la CP avec la grille en vigueur à `date_debut` de la
   Souscription (engagée). Les deux résolvent donc la même règle : *la grille en vigueur est
   la plus récente à avoir commencé*. Seule la date **passée** à cette règle diverge (Période
   vs Souscription) — jamais la borne interrogée (toujours le début).

3. **La fin est dérivée, jamais stockée.** `grille.prix.date_fin` se calcule (`date_debut` de
   la grille suivante du même régime) au lieu d'être écrit par un effet de bord de `create()`.
   Un champ stocké tenu par un effet de bord est le **défaut structurel**, pas un simple
   symptôme du bug de sélection : il rendait `write()` (correction d'un `date_debut` sans
   toucher le prédécesseur), `unlink()` (trou de période) et le chargement hors-ordre
   irreprésentables sans code dédié pour chaque cas. Dériver le champ élimine la classe
   entière — rien à fermer, rien à laisser périmé.

4. **Un changement de grille tombe toujours un 1er du mois — jamais de prorata.** Contrainte
   sur `date_debut` (1er du mois), non rétroactive par nature. Alternative écartée : prixer un
   mois à cheval au prorata des deux grilles — aucune mesure commerciale ne justifie de
   découper un mois d'énergie entre deux barèmes ; la contrainte au 1er rend la situation
   structurellement impossible plutôt que de coder un cas que personne ne demande.

Voir aussi l'extension symétrique de la convention de borne dans l'amendement (#309) d'
[ADR-0031](0031-fin-souscription-gouvernee-fait-c15-sorties-tirees-cloture-campagne.md).
