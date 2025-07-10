FROM odoo:18.0

USER root

# Installer les dépendances Python et PostgreSQL client
RUN apt-get update && apt-get install -y \
    python3-pandas \
    python3-watchdog \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Installer les packages non disponibles via pip
RUN pip3 install --no-cache-dir --break-system-packages \
    pyarrow \
    fastparquet

# Copier le module souscriptions
COPY . /mnt/extra-addons/souscriptions

# S'assurer que les permissions sont correctes
RUN chown -R odoo:odoo /mnt/extra-addons/souscriptions

USER odoo

# Configuration par défaut
ENV ODOO_RC=/etc/odoo/odoo.conf
ENV ADDONS_PATH=/mnt/extra-addons

# Copier et utiliser notre script d'entrée personnalisé
COPY --chown=odoo:odoo docker-entrypoint-init.sh /
RUN chmod +x /docker-entrypoint-init.sh

# Utiliser notre entrypoint qui initialise automatiquement la démo
ENTRYPOINT ["/docker-entrypoint-init.sh"]