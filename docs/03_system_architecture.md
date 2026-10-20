# 3. System Architecture

## Architecture principle

Keep the application stateful and deterministic where consistency
matters, and use an LLM for language understanding and natural dialogue.
Non-deterministic behaviour should be constrained by persisted state and
validation.

Do not implement the entire product as one large prompt or a collection
of independent agents.

## High-level components

1. **Frontend:** React progressive web app (PWA) for the prototype: web manifest, service worker, mobile-first UI. A native app only if later needed.
2.  **Backend API:** Django or FastAPI.
3.  **Conversation orchestrator:** coordinates memory retrieval, state
    loading, LLM generation, validation, and persistence.
4.  **Persona state service:** stores stable identity and current
    fictional state.
5.  **Life simulation service:** generates and persists plausible
    events.
6.  **Memory service:** stores, ranks, retrieves, and updates memories.
7.  **Relationship service:** tracks familiarity, interaction
    preferences, and boundaries.
8.  **LLM adapter:** abstracts model provider, prompt assembly,
    structured outputs, retries, and token limits.
9. **Background scheduler/queue:** advances timelines and schedules persona-initiated messages at randomized times within each customer's allowed windows.
10. **Database:** PostgreSQL.
11. **Observability and billing:** records errors, usage, cost, entitlements, and subscriptions.
12. **Safety service:** crisis detection, age and content-tier gating (explicit tier locked in the first release), and output checks, run before and after generation.
13. **Notification delivery:** in-app messages and Web Push (through the service worker, with permission) for persona-initiated texts. The backend and scheduler must be running and reachable over HTTPS for pushes to arrive; a laptop that is switched off cannot send them.

## Suggested initial stack

  -----------------------------------------------------------------------
  Layer                               Starting choice
  ----------------------------------- -----------------------------------
  Frontend React, delivered as a PWA (manifest + service worker)

  Backend                             Django or FastAPI

  Database                            PostgreSQL

  Background jobs                     Celery with Redis, or equivalent

  Memory search                       PostgreSQL queries/full-text search
                                      initially

  Semantic retrieval                  Add vector search only when
                                      evaluations justify it

  AI                                  LLM API behind a provider adapter

  Payments                            Provider supporting the target
                                      geography and recurring
                                      subscriptions

  Monitoring                          Application logs, metrics, traces,
                                      and model-cost tracking
  -----------------------------------------------------------------------

## Message handling flow

1.  Authenticate the customer and validate account status.
2.  Screen the incoming message for crisis signals and content limits. If a crisis is detected, switch to the crisis-response path (supportive reply, helpline handoff, no romantic or conflict behaviour) instead of normal persona generation.
3.  Load recent conversation messages.
4.  Load current persona state and relevant relationship preferences, including content-tier and emotional-range settings.
5.  Retrieve memories related to the current message and topic.
6.  Assemble a bounded context for the model.
7.  Ask the model for a response and, if useful, structured metadata such as topic, referenced memories, or a proposed memory update.
8.  Validate output against persona facts, safety rules, content-tier gating, and customer boundaries.
9.  Deliver the response.
10. Persist the conversation.
11. Store or update only memories that pass validation.

Avoid automatically treating every generated model statement as a fact.
Separate fictional narrative, customer statements, and inferred details.

## Background life simulation flow

1.  Scheduler identifies personas whose simulated timeline should
    advance.
2.  Load current state and recent events.
3.  Generate candidate events from suitable event templates and weighted
    choices.
4.  Reject candidates that conflict with identity, timeline, or existing
    plans.
5.  Select a candidate or retain the current state.
6.  Persist the event and resulting state.
7.  If the persona may reach out, check customer consent, quiet hours, frequency caps, and recent-message history.
8.  Pick a randomized send time inside the allowed window and queue a short message grounded in the persona's current event, a stored memory, or an open loop. Skip it if it would repeat or add nothing.

The persona's internal timeline can advance without calling an LLM for
every time interval. Generate natural language only when an event is
used in a conversation or an approved notification.

## Data model

### users

-   `id`
-   `created_at`
-   `age_eligibility_status`
-   `locale`
-   `timezone`
- `notification_preferences`
-   `privacy_settings`
-   `adult_content_opt_in` (kept in the schema; the explicit tier stays locked in the first release)

### personas

-   `id`
-   `name`
-   `fictional_bio`
-   `stable_traits`
-   `language_style`
- `lifestyle_profile`
-   `persona_version`

The schema supports many personas from day one: the prototype seeds one, the early release at least 5.

### persona_state

-   `persona_id`
-   `current_activity`
-   `current_mood`
-   `current_plan`
-   `simulated_local_time`
-   `state_version`
-   `updated_at`

### conversations and messages

-   `id`
-   `user_id`
-   `persona_id`
-   `role`
-   `content`
-   `created_at`
-   `metadata`
- `relationship_id` (links content to one specific user-persona relationship for lifecycle deletion)

### memories

-   `id`
-   `user_id`
-   `persona_id`
- `relationship_id` (required for relationship-scoped memory; enables expiry deletion)
-   `memory_type`
-   `content`
-   `source_message_ids`
-   `occurred_at`
-   `confidence`
-   `importance`
-   `status`
-   `expires_at` (optional)

### open_loops

-   `id`
-   `user_id`
-   `persona_id`
- `relationship_id` (required for relationship-scoped open loops)
-   `topic`
-   `origin_memory_id`
-   `status`
-   `last_relevant_at`
-   `next_review_at` (optional)

### relationship_state

-   `user_id`
-   `persona_id`
-   `familiarity_context`
- `relationship_stage` (encounter, introduction, getting_to_know, dating, established, paused, dormant, ended, expired)
- `romantic_style_preference`
- `emotional_range_setting` (on by default, default intensity: realistic; customer can toggle off or change to mild; includes mature same-session de-escalation)
-   `boundaries`
- `last_user_initiated_interaction_at`
- `expires_at` (set only while the customer has no active plan: 15 days from the subscription end date, pushed back by any later user-initiated interaction; null while an active plan exists)
- `lifecycle_status` (active, dormant, expired, deletion_pending, deleted)
-   `updated_at`

### scheduled_events and usage_records

Store event schedules, delivery status, model usage, estimated cost, and subscription entitlements (daily, weekly, and monthly plans and daily top-ups). Scheduled persona messages must carry a `relationship_id` so expiry can cancel them. Entitlement status (active plan or not) is the input to the expiry rule. Add a lifecycle job queue/status record for expiry and deletion; make deletion idempotent and observable without storing conversation content in operational logs.

### safety_events

-   `id`
-   `user_id`
-   `event_type` (crisis_signal, content_block, age_flag)
-   `severity`
-   `handoff_shown`
-   `created_at`

Store minimal metadata, not message text, so no staff need to read customer chats.

### user_reports

-   `id`
-   `user_id`
-   `reported_at`
-   `snippet` (only what the customer chose to send)
-   `consent_recorded_at`
-   `category`
-   `status`
-   `retention_until`

Access is limited to named reviewers and logged. The customer can request deletion of a submitted report. Pilot testers who consent to review are tracked separately.

## Privacy and security

-   Separate tenant/customer data correctly.
-   Apply access controls to all user-specific data.
-   Avoid storing unnecessary sensitive details.
-   Provide memory review, correction, deletion, and account deletion.
-   Define retention periods and backup deletion procedures.
-   Never use private conversations for unrelated purposes without
    appropriate disclosure and authorization.
-   Do not expose internal prompts, other customers' data, or hidden
    system state.

### India DPDP Act 2023 (draft notes, lawyer review required)

Facts below are from public summaries in October 2026; a lawyer must confirm what applies and when.

-   The Digital Personal Data Protection Act 2023 and the DPDP Rules 2025 (notified 14 November 2025) apply in phases. Board provisions started first, consent-manager registration follows at one year, and the core obligations (notice, consent, security safeguards, breach reporting, children's data) apply about 18 months after notification, reported as around 14 May 2027. Design for them now.
-   Plain-language privacy notice and specific consent for each purpose (chat processing, memory, notifications, "report this"). Withdrawing consent must be as easy as giving it.
-   Customer rights: access, correction, erasure, and a grievance channel. The Rules set a maximum time to resolve grievances (reported as 90 days); confirm.
-   Reasonable security safeguards (encryption, access control, logging) and a breach-response process that covers notifying the Board and affected customers.
-   Retention and erasure: delete data when the purpose ends, and on account deletion, including backups.
-   Children: anyone under 18 is a child under the Act and needs verifiable parental consent. The product bars under-18 users, so age gating must be reliable.
-   Cross-border transfers are generally allowed, subject to restrictions the government may notify; check where the LLM provider and hosting process data.
-   Processor contracts with LLM, hosting, and payment vendors.
-   For the lawyer: data fiduciary role, notice languages, retention periods, whether Significant Data Fiduciary duties could ever apply, and grievance officer details.

## Customer style profile

Store communication preferences separately from relationship memories and persona state. Possible fields: preferred language, response length, tone, emoji frequency, humour preference, advice-versus-listening preference, confidence, provenance, and update timestamp. Update gradually from repeated signals or explicit settings, then pass a compact profile into the LLM context. Do not fine-tune after every message.

## Zero-cost development mode

Support a local backend and a local PostgreSQL database, rule-based life simulation, template responses, synthetic test data, and an optional local quantized model behind a model adapter. No external API should be required for the core workflow.

---

## Relationship expiry and deletion architecture

### Clock and expiry job

- Maintain `last_user_initiated_interaction_at` and derive `expires_at` only for relationships whose customer has no active plan: `expires_at = max(plan_ended_at, last_user_initiated_interaction_at) + 15 days`, so the clock starts on the subscription end date. While a daily, weekly, or monthly plan is active, `expires_at` is null and the relationship does not expire. Store UTC timestamps and use the user's configured timezone for display. Lifetime storage is prohibited under DPDP data minimization principles.
- Only a user-authored message or reply resets the clock. App opens, read receipts, system prompts, push delivery, and persona-initiated messages do not count.
- Clear `expires_at` when a plan starts or renews; set it when a plan ends or lapses (per the rule above). The expiry worker re-checks entitlement at execution time, so a renewal racing with expiry never deletes a subscriber's memory.
- Run a scheduled expiry worker. At or after the deadline, evaluate the transition: during pilot testing, evaluate an intermediate `dormant` state to test resurrection dialog (*"It's been so long, I feel like we lost touch... tell me how you've been"*) versus immediate `expired`. Upon permanent expiry, atomically mark the relationship `expired`, disable scheduled outbound messages, revoke retrieval access, and enqueue deletion. Race conditions must not allow a message or memory write to revive an expired relationship.
- Make the deletion worker idempotent and retryable. Track job status and counts, not deleted message contents. Ensure expired data is excluded from model context immediately, even while physical deletion is pending.

### Deletion scope and separation

Delete or irreversibly anonymize relationship-linked conversation content, profile/episodic/shared-history memories, open loops, relationship state, and inferred communication-style data scoped to that relationship. Keep the persona's canonical fictional configuration and generic, non-user-specific life timeline. Do not write user-specific memories into shared persona state. A new user receives a clean relationship namespace.

Account data, payment/tax records, abuse-prevention records, and user-submitted reports may have different legal retention requirements; disclose these separately and retain only what is necessary. Define backup purge windows and ensure backups are inaccessible to normal product queries. A deletion request made before day 15 takes precedence where legally applicable. For subscribers, memory is retained while the plan is active; the privacy notice must state this retention purpose and period, and erasure on request always applies.

### Reminder and UX rules

A single neutral day-12 reminder (unsubscribed customers only) is allowed only if product reminders are enabled. Do not use the persona's voice to plead, imply distress, threaten replacement, or pressure the user to pay. Explain the 15-day rule before the first relationship starts, in settings, and at the reminder. Send the reminder from the app, not in the persona's voice. Subscription status decides whether the deadline applies (active plan: no expiry); it never changes the 15-day length or the deletion scope.
