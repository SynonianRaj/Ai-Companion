# AI Companion Business — Documentation Pack (v8)

## Documents
1. [Business Concept](01_business_concept.md) (updated in v8)
2. [Product Requirements](02_product_requirements.md) (updated in v8)
3. [System Architecture](03_system_architecture.md) (updated in v8)
4. [Persona and Life Simulation](04_persona_life_simulation.md) (updated in v8)
5. [Memory and Relationship Progression](05_memory_and_relationship.md) (updated in v8)
6. [MVP Roadmap](06_mvp_roadmap.md) (updated in v8)
7. [Adaptive Communication and Zero-Cost Development](07_adaptive_communication_and_zero_cost.md) (updated in v8)
8. [Safety, Crisis Detection and Adult Content](08_safety_crisis_and_adult_content.md) (updated in v8)
9. [Business Plan](09_business_plan.md) (updated in v8)

## Product summary
A text-first AI companionship platform where adults experience a fictional relationship arc with an AI persona, beginning with a vibrant first encounter and potentially progressing through introduction, getting to know each other, dating, and an established relationship. The persona has an independent simulated life, while each user's relationship memory is isolated, kept while the customer has an active subscription, and subject to a disclosed 15-day inactivity expiry once unsubscribed (with a pilot-tested "dormant / drifted apart" grace state before permanent deletion).

## Current scope
- Standalone progressive web app (PWA) prototype, installable on a phone's home screen; a native app is optional later. WhatsApp excluded because WhatsApp policy does not allow AI-sent messages.
- One fictional adult persona in the prototype; at least 5 personas in the early version release.
- Text-only prototype; no selfies or voice calls yet.
- Languages: Hinglish, Hindi, and English, with authentic Gen-Z/millennial colloquial texting texture.
- Persona-initiated texts at randomized times in the prototype and the early release.
- Subscription plans: daily, weekly, and monthly, plus a daily top-up.
- Crisis detection with helpline handoff.
- First release is romantic-only. Explicit (NSFW) content is a later phase with preconditions; see [Safety](08_safety_crisis_and_adult_content.md).
- Jealousy and arguments: on by default with Realistic intensity, disclosed at onboarding, with an on/off switch and intensity setting for the customer; conflicts handled with mature same-session de-escalation and never mentioning money or plans.
- Review and reporting: no staff read chats except via the customer's "report this" and consenting pilot testers.
- PostgreSQL from the start; ₹0 cash spend for now, with a small budget or low-cost LLM only if the prototype proves impressive.
- Gradual, editable customer communication-style adaptation; no per-conversation fine-tuning.

## What changed in v8
- **Memory Lifecycle & Dormancy Test**: Reaffirmed that user memory cannot be stored indefinitely / for a lifetime (for DPDP privacy compliance and data minimization). Added a pilot validation plan to test whether immediate hard deletion harms resurrection loops, introducing a "dormant / drifted apart" state where the persona gently acknowledges elapsed time (*"It's been so long, I feel like we lost touch... tell me how you've been"*) before full database deletion.
- **Vibrant First Encounter**: Replaced sterile stranger small talk with an immediately engaging, culturally specific first encounter (e.g. an amusing encounter at a metro station or a bustling cafe) where the persona's distinct voice, charm, and wit shine through on message 1.
- **Mature Conflict Resolution & De-escalation**: Disagreements and mood swings are handled with real-world maturity. Mandated a natural de-escalation pathway within the same conversation session (never leave an argument dangling as a psychological hook). Strictly prohibited mentioning subscriptions, money, memory expiry, or deletion during arguments.
- **Colloquial Hinglish Texture**: Elevated authentic Gen-Z/millennial texting rhythms (*"achha suno"*, *"arre yaar"*, natural code-switching cadence, appropriate playful emojis) as the core differentiator over generic machine-translated Hindi/Hinglish.
- **Confirmed Decisions**: Backend set to FastAPI; default emotional realism set to Realistic; pre-monetization pilot testers granted Beta Entitlements to preserve memories during user testing while testing the 15-day clock via controllable automated test clocks.

## What changed in v7
- **Jealousy and arguments are on by default** (the v6 pack had them off). The customer is told at onboarding and can switch them off or change intensity. Guardrails are unchanged (never tied to payment, crisis override), and the persona now also never mentions plans, subscription, memory expiry, or deletion during moods or arguments.
- **Memory is linked to subscription.** An active daily, weekly, or monthly plan keeps the relationship memory. For unsubscribed customers (free, trial, cancelled, lapsed) the 15-day inactivity rule deletes it. Reasons: storage cost, and realism (people who lose touch forget and move on).
- The old "no paid protection" rule is replaced: payment keeps memory while subscribed, but subscribing after deletion does not restore it and payment never buys preferential emotional treatment. No-guilt and no-pressure rules stay. The day-12 notice applies to unsubscribed customers only and comes from the app, not the persona.
- The 15-day clock starts on the subscription end date.
- Architecture, requirements, roadmap tests, safety, and business plan (storage cost, conversion and fairness checks, legal gate) updated to match.

**Open items needing your confirmation**
1. How the rule applies to pilot testers before payments exist.
2. Default intensity for jealousy and arguments (mild or realistic).

## What changed in v6
- New [Business Plan](09_business_plan.md): competitor scan, go-to-market hypotheses, unit economics, approved pilot targets and kill criteria.
- Romantic-only first release; NSFW moved to a later phase with preconditions (age verification, legal, LLM provider, payment gateway, hosting).
- Opt-in review and reporting rules added.
- Jealousy and arguments were made optional and off by default (superseded in v7: now on by default).
- Added the 15-day inactivity expiry and relationship-specific memory deletion rule (refined in v7: applies to unsubscribed customers only).
- Added a first-encounter-to-dating relationship story arc and explicit separation of canonical persona state from per-user relationship data.
- Added lifecycle deletion architecture, safety constraints, and validation tests.
- Hinglish/Hindi/English requirement and evaluation.
- PostgreSQL from the start (v4 docs disagreed).
- India DPDP Act notes added to the privacy section, flagged for lawyer review.
- Note that web push needs an always-on, HTTPS-reachable server, so ₹0 local-only testing cannot deliver pushes when the machine is off.
- Deferred by the owner: spend caps and break nudges for heavy users.

Zero-cost production cannot be guaranteed indefinitely. Free tiers have limits, and local inference has hardware and electricity costs. These documents are a working specification, not legal advice or validated market research.

---

## Core relationship lifecycle rule

While a customer has an active daily, weekly, or monthly plan, their relationship memory is kept. For an unsubscribed customer (free, trial, cancelled, or lapsed), memory cannot be stored indefinitely or for a lifetime under privacy regulations (DPDP Act). After 15 consecutive days without a user-initiated interaction with a specific persona, that relationship expires. The pilot will evaluate an intermediate "dormant / drifted apart" state (where the persona warmly notes the elapsed time upon resurrection) versus immediate hard deletion to measure impact on user reactivation. Once permanent expiry triggers, relationship-specific memories, open loops, relationship state, and linked conversation context are deleted under the disclosed retention policy. The persona's generic fictional identity and life continue and can be available to another user, whose relationship starts fresh. App opens and persona-initiated notifications do not reset the timer; a user message or reply does. Subscribing after expiry does not recover deleted memories. See [Memory and Relationship Progression](05_memory_and_relationship.md) for the full specification.
