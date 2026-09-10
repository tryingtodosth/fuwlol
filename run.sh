#!/usr/bin/env bash
# Starts the API (:8000) and the frontend dev server (:5173). Ctrl+C stops both.
set -euo pipefail
cd "$(dirname "$0")"
export FUWLOL_CORS_ORIGINS="http://localhost:5173,http://127.0.0.1:5173"
( cd backend && exec ../.venv/bin/python manage.py runserver 127.0.0.1:8000 ) &
( cd frontend && exec npm run dev -- --port 5173 --strictPort ) &
trap 'kill 0' INT TERM
wait
