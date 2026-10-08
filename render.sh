#!/bin/sh
# Compatibility entrypoint: render.sh input.html output.pdf [a4|letter] [options]
# Python handles browser discovery, private temporary files and delivery checks.
set -eu
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec python3 "$SCRIPT_DIR/scripts/render_cv.py" "$@"
