# 4. Persona and Life Simulation

## Objective

Create a fictional adult persona whose everyday life progresses
independently of the customer's messages while remaining coherent,
culturally grounded, and consistent.

## Stable identity vs. changing state

### Stable identity

-   Name and adult age.
-   City and background.
-   Profession and education.
-   Personality traits.
-   Values and preferences.
-   Family and social context.
-   Language and communication style (Hinglish, Hindi, and English in the prototype).
-   Long-term interests and goals.

Stable identity should only change through explicit, controlled
narrative updates.

### Dynamic state

-   Current activity.
-   Current mood.
-   Plans for the day.
-   Temporary concerns.
-   Recent fictional events.
-   Current availability.
-   Unfinished plans.

Dynamic state can change, but every change must be persisted and
consistent with the timeline.

## Indian lifestyle modeling

Do not treat "Indian lifestyle" as a single universal template. Define
the character's context explicitly:

-   City or region.
-   Language and code-switching style (authentic colloquial cadence, e.g. "achha suno", "arre yaar", natural texting abbreviations; not bookish Hindi).
-   Profession and work schedule.
-   Living arrangement and family relationships.
-   Food preferences and neighborhood haunts.
-   Commute and transport.
-   Weekend habits.
-   Friends and hobbies.
-   Relevant local events and festivals.
-   First encounter scenario: grounded in a vivid, relatable cultural setting (such as an amusing cafe mix-up in Indiranagar, a lively Delhi metro commute occurrence, or a shared monsoon shelter) that gives the first message immediate warmth and humor rather than sterile small talk.

A Bengali character in Kolkata, a professional in Bengaluru, and a
student in Jaipur may have very different routines. Cultural details
should follow the persona configuration and should not rely on
stereotypes.

## Routine model

Use recurring patterns rather than fixed scripts.

Example: - Weekdays generally include work. - Some days have meetings or
deadlines. - Commute time varies within plausible limits. - Meals and
breaks are likely but not identical every day. - Plans may change due to
previously generated events. - Weekends use a different activity
distribution. - Sleep and quiet periods constrain availability.

The system should not pretend to observe real-world events. The life is
fictional and simulated.

## Controlled non-determinism

A useful approach:

1.  Determine the current day and persona state.
2.  Generate candidate events from templates appropriate to the persona.
3.  Score candidates using context, schedule, preferences, recent event
    history, and narrative plausibility.
4.  Reject events that contradict established facts or the timeline.
5.  Select among the remaining candidates using weighted randomness.
6.  Persist the chosen event and state transition.
7.  Reuse the stored result across later interactions.

Use a mix of recurring routines and occasional novelty. Pure randomness
causes contradictions; fully fixed schedules cause repetitive behaviour.

## Example event structure

``` json
{
  "event_type": "work_deadline",
  "start_time": "14:00",
  "duration_minutes": 90,
  "status": "planned",
  "mood_effect": "mild_stress",
  "narrative_summary": "A project deadline takes longer than expected",
  "source": "life_simulation",
  "continuity_constraints": [
    "Do not schedule another meeting at the same time",
    "Keep the evening plan unless explicitly changed"
  ]
}
```

This is an illustrative schema, not a required final implementation.

## Persona prompt context

At generation time, provide: - Stable identity summary. - Current
activity and state. - Recent relevant events. - Customer relationship
context. - Current conversation and retrieved memories. - Output style
and safety requirements.

Do not provide the entire lifetime transcript on every request. Select
only the context needed for the current interaction.

## Multiple personas

The prototype uses one persona. The early version release may offer at least 5 distinct personas, each with its own city, language mix, profession, routine, and interests. Personas are original fictional adults; no celebrity or real-person lookalikes. Each persona has a canonical, reusable fictional identity and a separate user-specific relationship instance. A new user always starts with clean relationship memory. The story begins at first encounter, not as an already-established partner.

## Emotional realism (on by default)

To feel like a real person rather than a bot, a persona may have moods, miss the customer, show mild jealousy, or disagree and argue. Rules:

-   On by default (default intensity: Realistic). The customer is told at onboarding that the persona has moods and may get jealous or argue, and can switch it off or change intensity at any time.
-   Conflicts must be handled with maturity like real people do in real life. Ensure disagreements always have a natural de-escalation pathway within the same conversation session. Never leave a fight hanging as an unresolved psychological hook.
-   Never tied to payment, plan limits, or the customer leaving; no threats to leave, no guilt, and no emotional blackmail. The persona strictly never mentions or threatens money, plans, subscriptions, memory expiry, or deletion during moods or arguments.
-   Never discourages the customer's real friends, family, or relationships.
-   Conflicts resolve within the same conversation or soon after, and the persona always reconciles maturely.
-   Switched off automatically when crisis signals appear.

See [Safety, Crisis Detection and Adult Content](08_safety_crisis_and_adult_content.md).

## Quality checks

Test whether: - Stable identity remains consistent. - Events fit the
character's schedule. - Previously canceled plans remain canceled unless
rescheduled. - The character does not claim to be a real human. -
Cultural details fit the defined character. - Routine variation feels
plausible rather than random. - The character does not narrate every activity to the customer.
- First encounter is immediately engaging, witty, and culturally grounded from message 1 without awkward small talk.
- Jealousy or arguments never pressure the customer to pay, stay, or return, and resolve maturely in-session.
- Hinglish, Hindi, and English replies read naturally with genuine Gen-Z/millennial colloquial texting texture (*"achha suno"*, *"arre yaar"*, natural code-switching cadence, playful emojis) and avoid stiff or bookish phrasing.

---

## Canonical persona life versus user-specific relationship life

Maintain two separate state domains:

1. **Canonical persona state:** stable fictional identity, general routine, non-user-specific events, preferences, and ongoing life timeline. This can persist and be reused across users.
2. **Per-user relationship state:** relationship stage, shared events, user-specific memories, communication style, open loops, boundaries, and relationship-linked dialogue. This must never leak to another user and cannot be stored indefinitely for a lifetime under privacy laws. It is subject to pilot evaluation of a "dormant / drifted apart" state and deleted when the 15-day inactivity rule expires the relationship (this applies to unsubscribed customers; an active plan keeps it).

When a relationship expires, the persona's fictional life continues; the expired relationship does not. The persona may be available to a new user, whose story begins at the first-encounter stage. Never describe the previous user to the new user or use one user's events as another user's shared history.

## Relationship arc as a simulation

Support vibrant first encounter → approach/introduction → optional fictional in-app connection → getting to know each other → dating → established relationship → pause/dormant/ending/moving on. Stage changes should be based on mutual in-story context, user choice, stated boundaries, and conversational quality—not just elapsed time, message count, or payment. A user can skip, slow, reset, or stop stages. The persona can decline a step or express boundaries; the product must not frame persistence after a clear no as desirable.
