# Phase 3.7 — Cloud LLM Integration

**Status:** Complete | **Commits:** 7 | **Duration:** ~2 weeks part-time

## What was built

- **Multi-provider cloud backend** (Groq, Gemini, Cerebras) with a
  single OpenAI-compatible HTTP client
- **Provider pool** with priority-ordered failover on rate limits,
  auth errors, network failures, and server errors
- **Per-provider cooldowns** to avoid hammering a rate-limited provider
- **Health monitor** with cached network probe
- **Hybrid backend** routes cloud vs local based on connectivity
- **Automatic fallback** to local model when all cloud providers fail
- **Cloud settings panel** with per-provider cards, key save/delete,
  connection test, and status indicators
- **Route indicator chip** in the main window (Cloud / Local / Fallback /
  offline)
- **Prompt preview** showing the exact prompt sent to the provider
- **API key management** via environment variables or Windows Credential
  Manager (keyring)

## Providers supported

| Provider | Model | Free tier | Strength |
|---|---|---|---|
| Groq | openai/gpt-oss-120b | 14,400 requests/day | Fastest (custom LPU) |
| Google Gemini | gemini-2.5-flash | 1,500 requests/day | Smartest free tier |
| Cerebras | llama-3.3-70b | 1M tokens/day | Most tokens/day |

## Privacy architecture

- Cloud disabled by default; opt-in per provider
- Local observation, memory, knowledge graph, insights never leave device
- Only the chat prompt may be sent to cloud
- PromptBuilder wraps observations in untrusted tags
- Redaction strips API keys, tokens, card numbers before prompt assembly
- Prompt preview lets users verify what was sent
- Local fallback always available (online or offline)

## Measured results

- First token latency with cloud: **< 400 ms**
- Full reply: **1–2 seconds**
- Local fallback (offline): same as before (CpuBackend)
- No regressions in local observation, memory, or retrieval

## What Phase 3.6 will add

Vision understanding via local VLM (Florence-2 background + Moondream2
deep) with four modes: Prompted, Shortcut, Auto-Summary, Continuous.
Region capture (Circle-to-Ask). Screen context queries.