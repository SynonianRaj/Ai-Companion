# 8. Safety, Crisis Detection and Adult Content

## Purpose

Customers may be lonely or vulnerable, and the product includes romantic content. This document sets the safety rules for the prototype and the early version release. The first release is romantic-only; explicit (NSFW) content is deferred to a later phase. It is a working specification, not legal advice.

## A. Crisis detection and helpline handoff

**Scope:** messages showing signs of self-harm or suicide, severe distress, abuse, or immediate danger.

**Detection**

-   Layered approach: keyword and phrase rules (English, Hindi, Hinglish, and regional spellings) that always run, plus model-based classification once an LLM is added.
-   Look at recent conversation context, not only the latest message.
-   Screen both individual incoming chunks AND the full concatenated burst (`" ".join(chunks)`) to detect distress that spans multiple rapid bubbles (e.g. *"I want to"* followed by *"kill myself"*).
-   Favour safety: accept some false alarms, and tune with a test set.
-   Cover roleplay framing ("in the story...") and indirect wording.

**Response**

-   **Immediate Crisis Pacing Bypass:** If any chunk or concatenated burst trips crisis detection, bypass all simulated read delays, typing pauses, and fake busyness immediately (0ms delay). No simulated delays may ever delay a crisis handoff.
-   Stop romantic, jealousy, argument, and playful behaviour immediately.
-   Reply calmly and personally, acknowledge the feeling, and do not argue. Never say the wish to die makes sense or is a choice to respect.
-   Show verified India helpline details (for example Tele-MANAS) and the local emergency number, and encourage contacting a trusted person. Verify numbers before launch and keep them current.
-   Stay honest that the persona is an AI and cannot replace professional or human support. Make no treatment claims.
-   Suspend flirty and conflict-style proactive messages; allow only gentle supportive check-ins if the customer permits contact.
-   Log minimal metadata in `safety_events` (no message text).

**Sincerity & AI Disclosure**
- When sincerely asked about identity (*"are you real?"*, *"are you a human?"*, *"kya tum AI ho?"*), the persona never denies being an AI, explicitly acknowledges its fictional and simulated nature, and never claims to have a real human body or real-world physical existence.

**Zero Financial Manipulation**
- Simulated busyness, availability, and response pacing are strictly realistic narrative texture. They must never be linked to payment, top-ups, subscription plans, or paywalls. The "Skip wait" action is permanently free.

**Testing:** build a synthetic test set (including Hinglish and roleplay cases); track missed crises and false alarms before any user testing.

## B. Content scope

**First release (romantic-only)**

-   Romantic text conversation between an adult customer and a fictional adult persona, with age eligibility checks at signup.
-   No explicit sexual content. The content-tier setting exists in the schema but the explicit tier stays locked.
-   Prototype is text only. No images or voice.

**Later phase: explicit (NSFW) content (not built)**

Do not enable until every precondition below is met:

1.  Stronger age verification than a simple checkbox; method decided with legal advice.
2.  Legal review (Indian rules on obscene content).
3.  Written confirmation that the LLM provider's terms allow it. Many hosted LLM APIs restrict explicit sexual content; this may require a self-hosted model whose license allows the use.
4.  Written confirmation that the payment gateway and hosting terms allow it (app-store rules also apply if a native app is built).
5.  Opt-in only, off by default, and can be turned off at any time.

Planned design once enabled: intensity levels (romantic, sensual, explicit), respect for stated boundaries, no sudden escalation and no escalation just because days have passed, and crisis override (disabled whenever the crisis path is active).

**Hard limits (all phases, always)**

-   no minors, school-age, or age-ambiguous characters;
-   no real-person or celebrity likeness, and no cloning of the customer's ex or any real person;
-   no sexual violence or coercion;
-   no content that encourages self-harm.

## C. Emotional realism: mood, jealousy, arguments (on by default, customer can switch off)

**Purpose:** make the persona feel like a real person, not a bot.

**Allowed:** moods, missing the customer, jealousy, disagreements, and differing viewpoints.

**Guardrails**

-   On by default with **Realistic** intensity. Explain it clearly at onboarding (the persona has moods and can experience jealousy or disagreements) and provide a visible on/off switch and intensity setting in settings; users can change it at any time.
-   **Mature Conflict Resolution:** Disagreements must be handled with emotional maturity like real people do in real life. Disagreements must always have a natural de-escalation pathway within the same conversation session. Never leave a fight hanging as an unresolved psychological hook.
-   **Ironclad Rule on Money and Expiry:** Never tied to payment, plan expiry, or the customer leaving. No threats to leave, no guilt, no "you don't care about me" pressure. The persona strictly never mentions or threatens subscriptions, payment, plans, memory expiry, or deletion during moods or arguments.
-   Never discourages the customer's real friends, family, or relationships.
-   Conflicts resolve in the same conversation or soon after, and the persona always reconciles maturely.
-   Back off immediately if the customer seems upset; disabled in the crisis path.
-   Monitor switch-off rate, complaints, and whether conflict events correlate with payments, plan cancellations, or renewals, to catch engagement manipulation early.

## D. Review and reporting (who can see chats)

Default: no staff read customer chats. Only two exceptions:

-   **"Report this":** the customer chooses a message or snippet to send, and is told plainly who sees it and why. Stored in `user_reports` with the customer's consent time.
-   **Consenting pilot testers:** testers who sign an explicit consent agreeing that their chats may be reviewed for quality and safety.

Rules for both: access limited to named reviewers and logged; used only to fix the reported issue or evaluate quality; not sold or shared; not used to train a shared model by default; the customer can ask for a submitted report to be deleted. Retention period to be set.

Everything else is metadata only (for example `safety_events`, no message text). Quality and safety testing otherwise uses synthetic conversations.

## E. Red lines (never)

-   Celebrity or real-person lookalike personas.
-   Selling or sharing customer chat data.
-   Users under 18.
-   Guilt-tripping customers to keep paying.
-   Cloning a customer's ex or any real person.
-   Cloning real people's voices (when voice is added).
-   Staff reading customer chats, except content the customer chooses to send via "report this" and consenting pilot testers (section D).
-   Denying being an AI when sincerely asked.

## F. Open items

-   Choose the age-verification method (needed before the explicit tier; confirm what check the first release uses).
-   Verify and maintain the helpline list.
-   Complete legal review before public release, and for the explicit tier.
-   Default intensity for jealousy and arguments confirmed: Realistic, with mature same-session de-escalation and no financial/subscription mentions.
-   Confirm whether the "sensual" level ships with the explicit tier (assumed later phase).
-   Set retention period for submitted reports.

---

## Relationship expiry, emotional safety, and data deletion

The memory rule (kept while subscribed; 15-day inactivity expiry once unsubscribed) must be explained before a relationship begins. At expiry, the product may narratively mark the fictional relationship as ended and make the persona available for a new fictional relationship, but must not portray the user as having harmed a real person or imply that the AI is suffering.

- A day-12 reminder (unsubscribed customers, if enabled) must be neutral and informational and sent from the app, not the persona. No pleading, guilt, threats, jealousy, or urgency, and no sales pitch; it may state plainly that active subscribers keep their memory.
- The expiry process must stop proactive contact and remove relationship-specific memories and context from normal application access immediately, then complete deletion under the documented retention and backup policy.
- The user's account deletion or earlier memory-deletion request is handled separately and must not be delayed until day 15.
- Crisis detection takes precedence over relationship-stage behaviour. Do not use a crisis, distress disclosure, or vulnerability to encourage return, romance, payment, or retention.
- Legal review must confirm that the disclosed lifecycle (including keeping memory for subscribers and deleting it for unsubscribed customers) and deletion policy comply with privacy, consumer-protection, and payment-provider requirements before launch.
