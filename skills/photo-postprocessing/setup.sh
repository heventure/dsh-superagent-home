#!/bin/sh
# Create/refresh the photo venv used by SKILL.md (idempotent).
set -eu
VENV="${PHOTO_VENV:-$HOME/.local/photo-venv}"
python3 -m venv "$VENV"
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -r "$(dirname "$0")/requirements.txt"
"$VENV/bin/python" -c "import rawpy, PIL, numpy, pillow_heif; print('photo venv ready:', '$VENV')"
