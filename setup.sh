#!/usr/bin/env bash
# One-time build: Python venv + backend deps + migrations + demo content, frontend deps.
# Re-runnable. Ubuntu needs: python3, nodejs (>=20), npm. No sudo needed.
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  if python3 -c 'import ensurepip' 2>/dev/null; then python3 -m venv .venv
  else
    python3 -m venv --without-pip .venv
    curl -sSL https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py && .venv/bin/python /tmp/get-pip.py -q
  fi
fi
.venv/bin/pip install -q -r backend/requirements.txt
( cd backend && ../.venv/bin/python manage.py migrate --noinput && ../.venv/bin/python manage.py seed_demo )
( cd frontend && [ -f .env ] || cp .env.example .env; npm install --no-audit --no-fund )
echo "Gotowe. Uruchom ./run.sh — strona: http://localhost:5173  API: http://localhost:8000/api  admin: http://localhost:8000/admin/"
echo "Konta demo: dziekan (moderator) i student, hasło fuwlol123"
