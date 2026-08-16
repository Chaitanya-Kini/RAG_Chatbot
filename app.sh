#!/usr/bin/env bash
set -euo pipefail

# app.sh - unified control script for backend (FastAPI) and frontend (Streamlit)
# Usage: ./app.sh start|stop|restart|status
# Works in Linux/macOS and in Windows environments with a POSIX shell (WSL, Git Bash).

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
VENV="$PROJECT_ROOT/.venv"
BACKEND_DIR="$PROJECT_ROOT/backend"
FRONTEND_DIR="$PROJECT_ROOT/frontend"
PIDS_DIR="$PROJECT_ROOT/.pids"
LOGS_DIR="$PROJECT_ROOT/logs"
BACKEND_PID_FILE="$PIDS_DIR/backend.pid"
FRONTEND_PID_FILE="$PIDS_DIR/frontend.pid"
BACKEND_LOG="$LOGS_DIR/backend.log"
FRONTEND_LOG="$LOGS_DIR/frontend.log"

mkdir -p "$PIDS_DIR" "$LOGS_DIR"

activate_venv() {
  if [ -f "$VENV/bin/activate" ]; then
    # Unix-style venv
    # shellcheck disable=SC1090
    source "$VENV/bin/activate"
  elif [ -f "$VENV/Scripts/activate" ]; then
    # Git Bash may have Scripts/activate
    # shellcheck disable=SC1090
    source "$VENV/Scripts/activate"
  else
    echo "Warning: virtualenv not found at $VENV. Continuing without activation." >&2
  fi
}

is_running() {
  local pid_file="$1"
  if [ -f "$pid_file" ]; then
    local pid
    pid=$(cat "$pid_file")
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
      return 0
    fi
  fi
  return 1
}

start_backend() {
  if is_running "$BACKEND_PID_FILE"; then
    echo "Backend already running (pid $(cat $BACKEND_PID_FILE))."
    return
  fi
  echo "Starting backend..."
  pushd "$BACKEND_DIR" >/dev/null
  # Disable telemetry for this process to suppress non-critical warnings
  export OTEL_PYTHON_DISABLED=1
  nohup uvicorn app:app --host 127.0.0.1 --port 8000 --reload > "$BACKEND_LOG" 2>&1 &
  echo $! > "$BACKEND_PID_FILE"
  popd >/dev/null
  echo "Backend started (pid $(cat $BACKEND_PID_FILE)). Logs: $BACKEND_LOG"
}

start_frontend() {
  if is_running "$FRONTEND_PID_FILE"; then
    echo "Frontend already running (pid $(cat $FRONTEND_PID_FILE))."
    return
  fi
  echo "Starting frontend..."
  pushd "$FRONTEND_DIR" >/dev/null
  nohup streamlit run streamlit_app.py --server.address 0.0.0.0 --server.port 8501 > "$FRONTEND_LOG" 2>&1 &
  echo $! > "$FRONTEND_PID_FILE"
  popd >/dev/null
  echo "Frontend started (pid $(cat $FRONTEND_PID_FILE)). Logs: $FRONTEND_LOG"
}

stop_pid_file() {
  local pid_file="$1"
  if [ -f "$pid_file" ]; then
    local pid
    pid=$(cat "$pid_file")
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
      echo "Stopping pid $pid..."
      kill "$pid" || true
      sleep 1
      if kill -0 "$pid" 2>/dev/null; then
        echo "Force killing $pid..."
        kill -9 "$pid" || true
      fi
    fi
    rm -f "$pid_file"
  else
    echo "No pid file $pid_file" >/dev/null
  fi
}

stop_backend() {
  echo "Stopping backend..."
  stop_pid_file "$BACKEND_PID_FILE"
}

stop_frontend() {
  echo "Stopping frontend..."
  stop_pid_file "$FRONTEND_PID_FILE"
}

status() {
  if is_running "$BACKEND_PID_FILE"; then
    echo "Backend: running (pid $(cat $BACKEND_PID_FILE))"
  else
    echo "Backend: stopped"
  fi
  if is_running "$FRONTEND_PID_FILE"; then
    echo "Frontend: running (pid $(cat $FRONTEND_PID_FILE))"
  else
    echo "Frontend: stopped"
  fi
}

case "${1:-}" in
  start)
    activate_venv
    start_backend
    start_frontend
    ;;
  stop)
    stop_frontend
    stop_backend
    ;;
  restart)
    stop_frontend
    stop_backend
    activate_venv
    start_backend
    start_frontend
    ;;
  status)
    status
    ;;
  *)
    echo "Usage: $0 {start|stop|restart|status}"
    exit 2
    ;;
esac

exit 0
