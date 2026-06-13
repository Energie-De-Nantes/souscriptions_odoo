FROM odoo:19.0

USER root

# Installer les dépendances système
RUN apt-get update && apt-get install -y \
    python3-watchdog \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copier le module souscriptions
COPY . /mnt/extra-addons/souscriptions_odoo

# S'assurer que les permissions sont correctes
RUN chown -R odoo:odoo /mnt/extra-addons/souscriptions_odoo

USER odoo

# Configuration par défaut
ENV ODOO_RC=/etc/odoo/odoo.conf
ENV ADDONS_PATH=/mnt/extra-addons

# Copier et utiliser notre script d'entrée personnalisé
COPY --chown=odoo:odoo docker/docker-entrypoint-init.sh /
RUN chmod +x /docker-entrypoint-init.sh

# Utiliser notre entrypoint qui initialise automatiquement la démo
ENTRYPOINT ["/docker-entrypoint-init.sh"]