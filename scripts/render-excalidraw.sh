#!/usr/bin/env bash
# Régénère les .png à partir des .excalidraw (rendu FIDÈLE via le vrai moteur Excalidraw).
#
# Le style « hand-drawn » (roughjs + fontFamily Excalifont) n'existe qu'au travers du
# moteur Excalidraw : pas de rendu pur-python. On pilote donc un navigateur headless
# (Playwright Firefox), qui charge les polices depuis le CDN Excalidraw.
#   ⇒ nécessite RÉSEAU + navigateur ⇒ à lancer HORS sandbox (comme la convention actuelle).
#
# Usage :
#   scripts/render-excalidraw.sh                 # tous les docs/**/*.excalidraw
#   scripts/render-excalidraw.sh a.excalidraw b.excalidraw   # ciblés
#
# ponytail: rendu via `npx excalidraw-brute-export-cli` (playwright) plutôt qu'une
# dépendance node versionnée — zéro node_modules dans le repo. Passer à un devDep
# épinglé si le npx à chaud devient un point de douleur (offline / CI).
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

# Firefox Playwright (~105 Mo) au premier run seulement ; idempotent ensuite.
ls "$HOME"/.cache/ms-playwright/firefox-* >/dev/null 2>&1 || npx -y playwright install firefox

files=("$@")
if [ ${#files[@]} -eq 0 ]; then
  mapfile -t files < <(find docs -name '*.excalidraw' | sort)
fi

for src in "${files[@]}"; do
  png="${src%.excalidraw}.png"
  printf '→ %s\n' "$png"
  if ! log=$(npx -y excalidraw-brute-export-cli -i "$src" -o "$png" -f png -s 3 -b true 2>&1); then
    printf '%s\n' "$log" >&2
    printf '✗ échec sur %s\n' "$src" >&2
    exit 1
  fi
  # Compression (aplats pastel → la quantification de palette est quasi sans perte
  # visuelle) : le hook pre-commit check-added-large-files plafonne à 500 Ko.
  # Second étage plus agressif seulement si le premier ne suffit pas.
  magick "$png" -resize 60% -colors 255 PNG8:"$png"
  if [ "$(stat -c%s "$png")" -gt 480000 ]; then
    magick "$png" -resize 75% -colors 128 PNG8:"$png"
  fi
done
printf '✓ %d diagramme(s) régénéré(s)\n' "${#files[@]}"
