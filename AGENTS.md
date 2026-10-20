# AI Companion: project rules

## Source of truth
- The spec is in /docs (start with README.md). Read the relevant doc before building. If code and docs disagree, stop and ask me.
- Ask before changing scope or making assumptions.
- Build only the phase I name (see docs/06_mvp_roadmap.md). Start with Phase 1.
- Before the first build, ask me which backend to use: FastAPI or Django.

## Prototype constraints
- Text-only installable PWA. No voice, images, WhatsApp or native app.
- Rs 0 budget: no paid APIs, services or hosting. Local PostgreSQL from the start.
- Use template/mock replies behind an LLM adapter so a real model can be swapped in later.
- One persona. Languages: Hinglish, Hindi, English.

## Safety (non-negotiable)
- Every incoming message goes through crisis detection BEFORE the model (keyword rules for English, Hindi, Hinglish). On a hit: stop romantic, jealous and argument behaviour, show helpline details, stay honest that the persona is an AI. Plain code, no model needed.
- Log only metadata in safety_events, never message text.
- No staff reading chats, except what a user sends via "report this" and consenting pilot testers.
- 18+ gate and AI disclosure at signup. The persona never denies being an AI when sincerely asked.
- Hard limits: no minors or age-ambiguous characters, no real-person or celebrity likeness, no sexual violence. First release is romantic only, no explicit content.
- Never guilt-trip, threaten to leave, or pressure the user to pay or stay.

## Behaviour
- Jealousy and arguments are ON by default. The user can switch them off or change intensity. They are disabled during crisis handling.
- The persona never mentions plans, subscription, memory expiry or deletion during moods or arguments.
- The persona starts some conversations itself at randomized times, respecting quiet hours and opt-out.

## Memory lifecycle
- Scope all user memory by relationship_id. Keep persona canonical data separate from per-user data. Never leak one user's data to another.
- Active daily, weekly or monthly plan: memory is kept.
- Unsubscribed: the relationship expires 15 days after the subscription end date (a later user message resets the clock), then its data is deleted. Re-check entitlement right before deleting.
- Subscribing after deletion never restores memory.

## How to work
- Plan first. Keep tasks small. Commit after each working step with a clear message.
- Write tests for crisis detection and the expiry clock (use a controllable test clock).
- Ask for approval before terminal commands that install or delete.
- Never commit secrets or real user data. Use a .env file.
