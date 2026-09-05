#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
case "${1:-}" in
  ''|--omarchy|modus-operandi|modus-vivendi) ;;
  *) echo 'Usage: sh install.sh [--omarchy|modus-operandi|modus-vivendi]' >&2; exit 2 ;;
esac
[ "$#" -le 1 ] || { echo 'Expected at most one argument.' >&2; exit 2; }
data_home=${XDG_DATA_HOME:-"$HOME/.local/share"}
venv="$data_home/herdr-modus-themes/venv"
launcher="$HOME/.local/bin/herdr-modus"
if [ -e "$venv" ] && [ ! -f "$venv/pyvenv.cfg" ]; then
  echo "Refusing to replace unrelated directory: $venv" >&2; exit 1
fi
if [ -e "$launcher" ] || [ -L "$launcher" ]; then
  [ -L "$launcher" ] && [ "$(readlink "$launcher")" = "$venv/bin/herdr-modus" ] || {
    echo "Refusing to replace unrelated command: $launcher" >&2; exit 1
  }
fi
python3 -m venv "$venv"
"$venv/bin/python" -m pip install --disable-pip-version-check --upgrade "$root"
mkdir -p "$HOME/.local/bin"
ln -sfn "$venv/bin/herdr-modus" "$launcher"
case "${1:-}" in
  --omarchy) "$launcher" follow-omarchy ;;
  modus-*) "$launcher" apply "$1" ;;
  '') echo "Installed $launcher. Run herdr-modus apply modus-operandi to apply a palette." ;;
esac
