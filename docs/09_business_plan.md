# 9. Business Plan (draft)

Status: working draft. Targets in section 6 were approved by the owner. Market facts come from public web listings in October 2026 and are unverified; re-check before relying on them. Not legal, tax, or financial advice.

## 1. Purpose

Documents 1-8 specify the product. This document covers the business side: who else is in the market, how customers are reached, what the unit economics must look like, and when to stop or continue.

## 2. Customer and problem

See [Business Concept](01_business_concept.md). In short: adults who want a continuing, personal, Hinglish/Hindi/English-speaking companion with a believable daily life. Segment size and willingness to pay are unvalidated hypotheses.

## 3. Market and competitors (initial scan)

| Player | What public listings say | Implication |
|---|---|---|
| Replika | Large, well-known companion app (freemium). Prices are shown only inside the app and vary by region; third-party trackers disagree. One tracker reports Pro at about $8/month or $60/year, with higher tiers reported elsewhere. | Sets the global price anchor and user expectations (voice, avatar, memory). |
| Nomi AI | One July 2026 comparison reports tiers of $15.99, $39.99, and $99.99. | Shows users will pay for memory and continuity. |
| Character.AI | Large character-chat platform. | Research pending (pricing, policy, memory). |
| Urvashi (iOS) | Indian AI girlfriend app, 15 characters, 15+ languages including Hindi, free with in-app purchases, virtual gifts. | Direct Indian competitor using gifts as a revenue lever. |
| Mello | India-based, reported stealth startup with a reported seed round, about 12 Indian-named bots in Hindi and Punjabi. | Funded Indian competitor aimed at Gen Z. |
| Bubble / Sagi | Indian companion platform for English, Hindi, and Hinglish; rebranded. | Hinglish support already exists. |
| Ember | Free browser-based Hindi/Hinglish companion with no signup. | Free, private, zero-friction alternative. |

What this means:

- Hindi and Hinglish support is not a differentiator on its own. Do not claim "first".
- The true differentiator is **authentic colloquial texting texture** (natural Gen-Z/millennial code-switching cadence like *"achha suno"* and *"arre yaar"*, eliminating stiff textbook Hindi), an **immediately engaging and culturally vibrant first encounter** (preventing Day-0 drop-off), **independent routine**, **mature emotional realism** (Realistic intensity with same-session resolution and zero financial threats), and a **disclosed subscription-linked memory lifecycle** (memory kept while subscribed, 15-day inactivity reset once unsubscribed, with pilot evaluation of a dormant state).
- Free alternatives exist, so the paid value must be felt in personality craft, memory quality, and realism, not just access. Keeping memory is now part of what a subscription buys.
- Research still pending: Character.AI details, other Indian apps, and what users complain about most (repetition, forgetting, pushy upsells).

## 4. Go-to-market (hypotheses to test, owner to confirm)

- Prototype stage: no paid acquisition (₹0). Recruit 30-50 pilot adults from personal networks and online communities, with explicit consent.
- Distribution: installable PWA shared by link (no app store). Push works on iPhone only for the installed home-screen app on iOS 16.4 or later.
- Early organic channels to test: short-video content about the persona's "life", community posts, word of mouth.
- Paid acquisition only after retention and margin targets are met (see section 6).
- Cost of acquiring a customer (CAC) is unknown; measure it once any channel is tried.

## 5. Pricing and unit economics

- Plans: daily, weekly, monthly, plus a daily top-up. Illustrative monthly range: ₹199-299 (Companion). Daily, weekly, and top-up prices are set after measuring variable cost.
- Suggested principle: the per-day price falls as the plan gets longer (monthly cheapest per day).
- Variable costs per customer: LLM usage (including persona-initiated messages), hosting, storage for retained memory, push delivery, payment fees, and GST on digital services (rate and treatment to be confirmed with a CA).
- Approved target: variable cost at most 30% of net revenue per paying user.
- Illustration (not a forecast): at ₹249/month with GST at 18%, net revenue is about ₹211, so the cap is about ₹63 per paying user per month. At 40 messages a day (1,200 a month) that allows about ₹0.05 per message, all-in.
- Track from day one: cost per message, cost per active user, cost per paying user, gross margin.

## 6. Targets and kill criteria (approved)

| Metric | Target |
|---|---|
| Pilot size | 30-50 consenting adults |
| Day-7 retention | at least 25% |
| Day-30 retention | at least 10% |
| Free-to-paid conversion | at least 4% |
| Variable cost per paying user | at most 30% of net revenue |
| Kill or pivot | Day-7 retention stays below 15% after two pilot rounds |

Review at the end of each pilot round. Message volume and session length are never success metrics on their own. Add the qualitative checks from [MVP Roadmap](06_mvp_roadmap.md): continuity, relevance of memory, unwanted pressure, opt-out rate.

## 7. Budget

- Now: ₹0 (local development, free tools).
- Trigger to add budget: the owner's judgment that the prototype is impressive. Suggested evidence: pilot testers return voluntarily, memory and routine feel believable, and a measured quality gap that a better model would close.
- Then: a small budget or a low-cost LLM, with hard monthly and per-user limits set first.

## 8. Operations and compliance checklist (confirm with a CA/lawyer)

- Business registration and GST registration.
- Payment gateway onboarding, including whether the merchant category and content are accepted, and UPI recurring-payment rules.
- DPDP Act readiness (see [System Architecture](03_system_architecture.md), privacy section).
- Terms of service, privacy notice, AI disclosure text, grievance contact.
- Support process: refunds, account deletion, safety reports.
- Helpline list verified and maintained.

## 9. Top risks

1. Retention: companion novelty fades (see kill criteria).
2. Unit economics: heavy chatters can exceed the cost cap.
3. Language quality: weak Hinglish or Hindi breaks the core promise.
4. Platform dependencies: LLM provider, payment gateway, and hosting terms.
5. Privacy and safety incidents with sensitive conversations.
6. Subscription-linked memory loss feeling punitive and hurting trust or conversion (see the hypothesis below).

Detail in [MVP Roadmap](06_mvp_roadmap.md) and [Safety](08_safety_crisis_and_adult_content.md).

## 10. Deferred decisions

- Spend caps and break nudges for heavy users and top-ups: skipped for now by the owner; revisit before paid plans or top-ups are enabled.
- Explicit (NSFW) content: later phase.
- Voice, selfies, native app, more than 5 personas, external messaging channels.

## 11. Open items

- Finish competitor research (Character.AI, other Indian apps, user complaints).
- Set daily, weekly, and top-up prices after measuring cost.
- Choose acquisition channels to test after the pilot.
- Define what "impressive prototype" means in measurable terms, if the owner wants a hard gate.
- Memory rule for pilot testers confirmed: grant active Beta Entitlements to preserve memories during pilot feedback testing; test the 15-day expiry clock deterministically using a controllable test clock.

---

## Business hypothesis: finite relationship lifecycle

The product's distinctive rule is that memory is kept while the customer has an active subscription, and a user-persona relationship of an unsubscribed customer expires after 15 consecutive days without a user-initiated interaction. Reaffirm: user memory cannot be stored indefinitely or for a lifetime under privacy regulations (DPDP Act).

Relationship-specific memories and context are deleted upon confirmed expiry, while the persona's generic fictional life continues and becomes available for a new user. The story begins at a vibrant, culturally grounded first encounter and may progress through introduction, getting to know each other, dating, and an established relationship.

This finite lifecycle is a hypothesis to validate. In the pilot, test whether immediate hard deletion harms resurrection loops, and evaluate an intermediate **"dormant / drifted apart" state** where returning users are greeted with a gentle, realistic acknowledgment of elapsed time (*"It's been so long, I feel like we lost touch... tell me how you've been"*) before full deletion. Test comprehension, trust, day-7/day-30 retention, complaint rates, and willingness to pay. Memory retention is now a disclosed benefit of an active subscription; never sell it with guilt, pleading, or artificial distress, and never use it to induce a return. Also test whether tying memory to a plan helps or hurts free-to-paid conversion and whether it feels fair.

### Added launch gates

- Test the 15-day clock with accelerated test time and prove that automated messages do not reset it. Also prove that an active plan stops the clock and that a renewal racing with expiry never deletes a subscriber's memory.
- Verify relationship data deletion, backup expiry, account deletion, and clean onboarding for a new user of the same persona.
- Confirm the rule is disclosed at onboarding and in settings, and that the reminder is neutral and optional.
- Validate the first-encounter-to-dating narrative with consenting adults; ensure user choice and boundaries determine progression.
- Obtain legal review of the subscription-linked deletion rule (memory kept for subscribers, 15-day deletion for unsubscribed customers), notice wording, consumer fairness, and any records that must be retained for legal/accounting/security purposes.

### Updated positioning hypothesis

"An AI companion whose fictional life continues independently—and whose relationship with you develops from the first meeting, rather than starting as an instant partner."

Avoid claiming that the persona is a real person, has consciousness, or literally experiences heartbreak. The realism is a transparent fictional simulation.
