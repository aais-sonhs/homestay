#!/bin/bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -n "${APP_YML:-}" ]; then
    APP_CONFIG="$APP_YML"
elif [ -f "$ROOT_DIR/app.yaml" ]; then
    APP_CONFIG="$ROOT_DIR/app.yaml"
else
    APP_CONFIG="$ROOT_DIR/app.yml"
fi
PGHOST="${PGHOST:-127.0.0.1}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-postgres}"
PGDATABASE="${PGDATABASE:-homestay}"
CONDA_ENV_NAME="${CONDA_ENV_NAME:-env}"
DEFAULT_PORT_APP="${DEFAULT_PORT_APP:-8000}"
DEFAULT_NUM_WORKERS="${DEFAULT_NUM_WORKERS:-2}"
POSTGRES_WAIT_SECONDS="${POSTGRES_WAIT_SECONDS:-30}"
SEED_DEMO_DATA="${SEED_DEMO_DATA:-1}"
ENABLE_SLA_WORKER="${ENABLE_SLA_WORKER:-1}"
SLA_INTERVAL_SECONDS="${SLA_INTERVAL_SECONDS:-60}"

run_python() {
    if command -v conda >/dev/null 2>&1; then
        conda run --no-capture-output -n "$CONDA_ENV_NAME" python "$@"
    else
        python "$@"
    fi
}

run_uvicorn() {
    if command -v conda >/dev/null 2>&1; then
        conda run --no-capture-output -n "$CONDA_ENV_NAME" python -m uvicorn "$@"
    else
        python -m uvicorn "$@"
    fi
}

run_sla_worker() {
    while true; do
        if ! run_python manage.py evaluate_housekeeping_sla --limit 1000; then
            echo "Đánh giá thời hạn công việc buồng phòng thất bại; sẽ thử lại sau ${SLA_INTERVAL_SECONDS} giây." >&2
        fi
        sleep "$SLA_INTERVAL_SECONDS"
    done
}

read_app_config() {
    local key="$1"
    local fallback="$2"
    local value=""

    if [ -f "$APP_CONFIG" ]; then
        value="$(grep -E "^${key}:" "$APP_CONFIG" | awk -F ':' '{print $2}' | tr -d '[:space:]' | tail -n 1)"
    fi

    if [ -n "$value" ]; then
        printf '%s\n' "$value"
    else
        printf '%s\n' "$fallback"
    fi
}

cd "$ROOT_DIR" || exit 1

PORT_APP="${PORT_APP:-$(read_app_config PORT_APP "$DEFAULT_PORT_APP")}"
NUM_WORKERS="${NUM_WORKERS:-$(read_app_config NUM_WORKERS "$DEFAULT_NUM_WORKERS")}"

echo "Project dir: $ROOT_DIR"
echo "Conda env: $CONDA_ENV_NAME"
if [ -f "$APP_CONFIG" ]; then
    echo "Using config from $APP_CONFIG"
else
    echo "app.yaml/app.yml not found, using default startup values."
fi

echo "Waiting for PostgreSQL..."
for ((attempt = 1; attempt <= POSTGRES_WAIT_SECONDS; attempt++)); do
    if pg_isready -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" >/dev/null 2>&1; then
        echo "PostgreSQL is ready: $PGHOST:$PGPORT/$PGDATABASE"
        break
    fi
    if [ "$attempt" -eq "$POSTGRES_WAIT_SECONDS" ]; then
        echo "PostgreSQL is unavailable after ${POSTGRES_WAIT_SECONDS}s." >&2
        exit 1
    fi
    sleep 1
done

echo "PORT_APP is: $PORT_APP"
echo "NUM_WORKERS is: $NUM_WORKERS"

PIDS="$(lsof -t -i :"$PORT_APP" 2>/dev/null || true)"
if [ -n "$PIDS" ]; then
    echo "Port $PORT_APP is already in use by PID(s): $PIDS" >&2
    echo "Stop that process or choose another PORT_APP." >&2
    exit 1
fi

echo "Checking Django configuration..."
run_python manage.py check

echo "Applying database migrations..."
run_python manage.py migrate --noinput

if [ "$SEED_DEMO_DATA" = "1" ]; then
    echo "Ensuring demo accounts exist..."
    run_python manage.py seed_demo_data
    echo "Ensuring Housekeeping demo data exists..."
    run_python manage.py seed_housekeeping_data
fi

echo "Collecting static files..."
run_python manage.py collectstatic --noinput

echo "Starting Bliss Home at http://0.0.0.0:$PORT_APP"
SLA_WORKER_PID=""
SERVER_PID=""
cleanup() {
    if [ -n "$SERVER_PID" ]; then kill "$SERVER_PID" 2>/dev/null || true; fi
    if [ -n "$SLA_WORKER_PID" ]; then kill "$SLA_WORKER_PID" 2>/dev/null || true; fi
}
trap cleanup EXIT INT TERM

if [ "$ENABLE_SLA_WORKER" = "1" ]; then
    echo "Khởi động bộ đánh giá thời hạn công việc buồng phòng, chu kỳ ${SLA_INTERVAL_SECONDS} giây"
    run_sla_worker &
    SLA_WORKER_PID=$!
fi

run_uvicorn config.asgi:application \
    --host 0.0.0.0 \
    --port "$PORT_APP" \
    --workers "$NUM_WORKERS" \
    --no-access-log &
SERVER_PID=$!
wait "$SERVER_PID"
