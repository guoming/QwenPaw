#!/bin/sh
# Substitute QWENPAW_PORT in supervisord template and start supervisord.
# Default port 8088; override at runtime with -e QWENPAW_PORT=3000.
set -e

warn_docker_auth_setup() {
  secret_dir="${QWENPAW_SECRET_DIR:-/app/working.secret}"
  auth_file="${secret_dir}/auth.json"
  if [ -f "$auth_file" ] || [ -n "${QWENPAW_AUTH_USERNAME:-}" ]; then
    return
  fi

  cat >&2 <<EOF
============================================================
SECURITY NOTICE: No QwenPaw user is registered yet.

Web login is required once the first account is created (first user
becomes admin). For automated Docker/Kubernetes deploys, set:

  QWENPAW_AUTH_USERNAME=admin
  QWENPAW_AUTH_PASSWORD=<strong-password>

Otherwise open the console in a browser to complete registration.
============================================================
EOF
}

# Auto-initialize if config.json is missing (bind mount with empty directory).
if [ ! -f "${QWENPAW_WORKING_DIR}/config.json" ]; then
  echo "⚠️  No config.json found in ${QWENPAW_WORKING_DIR}"
  echo "📦 Running initialization..."
  qwenpaw init --defaults --accept-security
  echo "✅ Initialization complete!"
else
  echo "✓ Config found in ${QWENPAW_WORKING_DIR}, skipping initialization."
fi

export QWENPAW_PORT="${QWENPAW_PORT:-8088}"
warn_docker_auth_setup
envsubst '${QWENPAW_PORT}' \
  < /etc/supervisor/conf.d/supervisord.conf.template \
  > /etc/supervisor/conf.d/supervisord.conf
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf
