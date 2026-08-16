#!/system/bin/sh
set -eu

# Updates files/builds only. It does not restart s10-control, sshd, Wi-Fi, ADB, or Android.
project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
server_dir="$project_root/apps/server"
web_dir="$project_root/apps/web"

test -x "$server_dir/.venv/bin/python" || { echo "Run scripts/install-termux.sh first." >&2; exit 1; }
"$server_dir/.venv/bin/python" -m pip install --requirement "$server_dir/requirements.lock"
"$server_dir/.venv/bin/python" -m pip install --no-deps --no-build-isolation --force-reinstall --editable "$server_dir"
(cd "$web_dir" && npm ci && npm run build)
"$server_dir/.venv/bin/python" -m s10_control version
echo "Update built. To restart only this project service manually: sv restart s10-control"
