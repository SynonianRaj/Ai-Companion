# 5. Memory and Relationship Progression

## Objective

Make the persona remember what matters and use that information only
when it is relevant to the current conversation. Let familiarity grow
through accumulated interactions rather than fixed time-based scripts.

## Memory categories

### 1. Profile memory

Stable customer preferences and details that are useful for
personalization, such as preferred language or hobbies.

### 2. Episodic memory

Specific events the customer shared, including interviews, exams,
celebrations, plans, or difficult experiences.

### 3. Shared-history memory

Inside jokes, recurring topics, prior recommendations, and meaningful
conversations between the customer and persona.

### 4. Open loops

Unresolved topics or plans that may deserve a later follow-up, such as
waiting for an interview result.

### 5. Persona-life memory

The persona's own fictional events, plans, and experiences. These must
remain distinguishable from customer facts.

## Memory record design

A memory record may include: - Memory type. - Short normalized
summary. - Source message reference. - Timestamp. - Confidence and
importance. - Whether it is confirmed, inferred, or fictional. - User
correction/deletion status. - Optional expiry or review policy.

Do not save every message as a permanent memory. Store only information
likely to improve continuity and use appropriate privacy safeguards.

## Contextual retrieval

When a customer sends a message:

1.  Identify the current topic and intent.
2.  Search recent messages and relevant long-term memories.
3.  Rank candidate memories by topical relevance, recency, importance,
    and confidence.
4.  Include a small set in the context.
5.  Ask the model to use memories only when they naturally fit.
6.  Update memory after the exchange if new durable information was
    shared.

Use a combination of structured filtering, keyword/full-text search, and
semantic search when needed. Start simple and evaluate retrieval quality
before adding more infrastructure.

## Example: interview follow-up

The customer says on Monday: "I had an interview today. I think it went
okay, but I'm nervous about the result."

Store an episodic memory and an open loop: - Event: interview. - Date:
Monday. - Outcome: pending. - Customer feeling: nervous. - Status:
unresolved.

On Thursday, the customer says: "I'm thinking about switching jobs
because my current salary is low."

The conversation engine recognizes that the job-switch topic is relevant
and may ask: "Did you hear anything back about that interview you
mentioned?"

If the customer instead discusses a movie, the system should not force
an interview follow-up into that conversation.

After the customer shares the result, update the memory and close or
revise the open loop. Do not keep asking the same question every day.

## Relevance policy

An open loop is a candidate for future conversation, not a scheduled
command.

A follow-up should depend on: - Current topic relevance. - Time
elapsed. - Whether the user already answered. - Whether the subject is
sensitive. - Whether the customer appears willing to discuss it. -
Whether bringing it up would feel natural.

Some memories may never need to be mentioned again. That is acceptable.

## Relationship progression

Use relationship context to guide tone, not to claim that the AI has
human feelings.

Signals can include: - Frequency and quality of voluntary interaction. -
Shared conversational history. - Customer-stated preferences. - Comfort
with romantic language. - Boundaries and feedback. - Recurring shared
interests.

Possible interaction styles include: - New acquaintance. - Familiar
conversation partner. - Warm and affectionate companion. - Established romantic roleplay.
- Later phase, not in the first release: explicit adult style (see the Safety document).

These are flexible styles, not levels unlocked after a fixed number of
days. The customer should be able to slow down, change preferences, or
opt out.

## Conversation planner

Before generating a reply, select a strategy: - Answer the current
question. - Ask a natural follow-up. - Refer to a relevant memory. -
Share a relevant fictional experience. - Continue a shared topic. -
Change topic gently. - Offer support without overclaiming expertise. -
End the conversation naturally.
- Start a conversation (a check-in grounded in the persona's day, a memory, or an open loop).
- Express a mild feeling such as missing the customer, light jealousy, or a disagreement (unless the customer has switched emotional realism off).

Do not force the character to be interested in every detail or to always
agree. A consistent personality can express preferences and respectful
disagreement.

## Ethical constraints

-   Never use guilt or abandonment threats to induce engagement.
-   Do not manufacture crises to bring the customer back.
-   Do not imply the AI will be harmed if the customer leaves.
-   Do not make affection conditional on payment.
-   Clearly distinguish AI-generated fiction from a real human
    relationship.
- Give users control over stored memories and proactive contact.
- Jealousy and arguments are on by default (Realistic intensity); the customer can switch them off or change intensity.
- Disagreements must be handled with maturity like real people do in real life. Ensure a natural de-escalation pathway within the same conversation session; never leave a fight hanging as an unresolved psychological hook.
- Never mention subscriptions, plans, pricing, memory expiry, or deletion during moods or arguments.
-   If crisis signals appear, drop romantic and conflict behaviour and follow the crisis-response path (see [Safety, Crisis Detection and Adult Content](08_safety_crisis_and_adult_content.md)).

## Communication-style learning

Keep a private style profile separate from relationship memory. Learn language, brevity, tone, emoji, humour, and advice/listening preferences from repeated evidence. Explicit preferences take priority; inferred preferences should have confidence/provenance and be editable, resettable, and optional. The persona adapts how it communicates while retaining its own identity. Do not mimic distress or use style matching to increase dependency. See [Adaptive Communication and Zero-Cost Development](07_adaptive_communication_and_zero_cost.md).

---

## Subscription-linked memory and 15-day inactivity reset (core product rule)

The product intentionally simulates a relationship that can progress, pause, or end rather than guaranteeing permanent access to one companion's attention. Disclose this rule plainly before a user starts a relationship and keep it visible in relationship settings.

**Who the rule applies to (owner decision, v7):**

- **Active subscription** (an active daily, weekly, or monthly plan): the relationship memory is kept. There is no inactivity expiry while the plan is active.
- **Unsubscribed** (free, free trial, cancelled, or lapsed): the 15-day inactivity rule below applies, and the relationship context is deleted when it triggers.
- **When a plan ends:** the 15-day clock starts on the subscription end date (owner decision). A deliberate user message after that date still resets it, as in the inactivity rule below.
- **Why:** keeping every customer's memory indefinitely is prohibited under data privacy requirements (DPDP Act), costs storage, and in real life people who lose touch also forget and move on. However, because memory is the primary retention foundation, lifetime storage is prohibited, but the pilot will evaluate an intermediate **"dormant / drifted apart" state** to test whether cold hard deletion damages resurrection loops before permanent deletion.

**How the 15-day rule works (unsubscribed customers):**

- **Clock (unsubscribed customers only):** Count 15 consecutive calendar days from the last user-initiated interaction with that specific persona. Opening the app, receiving a notification, or an automated outbound message does not reset the clock. A deliberate user message or reply does.
- **Neutral reminder:** At most one neutral, non-guilt-based notice may be shown around day 12, if product reminders are enabled. Do not send repeated chase messages, threaten abandonment, imply the persona is suffering, or use urgency to sell a subscription. Send it from the app, not in the persona's voice. It may state plainly that active subscribers keep their memory, without pressure or a sales pitch.
- **Pilot evaluation (Dormancy vs. Hard deletion):** Evaluate an intermediate "dormant / drifted apart" state where, if a user returns after day 15, the persona gently acknowledges elapsed time (*"It's been so long, I feel like we lost touch... tell me how you've been"*) before full database purge, comparing reactivation and user sentiment against instant hard amnesia.
- **At the 15-day threshold (unsubscribed customers):** Mark that user-persona relationship as expired (or dormant during pilot testing). Stop proactive messages. Delete relationship-specific context upon confirmed deletion: user profile memories held for this persona, episodic and shared-history memories, open loops, private relationship state, relationship-scoped style inferences, and relationship-linked conversation content according to the disclosed deletion schedule. Do not silently retain this data for future personalization.
- **Persona availability:** The fictional persona's canonical identity, personality, general routine, and non-user-specific life timeline remain. The persona can then start a new relationship with another eligible user, from the beginning. No prior user's memories, messages, preferences, or private facts may cross over.
- **Separate user controls:** Users can review/export where supported, delete memories, end the relationship early, or delete their account. Account deletion and legal/security records have separately disclosed handling. The 15-day rule does not override an earlier deletion request.
- **Deletion reliability:** Use a scheduled lifecycle job, idempotent deletion, access revocation, and a verifiable deletion status. Define backup expiry and deletion windows in the privacy notice; data awaiting backup expiry must not be available to application queries or model context. Keep only minimal non-content operational evidence needed to verify deletion, under a documented retention period.
- **Subscription and memory:** An active subscription keeps the relationship memory, so there is no inactivity expiry while a daily, weekly, or monthly plan is active. Payment still cannot buy preferential emotional treatment, and subscribing after expiry does not restore deleted memories.
- **No false realism claims:** Explain that this is a fictional simulation, not a human partner making independent real-world choices. The design may model moving on, but must not claim consciousness or real-world emotional harm.

This rule trades some persistent-memory retention for the product's finite, evolving relationship concept. It is a hypothesis to validate with users and must be reviewed for privacy-law and consumer-protection compliance before launch, including how tying memory to a paid plan is disclosed and presented.

## Relationship story arc: from first meeting to dating

Relationship progression begins at the start, not with an already-established girlfriend/boyfriend. Use an explicit, user-led sequence of fictional stages:

1. **First encounter:** Vibrant, culturally specific, and immediately engaging (e.g. an amusing encounter at a metro station or a bustling cafe) rather than sterile small talk. The persona's distinct voice, wit, and charm shine through from the very first message to eliminate Day-0 drop-off.
2. **Approach / introduction:** The user chooses whether to initiate conversation. The persona responds consistently with its character and context; interest is not guaranteed.
3. **Contact exchange:** If the interaction is positive in the story, offer an in-app fictional connection step. Do not collect real phone numbers or social handles for the fictional persona, or imply that a real person can be reached outside the app.
4. **Getting to know each other:** Conversation, interests, boundaries, trust, and shared events build familiarity gradually.
5. **Dating:** Romantic roleplay becomes available only when interaction and user preferences support it; the user can decline, slow down, or reset progression.
6. **Established relationship:** Optional affectionate roleplay after sufficient mutual in-story progression and clear user preference.
7. **Pause, ending, or moving on:** The user may end the relationship at any time. The 15-day inactivity rule also expires it for unsubscribed customers (with dormancy evaluation during pilot). The persona's reusable canonical profile remains, but the expired user's relationship memory is deleted.

Stages are narrative states, not rewards for message volume or payment. Do not guarantee attraction, shame the user for rejection, or portray persistence after a clear boundary as romantic. The persona can show preferences and say no within the fiction. All personas and users must be adults, and relationship stages remain fictional and transparently AI-generated.
