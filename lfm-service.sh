#!/bin/bash
# LFM Service Manager — systemd unit generator + controller
# Usage: lfm-service.sh [install|start|stop|status] [tier]

set -euo pipefail

TIER="${2:-fast}"
MODELS_BASE="/home/gio/models"
LLAMA_SERVER="/home/gio/llama.cpp/llama-server"
COLI="/home/gio/colibri_pansa/src/c/coli"
ROUTER="/home/gio/llama.cpp/lfm_router.py"

get_model_file() {
  local name=$(readlink "$MODELS_BASE/active/$1" 2>/dev/null | sed 's|.*/||')
  ls "$MODELS_BASE/$name"/*.gguf 2>/dev/null | head -1
}

generate_unit() {
  local name=$1
  local exec_cmd=$2
  local port=$3
  
  cat <<EOF
[Unit]
Description=LFM Inference Server — ${name}
After=network.target
Wants=network.target

[Service]
Type=simple
User=gio
WorkingDirectory=/home/gio
ExecStart=${exec_cmd}
Restart=on-failure
RestartSec=5
StandardOutput=append:/tmp/lfm-${name}.log
StandardError=append:/tmp/lfm-${name}.log

# Resource limits
MemoryMax=14G
CPUQuota=800%

# Security
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=/home/gio/models /home/gio/.physis /tmp

[Install]
WantedBy=multi-user.target
EOF
}

install_units() {
  echo "[lfm-service] installing systemd user units..."
  
  # Fast tier (LFM2.5 standalone)
  local fast_model=$(get_model_file fast)
  generate_unit "lfm-fast" "$LLAMA_SERVER --model $fast_model --port 8080 --host 0.0.0.0 --threads 6 --ctx-size 32768 --jinja" 8080 > /tmp/lfm-fast.service
  
  # Default tier (ornith via coli)
  local default_model=$(get_model_file default)
  generate_unit "lfm-default" "$COLI serve --model $default_model --port 8080 --host 0.0.0.0 --ctx 32768" 8080 > /tmp/lfm-default.service
  
  # Toolcall tier (LFM2.5 + ornith)
  local tool_model=$(get_model_file toolcall)
  generate_unit "lfm-toolcall-lfm25" "$LLAMA_SERVER --model $tool_model --port 8081 --host 127.0.0.1 --threads 4 --ctx-size 32768 --jinja" 8081 > /tmp/lfm-toolcall-lfm25.service
  generate_unit "lfm-toolcall-ornith" "$LLAMA_SERVER --model $default_model --port 8082 --host 127.0.0.1 --threads 6 --ctx-size 32768" 8082 > /tmp/lfm-toolcall-ornith.service
  generate_unit "lfm-toolcall-router" "/usr/bin/python3 $ROUTER --listen 0.0.0.0:8080 --tool-server http://127.0.0.1:8081 --brain-server http://127.0.0.1:8082" 8080 > /tmp/lfm-toolcall-router.service
  
  # Copy to systemd
  cp /tmp/lfm-*.service ~/.config/systemd/user/
  systemctl --user daemon-reload
  
  echo "[lfm-service] units installed. Use: lfm-service.sh start [fast|default|toolcall]"
}

start_tier() {
  case "$TIER" in
    fast)
      echo "[lfm-service] starting fast tier (LFM2.5 on :8080)..."
      systemctl --user start lfm-fast
      ;;
    default)
      echo "[lfm-service] starting default tier (ornith on :8080)..."
      systemctl --user start lfm-default
      ;;
    toolcall)
      echo "[lfm-service] starting toolcall tier (LFM2.5 + ornith on :8080)..."
      systemctl --user start lfm-toolcall-lfm25
      systemctl --user start lfm-toolcall-ornith
      sleep 2
      systemctl --user start lfm-toolcall-router
      ;;
    *)
      echo "unknown tier: $TIER"
      echo "usage: lfm-service.sh [install|start|stop|status] [fast|default|toolcall]"
      exit 1
      ;;
  esac
  echo "[lfm-service] started."
}

stop_tier() {
  echo "[lfm-service] stopping all LFM services..."
  systemctl --user stop lfm-fast lfm-default lfm-toolcall-lfm25 lfm-toolcall-ornith lfm-toolcall-router 2>/dev/null || true
  echo "[lfm-service] stopped."
}

status_tier() {
  echo "=== LFM Services ==="
  systemctl --user status lfm-fast lfm-default lfm-toolcall-lfm25 lfm-toolcall-ornith lfm-toolcall-router 2>/dev/null || true
  echo ""
  echo "=== Listening Ports ==="
  ss -tlnp | grep -E "808[0-2]" || echo "no LFM ports listening"
}

case "${1:-status}" in
  install) install_units ;;
  start)   start_tier ;;
  stop)    stop_tier ;;
  status)  status_tier ;;
  *)       echo "usage: lfm-service.sh [install|start|stop|status] [fast|default|toolcall]" ;;
esac
