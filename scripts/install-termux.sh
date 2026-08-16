#!/system/bin/sh
set -eu

# This script installs only this project. It never restarts the phone, Wi-Fi, ADB or sshd.
project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
server_dir="$project_root/apps/server"
web_dir="$project_root/apps/web"
: "${PREFIX:=${HOME}/../usr}"

command -v python >/dev/null 2>&1 || { echo "Missing Python 3.11+ (install it manually with: pkg install python)" >&2; exit 1; }
command -v npm >/dev/null 2>&1 || { echo "Missing Node.js (install it manually with: pkg install nodejs-lts)" >&2; exit 1; }
command -v sv-enable >/dev/null 2>&1 || { echo "Missing termux-services (install it manually with: pkg install termux-services)" >&2; exit 1; }

python -m venv "$server_dir/.venv"
"$server_dir/.venv/bin/pip" install --requirement "$server_dir/requirements.lock"
(cd "$web_dir" && npm ci && npm run build)
(cd "$server_dir" && "$server_dir/.venv/bin/python" -m s10_control bootstrap-token >/dev/null)

service_dir="$PREFIX/var/service/s10-control"
mkdir -p "$service_dir"
sed "s|exec python -m s10_control serve|exec '$server_dir/.venv/bin/python' -m s10_control serve|" "$project_root/deploy/termux/runit/s10-control/run" > "$service_dir/run"
chmod 700 "$service_dir/run"
sv-enable s10-control
echo "Installed s10-control. Review and run: sv up s10-control"
echo "Obtain the one-time admin token locally: $server_dir/.venv/bin/s10-control bootstrap-token"
