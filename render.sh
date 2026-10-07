#!/bin/zsh
# render.sh <input.html> <output.pdf> [a4|letter]
# Renders a CV's HTML to PDF via headless Chrome/Brave. Exit 0 on success.
#
# Paper size lives in the template's `@page { size: … }` CSS rule. When the
# caller asks for a size other than the template default (a4), the rule is
# swapped in a temp copy so the original file is never modified.
set -euo pipefail

if [ "$#" -lt 2 ]; then
  echo "usage: render.sh <input.html> <output.pdf> [a4|letter]" >&2
  exit 2
fi

IN=$1
OUT=$2
PAPER=${3:-a4}

if [ ! -f "$IN" ]; then
  echo "render.sh: input not found: $IN" >&2
  exit 1
fi
if [ ! -s "$IN" ]; then
  echo "render.sh: input is empty: $IN" >&2
  exit 1
fi
case "$PAPER" in
  a4|letter) ;;
  *) echo "render.sh: unknown paper '$PAPER' (use a4 or letter)" >&2; exit 2 ;;
esac

# Prefer dedicated Chrome; fall back to Brave (both verified on this machine).
CANDIDATES=(
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
  '/Applications/Brave Browser.app/Contents/MacOS/Brave Browser'
  '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge'
  '/Applications/Chromium.app/Contents/MacOS/Chromium'
)
BROWSER=""
for b in $CANDIDATES; do
  if [ -x "$b" ]; then BROWSER=$b; break; fi
done
if [ -z "$BROWSER" ]; then
  echo "render.sh: no Chrome-family browser found in /Applications" >&2
  exit 3
fi

RENDER_SRC=$IN
TMP_HTML=""
if [ "$PAPER" != "a4" ]; then
  TMP_HTML=$(mktemp -t cvforge).html
  # Swap the @page size rule; the template always carries exactly one.
  sed -e "s/@page { size: A4; /@page { size: $PAPER; /" "$IN" > "$TMP_HTML"
  RENDER_SRC=$TMP_HTML
fi
trap '[ -n "$TMP_HTML" ] && rm -f "$TMP_HTML"' EXIT

mkdir -p -- "${OUT:h}"
# file:// URL needs the absolute path percent-encoded for spaces etc.
IN_ABS=$(cd -- "${RENDER_SRC:h}" && printf '%s/%s' "$PWD" "${RENDER_SRC:t}")
IN_URL="file://${IN_ABS// /%20}"

"$BROWSER" --headless --disable-gpu --no-pdf-header-footer \
  --print-to-pdf="$OUT" \
  "$IN_URL" 2>/dev/null

if [ ! -s "$OUT" ]; then
  echo "render.sh: Chrome produced no PDF at $OUT" >&2
  exit 4
fi
SIZE=$(du -h "$OUT" | cut -f1)
echo "rendered: $OUT ($SIZE), paper=${PAPER}"
