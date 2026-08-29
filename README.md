# LFM — Local File Manager

Multi-model LLM inference farm for Axiom agent. Runs on omo (15GB RAM) + pansa (15GB RAM) with CPU-only inference.

## Architecture

| Component | Port | Machine | Purpose |
|-----------|------|---------|---------|
| LFM fast (LFM2.5) | 8080 | pansa | Trivial queries + tool calls (~50 t/s) |
| LFM Gateway | 8090 | pansa | Unified API for all stacks |
| Physis master | 19876 | pansa | Coherence engine + semantic embedder |
| Physis stream | 19876 | omo | Proxy to pansa with local cache |

## Tiers

- **fast**: LFM2.5-8B-A1B (~50 t/s) — trivial queries, tool calls
- **default**: Ornith-1.5-35B-A3B (~15-20 t/s) — reasoning
- **heavy**: Qwen3.8-27B (~3-5 t/s) — complex tasks, RPC split
- **toolcall**: LFM2.5 + Ornith pair — fast tool loop + reasoning brain

## Stacks

1. **DEV** — single model, direct inference
2. **SWARM** — N agents in parallel + synthesis
3. **NOTEBOOK** — Physis classify + llmwiki search
4. **AXIOM** — daily brief: PDCA + coherence + LLM synthesis

## Files

- `models.yaml` — model manifest with all tiers
- `lfm.sh` — launcher script (default/heavy/max/glm/toolcall/fast/status/stop)
- `lfm-gateway.py` — unified FastAPI gateway
- `lfm_router.py` — tool calling pair router
- `lfm-service.sh` — systemd user unit installer
- `physis_stream.py` — Physis stream proxy (omo → pansa)
- `systemd/` — systemd user units for all tiers
- `docs/LFM_FULL_ANALYSIS_2026-08-28.md` — comprehensive system analysis

## Usage

```bash
# Source aliases
source ~/.lfm_aliases

# Start fast tier
lfm.sh fast

# Start all tiers
lfm.sh default
lfm.sh toolcall

# Check status
lfm.sh status

# Query gateway
curl -s http://127.0.0.1:8090/v1/fast/chat -H "Content-Type: application/json" -d '{"message":"hello"}'
```
