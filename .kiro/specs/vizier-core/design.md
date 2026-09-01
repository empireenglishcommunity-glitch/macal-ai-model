# Design — The Vizier (الوزير)

**Spec:** `vizier-core` · **Status:** 🟡 **DRAFT — AWAITING OWNER APPROVAL. NOTHING IMPLEMENTED.**
**Requirements:** [`requirements.md`](./requirements.md) · **Vision:** [`BLUEPRINT.md`](../../../BLUEPRINT.md)

> Decisions are numbered `D#` and each states **what was rejected and why**. A decision
> without a rejected alternative is an assumption in disguise. Where a decision depends on a
> measurement not yet taken, it says so and names the measurement — it is not guessed.

---

## 1. Shape of the system

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  OWNER — phone / desktop / web, anywhere on earth                            │
│  text · voice note · photo · document · forwarded message                     │
└───────────────────────────────┬──────────────────────────────────────────────┘
                                │ Telegram Bot API (long-poll — no inbound port)
┌───────────────────────────────▼──────────────────────────────────────────────┐
│  HETZNER CX23 · container `macal-vizier` · non-root · 400 MB / 0.5 vCPU cap   │
│                                                                              │
│  ┌────────────┐   ┌──────────────┐   ┌───────────────┐   ┌────────────────┐  │
│  │  DOOR      │──►│  ORCHESTRATOR│──►│  CONSCIENCE   │──►│  HANDS         │  │
│  │ telegram   │   │  (from Aql)  │   │ classify →    │   │ registry of    │  │
│  │ allowlist  │◄──│  bounded     │◄──│ gate → audit  │◄──│ tools          │  │
│  │ ack/queue  │   │  max 5 calls │   │ /halt         │   │                │  │
│  └────────────┘   └──┬────┬──────┘   └───────────────┘   └───┬────────┬───┘  │
│                      │    │                                  │        │      │
│              ┌───────▼─┐  │  ┌────────────┐         ┌────────▼──┐  ┌──▼────┐ │
│              │ ROUTER  │  └─►│  SPINE     │         │ SENSES    │  │ CODER │ │
│              │ tier A/ │     │  memory    │         │ read-only │  │ hand  │ │
│              │ B/C/D + │     │  SQLite +  │         │ ingesters │  │ (D2)  │ │
│              │fallback │     │  git text  │         └───────────┘  └───┬───┘ │
│              └──┬──────┘     └────────────┘                            │     │
│                 │            ┌────────────┐                            │     │
│                 │            │ HEARTBEAT  │  scheduler: brief, alerts  │     │
│                 │            └────────────┘                            │     │
└─────────────────┼──────────────────────────────────────────────────────┼─────┘
                  │                                                      │
     ┌────────────┼────────────┬──────────────┐              ┌───────────▼────────────┐
     ▼            ▼            ▼              ▼              │ SANDBOX container      │
  Groq       provider #2   provider #3   Windows PC          │ git + coding harness   │
  (free)      (fallback)    (deep)       Ollama (private)    │ NO prod creds          │
                                                             └───────────┬────────────┘
                                                                         ▼
                                                            GitHub — branch + PR only
                                                            verification runs in ACTIONS (D5)
```

**Reading of the diagram:** the owner touches exactly one thing. Everything below the Door is
invisible to him — including which brain answered, and whether the answer came from memory,
a sense, or a hand.

---

## 2. Decisions

### D1 — The Vizier owns the conversation; it is not a coding tool with a chat bolted on

**Decision.** Build the Vizier core (door, memory, router, conscience, ministries, trust
ladder, heartbeat) as our own service. It is small and it is the part that is specifically the
owner's.

**Rejected:** wrapping a coding agent in Telegram and calling it done. Coding harnesses are
built around *a repository and a task*. The Vizier is built around *a person and a life* — it
must persist across tasks, hold ministries that have nothing to do with code, speak first,
and enforce autonomy levels. Those assumptions do not fit inside a repo-scoped tool, and
fighting them would cost more than the core costs to write.

### D2 — Repository work is delegated to a third-party coding harness, invoked as a hand ⭐

**Decision.** The Vizier does **not** implement its own file-editing / test-running agent
loop. It exposes one hand, `coder.dispatch(repo, task)`, which runs an existing open-source
agentic coding tool headless inside a sandbox container and returns a branch plus a PR.

**Why.** The harness is the single most commoditised layer in this stack: mature, MIT/Apache
licensed, model-agnostic, and enormous — OpenCode is at ~165–172k GitHub stars, Aider ~46k,
plus OpenHands and Goose. Writing our own would be months of work to arrive somewhere worse.

**Which harness — decided by measurement, not preference.** Default is **OpenCode** (MIT;
designed so the model is a replaceable component rather than the tool's identity; largest
ecosystem; local models via Ollama). **OpenHands** is the alternative and is genuinely better
suited to "here is a whole ticket, go away and do it".

> **Task 2.1 is a bake-off, not an install.** Both are run against the **same three real
> tasks** on the owner's own repositories, and the winner is chosen on measured results.
> A default is not a conclusion.

**Rejected:** (a) our own loop — see above; (b) committing to a harness before measuring —
this ecosystem's rule is that a documented choice must be re-derived, not inherited;
(c) an IDE-bound tool (Cline) — there is no IDE here; (d) a vendor-bound CLI — violates D4.

### D3 — Resurrect Aql as the orchestrator core ⭐

**Decision.** Recover the `src/nour/` package from `empire-nexus` at commit **`373c560c`**
(the commit before `6d421edd` removed it on 2026-07-24) and adapt it as the Vizier's
orchestrator: bounded tool-calling loop, guardrails, role/permission boundary, shadow mode,
and SQLite+numpy retrieval.

**Verified present at that commit** (GitHub API, 2026-08-31):

| File | Size | Role here |
|---|--:|---|
| `orchestrator.py` | 25,873 B | the bounded tool-calling loop — becomes the Vizier's turn engine |
| `guardrails.py` | 11,251 B | script conformance, bidi, role-leak, retry→template fallback → **R6** |
| `permissions.py` | 5,396 B | permission boundary → foundation of the Conscience → **R7** |
| `roles.py` | 2,569 B | role resolver |
| `shadow.py` | 5,575 B | run without delivering → how every new hand is trialled |
| `knowledge/{chunker,embedder,retriever}.py` | — | SQLite + numpy retrieval → **R3** |
| `tools/{dispatcher,owner_tools,student_tools}.py` | — | tool dispatch → the Hands registry |

Its bound on tool calls was **structural** (no tool schema is offered on the final turn, so
the model is forced to answer) — exactly the property R7 needs, and much harder to retrofit
than to inherit.

> ⚠️ **This is a candidate, not a dependency, until measured.** The claim of "717 tests" is
> copied from `empire-chronicle`, whose counts have been provably 507 tests stale. **Task 1.6
> resurrects it into a branch and runs its suite under `python3.12`, and the real number goes
> in the PR body.** If it does not run standalone within one day of work, we write a minimal
> orchestrator instead and record that as a decision. **No phase after 1 may depend on Aql
> until task 1.6 has passed.**

**Rejected:** writing a fresh orchestrator first (throws away tested guardrails and a
structural safety property); importing it as a live dependency on `empire-nexus` (couples the
owner's assistant to the students' bot — the coupling that killed it the first time).

### D4 — The brain is a swappable dependency; four tiers, provider-agnostic ⭐

**Decision.** A `Brain` interface with per-provider adapters. Model identifiers appear **only
in configuration**, never in code. The router selects a tier per task and falls through on
failure.

| Tier | Purpose | v1 choice | Why |
|:--:|---|---|---|
| **A — reflex** | routing, intent, classification, short summaries | smallest fast Groq model | ~90% of calls; must be cheap and instant |
| **B — thinking** | ordinary turns, drafting, memory writes | Groq, mid open-weight model | free tier, already the ecosystem's primary in `ai_engine.py` |
| **C — deep** | multi-file code work, architecture, hard reasoning | a near-frontier **open-weight** model (DeepSeek-V4-Pro / Kimi-K3 class) via the cheapest provider serving it | open weights now score at the top of SWE-bench Verified (~93–96%), *above several closed frontier models* — near-frontier without vendor lock-in |
| **D — private/offline** | sensitive ministries; no internet | Ollama on the Windows PC (Qwen3-8B class) | nothing leaves the house; **R12.4**, **R11.1** |

**Fallback chain:** `preferred tier → same tier alternate provider → tier B → tier D → queue
and tell the owner`. Rate limiting triggers fallback, never failure (**R11.3**).

**Start:** Groq only, because it is already the ecosystem's primary, is free without a card,
and needs no new account. **Tier C's exact model is deliberately unresolved** — it is
selected in task 4.1 by running the owner's own three-task bake-off, because published
benchmarks are gamed (scores moved ~20%→80%+ in eighteen months largely through benchmark
contamination) and because model availability per provider changes monthly.

**Cost posture (N1):** the config **refuses paid providers unless a flag is explicitly
enabled**, so $0 is the enforced default rather than an intention. Google/Gemini is not in
the v1 chain at all — **the owner's Google project is 403-denied**, documented in
`SYSTEM-MAP.md` §8.

**Rejected:** one model everywhere (either too weak for code or too expensive for chat);
hardcoding a provider (guarantees a rewrite within a year); a paid frontier model in v1
(breaks N1 without an owner exception); training anything (BLUEPRINT §0.5).

### D5 — Heavy compute runs in GitHub Actions, never on the Hetzner box ⭐

**Decision.** The Vizier edits and pushes; **verification runs in CI**. It opens the branch,
CI runs the suite, and it reads the result back and reports it.

**Why.** The box is 2 vCPU / 4 GB already running ~25 services. `empire-nexus` runs 2,571
tests; running that on the box would contend with the live student bot. GitHub Actions is
free for these repos, isolated, reproducible, **already how the bot deploys**, and produces a
public artefact the owner can inspect. This turns the platform's tightest constraint into a
non-issue and simultaneously satisfies N9.

**Consequence:** the sandbox container needs only git, a runtime, and the harness — no test
matrices, no browsers, no build toolchains. Concurrency is capped at **1** dispatch.

**Rejected:** running suites on the box (risks the live bot for 17 students); skipping
verification (the exact failure mode this ecosystem is scarred by); a second server (breaks
the $7 ceiling).

### D6 — Memory: plain text in a private git repo + SQLite index, local embeddings ⭐

**Decision.** Two stores, one truth.

```
macal-memory/                 ← PRIVATE repo. Human-readable. THE truth.
├── STATUS.md                 small, overwritten. "where I am now."
├── LIFE-MAP.md               durable: people, assets, accounts, obligations
├── CONTINUITY.md             append-only journal, archived quarterly
├── DECISIONS/                one file per settled decision + what it ruled out
├── MISTAKES/                 searched BEFORE acting, not after failing (§8.9)
└── ministries/{machine,empire,time,mind,home,people,treasury,body}.md

data/memory.db                ← DERIVED index. Rebuildable from the text at any time.
   facts(id, ministry, text, source, learned_at, valid_until, embedding)
   events(id, ministry, kind, payload, occurred_at, source)
   commitments(id, text, promised_at, due_at, status, evidence)
   people(id, name, relation, cadence_days, last_contact_at)
   audit(id, at, actor, ministry, action, blast, autonomy, reason, outcome, approved_by)
   trust(ministry, action, level, consecutive_clean, last_change_at, reason)
   deferrals(id, question, context_ref, wake_condition, created_at)
```

**Rules with reasons, each from a real defect in this ecosystem:**

| Rule | Because |
|---|---|
| The SQLite DB is **derived and rebuildable**; the text is authoritative | a memory only the assistant can read is a memory it can hold hostage (R3.2) |
| Every fact has `source` and `learned_at`, enforced `NOT NULL` | *"counts in docs are claims"* — an unsourced fact is a rumour, and a rumour is how the bot decided a 43-day-streak student was inactive |
| **Derived values are never stored** | `current_streak` went stale because it only recalculated on submit, which silently disabled the nudge for all 7 students who needed it |
| All timestamps stored **UTC, ISO-8601, one format**; compared as instants, never strings | `' '`(32) sorts before `'T'`(84), so *active 17 hours ago* evaluated as *inactive over a day* |
| One helper for "now", one parser, `days_since` returns **`None`, never `0`** | four separate sites had the naive-local-minus-UTC bug; three were latent and would have activated on adding `ENV TZ` |
| Deletions and expiries write an audit row | R3.5 — nothing forgotten silently |

**Embeddings: a local CPU sentence-transformer (MiniLM class, ~90 MB), not an API.** Zero
cost, zero rate limit, works offline, and no life data leaves the box for indexing.
Aql used Gemini embeddings — **not available to the owner (403-denied)** — so this is a
correction, not a preference. Vectors are stored as BLOBs and searched with numpy; at this
corpus size that is milliseconds.

**Rejected:** a hosted vector DB (vendor lock-in on the one irreplaceable asset; explicitly
rejected in Aql's own design); database-only memory (fails R3.2); Markdown-only (no retrieval
at scale); API embeddings (cost, rate limits, privacy, and currently blocked).

### D7 — The Conscience is a gate in the call path, not a policy document ⭐

Every hand invocation passes through one chokepoint. There is exactly one, and it cannot be
bypassed because hands are only reachable through it.

```
intent → resolve(ministry, action) → classify blast → look up autonomy
       → BLACK?  refuse + audit + tell owner                        ← unconditional
       → RED?    request approval (inline buttons) + audit; expire after 5 min
       → L0/L1?  produce a draft, never execute
       → L2/L3?  execute in sandbox → audit → report (L2) or log (L3)
```

Enforcement is layered so that no single failure is fatal:

| Layer | Mechanism |
|---|---|
| **Branch rule** | ⭐ a GitHub **ruleset** on the default branch requiring a pull request, with an **empty bypass list**. See the correction below. |
| **Credential** | the token carries **no `Administration` and no `Workflows` permission**, so it can neither change the branch rule that gates it nor edit the CI that catches it. The SSH key has a forced-command allowlist. Prompt-independent. |
| **Process** | container, non-root, read-only root filesystem, no host mounts, explicit memory/CPU limits, capped concurrency |
| **Code** | the classifier; `BLACK` raises before any side effect; a test asserts every `BLACK` entry refuses |
| **Data** | append-only audit table; `/halt` sets a flag every hand checks |
| **Human** | inline approval for `RED`; ceilings that cannot be promoted (R8.4) |

**The Vizier cannot modify its own permission rules, flags, ceilings or audit log.** Those
paths are `BLACK`, and a test asserts it — the same structural posture as Aql's tool bound,
and the reason the standing rule *"never remove a payment approval gate"* holds even against
the assistant itself.

#### ✏️ Correction to D7, 2026-08-31 — the token alone does **not** protect `main`

As first written, this section claimed the credential layer made `main` unreachable. **That
was wrong**, and it is the kind of wrong that would have been discovered only after something
was already pushed. A fine-grained PAT with `Contents: write` **can** push directly to
`main`. The token acts as its creator, who is an org owner, so no permission checkbox on the
token prevents it.

What actually enforces it is a **branch ruleset**, and it only works with an empty bypass
list — an org or repository admin in the bypass list defeats the whole thing silently.

**Configured and verified live, 2026-08-31:**

```
ruleset  protect-main   id 21968385   enforcement: active
target   ~DEFAULT_BRANCH
rules    pull_request · non_fast_forward · deletion
bypass_actors  []            ← the load-bearing detail
```

```
PUT /repos/.../contents/.vizier-gate-test  (branch: main)
→ HTTP 409
  "Repository rule violations found\n\nChanges must be made through a pull request."
```

A follow-up check confirmed **no file was created** (`GET .vizier-gate-test` → 404) and
`main`'s tree is unchanged. The `409` is the success condition; a `201` would have meant the
gate was decorative.

**Consequence accepted deliberately:** with an empty bypass list the **owner** cannot push to
`main` either — only merge PRs. That matches his own standing rule ("never push to `main`,
even for docs") and moves it from memory to mechanism. It also means the bootstrap commit
`826f75c` could not be repeated today, which is correct.

**The general lesson, recorded because it will recur:** a permission model has to be tested by
*attempting the forbidden thing*. Reading the checkbox list is not verification — it is the
same error as trusting a green test suite.

**Rejected:** trusting the system prompt (a prompt is a suggestion, not a boundary);
approval on everything (the owner stops reading and rubber-stamps — the "red check on a
healthy system" failure mode); running on the host as root (one bad command ends the
business).

### D8 — Trust ladder: state in one table, decisions in one pure function

`trust(ministry, action) → level`. Promotion is **proposed, never automatic** (R8.2);
demotion **is** automatic (R8.3).

```python
def trust_decision(history, ceiling, now) -> Decision   # pure; moment passed in
```

Pure and moment-injected, so it is testable at any simulated history — the shape that made
`nudge_decision()` reviewable and replayable against real students. It returns a **reason
string** that is stored and shown, because *"why am I being asked this?"* must always be
answerable.

**Rejected:** automatic promotion (the owner must never discover new autonomy by surprise);
a single global autonomy setting (drafting a DM and restarting a container are not the same
risk); time-based promotion (time is not evidence).

### D9 — The heartbeat learns the owner's hour; it does not own a clock ⭐

**Decision.** Port the bot's per-student rhythm learner and point it at the owner. The brief
hour is the **circular mean** of his own observed activity hours in UTC. Under 5 observed
days, nothing is sent (R4.3).

**Why circular:** a plain mean puts a midnight-UTC actor at 12:00 — twelve hours wrong. This
is measured, not theoretical, in the existing codebase.

**Why it matters beyond politeness:** the ecosystem has an **open, dated** timezone problem —
`TIMEZONE` is `Asia/Dubai` while the owner and students are in Egypt, 20 clock-scheduled loops
fire an hour early, and **on 2026-10-30 Egypt leaves DST and the drift doubles by itself**. A
learned hour has no timezone to be wrong about. The Vizier sidesteps the bug rather than
inheriting it.

**Rejected:** a configured hour (wrong for someone who studies at 04:44 Cairo; and it is the
exact bug class already burning this ecosystem); fixed cron per ministry (five ministries
would produce five pings).

### D10 — Ministries are a registry, and only `machine` ships in v1

One `MINISTRIES` registry declares id, arabic name, tools, sensors, default autonomy, brief
contributor, and sensitivity. A ministry string appearing in code without registration
**fails a test** — the same discipline as `flag_registry.py`, chosen because that discipline
has already prevented drift here.

**Order:** `machine` → `empire` → `time` → `mind` → `people` → `home` → `treasury` → `body`.
`machine` is first because **every claim it makes is independently verifiable by the owner in
seconds**, which is what makes it the right place to earn trust. `empire` is second: highest
value, but it touches 17 real students, so it goes second deliberately, not first.

**Rejected:** shipping several ministries at once (eight half-ministries is a dead project);
starting with `empire` (highest blast radius before any trust exists).

### D11 — Voice: Groq Whisper primary, local faster-whisper fallback, Kokoro out

Transcription has two providers and one of them needs no internet (R5.3). TTS is the
**existing** Kokoro service on `:8880` — already OpenAI-compatible, already shared by three
repos, 9,360 clips deep, zero new cost.

**One inherited trap, recorded:** **slowing Kokoro corrupts phonemes** — measured at 16/56
wrong when slowed vs 0/56 at speed 1.0. Render at 1.0 always; any slowdown happens at
playback. This cost real student trust once and must not be rediscovered.

**Rejected:** browser speech synthesis (deliberately removed from the ecosystem for being
robotic); a paid STT/TTS API (N1).

### D12 — Deployment: one container, `127.0.0.1`, long-poll, no new inbound port

The Vizier joins the existing `docker compose` stack, binds `127.0.0.1`, and reaches Telegram
by **long-polling** — so it needs **no** webhook, no new tunnel ingress rule, and no inbound
port at all. Rebuild is **by service name** (`docker compose up -d --build macal-vizier`),
because a bare `--build` already fails on this box.

**Rejected:** a webhook (needs public ingress for no benefit at one user's volume); host
install (violates D7); a separate box (breaks the $7 ceiling).

---

### D13 — Screen every inbound message with a purpose-built injection classifier ⭐

**Unplanned. This decision exists because the owner's real model list contained something
better than anything the design had planned for.**

`meta-llama/llama-prompt-guard-2-86m` and `-22m` are **dedicated prompt-injection and
jailbreak classifiers** — 86M and 22M parameters, 512-token context — available on the same
free key. A 22M-parameter classifier costs approximately nothing and returns approximately
instantly.

**Decision.** Every inbound message is screened by prompt-guard **after** the allowlist and
**before** the orchestrator, as a `GREEN` pre-step in the Conscience. A positive result does
not silently drop the message: it is audited with the score, and the turn proceeds in a
restricted mode that offers **no tools at all**, so the worst case is an unhelpful answer
rather than an action.

**Why this is worth a decision of its own.** R7 and success criterion S6 previously relied on
guardrails the Vizier applies to its *own output*, plus a 50-prompt red-team set in CI. That
detects a bad *answer*. It does not detect a hostile *input* before the orchestrator has
already reasoned about it and possibly selected a tool. A classifier trained for exactly this
job, running before the reasoning, is a different and better layer — and it is free.

**Honest limits, stated now:** a 512-token window cannot see a long document, so this screens
the *instruction*, not attached content; and a classifier is a probability, never a boundary.
It sits **on top of** the `BLACK` list and the approval gates, which remain the actual
enforcement (D7). It is defence in depth, not a replacement for depth.

**Rejected:** relying on the orchestrator's own judgement (the thing being attacked cannot be
the thing detecting the attack); a hand-written keyword blocklist (trivially evaded, and it
would fire on legitimate owner instructions such as "ignore the previous plan").

---

## 2.1 Measured model availability — and one correction to D4

Queried against the owner's own Groq key, **2026-09-01**. Recorded because model catalogues
change monthly and this ecosystem's rule is that a documented figure must be re-derived, not
inherited. **Re-run before trusting any row of this table:**

```bash
curl -s https://api.groq.com/openai/v1/models -H "Authorization: Bearer ${VIZIER_GROQ_API_KEY}"
```

**14 models, all active.** Grouped by what they are actually for:

| Purpose | Model | Context | Note |
|---|---|--:|---|
| **Reasoning, large** | `openai/gpt-oss-120b` | 131,072 | the strongest thing reachable on this key |
| **Reasoning, mid** | `qwen/qwen3.8-27b` · `qwen/qwen3.6-27b` | 131,042 · 131,072 | 27B; the `131,042` is as reported, not a typo of ours |
| **Reasoning, small** | `openai/gpt-oss-20b` | 131,072 | fast, cheap, full context |
| **Arabic specialist** | `allam-2-7b` (SDAIA) | 4,096 | Arabic-first, but a small window |
| **Agentic system** | `groq/compound` · `-mini` | 131,072 | brings its **own** tool loop — see below |
| **Injection classifier** | `meta-llama/llama-prompt-guard-2-{86m,22m}` | 512 | → **D13** |
| **Output safety** | `openai/gpt-oss-safeguard-20b` | 131,072 | candidate for the delivery guardrail (R6.3) |
| **Speech → text** | `whisper-large-v3` · `-turbo` | — | → **D11 confirmed** |
| **Text → speech** | `canopylabs/orpheus-arabic-saudi` · `-v1-english` | 4,000 | → see D11 note |

### ✏️ Correction to D4 — tier C is weaker than the design assumed

D4 specified tier C as *"a near-frontier open-weight model (DeepSeek-V4-Pro / Kimi-K3
class)"*. **Neither is on this key, and nothing of that class is.** The strongest model
available is `openai/gpt-oss-120b`.

This is a **real capability gap, recorded rather than papered over**: hard multi-file
architectural work will be measurably weaker than the design implied. Reaching a
93–96%-SWE-bench-class model means a different provider, which in practice means paid, which
requires the owner's written exception (N1). **Deferred to task 4.1's bake-off with real
numbers, not resolved by assumption here.** Phases 1–3 do not need tier C.

### Tier assignments for task 1.3

| Tier | Model | Why this one |
|:--:|---|---|
| **A — reflex** | `openai/gpt-oss-20b` | smallest reasoning model with a *full* 131k window; ~90% of calls are routing and classification |
| **B — thinking** | `qwen/qwen3.8-27b` | newest mid model; the default workhorse |
| **C — deep** | `openai/gpt-oss-120b` | the strongest available — with the gap above recorded |
| **D — private** | Ollama, owner's PC | unchanged; still disabled until Phase 7 |

**`groq/compound` rejected for tier C**, despite being tempting: it is an agentic *system*
with its own built-in tool use, and pointing the bounded orchestrator at it means two agent
loops interleaving. D3's tool bound is structural precisely because it is enforced by *not
offering a tool schema* on the final turn — a model that calls tools on its own initiative
breaks that guarantee silently. It is a good candidate for a future explicit
`research`/`web-search` hand, where its tool use is the point and is contained.

### D11 confirmed, plus one gap it had not acknowledged

**Transcription is settled and free:** `whisper-large-v3-turbo` primary, `whisper-large-v3` as
the accuracy fallback, both on the key that already exists. No new provider, no new
credential.

**And a gap in D11 that this list exposes:** D11 specified Kokoro for TTS, but Kokoro's voices
are English — **Arabic voice output was an unstated hole in R5.4**, and the owner is Egyptian
writing for Arabic-speaking students. `canopylabs/orpheus-arabic-saudi` is a candidate.
Flagged, **not decided**, for two honest reasons: the dialect is Saudi, not Egyptian, which is
a content judgement rather than a technical one; and this entry's capability is inferred from
its name and context size, so it must be **verified against the endpoint** before any design
depends on it. Task 4.3 owns that.

---

## 3. Components

| Component | Responsibility | Key requirements |
|---|---|---|
| `door/telegram.py` | long-poll, allowlist, media download, acknowledgement, inline approvals, outbound chunking | R1, R7.1 |
| `core/orchestrator.py` | one turn: retrieve → plan → bounded tool loop → guardrail → deliver (from Aql, D3) | R2.4, R6.3 |
| `core/router.py` | tier selection, provider fallback, queue-on-total-failure | R11.1–R11.3, D4 |
| `brains/*.py` | one adapter per provider; identical interface | N6 |
| `spine/{store,index,retriever,writer}.py` | text ↔ SQLite, sourced writes, rebuild-from-text | R3 |
| `conscience/{classify,gate,audit,halt}.py` | the single chokepoint; append-only audit | R7 |
| `trust/ladder.py` | pure `trust_decision`; state table | R8 |
| `hands/*.py` | one module per hand; each declares ministry + blast class + a check | R2, N9 |
| `hands/coder.py` | dispatch to the harness in the sandbox; return branch + PR | R2.1–R2.6, D2 |
| `senses/*.py` | read-only ingesters; failure disables only its own brief line | R4.6, R11.4 |
| `heartbeat/{rhythm,brief,alerts}.py` | learned hour, brief assembly, dedup + cool-down | R4, D9 |
| `ministries/registry.py` | the one declaration of the eight ministries | R9.1, D10 |
| `ops/cli.py` | `status`, `audit`, `trust`, `halt`, `memory inventory`, `rebuild-index` | R3.6, R7.7, R8.5 |

---

## 4. Failure modes designed for

| Failure | Behaviour |
|---|---|
| All brains down | acknowledge, queue, process on recovery. **Input is never lost.** (R11.2) |
| Rate limited | fall through the chain; the owner never sees a failure (R11.3) |
| Windows PC off | tier D unavailable; sensitive ministries **refuse rather than route to an API** and say why |
| Harness hangs | hard timeout, container killed, branch abandoned, reported |
| Owner unreachable during a `RED` approval | expires in 5 minutes, **auto-rejects**, audited |
| Restart mid-task | in-flight state committed or discarded, never half-applied (R11.5) |
| Memory DB corrupted | rebuild the index from the text repo (D6) |
| Telegram outage | queue outbound; deliver on reconnect |
| It is confidently wrong | PR-only + CI verification + audit + reversibility. **Assumed, not hoped against.** |
| A secret appears in a draft | guardrail scans outbound text for known secret shapes and env values; blocks and alerts (R7.10) |

---

## 5. Verification strategy — how we avoid this ecosystem's own scars

Each item exists because of a specific, documented, expensive incident.

| Guard | Prevents the recurrence of |
|---|---|
| Every new test must be **shown failing on pre-fix source** (stated in the PR body) | tests that pass because they do not look — *"a green check can be green because it did not look"* |
| **Live verification** required before any completion claim | 4 pages 404ing in production with every gate green, found only by making a real account and clicking |
| Counts and statuses **re-derived in the turn**, with the command quoted | a documented suite count 507 tests stale; *"counts in docs are CLAIMS"* |
| CI steps carry `if: !cancelled()` | a first failing step meaning later checks never ran at all |
| No commit message may contain `[skip ci]` | it silently suppressed runs three different ways, leaving `main` unverified with nothing reporting it |
| Remote command **exit codes captured separately**, never piped through `tail` | a rebuild that silently did not apply while the old container kept running and the output looked fine |
| Red-team set of 50 prompts in CI, asserting zero `BLACK` executions and zero secret leaks | the whole class of prompt-injection and jailbreak risk |
| Golden set including questions whose correct answer is **"I don't know"** | fabrication, the worst non-safety defect here (R10.2) |
| **Shadow mode** for every new hand before it is ever live | shipping an untested effector at a real target |
| Timezone tests pin **production** config, not a patched value | two "dubai day start" tests that patched `config.TIMEZONE` themselves and so pinned nothing |

---

## 6. What this design deliberately does not do

- No model training or fine-tuning (BLUEPRINT §0.5).
- No multi-agent architecture — one bounded orchestrator, many tools. Aql's own design
  rejected multi-agent and was right.
- No hosted vector database.
- No second server, no paid SaaS, no usage-capped dependency.
- No autonomous money movement, ever.
- No acting on behalf of other people (students, staff) — separate spec, separate approval.
- No writing to `main` in any repository, including this one.

---

## 7. Open items for the owner — needed before or during Phase 1

None of these block writing code, and each is flagged rather than assumed.

| # | Item | Needed by | Default if you say nothing |
|:-:|---|---|---|
| 1 | A **new** Telegram bot token from BotFather (dedicated, not the ops-hub bot) | Task 1.2 | blocked — only you can create it |
| 2 | A Groq API key for the Vizier (**its own**, not the bot's) | Task 1.3 | blocked |
| 3 | A fine-grained GitHub token: contents+PR write, **no push to `main`**, only the repos you choose | Task 1.4 | I start with `macal-ai-model` only |
| 4 | Which repos it may touch in Phase 1 | Task 1.4 | this repo only |
| 5 | Windows PC: is it on most of the day? RAM/GPU? | Phase 6 | tier D is treated as often-absent |
| 6 | Which ministries are **sensitive** (local brain only) | Phase 5 | `treasury`, `body`, `people` |
| 7 | Whether a paid tier-C brain may ever be proposed | Phase 4 | free/open-weight only, forever |

---

## 8. Traceability

| Requirement | Design |
|---|---|
| R1 door | §3 `door/telegram.py`, D12 |
| R2 real work | D2, D5, §3 `hands/coder.py` |
| R3 memory | D6 |
| R4 speaks first | D9, §3 `heartbeat/` |
| R5 voice | D11 |
| R6 bilingual | D3 (guardrails), §5 |
| R7 safety | D7, D5, D12 |
| R8 trust | D8 |
| R9 ministries | D10 |
| R10 honesty | §5, D6 (sourced facts) |
| R11 degrades | D4 (fallback), §4 |
| R12 privacy | D6 (local embeddings), D4 (tier D), README warning |
| N1 cost | D4 (config refuses paid), D5, D11 |
| N2 footprint | D12, D5 |
| N3 heavy compute | D5 |
| N6 swappable model | D4 |
| N9 tests | §5, D2 |
