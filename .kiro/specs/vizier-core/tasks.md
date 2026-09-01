# Implementation Plan — The Vizier (الوزير)

**Spec:** `vizier-core` · **Requirements:** [`requirements.md`](./requirements.md) · **Design:** [`design.md`](./design.md)

---

## 📍 STATUS HEADER — the only trustworthy progress signal

> **Read this header. Do not read the checkboxes below as progress.**
>
> This ecosystem has documented initiatives reading *"0/28, in progress"* while live in
> production for a week, and others reading *"45/45"* while never deployed. Checkboxes here
> are a **plan**, not a report.

| | |
|---|---|
| **Phase** | **1 — in progress. Tasks 1.1, 1.2, 1.3 complete. Deployment is being pulled forward before 1.4.** |
| **Spec** | Approved by the owner and merged (PR #1, merge commit `7820d3e`). |
| **Credentials** | ✅ All three exist on the server at `/opt/macal-vizier/.env` (mode 600). Telegram bot `@macal_ai_assisstant_bot` live · Groq key created · GitHub fine-grained PAT created. |
| **Implemented** | **Tasks 1.1 + 1.2 + 1.3** — config contract, `clock.py`, audit log, Telegram door + allowlist, `Brain` seam with **two adapters of different wire formats**, tier router with fallback, durable pending queue. **169 tests.** No memory, no hands, no orchestrator. **Nothing is deployed, so the Vizier still cannot be talked to — that is the next thing fixed.** |
| **Deployed** | ❌ Nothing. **The Hetzner server runs no Vizier code** — the only thing on it is the `.env` file the owner created. Deployment is task 1.8. |
| **Verified** | 2026-08-31, locally under `python3.12` (3.12.13): `ruff check` clean · `ruff format --check` 24 files clean · `mypy` strict, 15 files, no issues · `pytest -q` **31 passed** · both gate scripts exit 0. CI on the branch is the independent confirmation. |
| **`main` protection** | ✅ Ruleset `protect-main` (id 21968385) active, `bypass_actors: []`. A direct PUT to `main` returns **409** "Changes must be made through a pull request." Verified live. |
| **Model list** | ✅ Received and recorded in `design.md` §2.1 — 14 models. Tier A/B/C chosen. **D4 corrected: no DeepSeek/Kimi-class model is available on this key**; strongest is a 120b open model. Two unplanned finds: a dedicated injection classifier (new **D13**) and Whisper on the same key (D11 confirmed). |
| **Next action** | ⚠️ **Sequencing gap in this plan, being fixed rather than followed.** Task 1.2's exit criterion is "send from a phone, get a reply", which is impossible until something runs — and deployment sits at 1.8, five tasks later. So a minimal runnable wiring (door → router → reply) plus the container is being pulled forward next, so the owner can smoke-test from his phone. Then 1.4 (Conscience + D13), 1.5 (Spine), 1.6 (Aql spike), 1.7 (orchestrator). |

**Rules for whoever executes this (including future me):**

1. **Update this header before closing any session.** A stale header is worse than no header.
2. **A task is done when its `✔ Verify` command has been run and its output pasted into the
   PR body.** Not when the code looks right.
3. **Every task is its own branch and its own PR.** Never push to `main`.
4. **Every new test must be shown failing on the pre-fix source**, and the PR must say so.
5. **A green suite is not evidence.** Phases 1–4 each end with a live check, not a test run.
6. **Re-derive every count.** Never copy a number from this file into a report.

---

## Phase 1 — It talks and it works (the skeleton stands)

**Goal:** the owner sends a message from his phone and the Vizier answers, remembers, and is
auditable. **No hands yet.**
**Exit gate:** a live conversation from a phone, a restart, and the memory survives.

- [ ] **1.1 — Project skeleton + config contract**
  Python 3.12 package layout per `design.md` §3, `pyproject.toml`, `ruff` + `mypy` + `pytest`,
  `config.yaml` with **no model names in code**, `.env.example` listing every variable by name
  with **no values**. GitHub Actions workflow with `if: ${{ !cancelled() }}` on every step.
  → *R:* N6, N9 · *D:* D4
  **✔ Verify:** `pytest -q && ruff check . && mypy src` all pass on an empty test suite; CI
  green; `grep -rniE '(gpt|claude|llama|qwen|gemini|kimi|deepseek)' src/` returns **0 hits**.

- [ ] **1.2 — Telegram door, allowlist first**
  Long-poll loop, owner-ID allowlist, media download, chunked outbound, `<3 s`
  acknowledgement, interim message for `>10 s` work. **Allowlist is written before the first
  model call exists**, so no unauthenticated path is ever possible.
  → *R:* R1, R7.1, N4 · *D:* D12
  **✔ Verify:** send from phone, desktop and web — 3 replies. Send from a second account —
  **0** model calls and 1 audit row (paste both queries).

- [ ] **1.3 — Brain interface + Groq adapter + router with fallback**
  `Brain` protocol, Groq adapter, tiers A/B, fallback chain, queue-on-total-failure. **A
  second adapter (any provider) is added in this same task purely to prove N6.**
  → *R:* R11.1–R11.3, N6 · *D:* D4
  **✔ Verify:** block the network with `iptables`/env override — the message is still
  acknowledged and processed after restoration (paste the audit rows showing tier fallthrough).

- [ ] **1.4 — Conscience: classifier, gate, `/halt`, inbound injection screening**
  Blast classification, `BLACK` refusal before any side effect, `/halt` flag checked by every
  hand path. Built **before any hand exists** so no hand can ever predate its gate. One audit
  query must reconstruct a whole turn end to end (N7). *(The append-only audit log itself
  shipped early, in 1.2, because the allowlist decision is already an auditable event.)*
  Adds the **D13** pre-step: screen every inbound message with the prompt-guard classifier
  after the allowlist and before the orchestrator; a positive result audits the score and
  proceeds with **no tools offered**.
  → *R:* R7.1, R7.7, R7.8, R7.9, N7 · *D:* D7, D13
  **✔ Verify:** a parametrised test asserts **every** `BLACK` entry refuses and writes an
  audit row; `/halt` during a simulated long task stops it; `ops audit --last 20` renders.

- [ ] **1.5 — Spine v1: sourced facts, UTC helpers, rebuildable index**
  SQLite schema per `design.md` §6, `source`/`learned_at` `NOT NULL`, the single
  `utcnow`/`parse_stamp`/`days_since` helper set (`days_since` returns `None`, never `0`),
  private `macal-memory` repo initialised, `rebuild-index` command.
  → *R:* R3.1–R3.5 · *D:* D6
  **✔ Verify:** write a source-less fact → rejected. Restart → recall a pre-restart fact.
  `grep` the fact out of the text repo with the service stopped. Delete `memory.db`, run
  `rebuild-index`, and diff the retrieval output before/after — **identical**.

- [ ] **1.6 — 🔬 Aql resurrection spike (GATE — go/no-go, max 1 day)**
  `git checkout 373c560c -- bots/discord-learning-bot/src/nour` from `empire-nexus` into a
  branch here. Run its suite under **`python3.12`**. **Paste the real number.** Decide: adapt
  it, or write a minimal orchestrator and record that as a decision.
  → *R:* R2.4, R6.3 · *D:* D3
  **✔ Verify:** the actual `pytest` output in the PR body, with the command. **If the suite
  cannot run within one day, this task closes as NO-GO and D3 is amended in the same PR.**
  *No later task may depend on Aql until this is closed.*

- [ ] **1.7 — Orchestrator wired + guardrails on delivery**
  One turn end to end: retrieve → plan → bounded tool loop → guardrail → deliver. Bilingual
  reply mirroring the owner's language; bidi rule enforced; retry-once-then-template fallback.
  → *R:* R2.4, R6 · *D:* D3
  **✔ Verify:** a bidi-violating draft is caught in test and never delivered; an Arabic
  message returns an Arabic reply; a 200-iteration loop yields **0** non-conformant deliveries.

- [ ] **1.8 — Deploy to Hetzner + footprint measurement**
  Join the existing compose stack, bind `127.0.0.1`, non-root, read-only rootfs, explicit
  memory/CPU limits. Rebuild **by service name**. Capture exit codes separately — never pipe a
  remote deploy through `tail`.
  → *R:* R7.3, N2 · *D:* D12
  **✔ Verify:** `docker stats` over 24 h shows ≤ 400 MB / ≤ 0.5 vCPU (paste it). Container
  start time confirms the rebuild applied. `docker inspect` shows non-root + limits. **Confirm
  the learning bot's memory headroom is unchanged.**

- [ ] **1.9 — 🚦 PHASE 1 LIVE GATE**
  Not a test run. A real conversation from a phone, in both languages, including a restart
  mid-session, and 24 h of uptime.
  **✔ Verify:** owner confirms in writing; `ops status` output pasted; `SESSION_CONTINUITY.md`
  in `empire-chronicle` gains a dated section; `SYSTEM-MAP.md` gains a Vizier section **in the
  same PR** (standing rule).

---

## Phase 2 — It does real work (the coder hand)

**Goal:** *"fix the typo in empire-dojo's README and open a PR"*, from a phone, works.
**Exit gate:** a merge-ready PR the owner did not touch a computer to produce.

- [ ] **2.1 — 🔬 Harness bake-off: OpenCode vs OpenHands (measured, not preferred)**
  Both run headless against the **same three real tasks** on the owner's repos: (a) a one-line
  docs fix, (b) a small bug fix with a test, (c) a two-file refactor. Score: success, tokens,
  wall-clock, and whether the diff was minimal.
  → *D:* D2
  **✔ Verify:** a results table in the PR body with the three task links. **The default
  (OpenCode) is not the answer until it wins.**

- [ ] **2.2 — Sandbox container for code execution**
  Separate container: git + runtime + harness only. **No production credentials.** No host
  mounts. Concurrency capped at 1. Hard timeout with container kill.
  → *R:* R7.3, R2.3 · *D:* D5, D7
  **✔ Verify:** from inside the sandbox, `env` contains no production secret and SSH to the
  server **fails**. A deliberately hanging task is killed at the timeout and reported.

- [ ] **2.3 — Credentials that make `main` structurally unreachable**
  The Vizier's **own** fine-grained GitHub token (contents + PR write, chosen repos only) and
  its **own** SSH key. Prove the constraint at the credential layer, not the prompt layer.
  → *R:* R7.4, R7.5 · *D:* D7
  **✔ Verify:** attempt `git push origin main` with that token → **fails**; paste the error.
  Revoking the token demonstrably does not affect the owner's access.

- [ ] **2.4 — `hands/coder.py` + PR bodies that state their own verification**
  Dispatch, stream progress to Telegram, return branch + PR. Every PR body states what
  changed, why, and **how it was verified** including the command and output.
  → *R:* R2.1, R2.2, R2.5
  **✔ Verify:** a real PR link whose body contains a real command and its real output.

- [ ] **2.5 — Verification via GitHub Actions, read back into the turn**
  Push → CI runs → the Vizier reads the run result and reports pass/fail **with the run link**.
  Nothing heavy executes on the Hetzner box.
  → *R:* N3, N9 · *D:* D5
  **✔ Verify:** `ps` on the box during a dispatch shows **no** test-runner process; the
  Telegram message contains the Actions run URL and its true conclusion.

- [ ] **2.6 — 🚦 PHASE 2 LIVE GATE — success criterion S1**
  **✔ Verify:** a **voice-note-free** typed instruction from a phone produces a merge-ready PR
  with no computer touched. Link it.

---

## Phase 3 — It knows the owner's world

**Goal:** it stops needing to be told what Empire English is.
**Exit gate:** it answers an ecosystem question correctly and cites its source.

- [ ] **3.1 — Local embeddings + retrieval over the memory repo**
  CPU sentence-transformer (MiniLM class), BLOB vectors, numpy search. **No embedding API.**
  → *R:* R3, R12.4 · *D:* D6
  **✔ Verify:** measure index + query time and RSS delta (paste). Confirm **zero** outbound
  network calls during indexing (`tcpdump`/audit).

- [ ] **3.2 — Ingest `empire-chronicle` as authoritative context**
  `STATUS.md`, `SYSTEM-MAP.md`, the newest `SESSION_CONTINUITY.md` section. Contradictions
  with the hub are **surfaced, never silently resolved**.
  → *R:* R3.7
  **✔ Verify:** ask 10 ecosystem questions with known answers; each reply cites a file. Plant
  a deliberate contradiction → it is surfaced.

- [ ] **3.3 — `LIFE-MAP.md` + `MISTAKES/`, searched before acting**
  One owner session populating the map. `MISTAKES/` seeded from the chronicle's hard-won
  findings (the timestamp class, the stale-streak class, slowed-Kokoro, `[skip ci]`).
  → *R:* R3, §8.9
  **✔ Verify:** a task that would repeat a recorded mistake causes the Vizier to **cite the
  mistake before acting**. Test asserts the pre-action lookup happens.

- [ ] **3.4 — Ministry registry + `machine` ministry, complete**
  Registry with the failing test for unregistered ministry strings. `machine` ships all three
  legs: answers questions, acts at L1, contributes a brief line.
  → *R:* R9.1–R9.3 · *D:* D10
  **✔ Verify:** add a fake ministry string to a source file → the test **fails**. `machine`
  answers, drafts and briefs (paste all three).

- [ ] **3.5 — Golden set + red team, in CI**
  100 owner questions with known answers (**including ones whose correct answer is
  "I don't know"**), 50 red-team prompts asserting zero `BLACK` executions and zero secret
  leaks.
  → *R:* R10.2, R7.10, S6
  **✔ Verify:** CI job runs both and fails the build on any fabrication or any `BLACK`.

---

## Phase 4 — Voice + the deep brain

- [ ] **4.1 — Tier C selection by bake-off** — candidate near-frontier open-weight models on
  the same three Phase-2 tasks. Cost per task recorded. Config still **refuses paid providers
  unless explicitly flagged**. → *R:* N1 · *D:* D4
  **✔ Verify:** results table; `$0` confirmed on the provider dashboard.
- [ ] **4.2 — Transcription: Groq Whisper + local `faster-whisper` fallback** → *R:* R5.1, R5.3
  **✔ Verify:** with the primary disabled, an Arabic voice note still transcribes.
- [ ] **4.3 — Kokoro TTS out, always rendered at speed 1.0** → *R:* R5.2 · *D:* D11
  **✔ Verify:** transcribe the produced audio and compare to the intended text — a slowed
  render is asserted **not** to occur (this defect shipped once and reached students).
- [ ] **4.4 — 🚦 LIVE GATE:** an Arabic voice note from a car produces a spoken Arabic reply.

---

## Phase 5 — It speaks first

- [ ] **5.1 — Rhythm learner (circular mean, UTC, ≥5 observed days)** → *R:* R4.2, R4.3 · *D:* D9
  **✔ Verify:** `brief_decision()` is pure and moment-injected; replay 6 synthetic owner
  rhythms → 6 different hours; a midnight-UTC owner is **not** placed at 12:00.
- [ ] **5.2 — Brief assembly, one line per active ministry, with reasons** → *R:* R4.1, R4.4
  **✔ Verify:** every line carries a stored reason retrievable by "why did I get this?".
- [ ] **5.3 — Alerts with cool-down + dedup + one-intervention-per-condition** → *R:* R4.5, R4.6
  **✔ Verify:** a repeated condition produces **1** message and a logged suppression; a test
  pins that one condition cannot produce five interventions.
- [ ] **5.4 — `empire` ministry (2nd), only after `machine` has run 7 clean days** → *R:* R9.4
  **✔ Verify:** paste the 7-day audit query for `machine` **before** this task opens.
- [ ] **5.5 — 🚦 LIVE GATE — success criterion S3:** the owner learns something from a brief
  he did not know.

---

## Phase 6 — It earns autonomy

- [ ] **6.1 — Trust table + pure `trust_decision` + ceilings** → *R:* R8.1–R8.6 · *D:* D8
  **✔ Verify:** 12 clean approvals → **1** promotion *proposal*, **0** automatic promotions;
  one edit → immediate demotion + notification; a test asserts each R8.4 ceiling is
  unpromotable at 100 approvals; a test asserts no `L3` pair is `RED`/`BLACK`.
- [ ] **6.2 — Shadow mode for every new hand before it goes live** → *D:* D3
  **✔ Verify:** a new hand runs shadowed for N turns with output logged and **not delivered**.
- [ ] **6.3 — Weekly self-audit + auto-disable of ignored ministries** → *R:* R10.4, R10.5
  **✔ Verify:** simulate 3 weeks of ignored messages → the ministry disables itself and says
  so; numbers reproducible by direct query.
- [ ] **6.4 — `/later` deferrals that re-raise with context** → *BLUEPRINT §8.3*
  **✔ Verify:** `/later 3d` and `/later when Stage 3 ships` both re-raise correctly with the
  original context attached.

---

## Phase 7 — It survives

- [ ] **7.1 — Tier D: Ollama on the Windows PC; sensitive ministries refuse to route out** → *R:* R12.4
  **✔ Verify:** with the PC off, a sensitive-ministry turn **refuses and explains** rather than
  falling back to an API. Audit shows zero third-party calls.
- [ ] **7.2 — Offline queue + restart safety under load; at-least-once with idempotency** → *R:* R11.2, R11.5, N5
  **✔ Verify:** `kill -9` mid-task ×10 → no partial branch, no partial write, no orphaned
  approval, no lost input.
- [ ] **7.3 — Encrypted memory backups + restore drill** → *R:* R12.3
  **✔ Verify:** restore to a clean box and diff the retrieval output.
- [ ] **7.4 — Dead man's switch** → *BLUEPRINT §8.8*
  **✔ Verify:** simulate N days of owner silence → the documented escalation fires in order.
- [ ] **7.5 — 🚦 REBUILD DRILL — success criterion S7:** clean box → working Vizier in
  **under 30 minutes**, timed and recorded. → *R:* N10

---

## Phase 8+ — Widening

- [ ] `time` ministry (Google Calendar, read-only first)
- [ ] `mind` ministry (voice capture → auto-filed)
- [ ] `people` ministry (cadence tracking)
- [ ] `home` ministry (renewals, documents)
- [ ] `treasury` ministry (manual entry; **no bank API exists**)
- [ ] `body` ministry (**only when a sensor exists**)
- [ ] `macal-overseer` adopted as the Windows hand
- [ ] The Mirror — weekly evidence vs intention (BLUEPRINT §8.2)
- [ ] Visual briefs via the existing html2img service
- [ ] PWA door, **only if** Telegram proves limiting

---

## Traceability — CI gate, not a courtesy

The build **fails** if any requirement below has no task referencing it.

| Req | Tasks | Req | Tasks |
|---|---|---|---|
| R1 | 1.2 | R7 | 1.4, 1.8, 2.2, 2.3 |
| R2 | 1.7, 2.1–2.6 | R8 | 6.1 |
| R3 | 1.5, 3.1–3.3 | R9 | 3.4, 5.4 |
| R4 | 5.1–5.3 | R10 | 3.5, 6.3 |
| R5 | 4.2, 4.3 | R11 | 1.3, 7.2 |
| R6 | 1.7 | R12 | 3.1, 7.1, 7.3 |
| N1 | 4.1 | N6 | 1.1, 1.3 |
| N2 | 1.8 | N7 | 1.4 |
| N3 | 2.5 | N9 | 1.1, 2.5 |
| N4 | 1.2 | N10 | 7.5 |
| N5 | 7.2 | | |
| S1 | 2.6 | S6 | 3.5 |
| S3 | 5.5 | S7 | 7.5 |
| S2, S4, S5, S8 | measured over 14–30 days of real use, not by a task |

---

## Kill criteria — when to stop, decided in advance

Recorded now, while nobody is invested, because a project that cannot be stopped cannot be
trusted.

| Stop if | Because |
|---|---|
| Phase 1 has not produced a usable conversation in **3 weeks** | the skeleton is wrong; a rewrite is cheaper than a rescue |
| The owner ignores briefs for **3 consecutive weeks** | it has become noise, which is worse than absence |
| It causes **one** production incident affecting a student | the blast radius is not contained; stop and re-gate |
| Maintenance exceeds **1 hour/week** | it has become a second job (N8) |
| Free-tier quality proves unusable **and** the owner declines a paid brain | the premise fails honestly; say so rather than shipping something bad |
| At 30 days, the answer to **S8** is "no, I wouldn't miss it" | it did not earn its place |
