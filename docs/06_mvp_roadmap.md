# 6. MVP Roadmap and Validation Plan

## Product hypothesis

Adults will voluntarily return to a fictional AI persona when the
persona's life progresses independently, conversations use memory
naturally, and familiarity evolves over time.

## Phase 1 --- Text conversation foundation

### Build

- Progressive web app (PWA) shell and account system.
-   One fictional adult persona with a vibrant, culturally grounded first-encounter scenario (message 1 wit and charm).
-   Stable persona profile and communication style with authentic Gen-Z/millennial colloquial Hinglish texture (*"achha suno"*, *"arre yaar"*, natural code-switching cadence; no bookish Hindi).
-   Conversation history.
-   Basic memory extraction and retrieval.
- AI disclosure, 18+ gate, and privacy controls.
-   Basic crisis detection with helpline handoff (English, Hindi, Hinglish).
-   Content-tier setting scaffold (explicit tier locked).
-   Hinglish, Hindi, and English conversation with an evaluation set measuring natural colloquial cadence.
-   Emotional realism baseline (Realistic intensity default) with mature same-session conflict de-escalation; strictly never mentioning money, subscriptions, or memory deletion.
-   "Report this" flow and tester consent.
-   PostgreSQL schema from the start (FastAPI backend).
-   Cost and error logging.

### Exit criteria

-   Persona remains consistent across sessions.
-   First encounter immediately engages users and demonstrates persona wit from message 1 without sterile small talk.
-   Conversations can resume with relevant context.
-   Basic memory corrections and deletion work.
- Costs per conversation can be estimated.
-   Crisis messages in a test set reliably trigger the handoff path.
-   Disagreements resolve maturely in-session with no psychological hooks or financial guilt.

## Phase 2 --- Life simulation

### Build

-   Persona state and timeline.
-   Recurring routines.
-   Candidate event generation and weighted selection.
-   Timeline consistency checks.
-   Persisted plans and event consequences.

### Exit criteria

-   Events do not regularly contradict prior state.
-   Routine variation feels plausible in user testing.
-   State can advance without expensive continuous LLM calls.

## Phase 3 --- Contextual memory and relationship progression

### Build

-   Episodic and profile memories.
-   Open-loop tracking.
-   Contextual retrieval.
-   Conversation strategy selection.
- Preference-aware romantic tone (romantic-only in the first release).
-   Persona-initiated texts at randomized times, grounded in the persona's day, memories, and open loops.
-   Customer-controlled frequency, quiet hours, and notification opt-out.
-   Jealousy and argument behaviour, on by default and customer-controlled (switch and intensity setting).
-   Repetition and contradiction evaluations.

### Exit criteria

-   Relevant memories are used appropriately.
-   Follow-ups are not repeated mechanically.
-   Relationship tone follows customer preferences.
- Users can inspect, correct, and delete memories.
-   Persona-initiated messages add value without feeling intrusive; opt-outs and quiet hours are reliably enforced.
-   Jealousy and arguments (on by default) feel human and never pressure the customer.

## Phase 4 --- Early version release: personas and monetization

### Build

-   Expand to at least 5 distinct personas.
-   Daily, weekly, and monthly plans plus a daily top-up, with UPI payments.
-   Subscription and entitlement management.
-   Subscription status drives the memory-retention rule (active plan: memory kept; unsubscribed: 15-day inactivity expiry).
-   Usage limits and cost controls.
-   Free trial and gf/bf persona choice (nice-to-have).

### Exit criteria

-   Each persona stays consistent and distinct.
-   Persona-initiated messages, quiet hours, and crisis handling work across all personas.
-   Paying customers have positive contribution margin under tested usage assumptions.

## Phase 5 --- Expansion decisions

Only after the early release demonstrates retention:

-   Add voice notes or speech interaction (voice calls were originally planned).
- Consider a native mobile app only if the PWA hits limits (for example push reliability or store distribution); the PWA already covers mobile.
-   Add more personas beyond the first 5.
-   Explicit (NSFW) content, only after every precondition in the Safety document is met.
-   Explore external messaging channels (WhatsApp currently does not allow AI-sent messages) only after explicit policy and technical review.

Selfies and generated personal images remain outside the initial plan.

## User validation

Recruit a pilot of 30-50 consenting adult testers. Explain clearly that
the persona is fictional and AI-powered.

Evaluate: - Does the character feel consistent? - Does the routine feel
believable? - Are memories recalled at appropriate moments? - Does the
experience feel repetitive? - Is proactive contact welcome? - Does
romantic progression feel comfortable? - Would the tester return and pay
for the experience? - Does the product create unwanted pressure or distress?
-   Do jealousy and arguments feel human rather than manipulative?
-   Does crisis handling respond appropriately?

Avoid interpreting high message volume as proof of value. Use user
feedback, retention, renewal, and cost together.

## Pilot targets and kill criteria (approved)

-   Pilot of 30-50 consenting adults.
-   Day-7 retention at least 25%; Day-30 retention at least 10%.
-   Free-to-paid conversion at least 4%.
-   Variable cost at most 30% of net revenue per paying user.
-   Kill or pivot if Day-7 retention stays below 15% after two pilot rounds.

Review after each pilot round. Details in [Business Plan](09_business_plan.md).

## Business metrics

-   Activation and first-week retention.
-   Day 7 and Day 30 retention.
-   Paid conversion and renewal.
-   Churn.
-   Cost per active user.
-   Contribution margin per paying user.
-   Memory relevance and accuracy.
-   Persona contradiction rate.
-   Proactive-message opt-out rate.
-   User-reported companionship and unwanted pressure.

## Major risks

### Platform restrictions

WhatsApp policy does not allow AI-sent messages, so the first version is its own progressive web app, installed from the browser rather than an app store. External messaging integrations, app stores, and payment providers all need separate policy checks, especially for romantic and adult content.

### Privacy

Conversation histories can contain sensitive information. Minimize
collection, secure data, establish retention rules, and implement
deletion.

### Emotional dependency

Avoid coercive engagement design. Jealousy and arguments are on by default (the customer can switch them off) and never tied to payment or retention. Memory is kept while the customer has an active subscription; for unsubscribed customers the 15-day inactivity expiry is a disclosed lifecycle rule, not an engagement tactic: use no guilt or threats, keep the reminder neutral and from the app, and delete relationship-specific data as specified in the Memory and Relationship document. Because memory retention is now tied to a plan, test that it reads as a fair plan benefit and not as pressure.

### Vulnerable users

Lonely customers may be in distress. Crisis detection must work from the first prototype; test it with synthetic conversations and keep helpline details current.

### Adult content and legal

The first release is romantic-only. Before any explicit (NSFW) content: stronger age verification, opt-in, hard content limits, legal review (Indian rules on obscene content), and written confirmation that the LLM provider terms, payment gateway, and hosting all allow it. Any one of these can block the feature. Check app-store policies too if a native app is built.

### Technical complexity

Keep the architecture modular, but do not begin with multiple autonomous
agents. Conventional state and scheduling logic will cover much of the
initial need.

### Language quality

Small local models are often weak at Hinglish and Hindi, and natural texting is the core hypothesis. Test early with a Hinglish evaluation set; template responses cannot validate realism.

### Unit economics

Measure model use and notification costs early. Do not run the LLM
continuously to simulate every minute.

### Market uncertainty

Pricing, audience size, and willingness to pay are hypotheses until
tested with real users.

## Recommended immediate next steps

1.  Write the specification for the first persona.
2.  Define the persona-state and memory schemas.
3.  Write the crisis-detection and content-tier specification (see [Safety, Crisis Detection and Adult Content](08_safety_crisis_and_adult_content.md)).
4.  Build the basic text chat and persistence layer.
5.  Add a small set of routine and event templates.
6.  Create an evaluation set for memory relevance, continuity, and crisis detection.
7.  Add persona-initiated texts with randomized timing.
8.  Test with adult users.
9.  Add subscriptions and top-ups only after users demonstrate repeated use and willingness to pay.

## Added requirement: style adaptation

Implement a structured style profile and prompt conditioning before considering fine-tuning. Evaluate style fit, identity consistency, correction rate, and unwanted mimicry.

## Zero-spend gate

The first prototype should run locally without paid AI APIs or mandatory hosting. Validate orchestration with templates first, then test a small local model on existing hardware. Consider paid inference only after measuring a real quality gap, repeat use, estimated per-user cost, and an explicit spending cap. The ₹0 rule holds for now; if the prototype proves impressive, the owner may introduce a small budget or a low-cost LLM.

---

## Added validation work: relationship lifecycle and moving on

### Prototype requirements

- Implement a deterministic 15-day inactivity clock per user-persona relationship, active only while the customer has no active plan.
- Reaffirm that user memory cannot be stored indefinitely or for a lifetime under DPDP Act privacy requirements.
- Pilot testers are granted Beta Entitlements to preserve memories during user feedback testing, while the 15-day inactivity expiry clock is tested and validated deterministically using a controllable test clock.
- Test that only a user-initiated message/reply resets the clock.
- Simulate day 12, day 15, and the intermediate "dormant / drifted apart" state with a controllable test clock; do not wait 15 real days during QA.
- Verify expiry disables scheduled messages immediately and deletes relationship-specific context without deleting canonical persona configuration.
- Verify a customer with an active plan (or beta entitlement) never expires, that a plan ending starts the clock as specified, and that a renewal racing with expiry does not delete a subscriber's memory.
- Verify subscribing after expiry does not restore deleted context.
- Verify a new user receives a clean first-encounter story and cannot retrieve another user's facts.
- Test early relationship ending, user-requested deletion, retries, duplicate jobs, and deletion failures.

### User research questions

- Does the finite 15-day window feel like meaningful relationship simulation or an unfair penalty?
- Does an intermediate "dormant / drifted apart" state (where the persona warmly recognizes elapsed time upon resurrection) improve return rates compared to cold hard deletion?
- How do pilot testers perceive the memory expiration rule?
- Does tying memory to an active subscription feel like a fair plan benefit, or like pressure to pay?
- Is the rule understood before the user starts?
- Does the day-12 neutral reminder feel informative rather than pressuring?
- Would users prefer a pause option, and would that undermine the core concept?
- Does the first-encounter-to-dating arc feel natural, or too scripted?

Measure comprehension, trust, complaints, opt-outs, retention, and willingness to pay. If the lifecycle rule harms trust or makes the product feel coercive, revisit the product hypothesis and the subscription link rather than adding pressure or guilt mechanics.
