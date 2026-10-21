# 7. Adaptive Communication and Zero-Cost Development

## A. Learn the customer's communication style over time

The persona should gradually adapt its *delivery style* to the customer while retaining its own stable personality. Potential preferences include language/code-switching (English, Hindi, Hinglish, Bengali-English), message length, casual/formal tone, emoji frequency, humour, and whether the customer prefers advice or attentive listening.

### Authentic Colloquial Hinglish Texting Texture
The primary linguistic differentiator is authentic colloquial texture:
- **Natural Code-Switching:** Blend English and Hindi with authentic urban Indian Gen-Z/millennial cadence (*"achha suno"*, *"arre yaar"*, *"pakka batao"*, *"scene kya hai"*).
- **Conversational Rhythms:** Short, snappy texting structure, natural contractions, and conversational flow; strictly avoid stiff, archaic, or literal dictionary Hindi translations that sound like automated machine translations.
- **Playful, Grounded Emojis:** Natural emoji use that complements emotion without feeling spammy.
- **User Message Burst Debouncing:** Humans frequently send texts in short rapid bursts (*"hii"* [send], followed 2 seconds later by *"kya ho rha hai"* [send]). The interface never locks input while waiting for replies; it buffers rapid bursts (up to an 8-second ceiling, flushed on page unload) and screens both individual chunks and the concatenated text for crisis signals.
- **Multi-Bubble Chunked AI Delivery:** Instead of single monolithic paragraphs, the model outputs short, natural message bubbles with progressive typing indicator pauses proportional to bubble length.
- **Precise City Normalization & Familiarity Bridging:** Supports optional onboarding city input or contextual in-chat detection (`awaiting_city_reply` lifecycle, strictly evaluated on the immediate turn after the opener and cleared). Uses strict word boundaries (`\b(kolkata|calcutta)\b`, `\b(delhi|ncr|gurgaon|noida)\b`, `\b(bengaluru|bangalore|blr)\b`, `\b(mumbai|bombay)\b`) to prevent false-positive matches (such as matching "cal" in "calm" or "call").

Do not fine-tune a model after every conversation. For the MVP, maintain a private per-customer style profile and include a compact version in the conversation context. This is cheaper, faster, reversible, and easier to evaluate than model training.

Example profile:

```json
{
  "language_preference": "Hinglish",
  "message_length": "short_to_medium",
  "tone_preference": "casual_warm",
  "emoji_frequency": "low",
  "advice_preference": "ask_before_advising",
  "confidence": {"language_preference": 0.85},
  "last_updated": "2026-10-14"
}
```

This is illustrative, not a required schema. Learn from repeated evidence; don't overreact to one message. Explicit customer settings override inferred preferences. Let customers inspect, correct, reset, or disable style adaptation. Keep style profile separate from relationship memories, persona state, and relationship progression.

The persona should adapt its language and conversational rhythm, not copy every typo or mirror panic, anger, distress, or harmful language. Never use style matching to manipulate attachment or pressure users. Do not infer sensitive attributes or diagnoses from writing style. Tell users how conversation data is used, minimize collection, and don't use private conversations to train a shared model by default.

## B. Zero-cash-spend strategy

Target ₹0 cash spend during prototyping, but don't promise that a production service can stay free forever. Free tiers change and have limits; local inference has hardware, electricity, and maintenance costs.

### Phase 0 — no AI API
- Develop locally with Python and Django/FastAPI.
- Use React (or server-rendered pages with a manifest and service worker) as a PWA; choose the simplest UI you can build. Installability needs HTTPS (localhost is exempt), so testing on a phone needs a secure tunnel or free HTTPS hosting; check current free-tier limits.
- Use PostgreSQL locally from the start.
- Implement persona state, routine simulation, memory records, and contextual retrieval as ordinary code.
- Use templates or a mocked model response to test the complete workflow before adding an LLM.
- Use Git and a free repository; keep secrets and customer data out of public repos.
- Persona-initiated web push needs the backend and scheduler running and reachable over HTTPS. For phone tests use a secure tunnel or free HTTPS hosting, and expect no pushes while the host machine is off.
- Build crisis-keyword screening and helpline handoff as ordinary code from day one; it needs no paid API and must not depend on a small local model alone.

### Phase 1 — optional local model
Try a small quantized open-weight model with a local inference runtime, after checking its license for your intended use. Test on existing hardware before spending on upgrades. Small models can be less capable and slow; an older desktop with 8 GB RAM and a 2 GB GPU may require CPU inference and a very small quantized model. Do not buy hardware just to validate the idea. Test Hinglish and Hindi quality explicitly; small models are often weak there, and natural texting is the core of the product.

### Phase 2 — local testing, then free hosting only if needed
Localhost is the most reliable zero-hosting-cost option. Use a free hosting tier only if you need an online demo, and verify its current limits for storage, background jobs, sleep/uptime, and usage. Free-tier terms can change.

### Phase 3 — controlled pilot
Test with a small group of consenting adults, clearly disclosing that the persona is fictional and AI-powered. Use synthetic data during development and collect only what is necessary. Measure memory quality, style fit, repetition, contradictions, latency, and whether users return voluntarily.

### Phase 4 — paid services only after a decision gate
Consider paid inference only after the prototype works, testers show repeat use, you have measured quality gaps, and you can estimate cost per active user. Set hard monthly and per-user limits before enabling paid APIs. Owner's rule: ₹0 for now; a small budget or low-cost LLM only if the prototype proves impressive.

## Suggested free-first stack

| Component | Initial approach |
|---|---|
| Backend | Python + Django or FastAPI |
| Frontend | React or server-rendered UI, delivered as a PWA |
| Database | PostgreSQL (local) |
| Scheduler | Simple local process for prototype |
| Memory | SQL + keyword/full-text search first |
| Dialogue | Hybrid: Intelligent Contextual Engine (default ₹0) + Swappable LLM (Groq/Gemini/OpenAI/Ollama via `.env`) |
| Hosting | Local only until remote demo is needed |
| Version control | Git + free repository |

## Hybrid Architecture (Option 3: Contextual Engine & Swappable LLM)

To ensure the prototype never outputs disconnected random templates in offline ₹0 mode while allowing easy integration with real models, the dialogue layer uses a hybrid adapter:

1. **Intelligent Contextual Dialogue Engine (`MockTemplateLLMAdapter`)**:
   - Handles conversational intents:
     - Profile and location inquiries (e.g. *"how do you know my location/city"* -> explains onboarding entry).
     - First-turn question routing (addresses queries before introducing Aanya).
     - Status acknowledgments (e.g. *"thik chal raha hai"* -> acknowledges before topic change).
     - Conversational bridges for short affirmations (*"okay"*, *"hmm"*).
     - Persona inquiries (profession, current activity, Indiranagar lifestyle, indie music).
     - Natural, open-ended conversational fallbacks.
2. **Pluggable Remote LLM Adapter (`LLMAdapterFactory`)**:
   - Configurable via `.env`:
     - `LLM_PROVIDER=mock` (default offline ₹0 mode)
     - `LLM_PROVIDER=groq` (`GROQ_API_KEY`, `GROQ_MODEL=llama-3.3-70b-versatile`, `GROQ_FALLBACK_MODEL=llama-3.1-8b-instant` — free cloud tier)
     - `LLM_PROVIDER=gemini` (`GEMINI_API_KEY`, `GEMINI_MODEL=gemini-1.5-flash` — free cloud tier)
     - `LLM_PROVIDER=openai` or `ollama` (`OPENAI_API_KEY`, `OPENAI_API_BASE=http://localhost:11434/v1`)
   - Uses zero-dependency async HTTP calls via `httpx`.
   - **Token Limits vs. Daily Request Labels**:
     - Groq free tier imposes strict token boundaries that bind long before daily request numbers:
       - `llama-3.3-70b-versatile`: 12,000 TPM (tokens/min), 1,000 RPD, and 100,000 TPD (tokens/day). At ~600 tokens/turn, 70B exhausts after ~166 requests/day across all users.
       - `llama-3.1-8b-instant`: 6,000 TPM, 14,400 RPD, and 500,000 TPD (~800 requests/day).
     - **Dual Remote Fallback Chain**: Primary 70B -> on 429 (rate/token limit) or timeout fails over to 8B -> on 429 fails over to the **Intelligent Offline Contextual Mock Engine**.
     - **Structured Telemetry**: Every fallback emits a structured log (`event="llm_fallback"`, `attempted_model`, `fallback_model`, `status_code`, `reason`, `latency_ms`).
   - **Verified Groq Data Protection Terms**:
     - **Zero Model Training**: Explicitly prohibited from using customer prompts or completions to train AI models under Groq's Services Agreement.
     - **Default Non-Retention**: Standard inference requests are not retained.
     - **Temporary Operational Logs**: Kept for up to 30 days strictly for debugging system outages and abuse/rate-limit monitoring.
   - **Safety Invariant**: Plain-code crisis screening always executes with 0ms delay *before* any model/adapter invocation.
   - **Postgres-Backed Rate Limiting**: Usage counters (`user_rate_limits`) survive Render dyno spin-downs, capping users at 6 req/min and 40 LLM req/day before transparently serving from the mock engine.

## Recommended order

1. Define persona, memory, relationship, and style-profile schemas.
2. Build chat UI, message persistence, and basic crisis detection.
3. Test orchestration with template responses.
4. Implement the life timeline and persisted events.
5. Add contextual memory, open-loop handling, and persona-initiated messages with randomized timing.
6. Add gradual style-profile updates and user controls.
7. Evaluate a local model on existing hardware.
8. Run adult-user tests and measure retention/quality.
9. Consider paid services only when justified by evidence.

**Bottom line:** “learning the customer” initially means updating a private, editable memory and communication-style profile—not retraining the underlying model after every chat. Build and test locally first; make spending a deliberate later decision.

---

## Lifecycle scope for learned communication style

Communication-style adaptation is relationship-specific by default. If a user-persona relationship expires (this applies to unsubscribed customers; an active plan keeps it) after 15 consecutive days without a user-initiated interaction, delete that relationship's inferred language/tone preferences with its other relationship context. Do not transfer those inferences to another user or keep them as shared persona memory. The canonical persona voice remains stable and generic. Explicit account-level accessibility or UI preferences may be stored separately only with clear purpose, controls, and a distinct retention policy.
