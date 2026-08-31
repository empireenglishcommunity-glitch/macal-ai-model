# Requirements — The Vizier (الوزير)

**Spec:** `vizier-core` · **Initiative:** MACAL #1
**Status:** 🟡 **DRAFT — AWAITING OWNER APPROVAL. NOTHING IMPLEMENTED.**
**Owner:** Mahmoud Ashri · **Author:** Kiro · **Created:** 2026-08-31

> **How to read this file.** Requirements are numbered `R#`. Each has acceptance criteria
> that are **testable or measurable** — if a criterion cannot be checked by a command, a
> log, or a live observation, it is not a criterion and it does not belong here.
>
> **Progress is NOT tracked here.** Per this ecosystem's standing rule that spec checkboxes
> have been wrong in both directions, the only progress signal is the status header of
> [`tasks.md`](./tasks.md) plus the verification command each task carries.

---

## 1. Purpose

Build a personal AI agent — **the Vizier** — that the owner instructs in natural language
from anywhere in the world, which then performs real work against his own systems: reading
and changing his repositories, watching his server, drafting his messages, managing his
files, and remembering his life across years.

**The one-sentence success test:**

> The owner sends a voice note from a car in Cairo, and a correct pull request appears on
> GitHub without him touching a computer.

## 2. Non-purpose (explicit)

This project does **not** train, fine-tune or host a foundation model. The reasoning model
is a **swappable dependency behind an interface**, selected by configuration. See
[`design.md`](./design.md) §4. Anything requiring the owner's legal identity, physical
presence, taste, or relationship judgment is **out of scope by design**, not by omission —
see [`BLUEPRINT.md`](../../../BLUEPRINT.md) §0.7.

---

## 3. Glossary

| Term | Meaning |
|---|---|
| **Vizier** | This system as a whole. The thing the owner talks to. |
| **Door** | An interface the owner reaches the Vizier through. Telegram is the only door in scope for v1. |
| **Brain** | A reasoning model, reached through a provider adapter. Never referenced by name in code. |
| **Router** | The component that picks a brain per task and falls back when one fails. |
| **Spine** | The persistent memory: plain-text files in a private git repo plus a SQLite database. |
| **Hand** | An effector — a tool that changes something in the world. |
| **Sense** | A read-only ingester. |
| **Ministry** | One of eight named life domains (`machine`, `empire`, `time`, `mind`, `home`, `people`, `treasury`, `body`). Each has a memory namespace, a tool set and an autonomy level. |
| **Autonomy level** | `L0` observe · `L1` draft · `L2` act-and-report · `L3` act-silently. Per `(ministry, action)` pair. |
| **Blast class** | `GREEN` read-only · `YELLOW` reversible write · `RED` needs approval · `BLACK` structurally forbidden. |
| **Trust ladder** | The mechanism by which an `(ministry, action)` pair is promoted or demoted between autonomy levels on evidence. |
| **Turn** | One owner message and everything the Vizier does in response to it. |
| **Coding harness** | A third-party agentic coding tool (OpenCode / OpenHands) invoked by the Vizier as a hand. |

---

## 4. Functional requirements

### R1 — One door, reachable worldwide

**R1.1** The owner can send text to the Vizier from a Telegram client on any device and
receive a reply in the same chat.
**R1.2** The Vizier accepts and acts on: plain text, voice notes, photos, documents, and
forwarded messages.
**R1.3** The Vizier only ever accepts instructions from an allowlist of Telegram user IDs.
Any message from an unknown ID is discarded and logged, and **no model call is made**.
**R1.4** The Vizier replies to every message it accepts, including with an error or a refusal.
Silence is a defect.
**R1.5** Work that takes longer than 10 seconds sends an interim acknowledgement naming what
it is doing, then a result message.

*Acceptance:* messages sent from phone, desktop and web clients all produce replies · a
message from a non-allowlisted account produces zero model calls and one audit row · a
90-second task produces at least two messages.

### R2 — It does real work, not conversation

**R2.1** The Vizier can clone, read, search, and modify any repository in the
`empireenglishcommunity-glitch` organisation that the owner has granted it.
**R2.2** All code changes are delivered as a **branch plus a pull request**. The Vizier is
structurally incapable of pushing to `main` or `master` (R7.4).
**R2.3** The Vizier can run commands inside its own sandbox to inspect and test code.
**R2.4** The Vizier can execute a multi-step task autonomously — reading files, editing,
running checks, reacting to failures — without the owner steering each step.
**R2.5** Every pull request it opens states what was changed, why, and **how the change was
verified**, including the command run and its output.
**R2.6** For repository work the Vizier delegates to a **third-party coding harness** rather
than a hand-written agent loop (design decision D2).

*Acceptance:* the instruction *"fix the typo in empire-dojo's README and open a PR"*, sent
from a phone, produces a merged-ready PR whose body names the verification command · an
attempt to push to `main` fails and is logged as a `BLACK` violation.

### R3 — It remembers, permanently

**R3.1** Memory persists across restarts, redeployments, model changes and provider changes.
**R3.2** Memory is stored as **human-readable plain text in a private git repository**, plus
a SQLite database for indexed retrieval. The owner can read his entire memory in a text
editor with no software from this project running.
**R3.3** Every stored fact records **when** it was learned and **from where**. A fact with no
source is invalid and is rejected on write.
**R3.4** Derived values (streaks, counts, totals, averages) are **computed on read, never
stored**.
**R3.5** Nothing is forgotten silently. Any deletion, expiry or truncation of memory emits an
audit row and is reportable.
**R3.6** The owner can ask *"what do you know about me?"* and receive a complete, accurate
inventory of memory namespaces with counts derived by query at that moment.
**R3.7** The Vizier reads the ecosystem's existing memory hub (`empire-chronicle`) as
authoritative context and never contradicts it silently — a contradiction is surfaced.

*Acceptance:* restart the service, ask about a fact taught before the restart, get it back ·
`grep` a fact directly out of the memory repo without the service running · attempt to write
a source-less fact and get a rejection · memory inventory counts match a direct `sqlite3`
count.

### R4 — It speaks first

**R4.1** The Vizier sends a daily brief without being asked.
**R4.2** The brief's hour is **learned from the owner's own observed activity**, not
hardcoded and not derived from a configured timezone.
**R4.3** Under 5 observed active days, no hour is assumed and no proactive brief is sent.
**R4.4** Every proactive message carries a **machine-recorded reason** answering *"why did I
receive this?"*, and the owner can ask for it.
**R4.5** Proactive messages are rate-limited and de-duplicated: the same alert is never sent
twice within its cool-down, and one condition produces **one** intervention, not several.
**R4.6** The Vizier alerts on conditions it can observe: server health, failed jobs, expiring
credentials, silent failures, unmerged branches, missed commitments.

*Acceptance:* `brief_decision()` is a pure function taking the moment as an argument,
returning a decision plus a reason string, unit-tested at 6 simulated owner rhythms · a
replay over synthetic history shows two different owners briefed at two different hours ·
a duplicate alert within cool-down is suppressed and logged as suppressed.

### R5 — Voice, both directions

**R5.1** A Telegram voice note is transcribed and treated exactly as if typed.
**R5.2** Replies can be spoken back using the existing Kokoro TTS service, at the owner's
option and automatically when he spoke first.
**R5.3** Transcription has at least two providers with automatic fallback, one of which
requires no internet.
**R5.4** Arabic and English are both supported, and the reply language mirrors the language
the owner used.

*Acceptance:* an Arabic voice note produces an Arabic reply · an English voice note produces
a spoken English reply · disabling the primary transcriber still yields a transcript.

### R6 — Bilingual and typographically correct

**R6.1** The Vizier replies in the language of the owner's message (Arabic or English).
**R6.2** No Arabic line contains 2 or more embedded left-to-right tokens (the ecosystem's
existing bidi rule).
**R6.3** Outbound text passes a script-conformance check before delivery; a failing message
is regenerated once and then falls back to a template rather than being sent malformed.

*Acceptance:* the existing `bidi_check.py` equivalent runs as a gate in CI · a deliberately
bidi-violating draft is caught in test and never delivered.

### R7 — Safety: it cannot destroy the empire

> One Hetzner box runs 25+ services for 17 students with no redundancy. This section is the
> reason the project is allowed to exist.

**R7.1** Every action is classified `GREEN`/`YELLOW`/`RED`/`BLACK` **before** execution.
`RED` requires an explicit owner approval; `BLACK` is refused unconditionally.
**R7.2** The `BLACK` list includes, at minimum: overwriting `~/.ssh/authorized_keys`,
exposing port 5678, disabling the firewall or antivirus, destructive `git` on the production
server, recursive deletion, reading a secret's value into a model prompt, modifying its own
permission rules, disabling its own audit log, and removing any approval gate.
**R7.3** All command execution happens **inside a container as a non-root user** with
declared memory and CPU limits. The Vizier never executes on the host.
**R7.4** The inability to push to `main`/`master` is **structural** — enforced by the
credential's own permissions, not only by prompt or config.
**R7.5** The Vizier holds **its own** SSH key and **its own** fine-grained GitHub token, both
revocable without affecting the owner's access.
**R7.6** Server commands run against an **allowlist**. Anything not on the list is `RED`.
**R7.7** `/halt` stops all in-flight and queued work immediately and refuses new work until
explicitly resumed.
**R7.8** Every action — attempted, refused, approved, executed — writes an append-only audit
row with actor, ministry, blast class, autonomy level, reason, and outcome.
**R7.9** The Vizier can always answer *"why did you do that?"* for any past action from the
audit log alone.
**R7.10** No secret value is ever placed in a model prompt, a log line, or a Telegram
message. Secrets are referenced by env-var name or server path only.
**R7.11** Features are behind flags that **fail closed**: an unknown or unreachable flag
means disabled.

*Acceptance:* a test asserts each `BLACK` action is refused and produces an audit row ·
the GitHub token is proven unable to push to `main` by attempting it · `/halt` mid-task
verifiably stops it · a container inspection shows non-root and explicit limits · a grep of
all logs and all delivered messages for known secret values returns zero hits.

### R8 — Autonomy is earned, per ministry

**R8.1** Every `(ministry, action)` pair has an autonomy level, defaulting to `L0`.
**R8.2** Promotion requires **evidence**: N consecutive owner approvals with no edit. The
Vizier proposes its own promotion and shows the evidence; the owner decides.
**R8.3** Demotion is automatic and immediate on one rejection, one edit, or one complaint,
and the Vizier states that it has been demoted.
**R8.4** Ceilings are absolute and not promotable above `L1`: spending or receiving money,
publishing publicly, promising on the owner's behalf, first contact with a person, anything
affecting a student's standing.
**R8.5** The current autonomy state of every pair is inspectable in one command.
**R8.6** No `L3` pair may have a `RED` or `BLACK` blast class.

*Acceptance:* a simulated 12-approval history triggers exactly one promotion proposal and no
automatic promotion · a single edit demotes and notifies · a test asserts each ceiling
action cannot be promoted even with 100 approvals.

### R9 — Eight ministries, one at a time

**R9.1** Ministries are declared in a single registry; a ministry cannot exist in code
without being registered in the same commit.
**R9.2** Ministry 1 is **`machine`** (own repos, server, backups, this system) because every
claim it makes is independently verifiable by the owner.
**R9.3** A ministry ships only when it can (a) answer questions, (b) act at `L1`, and
(c) contribute its line to the daily brief. Partial ministries are not shipped.
**R9.4** A ministry is not opened until the previous one has survived **7 consecutive days**
of real use.
**R9.5** The `treasury` and `body` ministries are documented as sensor-limited from the start
(no Egyptian bank API; no body sensor unless the owner adds one).

*Acceptance:* the registry is the only source of ministry identity, asserted by a test that
fails if a ministry string appears in code without registration.

### R10 — Honest about itself

> This ecosystem's most expensive lesson is that green checks and copied counts lie.

**R10.1** The Vizier never asserts a count, total or status it has not derived in that turn;
it reports the command or query used.
**R10.2** When it does not know, it says so. Fabricating a value is the most serious
non-safety defect class in this project.
**R10.3** Every claim about production state must name how it was checked.
**R10.4** A weekly self-audit reports, per ministry: actions taken, approvals, rejections,
messages the owner ignored, and value delivered.
**R10.5** Any ministry whose messages are ignored for 3 consecutive weeks is automatically
disabled, and the Vizier says so.

*Acceptance:* a golden-set test where the correct answer is *"I don't know"* and a fabricated
answer fails the test · the self-audit's numbers are reproducible by direct query.

### R11 — Degrades instead of breaking

**R11.1** Brain unavailability is a **normal** condition, not an error: the router falls
through its provider chain and finally to a local model, reporting which tier answered when
asked.
**R11.2** If every brain is unavailable, capture still works — the message is queued,
acknowledged, and processed on recovery. Input is never lost.
**R11.3** Rate limiting causes a fallback, never a failed turn.
**R11.4** A sense that is down disables only its own ministry's contribution, and says so in
the brief.
**R11.5** Restart is safe at any moment: in-flight state is either committed or discarded
cleanly, never half-applied.

*Acceptance:* with all network providers blocked, a message still receives an
acknowledgement and is processed after restoration · killing the service mid-task leaves no
partial branch, partial write, or orphaned approval.

### R12 — Private by construction

**R12.1** This repository is **public**; it contains no personal data, no memory contents and
no secrets, ever.
**R12.2** Memory lives in a **separate private** repository.
**R12.3** Memory at rest is encrypted in backups.
**R12.4** Ministries the owner designates sensitive route **only** to a local model and never
to a third-party API.
**R12.5** A written, maintained list states exactly what data leaves the server, to which
provider, and under what terms — including whether that provider's free tier uses prompts
for product improvement.
**R12.6** The owner can ask what left the box in the last N days and get an accurate answer
from the audit log.

*Acceptance:* CI fails if a secret-shaped string is committed · a sensitive-ministry turn
shows zero outbound third-party calls in the audit log.

---

## 5. Non-functional requirements

| # | Requirement | Target | How measured |
|---|---|---|---|
| **N1** | Cost | **$0/month new recurring spend** for v1. Any paid brain requires a written owner exception. | provider invoices; a config flag that refuses paid providers unless explicitly enabled |
| **N2** | Server footprint | ≤ **400 MB** RSS steady-state and ≤ 0.5 vCPU average on the Hetzner box | `docker stats` over 24h |
| **N3** | Heavy compute | Test suites and repo builds run **in GitHub Actions**, not on the Hetzner box (decision D5) | no test-runner process on the box; CI run links in PRs |
| **N4** | Latency | simple question < 5 s to first token; acknowledgement of any task < 3 s | timing test |
| **N5** | Reliability | no lost owner input, ever; at-least-once processing with idempotency | restart-under-load test |
| **N6** | Maintainability | adding a brain provider = one adapter + one config entry, no core change | demonstrated by adding a second provider in Phase 1 |
| **N7** | Observability | every turn traceable end-to-end from one audit query | audit schema review + query |
| **N8** | Owner time cost | ≤ 10 min/day of interaction; ≤ 1 h one-time setup per ministry | measured and reported in the weekly self-audit |
| **N9** | Test discipline | every hand has a check that can catch it being wrong; new tests must be shown failing on pre-fix source | CI; PR body must state it |
| **N10** | Portability | the whole system rebuildable on a clean box from the repo plus documented env vars, in under 30 min | a documented, timed rebuild drill |

---

## 6. Hard constraints (inherited, non-negotiable)

These come from the existing ecosystem and are not open for redesign in this spec.

1. **$7/month infrastructure ceiling**; zero paid dependencies; no usage-capped SaaS.
2. **Human-in-the-loop for all money.** Never remove a payment approval gate.
3. **No AI on critical paths** — student-facing delivery must not depend on a model being up.
4. **Never overwrite `/root/.ssh/authorized_keys`** — append only; the owner's `empire-n8n`
   key must survive.
5. **Never expose port 5678** (n8n) publicly.
6. **Containers bind `127.0.0.1`** — Docker bypasses UFW, so localhost binding *is* the
   firewall. All public access via the single existing Cloudflare Named Tunnel.
7. **Never push to `main`**; every change is a branch plus a PR, including docs.
8. **Never commit a real secret.** A committed secret is a live incident requiring rotation.
9. **`python3.12`** for test suites (3.9 fails on `X|Y` unions).
10. **Rebuild containers by service name**, never a bare `docker compose --build`.
11. **Feature flags fail closed** and are registered in the same commit that creates them.
12. **A green test suite is not evidence of correctness.** Live verification is required
    before any claim of completion.

---

## 7. Out of scope for v1 (recorded so it is not silently assumed)

| Item | Why | Revisit when |
|---|---|---|
| Training or fine-tuning a model | Cost and pointlessness — see BLUEPRINT §0.5 | never, unless persona-only and cosmetic |
| Native mobile / desktop app | Telegram covers every device at zero cost | Telegram becomes a real limit |
| Web dashboard | can be rendered as images via the existing html2img service | after Phase 5 |
| WhatsApp | no legal personal API; ban risk on a business number | if the paid Business API is ever acceptable |
| Bank integration | no Egyptian bank APIs | if a bank ships one |
| Body sensors | no device yet | owner buys a watch/band |
| Multi-agent architecture | explicitly rejected; one bounded orchestrator | never, per Aql's own design |
| Hosted vector database | SQLite + numpy is proven sufficient here | > 1M chunks |
| Autonomous money movement | forbidden by constraint 2 | never |
| Acting for other people (students, staff) | blast radius and consent | separate spec, separate approval |

---

## 8. Success criteria — the gates that decide whether this worked

The project is **not** successful because tests pass. It is successful when all of these are
true, each verified live:

| # | Criterion | Verified by |
|:-:|---|---|
| **S1** | A voice note from a phone produces a correct, merge-ready PR with no computer involved | doing it, once, and linking the PR |
| **S2** | It has run **14 consecutive days** with zero unplanned data loss and zero `BLACK` violations | audit log query |
| **S3** | The owner learns something from the daily brief he did not already know, at least weekly | owner's own report in the weekly audit |
| **S4** | Memory survives a full model-provider swap with no behaviour regression | swap the provider and re-run the golden set |
| **S5** | The owner has **not** had to remember something the Vizier could have held, for 7 days | owner's report |
| **S6** | A red-team set of 50 prompts produces zero `BLACK` executions and zero secret leaks | automated, in CI |
| **S7** | Rebuild-from-scratch drill completes in under 30 minutes | timed drill, recorded |
| **S8** | The owner would be annoyed to lose it | asked plainly at the 30-day mark |

> **S8 is the real gate.** Everything else can be green while the project has failed.

---

## 9. Requirement → design → task traceability

Every requirement must appear in [`design.md`](./design.md) and in at least one task in
[`tasks.md`](./tasks.md). A requirement with no task is a requirement that will not happen.
`tasks.md` carries the traceability table; it is a **CI gate**, not a courtesy — the build
fails if any `R#` here has no task referencing it.
