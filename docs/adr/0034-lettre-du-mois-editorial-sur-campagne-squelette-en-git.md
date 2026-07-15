# La lettre du mois : l'éditorial vit sur la campagne, le squelette transactionnel vit en git

Instruit le chantier « Lettre du mois » (PRD #311, grillé le 2026-07-15). Le mail qui
accompagne les factures mensuelles porte, en plus des faits de facturation, un contenu
**éditorial** — prochaines dates, avancement du chantier roue à aubes, exceptions de
permanence, tarif solidaire, appels à bénévoles. Cet éditorial change tous les mois, et il
est aujourd'hui écrit **là où vit le corps du mail** : dans le `body_html` de deux
`mail.template` de production, édités à la main, en séquence, par le·la *Facturiste*.

La question tranchée ici : **où vit un contenu que le·la Facturiste doit pouvoir réécrire
chaque mois, sans être dev ni mainteneur·euse, et sans pouvoir casser la facture au
passage ?**

## Le point de départ : le diagnostic spontané était faux

L'hypothèse de travail à l'ouverture du grill était « une mise à jour de module a écrasé le
modèle de mail plusieurs fois ». Elle est **écartée par le code d'Odoo 19** :
`account/data/mail_template_data.xml` déclare l'ensemble de ses modèles dans un bloc
`noupdate="1"`, et la porte de chargement (`odoo/tools/convert.py`) lit l'**attribut XML du
fichier chargé** — pas la colonne en base — puis retourne dès que le record existe, sans
lire un seul champ. Un `-u account` ne touche à rien. Corollaires non évidents, qui valent
d'être consignés : basculer « Toggle Noupdate » en mode développeur **ne réarme pas**
l'écrasement (la porte lit le XML, pas la colonne) ; et **supprimer** un modèle ne tient pas
— `forcecreate` vaut `True` par défaut, donc il renaît au prochain `-u`.

Ce qui écrase réellement est **la main humaine**, et en second le bouton **Reset Template**
(`mail/models/template_reset_mixin.py`), qui relit le XML du disque en `mode='init'` — la
condition exacte qui désarme la protection — et blanchit au passage tout champ absent du
record XML. C'est un clic dans l'UI.

Cette correction du diagnostic a **supprimé la moitié coûteuse** du design : il n'y a pas
besoin de re-déclarer le corps standard d'Odoo dans un bloc non-`noupdate` pour le rendre
auto-cicatrisant contre les déploiements. Il n'y a jamais eu de menace côté déploiement.

## Le motif canonique — et pourquoi il perd ici

La *textbook way* Odoo pour ce besoin est établie, et c'est bien « **un champ rendu par un
modèle stable** » : `mail.template.body_html` est un champ à moteur de rendu **QWeb**, et le
modèle de facture standard d'Odoo fait déjà exactement ça avec un champ `Html` (la signature
du·de la commercial·e, gardée par un test de vacuité). Le motif communautaire qui
l'accompagne est : champ `Html` sur `res.company`, exposé via `res.config.settings`.

**Ce motif est rejeté ici, sur deux fronts.**

**1. Il est hors d'atteinte du·de la Facturiste.** `res.config.settings` est gardé par
`base.group_system` — à la fois dans l'ACL du modèle et sur le menu. Les groupes du module
s'arrêtent à `group_souscriptions_user` et `group_souscriptions_manager` ; aucun n'implique
`group_system`. Poser la lettre sur `res.company` reviendrait à exiger un·e
**administrateur·rice** tous les mois : c'est-à-dire le problème actuel — une personne
privilégiée qui édite un objet global à la main, périodiquement — **déplacé, pas résolu**.
La demande dit « pour un·e facturiste pas dev/mainteneur » ; `res.company` la contredit
frontalement.

**2. Il est global, donc sans mois.** Un champ de société est **écrasé** d'un mois sur
l'autre : l'historique éditorial est perdu, et une facture d'octobre renvoyée en décembre
porterait le texte de décembre — un mail incohérent avec sa propre facture.

La *Campagne de facturation* (ADR 0025) répond aux deux : elle est **déjà** un enregistrement
par mois (`UNIQUE(mois)`), **déjà** le tableau de bord du·de la Facturiste, **déjà** porteuse
d'état persisté (validations de portes, notes). L'objection YAGNI habituelle contre « un
modèle avec un enregistrement par mois » ne s'applique pas : on n'invente ni modèle, ni
calendrier, ni cycle de vie — le coût réel est **un champ**.

## Le second détour : un encart mensuel dans un texte permanent

L'hypothèse suivante — et l'intuition naturelle — était : le template garde l'evergreen
(tarif solidaire, permanences, bénévoles, rappels), et un petit champ « mot du mois » vient
s'insérer dedans. **Le corps réel en production l'a rejetée.**

L'éditorial y est **entrelacé**, pas empilé : prochaines dates (mensuel) → tarif solidaire
(evergreen) → permanences (evergreen) → exception estivale (saisonnier) → roue à aubes
(mensuel) → bénévoles (evergreen). Le découper exige soit trois champs à trois points
d'insertion, soit de décréter un ordre nouveau. Mais surtout, il produit une **régression** :
les horaires de permanence, le pourcentage de foyers éligibles au tarif solidaire, les liens
partiraient en git — et changer une heure de permanence redemanderait **un dev et un
déploiement**. C'est exactement le pouvoir qu'on cherche à rendre.

**La lettre porte donc TOUT l'éditorial**, evergreen compris. Ce qui rend l'evergreen viable
sans retype mensuel : la lettre du mois M est **reportée depuis M-1** à la création de la
campagne, en réutilisant l'idiome des *notes* « à reporter » (`_reporter_notes_precedentes`,
qui chaîne déjà N → N+1 → N+2). On ouvre, on change les dates, on valide.

Le partage devient net, et c'est **la** décision :

| En git, jamais rouvert | Sur la campagne, réécrit chaque mois |
| --- | --- |
| Salutation + nom de l'usager·ère | Prochaines dates |
| N° de facture, montant, période | Tarif solidaire |
| Instruction de paiement (prélèvement / Moneko) | Permanences & exceptions |
| Signature / sign-off | Roue à aubes, bénévoles, rappels |

Le·la Facturiste peut toujours casser sa lettre. Il·elle ne peut **plus jamais** casser le
montant, le numéro, ni l'instruction de paiement — ce qui est précisément ce qui a été
écrasé en production.

## La facture tire, la campagne ne pousse pas

Tentation symétrique, écartée : faire porter l'envoi **et** le mail par la campagne (« elle a
tout ce qu'il faut »). Elle ne l'a pas. Le corps est rendu **une fois par facture**, avec
`object` = la facture : le montant, le numéro, le·la client·e, l'échéance. La campagne n'a
qu'un mois et une liste.

L'inversion est gratuite : **la facture sait retrouver sa campagne** via son propre mois
(`periode_id.mois` → campagne, résolution non ambiguë grâce à `UNIQUE(mois)`). Un compute
non stocké sur `account.move` porte la résolution ; le modèle de mail reste **bête** — un
`t-out`, aucun `search`, aucun `t-set` — donc testable en Python sans rendre un mail.

Effet de bord recherché : **pas de période → pas de campagne → lettre vide → le bloc
disparaît**. Les factures de *régularisation* (qui portent `regularisation_id`, jamais
`periode_id`) sont exclues **par construction**, sans une ligne de cas particulier — une
clôture est la facture de quelqu'un qui part, la newsletter n'y a pas sa place. Il n'y aurait
du code à écrire que pour obtenir le comportement **inverse**.

De même, la résolution du modèle passe par la surcharge de `account.move._get_mail_template()`
— la **racine unique** côté Odoo, consommée aussi bien par l'envoi de masse que par le bouton
unitaire — plutôt que par un paramètre passé depuis la campagne. Sinon, un renvoi unitaire
(« je n'ai rien reçu ») produirait un mail Odoo nu, sans la lettre, différent de celui reçu
par tous les autres.

## Conséquences non évidentes

**Le module possède désormais un corps de mail de facture, et un seul.** Les deux copies de
production (« Envoi EDN » / « Envoi EDN Moneko ») fusionnent : une fois l'éditorial sorti,
elles ne diffèrent plus que par quatre régions — salutation, instruction de paiement, QR-code,
sign-off — dont une seule est substantielle, réductible à un `t-if` sur `mode_paiement`. Ce
n'est pas un fork du corps standard d'Odoo : le corps part de **l'existant prod**, qui est
déjà du wording EDN. Repartir du standard ferait régresser le mail vers l'usine.

**Ce modèle est déclaré SANS `noupdate`, contrairement aux modèles de bienvenue du module.**
Le raisonnement s'inverse : les modèles de bienvenue sont `noupdate` pour laisser
l'utilisateur·rice les personnaliser librement (c'est aussi le motif du core) ; celui-ci ne
doit **jamais** être édité à la main — c'est la maladie qu'on soigne. Sans `noupdate`, un
`-u souscriptions_odoo` ré-affirme notre version et **répare** un édit manuel ou un clic sur
Reset Template. Auto-cicatrisant par déploiement.

**La duplication était déjà en train de coûter, mais pas là où on croyait.** Le texte des deux
copies est byte-identique (empreinte identique, mêmes typos synchronisées) : le copier-coller
tient. Le vrai coût est ailleurs — **les corrections ne se propagent pas**. Le sign-off a été
sorti de sa condition dans la copie Moneko et jamais reporté dans l'autre, où il reste absent
dès qu'aucune signature n'est configurée. Le risque à retenir n'est pas « le texte dérive »,
c'est « un correctif ne vit que dans une copie ».

**Le marketing gate la facturation, délibérément.** La porte `mot_du_mois` (type `porte`,
racine du DAG) garde l'étape d'envoi. Le type est dicté par le catalogue d'étapes : `derive`
là où un signal existe, `porte` là où il manque — et une lettre vide est **ambiguë** (« pas
encore écrite » vs « rien à dire ce mois-ci » sont indiscernables). En `derive`, un mois sans
lettre ne serait jamais « fait » et bloquerait l'envoi à vie. La porte valide une
**décision**, pas une écriture ; la valider avec une lettre vide est légitime. Précédent
assumé : `gestes_commerciaux`, porte commerciale qui garde déjà le gel comptable.

**L'invariant « toute Souscription a un mode de paiement » devient porteur.** Le `t-if` sur
`mode_paiement` n'écrit **aucune** branche de repli : le mail ne compense pas une donnée
manquante, l'invariant s'impose sur la Souscription. Il n'est pas tenu aujourd'hui
(`required=False`, non renseigné sur 63 % des souscriptions dans la base locale de travail ;
la production distingue Moneko par un **tag partenaire**, pas par un champ). C'est une
dépendance du chantier **migration**, même classe de décision que `puissance required` — pas
un problème de mail.

## Voies écartées, pour ne pas les réinstruire

- **Le layout de notification** (`_get_mail_layout()` + vue héritée `primary`) est un vrai
  point d'extension natif, surchargeable proprement, et évitait de posséder un corps de mail.
  Écarté : le chatter archive le corps **sans** le layout, donc la lettre disparaîtrait de
  l'archive de la facture ; et un layout est un mauvais endroit pour de l'éditorial.
- **`ir.config_parameter`** : valeur `Text`, ni éditeur riche ni ACL fine. Mauvais outil.
- **Une vue QWeb éditable + `t-call`** : techniquement possible depuis un corps de modèle
  (le core n'en ship aucun exemple — on serait les premiers), mais reviendrait à faire
  éditer du XML QWeb au·à la Facturiste. Strictement pire qu'un champ en texte riche.
- **`mass_mailing`** : la lettre ne part jamais seule, elle chevauche la facture.
- **Un module OCA** : aucun ne fait ceci. `email_template_qweb`, `mail_layout_force`,
  `mail_template_substitute` sont tous arrêtés en 16.0 et leurs fonctions absorbées par le
  core.

## Piège de rendu à connaître

Si un corps de modèle ne contient **que** des `t-out` de chemins whitelistés
(`object.name`, `object.partner_id`…), Odoo 19 court-circuite QWeb au profit d'une
substitution par **regex** — sans support de `t-if`, `t-set`, `t-call`, et tout ce que la
regex ne matche pas passe **verbatim**. Notre corps contient des `t-if`, donc le vrai moteur
tourne. Non-problème aujourd'hui, mais une « simplification » future du corps pourrait
changer de moteur **silencieusement**.

À noter aussi : `mail.template` désactive la restriction de rendu (`_unrestricted_rendering`),
donc `env` est accessible depuis un corps — n'importe quel·le utilisateur·rice ayant accès aux
Réglages peut y placer du code exécuté à l'envoi. On n'en a **pas besoin** (la résolution est
en Python) ; c'est une raison de plus pour que ce corps ne soit jamais un lieu d'édition.
