#!/usr/bin/env bash
# Prepare a fresh Ubuntu 24.04 LTS VM for the pilot stack (ADR-0014). Idempotent: safe to re-run.
#
#   sudo REPO_URL=https://github.com/ManishPandey21/Vanshavali.git REPO_REF=main \
#        ADMIN_SSH_CIDR=203.0.113.0/24 deploy/pilot/scripts/bootstrap-host.sh
#
# What it does:
#   - packages: Docker Engine + Compose plugin (Ubuntu archive), age, python3, ufw, unattended-upgrades
#   - Docker daemon: log rotation, live-restore, no userland proxy (keeps real client IPs for Caddy)
#   - firewall: SSH (from ADMIN_SSH_CIDR if given), 80/tcp, 443/tcp+udp; everything else denied
#   - SSH: keys only, no root login
#   - user "vanshavali" (deploy user, member of the docker group), its directories, the repository
#   - /etc/vanshavali/*.env from the examples, with fresh random values for the secrets the VM
#     itself generates (data keys, signing key, metrics token, app DB password); the rest stay
#     CHANGE_ME until you fill them in (docs/deployment/environment-variables.md)
#   - cron: nightly backup, daily document purge, weekly orphan report and image prune
#
# It never overwrites an existing /etc/vanshavali file.
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "run as root (sudo)" >&2; exit 1; }

REPO_URL="${REPO_URL:-https://github.com/ManishPandey21/Vanshavali.git}"
REPO_REF="${REPO_REF:-main}"
DEPLOY_USER="${DEPLOY_USER:-vanshavali}"
APP_DIR=/opt/vanshavali
CONF=/etc/vanshavali
STATE=/var/lib/vanshavali

say() { printf '\n== %s\n' "$*"; }

say "packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q docker.io docker-compose-v2 age python3 git ufw unattended-upgrades curl
systemctl enable --now docker unattended-upgrades

say "docker daemon"
mkdir -p /etc/docker
if [[ ! -f /etc/docker/daemon.json ]]; then
  cat >/etc/docker/daemon.json <<'JSON'
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "20m", "max-file": "5" },
  "live-restore": true,
  "userland-proxy": false
}
JSON
  systemctl restart docker
fi

say "firewall"
ufw default deny incoming
ufw default allow outgoing
if [[ -n "${ADMIN_SSH_CIDR:-}" ]]; then ufw allow from "$ADMIN_SSH_CIDR" to any port 22 proto tcp; else ufw allow 22/tcp; fi
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 443/udp
ufw --force enable
# Docker publishes ports through its own iptables chains, bypassing ufw: only Caddy publishes
# public ports in compose.yml; Prometheus/Alertmanager publish on 127.0.0.1 only.

say "ssh"
cat >/etc/ssh/sshd_config.d/60-vanshavali.conf <<'SSH'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
SSH
systemctl reload ssh || systemctl reload sshd || true

say "deploy user and directories"
id "$DEPLOY_USER" >/dev/null 2>&1 || useradd --create-home --shell /bin/bash "$DEPLOY_USER"
usermod -aG docker "$DEPLOY_USER" # NB: docker group membership is root-equivalent on this VM
install -d -m 700 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "$CONF" "$STATE" "$STATE/release" "$STATE/backups"
install -d -m 755 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "$STATE/textfile"
if [[ ! -d "$APP_DIR/.git" ]]; then
  git clone --quiet "$REPO_URL" "$APP_DIR"
fi
git -C "$APP_DIR" fetch --quiet origin "$REPO_REF"
git -C "$APP_DIR" checkout --quiet --detach FETCH_HEAD
chown -R "$DEPLOY_USER:$DEPLOY_USER" "$APP_DIR"

say "configuration files (existing files are kept)"
rand_b64() { python3 -c 'import base64,os;print(base64.b64encode(os.urandom(32)).decode())'; }
rand_hex() { python3 -c 'import secrets;print(secrets.token_hex(32))'; }
set_value() { # set_value FILE KEY VALUE: replace the CHANGE_ME placeholder of KEY
  python3 - "$1" "$2" "$3" <<'PY'
import re, sys
path, key, value = sys.argv[1:]
text = open(path).read()
text = re.sub(rf"^{key}=.*$", lambda m: f"{key}={value}", text, count=1, flags=re.M)
open(path, "w").write(text)
PY
}
for name in compose app migrate backup smoke; do
  dst="$CONF/$name.env"
  [[ -f "$dst" ]] && continue
  install -m 600 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "$APP_DIR/deploy/pilot/env/$name.env.example" "$dst"
  case "$name" in
    app)
      set_value "$dst" VSH_STANDARD_DATA_KEY "$(rand_b64)"
      set_value "$dst" VSH_VAULT_DATA_KEY "$(rand_b64)"
      set_value "$dst" VSH_SIGNING_KEY "$(rand_hex)"
      token="$(rand_hex)"
      set_value "$dst" VSH_METRICS_TOKEN "$token"
      printf '%s' "$token" >"$CONF/metrics_token"
      chmod 644 "$CONF/metrics_token" # read by the Prometheus container (nobody); scrape-only token
      echo "  generated data keys, signing key and metrics token in $dst: ESCROW the data keys now"
      echo "  (docs/security/secrets-management.md). Losing them makes every document unreadable."
      ;;
    migrate)
      set_value "$dst" VSH_APP_DB_PASSWORD "$(rand_hex)"
      echo "  generated the app role password in $dst; put the same value in app.env's VSH_DATABASE_URL"
      ;;
  esac
done
[[ -f "$CONF/alertmanager.yml" ]] ||
  install -m 600 -o 65534 -g 65534 "$APP_DIR/deploy/pilot/monitoring/alertmanager.yml.example" "$CONF/alertmanager.yml"

say "scheduled jobs"
cat >/etc/cron.d/vanshavali <<CRON
# Vanshavali pilot (deploy/pilot/scripts/bootstrap-host.sh). Times are UTC.
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
41 20 * * * $DEPLOY_USER $APP_DIR/deploy/pilot/scripts/backup.sh nightly >>$STATE/backup.log 2>&1
30 21 * * * $DEPLOY_USER cd $APP_DIR && source deploy/pilot/scripts/lib.sh && dc --profile tools run --rm tools python -m app.cli.maintenance purge-deleted-documents >>$STATE/maintenance.log 2>&1
45 21 * * 0 $DEPLOY_USER cd $APP_DIR && source deploy/pilot/scripts/lib.sh && dc --profile tools run --rm tools python -m app.cli.maintenance sweep-orphans >>$STATE/maintenance.log 2>&1
15 22 * * 0 root docker image prune -af --filter "until=720h" >/dev/null 2>&1
CRON
chmod 644 /etc/cron.d/vanshavali

say "done"
cat <<EOF
Next steps (docs/deployment/pilot-deployment-plan.md, "Provisioning"):
  1. Fill in every CHANGE_ME in $CONF/*.env and $CONF/alertmanager.yml (database URLs, buckets,
     SMTP, backup recipient, smoke account, domain).
  2. As $DEPLOY_USER: docker login ghcr.io (a read-only package token).
  3. As $DEPLOY_USER: $APP_DIR/deploy/pilot/scripts/deploy.sh <image tag>
EOF
