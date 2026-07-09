# Campagne de facturation : matrice à prérequis (DAG-rollup) et porte de vérification à la maille campagne

*Statut : accepté. Fixe l'architecture de la Campagne de facturation (#153, issues #155–#159)
avant que le code n'atterrisse — le tableau de bord mensuel du·de la *facturiste*
(CONTEXT.md « Campagne de facturation »), pendant côté facturation du kanban de
*raccordement*. Décide la **forme d'orchestration** (DAG-rollup) et la **granularité de
vérification** (porte à la maille campagne), sur lesquelles s'appuient #156 (spine), #157
(signaux dérivés), #158 (boutons d'étape) et #159 (notes reportées). CONTEXT.md porte déjà
l'entrée de glossaire « Campagne de facturation » (vocabulaire, DAG, porte, statut dérivé,
notes, #153) — cet ADR n'y touche pas, il en fixe l'architecture et le raisonnement.*

## Décision

1. **Forme d'orchestration : DAG-rollup — ni file linéaire, ni kanban par sous-modèle.**
   La Campagne (`souscription.campagne.facturation`, **un enregistrement par mois**) orchestre
   un catalogue **fixe** d'étapes déclaré en code (~7 étapes), reliées par des **prérequis
   explicites** — un DAG, pas une séquence :

   ```
   pull méta-périodes ──┐                       sync F15 ──────┐
                         ├─→ vérif périodes ──┐                ├─→ vérif refacturations
   relevés d'index ──────┘                    │                │
                                               ├─→ créer factures ─→ émettre factures
                                               └────────────────┘
   ```

   Chaque étape affiche soit un **reste-à-faire dérivé** des données quand un signal libre
   existe (périodes tirées, factures créées/émises — #157), soit une **porte de validation
   manuelle** quand il manque (relevés, vérif périodes, vérif refacturations). Aucun moteur de
   workflow, aucun modèle de configuration : le DAG est une constante Python
   (`ETAPES_CAMPAGNE`), relue à chaque affichage — jamais un état de transition consommé.

2. **Granularité de vérification : porte à la maille campagne, 0 champ métier.**
   La validation (« vérif périodes », « vérif refacturations », « relevés d'index ») se
   persiste **sur la Campagne** — un booléen `validé` + `validé_par` + `validé_le` par étape
   (`souscription.campagne.etape`) — **jamais** comme un drapeau « vérifiée » posé sur chaque
   `souscription.periode` ou `souscription.refacturation`. La Campagne reste une fine couche
   d'orchestration au-dessus d'états déjà dérivables ; elle n'instrumente pas les modèles
   métier qu'elle orchestre.

3. **Le DAG est pensé rejouable par un automate.** Chaque étape est soit une fonction pure de
   l'état courant (dérivée), soit une porte explicite (validée) — jamais un événement consommé
   au fil de l'eau. Une facturation automatique future pourra donc parcourir le même DAG, dans
   le même ordre, sans distinguer un parcours humain d'un parcours automatisé : propriété du
   DAG-rollup (état courant, relisible à tout moment), que ni la file linéaire (événements
   consommés) ni le kanban par sous-modèle (état porté par le déplacement d'une carte) n'offrent
   aussi directement.

## Conséquences

- `souscription.periode` et `souscription.refacturation` ne reçoivent **aucun** nouveau champ.
  Le seul état vraiment persisté par la feature est : les validations manuelles (booléen +
  `validé_par` + `validé_le`, par étape et par campagne) et les notes reportées (#159). Tout le
  reste (statut de facturation par souscription, compteurs reste-à-faire, prêt/bloqué) est
  recalculé à la volée à chaque lecture — jamais stocké, jamais désynchronisable de la réalité.
- **Réversible** : si un besoin concret de vérification au grain `periode`/`refacturation`
  émerge (ex. verrouiller une période individuellement), il s'ajoutera comme un champ dédié sur
  ce modèle, sans toucher à la Campagne — la porte à la maille campagne n'empêche pas une porte
  plus fine plus tard, elle ne la préjuge pas.
- Le catalogue d'étapes (prérequis compris) vit dans un seul fichier Python
  (`models/core/souscription_campagne.py`), relu par le calcul de prêt/bloqué, par les boutons
  d'étape (#158) et par un futur automate — une seule source de vérité, jamais dupliquée entre
  vue et logique.
- Coût accepté : les signaux dérivés (reste-à-faire, statut par souscription) n'ont pas de
  relation ORM déclarée entre `souscription.campagne.etape` et
  `souscription.periode`/`account.move` (le rapprochement se fait par requête sur le mois, pas
  par clé étrangère) — donc pas d'invalidation de cache Odoo automatique au travers des
  modèles : recalcul à chaque lecture. Coût jugé négligeable à l'échelle d'un tableau de bord
  facturiste mensuel (dizaines à centaines de souscriptions, pas un flux temps réel).

## Options écartées

- **File linéaire (pipeline séquentiel)** : modéliser la facturation mensuelle comme une
  séquence d'étapes consommées dans l'ordre (une file). Écartée : le sync F15 et le pull
  méta-périodes n'ont **aucune** dépendance entre eux (CONTEXT.md, #156) — les forcer dans une
  séquence imposerait un ordre arbitraire et bloquerait l'un derrière l'autre sans raison
  métier. Le DAG représente fidèlement les deux racines indépendantes ; une file les aurait
  aplaties à tort.
- **Kanban par sous-modèle** (une carte par période, ou par refacturation, glissée à travers des
  colonnes — sur le modèle du kanban de *raccordement*) : écarté. La Campagne est **un**
  enregistrement par mois, pas une collection de cartes individuelles — le kanban de
  raccordement fait avancer *une demande à la fois* ; la facturation mensuelle traite un lot
  complet de souscriptions d'un même geste (pull, sync, créer, émettre). Un kanban par période
  aurait multiplié les cartes sans donner la vue d'ensemble du mois qui est l'objet même du
  tableau de bord.
- **Vérification instrumentée sur `souscription.periode`/`souscription.refacturation`** (un
  champ « vérifiée » par enregistrement) : écartée pour cette itération. Plus fine, mais
  prématurée — aucun besoin concret ne le réclame encore (#156-#159), et cela instrumenterait
  deux modèles métier pour une préoccupation de facturation *mensuelle*, alors que la Campagne
  peut porter seule cet état. Réversible : si le besoin apparaît, cette option reste ouverte
  (cf. Conséquences).

## Raison

La Campagne de facturation est un **tableau de bord**, pas un moteur métier : elle lit et
oriente des faits qui vivent ailleurs (périodes, factures, refacturations), elle n'en devient
jamais la source de vérité. Le DAG-rollup donne au·à la facturiste une vue d'ensemble fidèle
(deux racines indépendantes, une convergence avant facturation) sans lui imposer un ordre
arbitraire ; la porte à la maille campagne garde l'invariant « 0 champ métier » de CONTEXT.md
sans empêcher une granularité plus fine si le besoin se précise un jour. Les deux choix se
répondent : un DAG d'étapes **dérivées** ne peut fonctionner que si le peu d'état qu'il
persiste (les validations manuelles) est lui-même localisé au même endroit que
l'orchestration — la Campagne, pas les modèles qu'elle survole.
