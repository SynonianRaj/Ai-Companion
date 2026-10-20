# 2. Product Requirements

## Product goal

Validate whether adult users return to the same fictional AI persona
because the experience feels personal, continuous, and naturally
evolving.

## MVP scope

### Included

-   Account creation and age eligibility checks appropriate to the
    service.
-   Clear disclosure that the persona is fictional and AI-generated.
-   One carefully designed adult persona.
- Text-first progressive web app (PWA): installable on mobile, with a web manifest, service worker, and HTTPS.
-   Persistent conversation history.
-   Structured persona identity and current state.
-   Basic daily-life simulation with controlled variation.
-   Long-term memory for meaningful facts and episodes.
-   Contextual memory retrieval.
-   Tracking of unresolved conversation topics ("open loops").
-   Basic relationship familiarity and customer preference state.
- Customer-controlled notification frequency and quiet hours.
-   Persona-initiated text messages at randomized times (see Proactive interaction).
-   Crisis detection with helpline handoff.
-   Romantic content for adult customers (age eligibility checks). Explicit (NSFW) content is not in the first release; see the Safety document.
-   Hinglish, Hindi, and English conversation quality (see Language requirements).
-   "Report this" flow: the customer can choose to send a message or snippet to the team.
-   Emotional realism (jealousy, moods, disagreements), on by default, with clear disclosure at onboarding and a customer on/off switch and intensity setting.
-   Plan and top-up entitlement model (daily, weekly, monthly, daily top-up); payment integration can follow the prototype. Subscription status also decides whether the memory-expiry rule applies.
-   Privacy settings, memory controls, and account deletion.
-   Usage and cost tracking.

### Excluded from initial MVP

- WhatsApp integration (WhatsApp policy does not allow AI-sent messages).
-   Selfies or generated personal images.
-   Voice calls and voice notes (text-only prototype).
-   More than one persona in the prototype (at least 5 personas arrive in the early version release).
-   Persona marketplace.
-   User-generated persona builder.
-   Complex multi-agent architecture.
-   Claims of medical or therapeutic outcomes.
-   Explicit (NSFW) content (deferred to a later phase).

## Customer journey

1.  Customer discovers the service.
2.  Customer creates an account, completes age eligibility steps, and
    reads the AI disclosure.
3.  Customer chooses basic conversation and contact preferences.
4. Customer meets a fictional adult persona (one in the prototype; a choice of at least 5 in the early release).
5.  Customer begins text conversations.
6.  The persona learns and stores relevant details according to privacy
    settings.
7. The persona's fictional day progresses independently, and the persona sometimes starts a conversation.
8.  Relevant memories influence future conversations when context
    warrants them.
9.  Familiarity and romantic tone evolve according to interaction
    history and customer preferences.
10. Customer can pause notifications, review/delete memories, export where supported, end the relationship, or delete the account.
11. Customer is told before starting that memory is kept while they have an active subscription, and that once unsubscribed, 15 consecutive days without a user-initiated interaction ends that relationship and triggers deletion of its relationship-specific context.

## Functional requirements

### Persona consistency

-   Store core identity and personality as structured data.
-   Prevent arbitrary changes to stable facts.
-   Distinguish stable traits from temporary moods and activities.
-   Ensure all generated events fit the character's background.

### Life simulation

-   Maintain a fictional timeline.
-   Support recurring patterns with variable events.
-   Persist generated events to avoid contradictions.
-   Represent current activity and availability.
-   Use a local timezone configured for the persona.
-   Avoid claiming fictional events occurred in the real world.

### Memory

-   Store customer facts, episodic memories, shared history, and open
    loops separately.
-   Attach timestamps and confidence/provenance metadata where
    appropriate.
-   Retrieve memories based on semantic and conversational relevance.
-   Avoid repeated follow-ups when a topic is not relevant.
-   Allow users to inspect, correct, or delete stored memories.

### Conversation

-   Use recent dialogue and a limited set of relevant memories.
-   Identify the current topic and conversational intent.
-   Choose a response strategy before generating the final message.
-   Check responses for contradictions, repetitive patterns, policy
    issues, and unwanted pressure.
-   Keep the character's communication style consistent.

### Relationship progression

-   Use accumulated interactions, shared experiences, stated
    preferences, and boundaries.
-   Do not escalate romance solely because a certain number of days have elapsed.
-   Allow customers to choose a lighter or more romantic interaction style.
-   Start at a vibrant, culturally specific first encounter (e.g. cafe or metro mishap with immediate wit and charm) and progress through user-led narrative stages; romantic progression must respect boundaries and may be declined.
-   Emotional realism (moods, jealousy, arguments) is on by default (Realistic intensity); the customer can switch it off or change intensity at any time.
-   Disagreements must be handled with emotional maturity like real people do in real life. Ensure a natural de-escalation pathway within the same conversation session; never leave an argument hanging as an unresolved psychological hook.
-   Never use jealousy, guilt, threats of abandonment, or artificial distress to pressure payment, increase usage, or stop the customer from leaving. The persona never mentions subscriptions, plans, pricing, memory expiry, or deletion during arguments or moods.

### Relationship lifecycle, subscription and inactivity expiry

- Subscription rule: an active daily, weekly, or monthly plan keeps the relationship memory with no inactivity expiry. The inactivity expiry applies only to unsubscribed customers (free, trial, cancelled, lapsed). When a plan ends, the 15-day clock starts on the subscription end date; a deliberate user message after that date still resets it.
- Privacy limit: user memory cannot be stored indefinitely or for a lifetime under DPDP Act data minimization requirements.
- Pilot evaluation (Dormancy vs. Hard deletion): evaluate an intermediate "dormant / drifted apart" state where returning users are greeted with a warm recognition of elapsed time (*"It's been so long, I feel like we lost touch... tell me how you've been"*) to measure impact on resurrection loops before permanent deletion.
- Track `last_user_initiated_interaction_at` per user-persona relationship. Only a deliberate user message/reply resets it; opening the app, a notification, or a persona-initiated message does not.
- For unsubscribed customers, at 15 consecutive days, expire the relationship (or transition to dormant during pilot evaluation), stop proactive messages, and queue deletion of relationship-specific memories, open loops, style inferences, relationship state, and relationship-linked conversation content under the disclosed deletion policy.
- Keep only the persona's canonical fictional identity and non-user-specific timeline. Never transfer another user's content or memory to a new user.
- Provide a neutral reminder around day 12 (unsubscribed customers only, sent by the app rather than in the persona's voice) only if product reminders are enabled; no guilt, distress, pressure, or repeated chase messages.
- Subscribing after expiry does not recover deleted context, and payment never buys preferential emotional treatment. Users can end the relationship or request deletion earlier. Define and test backup expiry separately.

### Proactive interaction (included in the prototype and early release)

-   The persona starts conversations itself, for example casual check-ins about the customer's day, meals, or whereabouts.
-   Send times are randomized within allowed windows, not fixed or predictable.
-   Each message needs a natural reason: the persona's simulated day, a stored memory, or an open loop. A fired timer alone is not enough.
-   Respect consent, customer-set frequency, quiet hours, and opt-out.
-   Avoid excessive or repetitive messages; apply daily caps.
- PWA delivery: in-app message, plus web push notification if the customer installs the app and allows it (on iPhone, push works only for the installed home-screen app, iOS 16.4 or later). Calls are out of scope (text-only).

### Safety and adult content

-   Crisis detection with a supportive response and helpline handoff.
-   First release is romantic-only. Explicit (NSFW) content is a later phase with preconditions listed in the Safety document; hard content limits always apply.
-   Product red lines: no celebrity or real-person lookalikes, no selling or sharing chat data, no guilt-tripping to keep paying, no cloning exes or real people or voices, no staff reading customer chats (except what a customer chooses to send through "report this", and consenting pilot testers).
-   Details: [Safety, Crisis Detection and Adult Content](08_safety_crisis_and_adult_content.md).

## Language requirements

-   The prototype must converse naturally in Hinglish, Hindi, and English, and follow the customer's language and script choice (Roman or Devanagari).
-   Must capture authentic Gen-Z/millennial colloquial Indian texting texture: natural code-switching cadence (*"achha suno"*, *"arre yaar"*, *"pakka"*, *"scene kya hai"*), conversational abbreviations, and playful emojis; strictly avoid stiff, textbook Hindi or robotic translations.
-   Build an evaluation set of Hinglish, Hindi, and English conversations and score naturalness, consistency of the persona's language mix, colloquial texture, and memory use.
-   Crisis detection must cover the same languages and colloquial expressions.

## Review and reporting

-   No staff read customer chats by default.
-   "Report this": the customer picks what to send and is told who sees it and why.
-   Pilot testers sign a consent that lets reviewers see their chats for quality and safety.
-   Access is limited and logged; see the Safety document, section D.

## Non-functional requirements

- Secure authentication and authorization.
-   PWA basics: installable (manifest and icons), service worker caching the app shell, mobile-first responsive UI, HTTPS. Chatting needs a connection; offline shows history read-only.
-   Encryption in transit and appropriate protection at rest.
-   Data minimization and defined retention rules.
-   Observability for model latency, errors, and costs.
-   Rate limits and abuse prevention.
-   Reliable background job processing.
-   Clear deletion and consent workflows.
-   Maintainable architecture with replaceable LLM providers.

## Success metrics

### Quality

-   Memory precision and recall quality.
-   Rate of contradictory persona events.
-   Repetitive response rate.
-   User-rated conversational relevance.
-   Rate of inappropriate or unwanted follow-ups.

### Business

-   Activation rate.
-   Day 1, Day 7, and Day 30 retention.
-   Free-to-paid conversion.
-   Renewal rate and churn.
-   Variable cost per active and paying user.
-   Contribution margin.

### User experience and safety

-   User-rated sense of continuity and companionship.
-   Notification opt-out rate.
-   Reports of unwanted pressure or distress.
-   Memory correction/deletion usage.
-   Privacy and safety incidents.

Message volume and session length must not be treated as success by
themselves.

Numeric targets and kill criteria are in [Business Plan](09_business_plan.md).

## Adaptive-style requirements
- Maintain a separate per-customer communication-style profile.
- Learn cautiously from repeated evidence; explicit preferences override inference.
- Allow customers to inspect, correct, reset, or disable adaptation.
- Adapt delivery style without erasing persona identity or mirroring distress.
- Do not fine-tune a shared model on private conversations by default.

## Zero-cost prototype requirements
- The end-to-end prototype must run locally without paid APIs (₹0 for now; a small budget or low-cost LLM only if the prototype proves impressive).
- Use a template/mock response layer before adding an LLM.
- Use PostgreSQL from the start (local install).
- Add hard usage limits and a budget gate before enabling any paid API.

---

## Required relationship narrative and lifecycle

Implement the staged fictional arc: vibrant first encounter (culturally vivid, witty message 1) → approach/introduction → optional in-app connection/contact exchange → getting to know each other → dating → established relationship → pause/dormant/ending/moving on. The user chooses whether to proceed at each stage; the persona may decline or express boundaries. Never collect real phone numbers/social handles as if the fictional persona could be contacted outside the service. The canonical rules are in [Memory and Relationship Progression](05_memory_and_relationship.md).
