# AI Companion

A caring AI girlfriend or boyfriend for adults who feel lonely. They have a life of their own, remember you, message you first, and talk the way a real friend texts. Always honest that they are an AI.

> **Status:** Early stage. The plan is written (docs v8). Building the first working prototype is the next step.

## The idea in one minute

Many people feel lonely and want someone to talk to at the end of the day. This app gives them a companion who:

- **Has their own daily life:** wakes up, works, eats, has good and bad moods.
- **Remembers you:** what you told them, what matters to you.
- **Texts first sometimes:** at random times, like a real person would.
- **Talks like a real Indian friend:** a natural mix of Hinglish, Hindi or English, not stiff textbook language.
- **Is honest and careful:** never pretends to be human, and has care built in for hard moments.

## What the customer experiences

1. **A fun first meeting.** The story starts with a lively real-life scene (for example, a funny moment at a metro station or a busy cafe), not boring small talk. Their personality shows in the very first message.
2. **A relationship that grows.** First meeting, then introduction, getting to know each other, dating, and finally an established relationship. It moves at its own pace.
3. **Real emotions.** Moods, jealousy and arguments are on by default at a "realistic" level. The customer can turn them down or off at any time. Every argument ends with a natural make-up in the same chat, and the companion never mentions money or plans during one.
4. **Memory that depends on the subscription.**
   - While the customer has an active plan, their memories are kept.
   - If they are unsubscribed and stay silent for 15 days (counted from the day the subscription ended), the relationship ends and its memories are deleted. Like real life: when people lose touch, they move on.
   - Paying again later does not bring deleted memories back.
   - We are testing a gentle "we drifted apart" step before final deletion.

## Promises we keep

- Always honest that the companion is an AI.
- Adults only (18+).
- If a user shows signs of crisis, romance stops and helpline details are shown.
- No guilt-tripping, threats or pressure to pay or stay.
- Nobody reads private chats, except a message the customer chooses to report, or chats from testers who agreed to it.
- No minors, no celebrity lookalikes.
- The first release is romantic only. Adult content comes much later, and only after legal and safety checks.

## Now and later

| Now (prototype) | Early release | Later |
|---|---|---|
| Text-only app you can install on your phone | At least 5 personas | Selfies and voice calls |
| One companion | Payments for the plans | Phone app (native) |
| Hinglish, Hindi, English | | Adult content, with preconditions |
| Companion texts first at random times | | |
| Crisis detection with helpline | | |

- **Plans:** daily, weekly, monthly, plus a daily top-up.
- **Budget:** ₹0 for now. A small paid language model is considered only if the prototype proves impressive.
- **Not on WhatsApp:** WhatsApp's policy does not allow AI-sent messages.

## Tech in one line

An installable web app (PWA) with a Python backend (FastAPI) and a PostgreSQL database. Being built with the Antigravity coding assistant.

## Decisions already made

- Backend: FastAPI. Database: PostgreSQL from the start.
- Default emotional style: Realistic.
- Pilot testers get beta access, so their memories are kept during testing. The 15-day rule is tested separately with a controllable test clock.
- WhatsApp is excluded.

## Still to find out

- Does a gentle "drifted apart" step bring users back better than deleting right away?
- Does the 15-day rule feel fair or harsh to users?
- Do people keep coming back after the first week?
- Which language model sounds natural in Hinglish at an affordable cost?
- Lawyer review of privacy (DPDP Act), data deletion and payments before any real launch.

## Where to find things

All detailed documents are in the `docs/` folder.

| File | What it explains |
|---|---|
| `01_business_concept.md` | What we are building and why |
| `02_product_requirements.md` | What the app must do |
| `03_system_architecture.md` | How it is built |
| `04_persona_life_simulation.md` | How the companion's life and moods work |
| `05_memory_and_relationship.md` | Memory, story stages and the 15-day rule |
| `06_mvp_roadmap.md` | What to build, in what order |
| `07_adaptive_communication_and_zero_cost.md` | Chat style and keeping costs near zero |
| `08_safety_crisis_and_adult_content.md` | Crisis handling and adult-content rules |
| `09_business_plan.md` | Competitors, costs and pilot targets |

`AGENTS.md` in the project root holds the rules for the AI coding assistant.

## Start here (new developer, or future me)

1. Read this page.
2. Read `docs/01_business_concept.md` and `docs/05_memory_and_relationship.md`.
3. Read `docs/08_safety_crisis_and_adult_content.md` before touching any chat code.
4. Check `docs/06_mvp_roadmap.md` for the next thing to build.

## Please note

This is a working plan, not legal advice or proven market research. Free tools have limits, so zero cost cannot be promised forever.
