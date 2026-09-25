#!/usr/bin/env bash
set -e

# Garante banco + índice RAG (idempotente).
if [ ! -f /app/data/laria.db ] || [ ! -f /app/data/index/imoveis.npz ]; then
  echo "[entrypoint] preparando banco e índice RAG..."
  python -m scripts.seed_db ${SEED_ARGS:-}
fi

case "${1:-api}" in
  api)
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000
    ;;
  dashboard)
    exec streamlit run dashboard/Home.py --server.port 8501 --server.address 0.0.0.0
    ;;
  telegram)
    exec python -m app.channels.telegram
    ;;
  seed)
    exec python -m scripts.seed_db "${@:2}"
    ;;
  *)
    exec "$@"
    ;;
esac
