#!/bin/zsh
set -e

cd "$(dirname "$0")"

if [[ ! -x ".venv/bin/protocol-lens-app" ]]; then
  PYTHON_BIN=""
  for candidate in python3.13 python3.12 python3.11 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
      if "$candidate" -c 'import sys; raise SystemExit(sys.version_info < (3, 11))'; then
        PYTHON_BIN="$candidate"
        break
      fi
    fi
  done

  if [[ -z "$PYTHON_BIN" ]]; then
    echo "Protocol Lens needs Python 3.11 or newer."
    echo "Install it from https://www.python.org/downloads/macos/ and run this file again."
    read -k 1 "?Press any key to close."
    exit 1
  fi

  "$PYTHON_BIN" -m venv .venv
  .venv/bin/pip install -e .
fi

.venv/bin/protocol-lens-app

