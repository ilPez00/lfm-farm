# AI Network Test Report — 2026-08-29
# Machines: omo (192.168.1.7), pansa (192.168.1.15)

## Machine Discovery

| Machine | Hostname | IP | CPU | RAM | Status |
|---------|----------|-----|-----|-----|--------|
| omo | omo | 192.168.1.7 | Ryzen 9 6900HX | 14Gi | ONLINE |
| pansa | pansa | 192.168.1.15 | Ryzen 5 5600X | 15Gi | ONLINE |
| pi | raspberrypi | 192.168.1.11 | - | - | OFFLINE |
| air | air | 192.168.1.6 | - | - | OFFLINE (5d) |
| feather | feather | - | - | - | OFFLINE (3d) |
| k1 | k1 | 192.168.1.11 | - | - | OFFLINE |

## Local Services

### OMO (192.168.1.7)
- **Ollama** :11434 — RUNNING
  - Models: mistral (7B), lfm2.5 (8.5B), qwen2.5:3b, qwen2.5:7b, gemma4:e2b, fable-vl-heretic (9.2B), coder-heretic (11.9B), jaahas/qwen3.5-uncensored:4b, nomic-embed-text
  - All models respond OK
- **Physis Stream Proxy** :19876 — RUNNING (proxies to pansa master)
  - classify: OK (STUDY×LEARN 0.67 for "AI")
  - embed: OK (768-d vector)
- **LFM Fast** :8080 — NOT RUNNING
- **LFM Gateway** :8090 — NOT RUNNING

### PANSA (192.168.1.15)
- **Ollama** :11434 — RUNNING
  - Models: gemma4:e2b, nomic-embed-text
  - Limited model selection vs omo
- **LFM Fast** :8080 — RUNNING (LFM2.5-8B-A1B, llama.cpp b10276)
  - Response: "Hello, friend." — OK
- **LFM Gateway** :8090 — RUNNING (FastAPI)
  - Responds (schema fix needed for fast/chat endpoint)
- **Physis Master** :19876 — RUNNING (physis-runtime, BGE-base semantic)
  - classify: OK (STUDY×LEARN 0.69 for "AI research")
  - embed: OK (768-d vector)

## Provider/Key Inventory (OMO only — keys masked)

| Provider | Key Source | Status |
|----------|------------|--------|
| OpenRouter | OPENROUTER_API_KEY | ✅ key present |
| Mistral | MISTRAL_API_KEY | ✅ key present |
| Groq | GROQ_API_KEY | ✅ key present |
| Gemini | GEMINI_API_KEY | ✅ key present |
| DeepSeek | DEEPSEEK_API_KEY | ✅ key present |
| NVIDIA NIM | NVIDIA_NIM_API_KEY | ✅ key present |
| OpenCode ZEN | AI_OPENCODE_KEY | ✅ key present |
| xAI | XAI_API_KEY | ✅ key present |
| GitHub Models | GITHUB_TOKEN | ✅ key present |
| Together | TOGETHER_API_KEY | ✅ key present |
| Cerebras | CEREBRAS_API_KEY | ✅ key present |
| Cohere | COHERE_API_KEY | ✅ key present |
| Vertex AI | VERTEX_API_KEY | ✅ key present |
| Kolm | FREEAIAPIKEY | ✅ key present |
| ElevenLabs | ELEVENLABS_API_KEY | ✅ key present (TTS) |

## Test Results

### Ollama Local Models (OMO) — ALL OK
| Model | Parameter | Quant | Response |
|-------|-----------|-------|----------|
| mistral | 7.2B | Q4_K_M | ✅ "Hello! How can I..." |
| lfm2.5 | 8.5B | Q4_K_M | ✅ |
| qwen2.5:3b | 3.1B | Q4_K_M | ✅ |
| qwen2.5:7b | 7.6B | Q4_K_M | ✅ |
| gemma4:e2b | 5.1B | Q4_K_M | ✅ |

### LFM Services (PANSA)
| Service | Port | Status | Response |
|---------|------|--------|----------|
| LFM Fast | 8080 | ✅ RUNNING | "Hello, friend." |
| LFM Gateway | 8090 | ✅ RUNNING | schema validation |
| Physis | 19876 | ✅ RUNNING | semantic classify |

### Physis (OMO proxy)
| Endpoint | Status | Result |
|----------|--------|--------|
| /classify | ✅ | STUDY×LEARN 0.67 |
| /embed | ✅ | 768-d vector |

## Notes
- External provider tests blocked (no outbound key transmission)
- LFM services on omo need to be started manually
- Pansa has limited Ollama models vs omo
- Pi/air/feather all offline
