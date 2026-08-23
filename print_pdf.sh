#!/usr/bin/env bash
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PDFUNITE="/opt/homebrew/bin/pdfunite"
ROOT="$(cd "$(dirname "$0")" && pwd)"

if [ $# -lt 1 ]; then
  echo "Usage: $0 <username> [cover|collection|reference...] (default: all)" >&2
  exit 1
fi

USER="$1"
shift

ORDER=(cover reference collection)

# Optional: which sections to include. Default: all that exist.
SECTIONS=()
for arg in "$@"; do
  case "$arg" in
    cover|collection|reference)
      SECTIONS+=("$arg")
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      echo "Usage: $0 <username> [cover|collection|reference...] (default: all)" >&2
      exit 1
      ;;
  esac
done
if [ -z "$SECTIONS" ]; then
  SECTIONS=("${ORDER[@]}")
fi

TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' exit

RENDERED=0
for kind in "${SECTIONS[@]}"; do
  src="$ROOT/output/${kind}_${USER}.html"
  if [ ! -f "$src" ]; then
    echo "Skipping $kind (no output/${kind}_${USER}.html)"
    continue
  fi
  "$CHROME" --headless --no-pdf-header-footer --print-to-pdf="$TMPDIR/$kind.pdf" "file://$src"
  RENDERED=1
done

if [ "$RENDERED" = "0" ]; then
  echo "No HTML files found to convert for user '$USER'." >&2
  exit 1
fi

IN=()
for kind in "${ORDER[@]}"; do
  if [ -f "$TMPDIR/$kind.pdf" ]; then
    IN+=("$TMPDIR/$kind.pdf")
  fi
done

"$PDFUNITE" "${IN[@]}" "$ROOT/output/${USER}.pdf"
echo "Wrote output/${USER}.pdf"
