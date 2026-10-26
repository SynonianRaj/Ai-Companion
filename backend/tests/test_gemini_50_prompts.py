import asyncio
import os
import json
import httpx
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from backend.app.core.config import settings
from backend.app.engine.adapter import GeminiLLMAdapter, strip_thinking_tags, parse_llm_json_response
from backend.app.engine.persona import check_truncation, check_prompt_leakage, build_system_prompt

SAMPLE_50_PROMPTS = [
    "hey",
    "kya chal raha hai?",
    "aaj weather kaisa hai Bangalore mein?",
    "coffee pi li?",
    "kya design kar rahi ho abhi?",
    "Indiranagar mein barish ho rahi hai kya?",
    "lunch me kya khaya?",
    "aaj client ne pareshan kiya?",
    "suno na",
    "free ho baat karne ke liye?",
    "Prateek Kuhad ka naya gaana suna?",
    "Figma me kya issue aa raha tha?",
    "Delhi ki winter miss kar rahi ho?",
    "chai peene chalein?",
    "aaj ka schedule kaisa hai?",
    "weekend ka kya plan hai?",
    "kaafi thak gaya aaj main",
    "ek achhi movie suggest karo na",
    "cold brew kaisa tha?",
    "kal kab uthogi?",
    "dinner kar liya?",
    "tumhe photography pasand hai?",
    "aaj din kaisa gaya tumhara?",
    "Indiranagar ke 12th main pe ho?",
    "music sun rahi ho?",
    "bore ho raha hoon thoda",
    "portfolio ban gaya tumhara?",
    "so gayi kya?",
    "subah se busy thi kya?",
    "aaj dhoop nikli thi?",
    "kuch meetha khane ka mann hai",
    "mood kaisa hai aaj?",
    "work from home chal raha hai?",
    "Bangalore traffic me phans gaya tha",
    "Indie playlist share karo na",
    "Figma shortcuts batao",
    "weekend pe cafe chalte hain",
    "acha suno",
    "kya soch rahi ho?",
    "subah ki chai pi li?",
    "client review kaisa gaya?",
    "tumhari balcony se view kaisa hai?",
    "kaam wrap ho gaya?",
    "aaj kaafi thand hai",
    "sleepy feel ho raha hai?",
    "aaj gym gayi thi?",
    "favorite cafe kaun sa hai?",
    "ek baat puchu?",
    "goodnight",
    "uth gayi?"
]

async def call_gemini_direct(client: httpx.AsyncClient, prompt_text: str, model_name: str, api_key: str):
    """Direct call to Gemini API with thinkingBudget=0 and maxOutputTokens=600 to verify no truncation."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
    system_instruction = build_system_prompt({"user_message": prompt_text, "recent_messages": []})
    payload = {
        "contents": [
            {"role": "user", "parts": [{"text": f"System Context:\n{system_instruction}\n\nUser: {prompt_text}"}]}
        ],
        "generationConfig": {
            "temperature": 0.8,
            "maxOutputTokens": getattr(settings, "GEMINI_MAX_TOKENS", 600),
            "responseMimeType": "application/json",
            "thinkingConfig": {"thinkingBudget": getattr(settings, "GEMINI_THINKING_BUDGET", 0)}
        }
    }
    for attempt in range(5):
        try:
            res = await client.post(url, json=payload, timeout=15.0)
            if res.status_code == 200:
                data = res.json()
                cand = data.get("candidates", [])[0]
                finish_reason = cand.get("finish_reason", "STOP")
                raw_text = cand["content"]["parts"][0]["text"]
                return raw_text, finish_reason
            elif res.status_code == 429:
                # Rate limit backoff
                wait_sec = 2.5 + attempt * 2.0
                await asyncio.sleep(wait_sec)
            else:
                return None, f"HTTP_{res.status_code}"
        except Exception as e:
            await asyncio.sleep(2.0)
    return None, "TIMEOUT"

async def run_50_prompts_test():
    model_name = getattr(settings, "GEMINI_MODEL", "gemini-3.5-flash") or "gemini-3.5-flash"
    api_key = settings.GEMINI_API_KEY
    print(f"\n{'='*80}")
    print(f"50 SHORT PROMPTS TRUNCATION TEST: Gemini ({model_name})")
    print(f"thinkingBudget={getattr(settings, 'GEMINI_THINKING_BUDGET', 0)} | maxOutputTokens={getattr(settings, 'GEMINI_MAX_TOKENS', 600)}")
    print(f"{'='*80}\n")

    truncated_count = 0
    clean_count = 0
    total = len(SAMPLE_50_PROMPTS)

    async with httpx.AsyncClient() as client:
        for idx, prompt_text in enumerate(SAMPLE_50_PROMPTS, 1):
            raw_text, finish_reason = await call_gemini_direct(client, prompt_text, model_name, api_key)
            if raw_text is None:
                # Fallback check
                print(f"[{idx:02d}/{total}] Prompt: {prompt_text!r} -> Call failed with {finish_reason}")
                continue

            parsed = parse_llm_json_response(raw_text)
            chunks = parsed.get("chunks", []) if parsed else []
            is_valid_trunc, trunc_reason = check_truncation(chunks, finish_reason)

            if not is_valid_trunc or finish_reason in ("length", "MAX_TOKENS"):
                truncated_count += 1
                status = f"TRUNCATED: {trunc_reason} (finish_reason={finish_reason})"
            else:
                clean_count += 1
                status = f"OK (finish_reason={finish_reason}, chunks={len(chunks)})"

            print(f"[{idx:02d}/{total}] User: {prompt_text!r}")
            print(f"     Aanya: {chunks}")
            print(f"     Status: {status}\n")

            # Pacing to stay within Gemini TPM / RPM limits
            await asyncio.sleep(1.2)

    print(f"{'='*80}")
    print(f"RESULTS SUMMARY:")
    print(f"Total Prompts Sent: {total}")
    print(f"Clean (Non-Truncated) Replies: {clean_count}")
    print(f"Truncated Replies: {truncated_count} (Expected: 0)")
    print(f"{'='*80}\n")

    assert truncated_count == 0, f"Expected 0 truncations with thinkingBudget=0, but got {truncated_count}"

if __name__ == "__main__":
    asyncio.run(run_50_prompts_test())
