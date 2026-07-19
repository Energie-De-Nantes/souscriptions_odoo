from odoo import fields, models


class SouscriptionMailConfig(models.Model):
    """Foyer de configuration des mails de facture, propre au module (#313,
    #316, ADR 0034 « Extension : les mails sans mois »). Distinct de la
    *Lettre du mois* (portée par la Campagne, rythme mensuel) : ce modèle
    porte ce qui n'a PAS de rythme — le QR-code Moneko (#313) et les *Textes
    permanents* des mails de Régularisation (#316) : difficultés de
    paiement, appel au don sur les avoirs, accusé de clôture.

    Volontairement PAS `res.company` / PAS `res.config.settings` : les deux
    exigent `base.group_erp_manager` / `base.group_system`, hors d'atteinte
    du·de la Facturiste (`group_souscriptions_manager`) — cf. ADR 0034 §
    « Le motif canonique — et pourquoi il perd ici » et
    « Conséquence : une surface de config pour l'éditorial sans rythme ».

    Enregistrement UNIQUE par convention (posé par data/souscription_mail_
    config_data.xml, ouvert directement par le menu — pas de vue liste) :
    pas de contrainte SQL de singleton, un seul champ ne justifie pas ce
    coût — si une deuxième ligne apparaît un jour par erreur,
    `_qr_moneko_image_url` (compute `account_move.py`) prend la première
    trouvée, jamais une erreur bloquante sur un chemin d'envoi de mail.
    """

    _name = 'souscription.mail.config'
    _description = 'Configuration des mails'

    # ponytail: pas de company_id — ce module n'a jamais eu besoin de
    # scoper cette config par société ailleurs ; ajouter si un vrai besoin
    # multi-société apparaît (#316 ou plus tard).
    qr_code_moneko = fields.Image(
        string='QR-code Moneko',
        max_width=1024,
        max_height=1024,
        help='Téléversable, jamais figé en git (ADR 0034) : le QR-code Moneko '
        'affiché dans le mail de facture pour les payeur·euses en monnaie '
        'locale, en complément de la marche à suivre in-app. Peut rester '
        'vide — le corps du mail ne le promet alors jamais.',
    )

    # Textes permanents des mails de Régularisation (#316, ADR 0034
    # « Extension : les mails sans mois ») : écrits par les facturistes
    # (« l'éditorial des régularisations… est écrit par les facturistes »),
    # sans rythme mensuel — donc pas de foyer sur la Campagne, contrairement
    # à la Lettre du mois. `t-out` par le corps de `mail_template_facture_
    # energie` (data/mail_templates_facture_energie.xml), jamais réaffirmés
    # par `data/souscription_mail_config_data.xml` (noupdate=1, comme
    # `qr_code_moneko`) : un `-u souscriptions_odoo` ne les écrase jamais.
    # Vides -> aucun bloc, aucun résidu (même contrat que `lettre_mois`).
    texte_regul_difficultes = fields.Html(
        string='Difficultés de paiement (régularisation)',
        help='Affiché sur une régularisation projetée en FACTURE (non clôture) : paragraphe '
        "difficultés (aides, étalement, « réponds à ce mail qu'on s'arrange »). Vide -> aucun bloc.",
    )
    texte_regul_appel_don = fields.Html(
        string='Appel au don (avoir)',
        help='Affiché sur une régularisation projetée en AVOIR (non clôture) : appel au don. Vide -> aucun bloc.',
    )
    texte_regul_cloture = fields.Html(
        string='Accusé de clôture (résiliation)',
        help='Affiché sur une régularisation de CLÔTURE, que ce soit une facture ou un avoir : '
        'accusé de prise en compte de la résiliation, registre du départ. Vide -> aucun bloc.',
    )

    def _qr_moneko_image_url(self):
        """URL affichable par un·e destinataire NON AUTHENTIFIÉ·E dans son
        client mail (#313, ADR 0034 § « Conséquences non évidentes »). `False` si
        aucun QR n'est configuré.

        Mécanisme retenu : `qr_code_moneko` (Binary/Image, `attachment=True`
        par défaut) est stocké par l'ORM comme un `ir.attachment` propre
        (res_model/res_id/res_field). On lui génère — ou récupère — un
        `access_token` (`ir.attachment.generate_access_token()`, méthode
        core historique, utilisée par le partage de facture/portail natif
        d'Odoo pour le même besoin) et on construit l'URL courte
        `/web/image/<attachment_id>?access_token=<token>` : le contrôleur
        binaire d'Odoo accepte ce token en substitut d'une session pour
        rendre l'image à un tiers non connecté — même mécanique que l'URL
        prod citée dans la demande (`/web/image/6486-346edfbd/...
        ?access_token=…`).

        Vérifié sur les sources réelles d'Odoo 19.0-20260630 : la route
        `/web/image/<int:id>` existe et est déclarée `auth='public'` ;
        `ir_binary._find_record` accepte le token via
        `record._can_return_content(field, access_token)`, dont
        l'implémentation `ir.attachment` compare le token en `consteq` puis
        renvoie l'enregistrement en `sudo()`. Le chemin tient donc sans
        session. Et il est tenu par un vrai test HTTP non authentifié
        (`TestQrMonekoServiSansSession`) : un test qui inspecte le HTML
        produit ne prouverait jamais qu'un tiers peut charger l'image."""
        self.ensure_one()
        if not self.qr_code_moneko:
            return False
        attachment = self.env['ir.attachment'].search(
            [
                ('res_model', '=', self._name),
                ('res_id', '=', self.id),
                ('res_field', '=', 'qr_code_moneko'),
            ],
            limit=1,
        )
        if not attachment:
            return False
        token = attachment.generate_access_token()[0]
        return f'/web/image/{attachment.id}?access_token={token}'
