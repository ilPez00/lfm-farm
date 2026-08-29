#!/bin/bash
# LFM Launcher — start the right model on the right engine
# Usage: lfm.sh [default|heavy|max|glm|toolcall|fast|status|stop]

TIER="${1:-default}"
MODELS_BASE="/home/gio/models"
ACTIVE="$MODELS_BASE/active"

# ── Helpers ──────────────────────────────────────────────
get_model_file() {
  local name=$(readlink "$ACTIVE/$1" 2>/dev/null | sed 's|.*/||')
  local file=$(ls "$MODELS_BASE/$name"/*.gguf 2>/dev/null | head -1)
  echo "$file"
}

# ── Stop all running servers ─────────────────────────────
lfm_stop() {
  echo "[lfm] stopping all inference servers..."
  pkill -f "llama-server" 2>/dev/null
  pkill -f "ggml-rpc-server" 2>/dev/null
  pkill -f "coli" 2>/dev/null
  pkill -f "colibri" 2>/dev/null
  pkill -f "lfm_router" 2>/dev/null
  sleep 1
  echo "[lfm] done."
}

# ── Tier 0: Fast (LFM2.5 standalone) ─────────────────────
start_fast() {
  local model_file=$(get_model_file fast)
  
  if [[ -z "$model_file" ]]; then
    echo "[lfm] ERROR: LFM2.5 not downloaded yet"
    exit 1
  fi

  echo "[lfm] tier: fast (LFM2.5-8B-A1B standalone)"
  echo "[lfm] engine: llama.cpp (single box)"
  echo "[lfm] model: $model_file"

  /home/gio/llama.cpp/llama-server \
    --model "$model_file" \
    --port 8080 \
    --host 0.0.0.0 \
    --threads 6 \
    --ctx-size 32768
}

# ── Tier 0.5: Tool calling (LFM2.5 + smart model) ────────
start_toolcall() {
  local tool_file=$(get_model_file toolcall)
  local brain_file=$(get_model_file default)
  
  if [[ -z "$tool_file" ]]; then
    echo "[lfm] ERROR: LFM2.5 not downloaded yet"
    exit 1
  fi
  
  if [[ -z "$brain_file" ]]; then
    echo "[lfm] ERROR: default model (ornith) not downloaded yet"
    exit 1
  fi

  echo "[lfm] tier: toolcall (LFM2.5 + ornith brain)"
  echo "[lfm] tool model: $tool_file"
  echo "[lfm] brain model: $brain_file"

  # Start LFM2.5 on port 8081 (tool execution)
  echo "[lfm] starting LFM2.5 on :8081..."
  /home/gio/llama.cpp/llama-server \
    --model "$tool_file" \
    --port 8081 \
    --host 127.0.0.1 \
    --threads 4 \
    --ctx-size 32768 &
  LFM_PID=$!
  sleep 2

  # Start ornith on port 8082 (reasoning)
  echo "[lfm] starting ornith on :8082..."
  /home/gio/llama.cpp/llama-server \
    --model "$brain_file" \
    --port 8082 \
    --host 127.0.0.1 \
    --threads 6 \
    --ctx-size 32768 &
  BRAIN_PID=$!
  sleep 2

  # Start router on :8080
  echo "[lfm] starting toolcall router on :8080..."
  /home/gio/llama.cpp/lfm_router.py \
    --listen 0.0.0.0:8080 \
    --tool-server http://127.0.0.1:8081 \
    --brain-server http://127.0.0.1:8082

  # Cleanup on exit
  kill $LFM_PID $BRAIN_PID 2>/dev/null
}

# ── Tier 1: default (ornith — single box, colibri) ────────
start_default() {
  local model_file=$(get_model_file default)
  
  if [[ -z "$model_file" ]]; then
    echo "[lfm] ERROR: ornith not downloaded yet"
    exit 1
  fi

  echo "[lfm] tier: default (ornith-1.5-35b-a3b)"
  echo "[lfm] engine: colibri (single box)"
  echo "[lfm] model: $model_file"

  if [[ ! -x "/home/gio/colibri/coli" ]]; then
    echo "[lfm] building colibri..."
    make -C /home/gio/colibri coli 2>&1 | tail -3
  fi

  /home/gio/colibri/coli --model "$model_file" --port 8080 --host 0.0.0.0
}

# ── Tier 2: heavy (qwen3.8-27b — RPC split) ─────────────
start_heavy() {
  local model_file=$(get_model_file heavy)
  
  if [[ -z "$model_file" ]]; then
    echo "[lfm] ERROR: qwen3.8-27b not downloaded yet"
    exit 1
  fi

  echo "[lfm] tier: heavy (qwen3.8-27b)"
  echo "[lfm] engine: llama.cpp RPC (split omo+pansa)"

  if ! ssh pansa "pgrep -f ggml-rpc-server" > /dev/null 2>&1; then
    echo "[lfm] starting rpc-server on pansa..."
    ssh pansa "nohup /home/gio/llama.cpp/ggml-rpc-server \
      --model '$model_file' \
      --port 50052 \
      --layers 33-64 \
      --threads 4 \
      --host 0.0.0.0 \
      > /tmp/rpc-pansa.log 2>&1 &"
    sleep 3
  else
    echo "[lfm] pansa rpc-server already running"
  fi

  echo "[lfm] starting llama-server on omo (main)..."
  /home/gio/llama.cpp/llama-server \
    --model "$model_file" \
    --port 8080 \
    --host 0.0.0.0 \
    --layers 1-32 \
    --rpc pansa:50052 \
    --threads 6 \
    --ctx-size 32768
}

# ── Tier 3: max (qwen3.8-max — colibri) ─────────────────
start_max() {
  local model_file=$(get_model_file max)
  
  if [[ -z "$model_file" ]]; then
    echo "[lfm] ERROR: qwen3.8-max not downloaded yet"
    exit 1
  fi

  echo "[lfm] tier: max (qwen3.8-max)"
  echo "[lfm] engine: colibri (single box)"
  echo "[lfm] model: $model_file"

  if [[ ! -x "/home/gio/colibri/coli" ]]; then
    echo "[lfm] building colibri..."
    make -C /home/gio/colibri coli 2>&1 | tail -3
  fi

  /home/gio/colibri/coli --model "$model_file" --port 8080 --host 0.0.0.0
}

# ── Tier 4: glm (glm-5.2 — colibri) ─────────────────────
start_glm() {
  local model_file=$(get_model_file glm)
  
  if [[ -z "$model_file" ]]; then
    echo "[lfm] ERROR: glm-5.2 not downloaded yet"
    exit 1
  fi

  echo "[lfm] tier: glm (glm-5.2, 744B MoE)"
  echo "[lfm] engine: colibri"

  if [[ ! -x "/home/gio/colibri/coli" ]]; then
    echo "[lfm] building colibri..."
    make -C /home/gio/colibri coli 2>&1 | tail -3
  fi

  /home/gio/colibri/coli --model "$model_file" --port 8080 --host 0.0.0.0
}

# ── Main switch ──────────────────────────────────────────
case "$TIER" in
  stop)      lfm_stop ;;
  fast)      start_fast ;;
  toolcall)  start_toolcall ;;
  default)   start_default ;;
  heavy)     start_heavy ;;
  max)       start_max ;;
  glm)       start_glm ;;
  status)
    echo "[lfm] active symlinks:"
    ls -la "$ACTIVE/"
    echo ""
    echo "[lfm] running servers:"
    ps aux | grep -E "llama-server|ggml-rpc-server|coli|lfm_router" | grep -v grep || echo "  none"
    ;;
  *)
    echo "usage: lfm.sh [fast|toolcall|default|heavy|max|glm|status|stop]"
    echo ""
    echo "  fast      → LFM2.5-8B-A1B standalone (~50 t/s, CPU, fast inference)"
    echo "  toolcall  → LFM2.5 (tool exec) + ornith (brain) paired"
    echo "  default   → ornith-1.5-35b-a3b (Colibri, daily coding)"
    echo "  heavy     → qwen3.8-27b (RPC split, dense quality)"
    echo "  max       → qwen3.8-max (Colibri, frontier)"
    echo "  glm       → glm-5.2 (Colibri, alternative frontier)"
    echo "  status    → show active tier + running servers"
    echo "  stop      → kill all servers"
    ;;
esac
