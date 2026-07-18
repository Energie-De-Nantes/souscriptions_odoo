# La campagne naît tirée — amorçage à la création, catalogue-interface du DAG

*Statut : accepté. Instruit le PRD **#339** (« la campagne naît tirée »), tranche `docs` (#340)
d'une pile de cinq tranches : #340 (docs) → #341 (coutures-données) → #342 (catalogue-interface,
grand A) → #343 (amorçage à la création), linéaires dans cet ordre ; #344 (vue en phases) dépend de #342 et
va en parallèle de #343.
Cet ADR fixe l'architecture avant que le code n'atterrisse, comme ADR 0025 l'a fait pour la Campagne
elle-même et ADR 0035 pour la tâche de fond. Il **n'ouvre aucune nouvelle porte de vérification** (ADR 0025
§2 reste entier) et ne re-décide ni la forme DAG-rollup (ADR 0025) ni le mécanisme de vidange en tâche de
fond (ADR 0035) : il décide **que la campagne s'amorce seule à sa création** et **que le catalogue des
étapes devient l'interface complète du DAG**. CONTEXT.md (« Campagne de facturation ») est mis à jour par
ce même changement.*

## Le déclencheur : trois clics qui ne portent aucune décision

La Campagne de facturation s'ouvre vide. Le·la Facturiste crée l'enregistrement du mois, puis doit cliquer
trois pulls — sorties C15, méta-périodes, sync F15 — avant de pouvoir commencer son vrai travail : vérifier,
puis facturer. Ces trois clics ne portent **aucune décision humaine** : les pulls sont idempotents,
auto-cicatrisants, sans fenêtre — de la manutention. ADR 0025 (décision 3) promettait un DAG « rejouable
par un automate » ; ADR 0035 a livré cet automate pour créer/émettre les factures ; les pulls restaient à
la main sans raison de fond.

Trois frictions s'y ajoutaient :

- **les erreurs de pull par souscription ne vivaient que dans un toast sticky** — aucune trace durable, même
  sur le chemin manuel ;
- **l'invariant « la campagne se crée toujours sur un mois révolu » n'était encodé nulle part** — une
  campagne prématurée tirerait un mois incomplet, et l'amorçage automatique rendrait cette erreur *agissante* ;
- **la connaissance d'une étape du DAG était éparpillée** : le catalogue `ETAPES_CAMPAGNE` déclarait
  label/type/prérequis, mais six tables satellites, des décisions de gate en corps de méthode et deux crons
  jumeaux portaient le reste. Vérifier ou étendre le DAG demandait de lire ~9 endroits du même fichier ; la
  dureté des arêtes était du folklore.

## La frontière : tirer de la donnée = machine ; juger et engager comptablement = humain

C'est le principe qui tranche tout le reste. L'automate **n'exécute que les trois pulls**. Il ne crée ni
n'émet jamais de factures (engagement comptable, déclenché par intention humaine après les portes), ne
régularise jamais les clôtures (poste des factures), ne prépare jamais les prélèvements (geste UI). Un pull
rapproche de la donnée d'un tiers ; il ne décide rien. Tout ce qui décide reste un geste humain.

## Décision

1. **La campagne s'amorce à sa création, une seule fois.** Pas de re-walk périodique (autre sémantique —
   re-tirer du déjà-fait — et aucun besoin ne le demande). Le re-pull en cours de mois reste manuel (C15
   retardataires, F15 au fil de l'eau).

2. **Garde dure « mois révolu ».** La création refuse (`UserError`) un mois qui n'est pas strictement
   antérieur au mois courant. C'est l'invariant qui rend l'amorçage *sûr* : sans lui, amorcer
   automatiquement un mois en cours tirerait un périmètre et des relevés incomplets. La garde vit à la
   création, avant tout réseau.

3. **La création reste instantanée et sans réseau ; elle déclenche un cron d'amorçage dédié.** La
   transaction de création n'appelle jamais electricore — la naissance d'une campagne ne doit jamais
   échouer parce qu'electricore est occupé. Post-création, un `_trigger()` planifie un cron d'amorçage.

4. **Une passe séquentielle, au plus une tentative par étape.** Le cron descend le catalogue dans son ordre
   (topologique par construction) : pour chaque étape portant la clé d'amorçage (les trois pulls), si elle
   est **prête** (`etat_prerequis == 'prete'`) et **non faite** (`fait == False`) → exécuter sa
   méthode-données, poser `demande` au succès, **committer entre les étapes** (API de progression
   `ir.cron`). Aucun re-déclenchement, aucun marqueur d'état nouveau, aucune migration. Une passe = au plus
   une tentative par étape : la règle « pas de progrès » d'ADR 0035 est satisfaite **par construction**
   (la passe ne boucle pas). Pas le harnais de paquets : les pulls sont innocentés par la mesure d'ADR 0035
   (11–50 s à 5 000 souscriptions).

5. **La condition « prête » rend l'arête douce respectée de fait.** Conséquence voulue de la décision 4 : si
   le pull des sorties C15 échoue, le pull méta n'est **pas tenté** — jamais de périmètre tiré sur des dates
   de fin périmées. L'arête douce sorties→méta devient respectée par l'automate sans devenir un verrou pour
   l'humain (qui garde ses boutons). La sync F15, indépendante, reste tentée.

6. **`demande` conserve sa sémantique.** L'automate pose `demande` *après* le succès d'une étape d'amorçage —
   exactement comme `action_executer` au clic humain (ADR 0035 décision 1 : demander n'est pas terminer, le
   succès se lit dans le reste-à-faire dérivé). Aucun nouveau champ.

7. **Identité : `with_user(create_uid)`.** Toute la passe s'exécute sous l'identité du créateur de la
   campagne — créer la campagne EST la demande d'amorçage. Les écritures (dates de fin, Périodes,
   Refacturations) portent le nom du·de la Facturiste, jamais l'utilisateur technique du cron. Symétrie
   exacte avec ADR 0035 décision 5.

8. **Erreurs, trois étages** (idiome existant, aucune couture nouvelle) :
   - **(a) erreur par souscription** (skip-and-report : mapping, contrainte — jamais transitoire) → chatter
     de la souscription fautive, posé au point d'échec **dans le service**, pour les **deux** chemins,
     manuel et automate. Le toast du chemin manuel ne porte plus que les comptes ; les « conservées » /
     « inchangées » restent des comptes, jamais du chatter ;
   - **(b) échec transport** (ingestion en cours, contrat obsolète) → l'étape reste visiblement « à lancer »
     (vérité dérivée) + notification bus au créateur, best effort ;
   - **(c) fin de passe** → une notification bus récapitulative (comptes par étape, **durées par étape**,
     erreurs), idiome `_notifier_fin` de la vidange.

9. **Le grand A, maintenant : le catalogue absorbe ses satellites.** `ETAPES_CAMPAGNE` devient l'**interface
   complète** du DAG. Chaque entrée déclare tout ce qu'est son étape — **clés plates, méthodes nommées par
   chaîne, clé absente = défaut** (une porte reste ~4 lignes) : label, type, prérequis, `phase`, `gate`
   (dure/douce), cible de statut des étapes dérivées, action du bouton, cible du drill-down, libellé de
   réussite, stratégie de vidange (liste de travail / action unitaire / message d'échec) et `amorcage`
   (la méthode-données du pull ; présence de la clé = étape machine-runnable). Le moteur — rollup des
   prérequis, gates, vidange par paquets, notification de fin, drill-down — devient **générique** : zéro
   branche `if self.code ==`. Les six tables satellites disparaissent ; le catalogue est l'unique source.

10. **Deux crons conservés, un seul point d'entrée.** Les deux enregistrements `ir.cron` de vidange restent
    (xml_ids stables, parallélisme préservé) ; leurs deux points d'entrée jumeaux fusionnent en une méthode
    paramétrée `_cron_vidanger(code)`, et le moteur `_vidanger_un_paquet` lit sa stratégie au catalogue.

11. **Dureté des portes : statu quo comportemental, déclaré, avec le pourquoi en commentaire par entrée.**
    Dure sur créer / émettre (objet même des vérifs) et préparer les prélèvements (protège d'un batch SEPA
    incomplet avant émission) ; douce sur les pulls (auto-cicatrisation) et régulariser les clôtures (le
    garde-fou par unité — clôture non facturée ignorée ce passage — est plus fin que l'arête ; la durcir
    bloquerait les clôtures saines sur un échec d'émission tiers). Le folklore des gates devient une
    décision relue.

12. **Test structurel du catalogue.** Pur Python, aucune couture : chaque prérequis référence une étape
    existante, l'ordre d'insertion est topologique, chaque méthode nommée existe sur son modèle (`getattr`),
    toute clé inconnue est refusée. La classe de bug « étape bloquée à vie sur une faute de frappe, en
    silence » meurt ici.

13. **Coutures-données, gabarit uniforme ×3.** Chaque pull expose une méthode-données (scope + service →
    tuples de listes de libellés) ; le bouton l'emballe en toast au bord. Strictement, seule la sync F15
    l'exige (les services méta/sorties rendent déjà des tuples), mais **l'uniformité est l'interface** :
    l'automate traite chaque étape machine identiquement, et tout appelant non-UI (automate, tests) consomme
    des comptes, jamais un payload `display_notification`.

14. **Quatre phases : `tirer` / `verifier` / `facturer` / `solder`.** `tirer` = les trois pulls ;
    `verifier` = vérif périodes, vérif refacturations ; `facturer` = créer, gestes commerciaux, émettre ;
    `solder` = régulariser les clôtures, préparer les prélèvements. Champ compute stocké sur la ligne
    d'étape (idiome `type_etape`), valeur au catalogue. La frontière clôture est tranchée : le pull sorties
    est `tirer` (un pull qui corrige le périmètre), régulariser est `solder` ; le « sous-process clôture »
    n'est pas une lane de la campagne mais le cycle de vie de la Souscription (en attente de clôture →
    résiliée) que chaque campagne tranche mensuellement.

15. **Vue en phases.** Les étapes rendues en quatre sections (même one2many filtré par phase, un séparateur
    titré par section — l'idiome énergie/abonnement des factures, natif, zéro JS) ; une étape bloquée
    affiche **par quoi** (« Bloquée par : Vérif périodes », les libellés des prérequis non faits) au lieu
    du badge muet « Bloquée » ; suppression de la poignée de réordonnancement (un catalogue fixe et
    topologique ne se réordonne pas — la laisser glisser est un mensonge d'affichage).

## Points consignés explicitement (demandés par le PRD #339)

**Le dépassement justifié de la note de généricité de la PR #327.** La PR #327 notait, à raison pour son
échelle : « deux crons jumeaux plutôt que forcer une généralisation » — avec seulement deux clients du
moteur, l'abstraction n'était pas encore payée. L'amorçage change le compte : il amène les **3ᵉ, 4ᵉ et 5ᵉ**
clients du moteur générique (les trois pulls, désormais lus par l'automate comme des étapes du catalogue).
La condition « deux adaptateurs = couture réelle » est franchie ; généraliser cesse d'être spéculatif. Le
dépassement est donc **justifié par le nombre de clients**, pas décrété — c'est exactement le seuil que la
note #327 posait.

**La réserve « pull méta à froid » d'ADR 0035, acceptée et instrumentée, avec plan B nommé.** ADR 0035 a
mesuré `pull_meta_periodes` sur un *rafraîchissement* (3,2 s), pas sur une *création à froid* : une campagne
qui s'amorce (premier pull du mois, ~900 Périodes + Relevés à créer) peut coûter nettement plus. Le chiffre
n'a jamais été mesuré, faute d'avoir monté une campagne à froid dans la fenêtre de mesure. Décision : **on
accepte le risque et on l'instrumente** — la passe d'amorçage logue la **durée par étape** et la met au
récapitulatif de fin (décision 8c) ; la mesure se fait à la première vraie campagne. **Plan B nommé** : si
le coût à froid est mauvais, le pull méta rejoint le harnais de paquets d'ADR 0035 — liste de travail =
bucket exact « à tirer », unité = lot de RSC, une seule entrée de catalogue sur le moteur générique déjà
posé par la décision 9. Aucune refonte : le grand A rend ce plan B trivial.

**La frontière machine/humain** est le principe fondateur ci-dessus : *tirer de la donnée = machine ; juger
et engager comptablement = humain*.

## Options écartées

- **Re-walk périodique en cours de mois.** Sémantique différente (re-tirer du déjà-fait) et aucun besoin ne
  le demande. Extension possible du même automate, sur besoin — hors périmètre.
- **Amorcer sans la garde « mois révolu ».** L'automatisation rend agissante l'erreur « campagne prématurée » :
  sans la garde, un mois en cours se tirerait incomplet, en silence. La garde dure est le prix d'entrée de
  l'amorçage.
- **Un marqueur d'état d'avancement pour l'automate** (compteur de tentatives, drapeau « amorcé »). Refusé
  comme dans ADR 0035 : la passe unique (décision 4) et la condition « prête ∧ non fait » (décision 5)
  bornent le comportement sans persister d'état neuf.
- **A-minimal : ne toucher au catalogue que le strict nécessaire à l'amorçage.** Envisagé, écarté par
  Virgile au grill : l'amorçage franchit précisément le seuil de clients qui justifie le grand A (voir plus
  haut) ; le faire à moitié laisserait les six satellites en place et le plan B (méta au harnais) coûteux.
- **Trois phases (fusionner `solder` dans `facturer`).** Envisagé, écarté par Virgile : `solder`
  (régulariser les clôtures, préparer les prélèvements) est un temps distinct de `facturer` (créer/émettre) —
  les fusionner brouillerait la lecture du process mensuel.
- **Passer le pull méta (ou régulariser) au harnais de paquets tout de suite.** Sur mesure seulement : la
  mesure d'ADR 0035 innocente les pulls à 5 000 souscriptions ; on ne paie le harnais que quand un chiffre
  le demande (plan B nommé).
- **Une entrée de glossaire dédiée « Amorçage de campagne ».** Jugée redondante : l'entrée « Campagne de
  facturation » de CONTEXT.md, augmentée du paragraphe d'amorçage, suffit — l'amorçage n'est pas un concept
  autonome mais une propriété de la naissance de la campagne.

## Conséquences

- **Aucune dépendance ajoutée** : `ir.cron`, son `_trigger()` et son API de progression sont du cœur Odoo,
  déjà présents (ADR 0035).
- **Aucune nouvelle porte de vérification, aucun champ métier neuf** : ADR 0025 §2 reste entier (zéro champ
  de vérification sur `souscription.periode` / `souscription.refacturation`) ; `demande` garde sa sémantique.
- Le moteur générique du grand A rend l'**extensibilité future gratuite** : une nouvelle étape (ou le plan B
  du pull méta) = une entrée de catalogue, pas une branche dans le moteur.
- Le test structurel du catalogue devient un **filet permanent** : toute évolution du DAG est validée
  mécaniquement (prérequis existants, ordre topologique, méthodes présentes).
- Critère de review du grand A : **zéro comportement changé** — les ~106 tests campagne existants sont le
  filet de régression, sans modification de leurs assertions (hors renommages internes).
- CONTEXT.md (« Campagne de facturation ») gagne l'amorçage à la création, la garde « mois révolu », les
  quatre phases et les erreurs par souscription au chatter. Pas d'entrée de glossaire dédiée.

## Amendement à ADR 0025 — la création déclenche l'automate que la décision 3 attendait

ADR 0025 §Décision 3 anticipait un DAG « rejouable par un automate […] sans distinguer un parcours humain
d'un parcours automatisé », et ADR 0035 a exploité cette propriété pour la vidange en tâche de fond. Cet ADR
franchit le pas suivant : **la création de la campagne déclenche elle-même cet automate** pour les trois
pulls. Ce qui change n'est pas la forme DAG-rollup (intacte) mais le **moment** où l'automate part — non
plus seulement « quand un humain clique une étape lourde », mais « dès que la campagne naît ». Le bouton
manuel de création reste (ADR 0025) ; ce que la décision 3 d'ADR 0025 n'explicitait pas et que celui-ci
tranche : cette création **déclenche** désormais la première passe de l'automate, gardée par l'invariant
« mois révolu ». L'engagement comptable, lui, reste strictement humain (la frontière ci-dessus) : l'automate
s'arrête net aux portes.
