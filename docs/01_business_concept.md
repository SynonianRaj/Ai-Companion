# 1. Business Concept

## Executive summary

The business is a subscription-based AI companionship platform where adults experience a fictional relationship arc with an AI persona—from first encounter and introduction, through getting to know each other and dating, to an established relationship, pause, ending, or moving on.

It is not designed as a conventional chatbot that only answers direct
questions. Each persona has a stable identity, a simulated daily life,
personal interests, changing plans, long-term memory, and an evolving
interaction history with each customer.

The prototype is a standalone progressive web app (PWA) with text conversations and one persona, installable on a phone's home screen; a native mobile app is optional later. WhatsApp is excluded because its policy does not allow AI-sent messages. Selfies and voice calls are out of scope for now to limit complexity. The early version release adds more personas (at least 5). The first release is romantic-only; explicit (NSFW) content is deferred to a later phase. Market, pricing targets, and kill criteria are in [Business Plan](09_business_plan.md).

## Problem

Many chatbot experiences feel transactional or repetitive:

-   The character has no independent life outside the conversation.
-   Past conversations are forgotten or recalled at the wrong time.
-   Follow-up questions repeat on a schedule rather than emerging
    naturally.
-   Romantic language may escalate too quickly.
-   Daily interactions repeat predictable greetings and scripts.

## Proposed solution

Combine four systems:

1.  **Life simulation:** gives the persona a plausible timeline,
    activities, plans, and changing availability.
2.  **Relationship memory:** stores meaningful customer details and
    shared events.
3.  **Conversation intelligence:** chooses relevant responses and topics
    based on context.
4.  **Relationship progression:** adapts familiarity and romantic
    expression to accumulated interactions and customer preferences.

## Value proposition

A continuing AI relationship experience with:

-   A consistent fictional personality.
-   An independently advancing, culturally grounded life.
-   Contextual memory and relevant follow-ups.
-   Natural variation without contradictions.
-   Gradual, preference-aware romantic interaction.
-   Natural conversation in Hinglish, Hindi, and English with authentic colloquial texture (Gen-Z/millennial Indian texting cadence, natural code-switching like "achha suno" and "arre yaar", and playful emojis; never stiff or bookish).
- A persona that reaches out on its own at natural, randomized times.
- Emotional realism (moods, jealousy, disagreements), on by default (Realistic intensity), disclosed at onboarding, and controlled by the customer. Disagreements are handled with real-world maturity, include a natural same-session de-escalation pathway, and strictly never mention money, subscription, or memory loss.
-   Customer control over notifications, memory, and participation.

The intended emotional value is enjoyable companionship and a feeling of
being heard. These outcomes must be measured with users; the product
must not promise specific biological effects or guaranteed treatment of
loneliness or stress.

## Target audience

Adults who want one or more of the following:

-   A conversational companion.
-   Romance-themed fictional interaction.
-   Consistent, personalized conversations.
-   A character with a believable everyday life.
-   A low-friction way to enjoy companionship in their preferred
    language.

Validate the actual target segment through interviews and a small pilot
rather than assuming all users want the same relationship style.

## Differentiation

The core differentiator is **independent routine + contextual memory + conversational initiative + vibrant first encounter + authentic colloquial Hinglish texture + mature emotional realism + a disclosed subscription-linked memory lifecycle (memory kept while subscribed; 15-day inactivity reset once unsubscribed)**. 

The product should not compete only on the number of messages or characters. It should compete on continuity, personality craft, and texture. Indian-language and Hinglish companion apps already exist (see [Business Plan](09_business_plan.md)), so language support alone is not a differentiator—what matters is avoiding mechanical translations and capturing authentic Indian texting cadence, combined with an immediately engaging narrative.

## Business model

Subscription model with short and long plans, not per-minute charges:

-   **Plans:** daily, weekly, and monthly subscriptions.
-   **Daily top-up:** an extra usage pack for a single day.
-   **Free trial:** optional (nice-to-have), with limited conversations and basic memory.

Illustrative monthly prices for validation in India (not market-validated):

-   Companion: ₹199--299/month for persistent memory and richer usage.
-   Companion Plus: ₹499--799/month for higher limits and later optional voice features.

Daily, weekly, and top-up prices are to be set after measuring variable cost per active user. Unit-economics targets are in [Business Plan](09_business_plan.md). Payments should support UPI.

Do not charge users to prevent hostility, guilt, or punitive treatment. Paid tiers must provide transparent usage and feature benefits. Keeping the relationship memory is one disclosed benefit of an active subscription (see the memory rule below); payment never buys preferential emotional treatment, and subscribing after expiry does not restore deleted memories.

## Initial positioning

"An AI companion with a life of her own."

The persona is fictional and AI-powered. The customer is told this at signup; after that the persona stays in character and never denies being an AI if sincerely asked. Marketing must not imply that the customer is speaking to a real human or that the AI possesses human consciousness.

## Key assumptions to validate

-   Customers value persistent memory and a continuing persona.
-   The simulated routine makes interactions feel more coherent, not
    more artificial.
- Customers return voluntarily after the novelty period.
-   Customers welcome persona-initiated messages and, where enabled, human-like emotional range, without feeling pressured.
-   A meaningful share of users will pay for continuity and
    personalization.
-   Per-customer inference and messaging costs allow sustainable
    margins.

## Adaptive communication

The persona gradually adapts its delivery style to each customer using a private, editable communication-style profile (language, brevity, tone, emoji use, humour, and advice-versus-listening preference). It retains its own stable identity. The MVP uses profile updates and prompt conditioning, not continuous fine-tuning.

## Zero-cost philosophy

The prototype targets ₹0 cash spend using local development, open-source tools, structured memory, and rule-based simulation. Paid APIs and hosting are deferred until testing shows value. The owner's rule: ₹0 for now; if the prototype proves impressive, introduce a small budget or a low-cost LLM. See [Adaptive Communication and Zero-Cost Development](07_adaptive_communication_and_zero_cost.md).

---

## Subscription-linked memory and 15-day inactivity reset (core product rule)

The product intentionally simulates a relationship that can progress, pause, or end rather than guaranteeing permanent access to one companion's attention. Disclose this rule plainly before a user starts a relationship and keep it visible in relationship settings.

**Who the rule applies to (owner decision, v7):**

- **Active subscription** (an active daily, weekly, or monthly plan): the relationship memory is kept. There is no inactivity expiry while the plan is active.
- **Unsubscribed** (free, free trial, cancelled, or lapsed): the 15-day inactivity rule below applies, and the relationship context is deleted when it triggers.
- **When a plan ends:** the 15-day clock starts on the subscription end date (owner decision). A deliberate user message after that date still resets it, as in the inactivity rule below.
- **Why:** keeping every customer's memory indefinitely is prohibited under data minimization and privacy rules (DPDP Act), costs storage, and in real life people who lose touch also forget and move on. However, because memory is also a vital retention anchor, user memory cannot be stored for a lifetime, but the pilot will explicitly test whether cold hard deletion damages resurrection loops versus testing a **"dormant / drifted apart" state** before final deletion.

**How the 15-day rule works (unsubscribed customers):**

- **Clock (unsubscribed customers only):** Count 15 consecutive calendar days from the last user-initiated interaction with that specific persona. Opening the app, receiving a notification, or an automated outbound message does not reset the clock. A deliberate user message or reply does.
- **Neutral reminder:** At most one neutral, non-guilt-based notice may be shown around day 12, if product reminders are enabled. Do not send repeated chase messages, threaten abandonment, imply the persona is suffering, or use urgency to sell a subscription. Send it from the app, not in the persona's voice. It may state plainly that active subscribers keep their memory, without pressure or a sales pitch.
- **Pilot evaluation: Dormancy vs. Hard deletion:** In the pilot, evaluate an intermediate "dormant / drifted apart" state where, if a user returns after day 15, the persona gently acknowledges the gap (*"It's been so long, I feel like we lost touch... tell me how you've been"*) instead of displaying total instant amnesia, measuring user resurrection rates and qualitative sentiment before executing permanent deletion. Permanent deletion is ultimately enforced because lifetime storage is not permitted.
- **At the 15-day threshold (unsubscribed customers):** Mark that user-persona relationship as expired (or dormant during pilot evaluation). Stop proactive messages. Delete relationship-specific context upon confirmed expiry: user profile memories held for this persona, episodic and shared-history memories, open loops, private relationship state, relationship-scoped style inferences, and relationship-linked conversation content according to the disclosed deletion schedule. Do not silently retain this data for future personalization.
- **Persona availability:** The fictional persona's canonical identity, personality, general routine, and non-user-specific life timeline remain. The persona can then start a new relationship with another eligible user, from the beginning. No prior user's memories, messages, preferences, or private facts may cross over.
- **Separate user controls:** Users can review/export where supported, delete memories, end the relationship early, or delete their account. Account deletion and legal/security records have separately disclosed handling. The 15-day rule does not override an earlier deletion request.
- **Deletion reliability:** Use a scheduled lifecycle job, idempotent deletion, access revocation, and a verifiable deletion status. Define backup expiry and deletion windows in the privacy notice; data awaiting backup expiry must not be available to application queries or model context. Keep only minimal non-content operational evidence needed to verify deletion, under a documented retention period.
- **Subscription and memory:** An active subscription keeps the relationship memory, so there is no inactivity expiry while a daily, weekly, or monthly plan is active. Payment still cannot buy preferential emotional treatment, and subscribing after expiry does not restore deleted memories.
- **No false realism claims:** Explain that this is a fictional simulation, not a human partner making independent real-world choices. The design may model moving on, but must not claim consciousness or real-world emotional harm.

This rule trades some persistent-memory retention for the product's finite, evolving relationship concept. It is a hypothesis to validate with users and must be reviewed for privacy-law and consumer-protection compliance before launch, including how tying memory to a paid plan is disclosed and presented.

## Relationship story arc: from first meeting to dating

Relationship progression begins at the start, not with an already-established girlfriend/boyfriend. Use an explicit, user-led sequence of fictional stages:

1. **First encounter:** Vibrant, culturally specific, and immediately engaging (e.g. an amusing encounter at an Indiranagar cafe, a mix-up over orders, or a relatable mishap at a metro station) rather than sterile, generic small talk. The persona's distinct voice, wit, and charm shine through from the very first message to prevent Day-0 drop-off, while establishing clearly fictional adult roleplay.
2. **Approach / introduction:** The user chooses whether to initiate conversation. The persona responds consistently with its character and context; interest is not guaranteed.
3. **Contact exchange:** If the interaction is positive in the story, offer an in-app fictional connection step. Do not collect real phone numbers or social handles for the fictional persona, or imply that a real person can be reached outside the app.
4. **Getting to know each other:** Conversation, interests, boundaries, trust, and shared events build familiarity gradually.
5. **Dating:** Romantic roleplay becomes available only when interaction and user preferences support it; the user can decline, slow down, or reset progression.
6. **Established relationship:** Optional affectionate roleplay after sufficient mutual in-story progression and clear user preference.
7. **Pause, ending, or moving on:** The user may end the relationship at any time. The 15-day inactivity rule also expires it for unsubscribed customers. The persona's reusable canonical profile remains, but the expired user's relationship memory is deleted.

Stages are narrative states, not rewards for message volume or payment. Do not guarantee attraction, shame the user for rejection, or portray persistence after a clear boundary as romantic. The persona can show preferences and say no within the fiction. All personas and users must be adults, and relationship stages remain fictional and transparently AI-generated.
