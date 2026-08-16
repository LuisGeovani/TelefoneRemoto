#!/system/bin/sh
set -eu

# This script installs only this project. It never restarts the phone, Wi-Fi, ADB or sshd.
project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
server_dir="$project_root/apps/server"
web_dir="$project_root/apps/web"
: "${PREFIX:=${HOME}/../usr}"

command -v python >/dev/null 2>&1 || { echo "Missing Python 3.11+ (install manually: pkg install python python-pip python-ensurepip-wheels)" >&2; exit 1; }
command -v node >/dev/null 2>&1 || { echo "Missing Node.js (install it manually with: pkg install nodejs-lts)" >&2; exit 1; }
command -v npm >/dev/null 2>&1 || { echo "Missing npm (install it manually with the Termux Node.js package: pkg install nodejs-lts)" >&2; exit 1; }
command -v sv-enable >/dev/null 2>&1 || { echo "Missing termux-services (install it manually with: pkg install termux-services)" >&2; exit 1; }
python -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' || { echo "Python 3.11+ is required." >&2; exit 1; }
node_version=$(node -p 'process.versions.node')
node_major=${node_version%%.*}
node_rest=${node_version#*.}
node_minor=${node_rest%%.*}
if [ "$node_major" -lt 20 ] || { [ "$node_major" -eq 20 ] && [ "$node_minor" -lt 19 ]; } || [ "$node_major" -eq 21 ] || { [ "$node_major" -eq 22 ] && [ "$node_minor" -lt 12 ]; }; then
  echo "Node.js 20.19+ or 22.12+ is required; found $node_version." >&2
  exit 1
fi

python -m venv "$server_dir/.venv" || { echo "Could not create the venv; install python-pip and python-ensurepip-wheels, then retry." >&2; exit 1; }
"$server_dir/.venv/bin/python" -m pip --version >/dev/null 2>&1 || { echo "venv pip is missing; install python-pip and python-ensurepip-wheels, then retry." >&2; exit 1; }
"$server_dir/.venv/bin/python" -m pip install --requirement "$server_dir/requirements.lock"
"$server_dir/.venv/bin/python" -m pip install --no-deps --no-build-isolation --force-reinstall --editable "$server_dir"
(cd "$web_dir" && npm ci && npm run build)
(cd "$server_dir" && "$server_dir/.venv/bin/python" -m s10_control bootstrap-token >/dev/null)

service_dir="$PREFIX/var/service/s10-control"
service_was_new=false
if [ ! -d "$service_dir" ]; then
  mkdir -p "$service_dir"
  : > "$service_dir/down"
  service_was_new=true
fi
sed "s|exec python -m s10_control serve|exec '$server_dir/.venv/bin/python' -m s10_control serve|" "$project_root/deploy/termux/runit/s10-control/run" > "$service_dir/run"
chmod 700 "$service_dir/run"
if [ "$service_was_new" = true ]; then
  echo "Installed s10-control disabled. Review config, then start manually with: sv-enable s10-control"
else
  echo "Updated the existing service definition without restarting it."
fi
echo "Obtain the one-time admin token locally: $server_dir/.venv/bin/s10-control bootstrap-token"
