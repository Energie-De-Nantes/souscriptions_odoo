FROM odoo:19.0

USER root

# Installer les dépendances système (git : requis par le pin git+https de
# requirements.txt tant qu'electricore-client n'est pas re-publié sur PyPI)
RUN apt-get update && apt-get install -y \
    git \
    python3-watchdog \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copier le module souscriptions
COPY . /mnt/extra-addons/souscriptions_odoo

# Dépendances Python du module (electricore-client, #77) — épinglées dans
# requirements.txt, absentes de external_dependencies pour ne pas bloquer
# l'installation du module sans elles (garde d'import côté wizard).
# uv plutôt que pip : --break-system-packages reste requis (PEP 668, inhérent
# au Python système), mais uv shadowe proprement le typing_extensions Debian
# dans /usr/local sans le marteau --ignore-installed.
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv
RUN uv pip install --system --break-system-packages -r /mnt/extra-addons/souscriptions_odoo/requirements.txt

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
