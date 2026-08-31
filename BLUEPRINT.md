# MACAL — The Vizier

**A personal AI system for Mahmoud Ashri: one brain, one memory, many doors.**

> **STATUS: PROPOSAL / NOT APPROVED / NOTHING BUILT.**
> This document exists to be argued with. No code has been written, no repo has been
> committed to, nothing has been deployed. Every section ends with a decision that is
> yours, not mine. Reject freely — rejecting an idea here costs nothing; rejecting it
> in month three costs a month.

---

## 0. What you asked for, said back to you

> *"An AI model for my assistance, online and offline, that can help me with all my life
> aspects and do everything for me, linked to everything I use, reachable any time from
> phone or PC from anywhere in the world."*

That is a **complete vision** and an **incomplete specification**. Six words in it are
load-bearing and each one hides a decision: *model*, *offline*, *all*, *everything*,
*linked*, *anywhere*. This document takes each one apart, tells you what it can actually
mean, what it costs, and what it will do to you if built naively.

**The one-line version of my counter-proposal:**

> Don't build an AI model. Build a **nervous system** — a permanent memory and a permanent
> set of nerves — and treat the AI model as a **swappable organ** you replace twice a year
> without noticing.

---

## 0.5 "I just want one AI like Gemini, but free, that can do anything"

Added after your reply. This is the most important section in the document, because it
splits your sentence into one part that is **already solved and free** and one part that is
**the entire project**.

### You already have a free Gemini
`gemini.google.com` — free, on your phone, your PC, and any browser on earth. Also ChatGPT,
Claude, DeepSeek, Copilot: all free tiers, all excellent, all reachable from anywhere.
**If that were enough, you would not be asking me for anything.**

### So what is actually missing is not the brain
Ask the free Gemini to do any of these:

| Ask | What Gemini does |
|---|---|
| "What did I decide about the Dubai timezone in August?" | ❌ Doesn't know. Never will. |
| "Is my server healthy?" | ❌ No access. |
| "Which student hasn't submitted this week?" | ❌ No access. |
| "Move these 200 downloads into the right folders." | ❌ Cannot touch your PC. |
| "Remind me at the right moment, without me asking." | ❌ Never speaks first. |
| "Draft the reply to Mai and let me approve it." | ❌ No hands. |
| "What did we agree three months ago?" | ❌ Forgets everything between chats. |

**A model is a brain in a jar.** Brilliant, free, and it cannot remember you, see anything
you own, or move a single file. The free brain is a **commodity you plug in in one day.**
The memory and the hands are the **entire build** — and there is nothing on the market that
gives you those for your specific life, because your life is Empire English, a Hetzner box,
17 students, and a Windows PC.

### Two different meanings of "build me an AI like Gemini"

| Meaning | Verdict |
|---|---|
| **Train my own Gemini-class model** | ❌ Impossible for anyone outside a handful of companies: tens of thousands of GPUs, ~$100M+ of compute, a data operation of hundreds of people — and it would be obsolete in 9 months. This is arithmetic, not pessimism. |
| **Use a Gemini-class model, for free, as my assistant's brain** | ✅ **Exactly the plan.** Day one, one config line, $0. |

### The free brains actually available to you (checked 2026-08-31)

| Option | Free allowance | Notes for *you* specifically |
|---|---|---|
| **Groq** | no card, ~30 requests/min, ~14,400/day | **Already your primary** (`ai_engine.py`). Open models (Llama/Qwen class), extremely fast. Safest starting point. |
| **Google Gemini API** | free tier, roughly 5–15 requests/min depending on model | ⚠️ **Your Google project is 403-denied** (`SYSTEM-MAP.md` §8: "Gemini project is Google-denied → Groq made primary"). Needs a fresh project/account before it's an option at all. |
| **Ollama on your Windows PC** | unlimited, $0, private, works with no internet | Qwen3-8B class on 16 GB RAM. Weaker reasoning, but nothing leaves your house. |
| **Others** (Mistral, Cloudflare Workers AI, OpenRouter free models) | small free tiers | Useful as automatic fallbacks when one rate-limits. |

**The honest catch with "free":** free tiers are rate-limited, can change their terms without
notice, and **some providers use free-tier prompts to improve their products.** For a system
that will hold your money, family and health, that must be checked per provider before
anything sensitive is routed to it — which is exactly why §9.6 routes sensitive ministries to
the local PC brain instead.

**And this is why the router exists.** Not to be clever — so that "free" never means "broken":
when Groq rate-limits at 30/min, it falls to another free provider, then to your PC, without
you ever seeing it. **From your side it is one AI. Always.** You never pick a model, never see
a name, never know which one answered.

```
        YOU  ──►  one Telegram chat  ──►  "the Vizier"
                                             │
                    ┌────────────────────────┼────────────────────────┐
                    ▼                        ▼                        ▼
              free brain #1            your PC (private)         YOUR MEMORY
              → #2 → #3                Ollama, offline           + YOUR HANDS
              (invisible)                                        ← the actual product
```

---

## 0.6 THE REAL TARGET: "something like you" — an agent, not a chatbot

> Your words: *"I need to build something like you. I'm very comfortable with you and
> everything I do I just tell you and you do everything and build everything."*
>
> **This is now the spec.** Sections 0.5 and 1 are still true but they answered a smaller
> question. Everything below supersedes the roadmap in §11.

### What I actually am, mechanically — no mystery

There is nothing magic here, and you should know the parts because they are the parts you're
buying or building:

| Layer | What it is | Can you have it? |
|---|---|---|
| **1. The harness** | A loop: model gets a task → calls a tool (read file, edit file, run a command, grep, search the web) → sees the result → calls another → repeats until done. Plus context management and sub-agents. | ✅ **Free and mature.** Don't build it. |
| **2. The brain** | A strong model that doesn't lose the plot four tool calls into a debugging loop. | ✅ **Now genuinely achievable** — see below. This changed in 2026. |
| **3. The body** | A workspace with your files, git, credentials, and rules — plus steering files and memory so it knows *your* project. | 🔨 **This is what we build.** Nothing on the market does it for your life. |

That's it. A model, a tool loop, and a workspace. The reason it *feels* like more is layer 3 —
and layer 3 is the part that's specifically yours.

### Layer 1: the harness is free, mature, and huge (checked 2026-08-31)

You do not write this. Several open-source agents already do exactly what I do, are
MIT/Apache licensed, are **model-agnostic**, and **run local models via Ollama**:

| Harness | Scale | Character |
|---|---|---|
| **OpenCode** | ~165–172k stars, MIT | most popular; built so the model is a *replaceable component*, not the identity |
| **OpenHands** | self-hostable | designed for delegating a whole ticket asynchronously — closest to "just do it" |
| **Goose** | local-first, MCP-driven | good fit for private/offline work |
| **Aider** | ~46k stars, Apache-2.0 | terminal + git pair programming, very mature |
| **Cline / Gemini CLI / Codex CLI** | 63k / 105k / 90k | IDE-bound or vendor-bound |

**Adopting one of these instead of writing a harness saves months and is strictly better than
anything we would write.** Recommendation: OpenCode or OpenHands as the engine.

### Layer 2: the brain — the honest picture, and it's good news

Twelve months ago the answer was "you can't have this for free." That is no longer true.
**Open-weight models have reached the top of the coding leaderboards** — as of the numbers
published this month, DeepSeek V4 Pro scores ~96% on SWE-bench Verified (second overall,
within a point of the closed leader) and Kimi K3 ~93%, both **ahead of several closed
frontier models**. They're open weights, so multiple providers serve them cheaply or free.

**But read the fine print, because it decides your architecture:**

| | SWE-bench Verified | Where it runs | Cost to you |
|---|:--:|---|---|
| Best open-weight (DeepSeek V4 Pro / Kimi K3 class) | **93–96%** | someone's datacentre — **too big for your PC** | free tier or pennies/task |
| Best you can self-host on consumer hardware | **~60–72%** | your Windows PC, offline, private | $0 |
| Closed frontier | ~80–95% | vendor API | $$ |

So: **near-frontier is free-ish via an API. Fully local is a real step down.** Which means
the router in §2 isn't architectural vanity — it's the thing that lets one assistant be both
*strong* and *private* depending on the task.

**Two honest caveats:**
1. **Benchmarks are gamed.** Scores went from ~20% to 80%+ in eighteen months, and much of
   that is the benchmark, not the capability. 93% on SWE-bench is *not* the same as good
   judgment on `empire-nexus`. Expect a real gap on hard architectural work.
2. **Agent loops are token-hungry** — many calls, large contexts. The binding constraint on
   a free tier is tokens-per-minute, not requests. Plan for occasional throttling and a
   fallback chain.

### The thing that actually makes me useful in *your* repos — and it's free

This is the most important paragraph in this document.

I'm not effective in your codebase because of raw intelligence. I'm effective because of
**your scaffolding**: `empire-chronicle` tells me the state of the world, your steering files
tell me never to push to `main`, your learnings tell me `gh pr create` fails here, your gates
(`npm run wrappers`, `verify_clip_id_parity.py`, `coverage_ledger`, 2,571 tests) mean a wrong
guess gets caught instead of shipped.

**A weaker model with excellent context and hard verification beats a stronger model with
neither.** You have already built the part almost nobody has. That is why "something like me"
is realistic for you specifically, on a free-ish brain, when it wouldn't be for most people.

The corollary is a rule for the build: **every hand this agent grows must have a check that
can catch it.** Your own most-repeated lesson — a green suite is not evidence, four pages
404'd with every gate green — is the design constraint, not a slogan.

### ⚠️ The danger this version introduces, stated plainly

An agent with shell access to `77.42.43.250` can destroy your business in one command. 17
students, 25 services, one box, no redundancy. Your own standing rules exist because of near
misses: never overwrite `authorized_keys`, never expose 5678, never run destructive git on
the VPS.

So, non-negotiable from the first commit:

- It runs **in a container**, never as root on the host.
- **Code changes are PR-only.** It may never push to `main` — the same rule you already hold
  yourself to.
- Server commands are **allowlisted**; anything not on the list needs your press.
- `authorized_keys`, secrets, and the firewall are in the **BLACK** class — structurally
  unreachable, not merely discouraged.
- Every command it runs is logged with its reason, and `/halt` kills it instantly.
- It gets its **own** SSH key and its own GitHub token, so its access can be revoked without
  touching yours.

### Revised roadmap — this supersedes §11

| Phase | What you get | Size |
|:--:|---|:--:|
| **1** | **You talk to it in Telegram and it does real work.** An existing harness (OpenCode/OpenHands) running headless in a container on Hetzner + a Telegram front-end + your repos cloned + branch/commit/PR only. Free brain, fallback chain. → *"Fix the typo in the dojo README and open a PR"* works from your phone. | ~1 wk |
| **2** | **It knows your world.** The Spine (§7) + your steering/chronicle wired in as its permanent context. It stops needing to be told what Empire English is. | ~1 wk |
| **3** | **Voice.** Whisper in, Kokoro out (already running). Talk to it while driving. | ~3 d |
| **4** | **Hands beyond code.** Allowlisted server ops, n8n triggers, Discord/EEC reads, your Windows PC via `macal-overseer`. All at L1 (draft/propose) first. | ~1.5 wk |
| **5** | **It speaks first.** Heartbeat, morning brief at your learned hour, one inbox, alerts. | ~1 wk |
| **6** | **It earns autonomy.** Trust ladder (§6), per-ministry levels, weekly self-audit. | ~1 wk |
| **7+** | Private/offline brain via Ollama, dead man's switch, remaining ministries. | ongoing |

Phase 1 is the whole point: **by the end of week one you tell it something from your phone in
Cairo and a PR appears.** Everything after that is widening what it can touch.

---

## 0.7 Limits — what it will and won't do

You asked directly: *"will this do everything for me or there will be limitations?"*
There will be limitations. Here they are, sorted by whether they ever go away.

### A. Permanent walls — these never move

| Wall | Why | What it can still do |
|---|---|---|
| **The physical world** | It has no body. | Order, book, prepare, remind, draft — but recording a lesson, driving, being in a room, fixing hardware is you. |
| **Your legal identity** | Signatures, KYC, taxes, passport, bank verification, 2FA codes. | Prepare 95% and hand you the last step. |
| **Judgment about people** | Whether Mai deserves a refund, whether a student is lying, whether your mother is upset. It has no taste for relationships. **Your own bot DM'd a 43-day-streak student that she was inactive — and it was right by its own logic.** | Surface the evidence, draft the message, never decide the relationship. |
| **Taste and direction** | It cannot decide what Empire English *should be*. Your call that "Stage 0 stays grandfathered — a content decision, not a lint fix" is exactly this category, as are the 16 distorted teaching spellings that need content judgment. | Execute your taste consistently once you've set it. |
| **Wanting things** | It has no ambition. It will not chase your goals when you go quiet unless you told it to and built the mechanism. | Hold you to what *you* said (the Mirror, §8.2). |
| **Money, autonomously** | Your standing rule, and it does not get an exception. | Prepare, verify, queue — you press. |

### B. Policy walls — not technical, but just as hard

- **WhatsApp** — no legal personal API. Unofficial libraries get numbers banned, and yours is a business number.
- **Egyptian banks** — no APIs. Realistic path is parsing SMS/email, fragile and highly sensitive.
- **CAPTCHA / anti-bot surfaces** — including Cloudflare's own, which already 403'd your `audio-smoke` workflow for having no browser User-Agent.
- **Social platform automation** (Instagram/TikTok) — account-ban risk.
- **Providers you don't control** — free-tier terms change, models get deprecated, and **Google already 403-denied your Gemini project once.** Design assumes any provider can vanish.

### C. Real weaknesses that shrink over time

| Weakness | Today | Shrinks because |
|---|---|---|
| Long, novel, ambiguous work | "Grow my business" → plausible nonsense. Agents drift on multi-hour open-ended tasks. | You decompose into ministries + verifiable tasks. This is the **single biggest practical limit** and the reason for §4. |
| Architectural judgment | Noticeably weaker than a frontier model at "rethink this from first principles." | The model is one config line. Every upgrade is free. |
| Confidently wrong | It will be. Guaranteed. | Gates, PR-only, audit log, reversibility. Not hope — mechanism. |
| Blind where it has no sensor | Can't know you slept badly, or that a student is struggling emotionally, from submission counts. | Add a sensor, or accept the blind spot knowingly. |
| Needs internet for the strong brain | Power cuts, PC off. | Local fallback (weaker), offline capture always works. |

### D. The meta-limit — and it's the encouraging one

**It will be exactly as good as the context and the checks you give it.** That's not a wall,
it's a dial — and you are already further along that dial than almost anyone, because
`empire-chronicle`, your steering files, and your 2,571-test suite exist. Most of the limits
in section C are investments, not fates.

### The honest summary

> **It will not do everything. It will do almost everything that is boring, and nothing that
> is you.**

Realistically: most of the *hours* you currently spend on execution and nearly all of the
*remembering*. What's left is taste, relationships, decisions, and presence — which is the
part you shouldn't want to give away.

---

## 1. The first reframe: you do not want a model

"AI model" is the wrong unit of construction, for three reasons:

1. **Models expire.** The best open model today is mediocre in nine months. If your
   assistant *is* a model, your assistant expires. If your assistant *has* a model,
   you upgrade one line of config.
2. **Training your own is a trap.** Fine-tuning a model on "you" requires thousands of
   labelled examples of your own decisions, costs real GPU money, produces something worse
   at reasoning than a free API, must be redone every time the base model improves, and
   solves a problem you don't have. Your assistant doesn't need to *be* you — it needs to
   **know** you. Knowing is memory, not weights. *(A persona fine-tune is a legitimate
   Phase 9 luxury. It is not the product.)*
3. **The valuable part is the boring part.** Ten years from now, the thing you would cry
   about losing is not the model. It's the memory: every decision, every person, every
   password location, every commitment, every "we tried that and it failed because…".

So the asset list, in order of value:

| Rank | Asset | Replaceable? |
|:--:|---|---|
| 1 | **Your memory** (facts, people, decisions, history, preferences) | ❌ Never. Irreplaceable. |
| 2 | **Your connectors** (the wiring into Telegram, Google, GitHub, the server, the bots) | 😐 Painful. Weeks. |
| 3 | **Your permission rules + audit trail** (what it may do, what it did) | 😐 Painful, and dangerous to lose. |
| 4 | **Your interfaces** (Telegram, phone, PC, voice) | 🙂 Days. |
| 5 | **The model** | ✅ One config line. Swap monthly. |

Everything in this blueprint follows from that table. We build 1 → 4 carefully, and treat
5 as a commodity.

---

## 2. The anatomy — seven organs

This is the mental picture I want you to hold. Not "a chatbot". A body.

```
                              ┌──────────────────┐
                              │   ⑦ HEARTBEAT    │  speaks first, unprompted
                              │  proactive loop  │  morning brief · nudges · alarms
                              └────────┬─────────┘
                                       │
   ⑤ DOORS (how you reach it)          ▼          ③ SENSES (how it reaches the world)
  ┌─────────────────────┐      ┌───────────────┐      ┌──────────────────────────┐
  │ Telegram (primary)  │◄────►│               │◄────►│ Calendar · Email         │
  │ Phone / PC / Web    │      │  ② THE BRAIN  │      │ Discord (EEC) · GitHub   │
  │ Voice note (both    │      │   swappable   │      │ Server health · n8n      │
  │   directions)       │      │   3-tier      │      │ Bank SMS · News · Files  │
  │ Discord · Watch     │      │   router      │      │ Screenshots · Location   │
  └─────────────────────┘      └───┬───────┬───┘      └──────────────────────────┘
                                   │       │
                    ┌──────────────┘       └───────────────┐
                    ▼                                      ▼
        ┌───────────────────────┐              ┌────────────────────────┐
        │   ① THE SPINE         │              │   ④ HANDS              │
        │   MEMORY              │              │   effectors            │
        │ ─────────────────────  │              │ ──────────────────────  │
        │ facts · people        │              │ send · draft · schedule│
        │ decisions · journal   │              │ file ops (Windows PC)  │
        │ commitments · assets  │              │ shell · git · PRs      │
        │ plain text + SQLite   │              │ n8n workflows · browser│
        │ in a git repo YOU own │              │ post · pay (NEVER auto)│
        └───────────────────────┘              └───────────┬────────────┘
                                                           │
                                               ┌───────────▼────────────┐
                                               │  ⑥ THE CONSCIENCE      │
                                               │  permission guard      │
                                               │  approval gates        │
                                               │  audit log · kill switch│
                                               │  NOTHING passes un-logged│
                                               └────────────────────────┘
```

**Organ by organ:**

| # | Organ | What it is | Where it lives |
|:-:|---|---|---|
| ① | **Spine — Memory** | Plain-text + SQLite life-record in a private git repo. Human-readable *and* machine-readable. Survives every model, vendor and rewrite. | Hetzner + git + encrypted backup |
| ② | **Brain** | A 3-tier router: reflex (tiny/local) → thinking (fast cloud) → deep (best available). Model names live in config, never in code. | Cloud API + your Windows PC |
| ③ | **Senses** | Read-only ingesters. Each one is independently switchable and independently credentialed. | Hetzner (n8n does much of this already) |
| ④ | **Hands** | Effectors, each declaring its blast radius. `macal-overseer` becomes the *Windows hand*. | Hetzner + PC daemon |
| ⑤ | **Doors** | Telegram first, everything else later. See §5 — this is the biggest time-saver in the document. | Anywhere on earth |
| ⑥ | **Conscience** | Permission classes, approval gates, full audit journal, one kill switch. Built in **Phase 1**, not Phase 7. | Wraps every hand |
| ⑦ | **Heartbeat** | The scheduled proactive loop. This is the entire difference between a chatbot and an assistant. | Hetzner cron/n8n |

---

## 3. The reveal: you are ~60% built already

I audited your ecosystem before writing this. You are not starting from zero — you are
starting from an unusually strong position, and one piece of it is genuinely remarkable.

### 3.1 Already live, already paid for

| Asset | State | Reuse as |
|---|---|---|
| Hetzner CX23 + Cloudflare Named Tunnel | live, ~$7/mo, 25+ services | **the switchboard** (⑤ + ③ + ⑦) |
| n8n (pinned 2.26.8) + n8n-MCP | live, 8+ workflows | **half of Senses and Hands, already** |
| Kokoro TTS (`POST /v1/audio/speech`) | live on :8880, shared by 3 repos | **the voice out** — zero new work |
| Telegram bots + `ADMIN_CHAT_ID` + ops hub (Markaz) | live, you already run `/status`, `/flag` | **the primary door** |
| html2img Puppeteer service (:3200) | live | **visual briefs / posters / dashboards as images** |
| Feature-flag registry + kill switch + fail-closed discipline | mature, 51 flags, tested | **the Conscience's on/off layer, already designed** |
| `empire-chronicle` memory protocol (STATUS / SYSTEM-MAP / CONTINUITY) | mature, battle-tested | **the Spine's format — see §7** |
| `empire-agora/src/commerce/pricing.ts` | prices are *code*, CI-gated | assistant can answer money questions **without inventing** |
| `macal-overseer` | Phase 0 scaffold: daemon, Ollama client, tool registry, permission guard (GREEN/YELLOW/RED/BLACK), file ops, audit DB | **the Windows hand** (④), not a rival project |

### 3.2 The find: you already built a cognitive core, and then deleted it

In July you built **"Aql"** (العقل) — a full RAG + tool-calling + guardrails + memory
engine for Nour — across PRs #209–#218 in `empire-nexus`. Then on **2026-07-24** commit
`6d421edd` removed it as dormant dead code (~12,500 lines, correctly, since it was OFF in
production and slowing CI).

**It is not lost.** It is intact at commit `373c560c`, one commit before the removal.
Verified today via the GitHub API:

```
bots/discord-learning-bot/src/nour/
├── orchestrator.py         25,873 B   bounded orchestrator, max-3-tool-call limit
│                                      is STRUCTURAL (no tool schema on final turn)
├── guardrails.py           11,251 B   script conformance · bidi · role-leak · retry
│                                      → template fallback
├── permissions.py           5,396 B   role boundary
├── roles.py                 2,569 B   role resolver
├── shadow.py                5,575 B   shadow mode (run without delivering)
├── knowledge/{chunker,embedder,retriever}.py     SQLite + numpy retrieval, no vector DB
└── tools/{dispatcher,owner_tools,student_tools}.py
   plus  data/nour_eval/{golden_set_owner,golden_set_student,red_team_set}.json
   plus  .kiro/specs/nour-intelligence-core/{requirements,design,tasks}.md
   plus  scripts/embed_knowledge.py
```

Reported at the time: **717 tests**, a 200-iteration stress test producing zero
non-conformant deliveries, and owner-only knowledge domains where the flag-registry doc is
machine-generated so it cannot drift.

**Read what that inventory actually is.** A role-scoped retrieval brain with a bounded
tool-calling orchestrator, output guardrails, red-team set, shadow mode, and owner-only
knowledge. That is not a student chatbot. **That is a personal assistant.** It died because
it was built in the wrong house — a learning bot for 17 students does not need an
owner-scoped RAG brain with a deployment runbook in its knowledge base. **This repo is the
right house.**

> ⚠️ **Epistemic warning, per your own standing rule.** Every figure in §3.2 except the
> file sizes and the two commit SHAs is a **claim copied from `empire-chronicle`**, and
> your own chronicle documents that its counts have been 507 tests stale. Before Phase 3
> depends on this code, we resurrect it into a branch and **re-run its suite**, and I paste
> the command and the real number. It may need real work to run standalone. The claim
> "717 tests" is not evidence; a green run is.

### 3.3 So the honest framing

This is **not a new build**. It is:

> an **assembly** of things you already own, plus **one genuinely new thing** — the Spine
> (§7) — plus **one resurrection** (§3.2).

That is why I think a talking, useful v1 is weeks away rather than months. And it is why
the riskiest thing we could do is start writing new code before deciding what to reuse.

---

## 4. "All my life aspects" → eight ministries

"Everything" cannot be built, scheduled, tested or reviewed. **Eight named things can.**
Your whole ecosystem is themed as an empire, so the assistant is the **Vizier**, and life
is divided into **ministries** (دواوين). This is the single biggest enhancement I want to
make to your idea: it converts an infinite ask into a finite, countable, switchable one.

Each ministry has exactly four properties: a **memory namespace**, a **tool set**, an
**autonomy level** (§6), and **one line in the daily brief**.

**The rule that decides how much each ministry actually helps: it can only help with what it
can SEE.** A ministry whose data is already digital and reachable is strong on day one. A
ministry that lives in your head or on paper is weak until you give it a sensor. So each
ministry below carries an honest strength rating and the price of admission.

| # | Ministry | Owns | Needs from you | Strength |
|:-:|---|---|---|:--:|
| 1 | **Machine** ديوان الآلة | your repos, servers, backups, secrets, this assistant itself | nothing — SSH + GitHub, already yours | ⭐⭐⭐⭐⭐ |
| 2 | **Empire** ديوان الإمبراطورية | students, content, PRs, incidents, the bot, the sites | nothing — the DB, Discord and repos already exist | ⭐⭐⭐⭐⭐ |
| 3 | **Time** ديوان الوقت | calendar, deadlines, routines, prayer times, travel | Google OAuth, ~10 min | ⭐⭐⭐⭐ |
| 4 | **Mind** ديوان العقل | ideas, reading, learning, journaling, capture | the habit of one voice note | ⭐⭐⭐⭐ |
| 5 | **Home** ديوان البيت | bills, documents, IDs, warranties, car, renewals | one hour dumping dates and documents, once | ⭐⭐⭐⭐ |
| 6 | **People** ديوان الناس | family, friends, students-as-humans, who you owe a reply | tell it once who matters and how often | ⭐⭐⭐ |
| 7 | **Treasury** ديوان المال | income, EGP/USD, subscriptions, invoices, the $7 ceiling | manual entry — **no Egyptian bank API** | ⭐⭐ |
| 8 | **Body** ديوان البدن | sleep, food, water, movement, meds, energy | a watch/band, or you tell it — otherwise blind | ⭐⭐ |

Examples of what each actually says to you:

- **Machine** — "Backup last succeeded 9 days ago. It's been silently failing, not loudly."
- **Empire** — "Hadeer is silent 3 days; her own rhythm says that's abnormal. Draft ready."
- **Time** — "3 free hours before the 6pm call. The Stage 3 outline needs 2."
- **Mind** — "You've had this same idea three times in six weeks. Want it as a spec?"
- **Home** — "Passport expires in 7 months. Visa applications need 6."
- **People** — "Your mother's call is unreturned since Tuesday. Three student DMs unanswered."
- **Treasury** — "Hetzner renews in 4 days. Two subscriptions untouched in 60 days = $23/mo."
- **Body** — "Under 6h sleep four nights running. Every bug you shipped this month followed a short night."

**Read the pattern:** the two ministries where it is strongest are the two where your whole
life is already machine-readable — and they happen to be where most of your hours go. The two
weakest are weak for structural reasons (no bank API, no sensor), not because the assistant is
lacking, and both can be upgraded later by adding a sensor rather than rebuilding anything.

**Why this matters more than it looks:** it makes the system *auditable*. At any moment you
can ask "which ministries are actually earning their keep?" and switch one off. An
assistant that covers "everything" can never be evaluated, and therefore can never be
trusted or trimmed.

**Anti-scope rule:** we ship **one** ministry at a time, end to end, and it must survive a
week of real use before the next one opens. Eight half-ministries is a dead project.
My recommended order: **Machine → Empire → Time → Mind → People → Treasury → Body → Home.**
(Machine first because it's the one where you can verify every claim it makes; it's the
training ground for trust.)

---

## 5. "From phone or PC, anywhere in the world" → don't build an app

Here is the highest-leverage decision in this document.

The instinct is: *build a mobile app + a desktop app + a web dashboard.* That's three
codebases, app-store accounts, push-notification infrastructure, auth, and months of work
before you can say hello to it.

**You already have a client on every device you own: Telegram.**

| Requirement | Telegram gives you | Custom app costs |
|---|---|---|
| Phone | ✅ native iOS/Android | months + store review |
| PC | ✅ native desktop + web | more months |
| Anywhere in the world | ✅ works on bad Egyptian mobile data, and in China | your problem |
| Voice in | ✅ hold-to-record voice notes | mic permissions, encoding |
| Voice out | ✅ plays audio replies (Kokoro, already live) | audio pipeline |
| Files / photos / documents | ✅ built in | uploads, storage, CDN |
| Buttons / approvals | ✅ inline keyboards — perfect for "Approve / Reject / Later" | UI work |
| Push notifications | ✅ free, reliable, worldwide | FCM/APNs + certs |
| Offline outbox | ✅ Telegram queues your message and sends when you reconnect | you build it |
| History / search | ✅ synced across devices forever | you build it |
| Auth | ✅ your chat ID is your identity | the whole auth stack |
| Cost | **$0** | weeks of your life |

**And you already run Telegram bots on this exact server, with an ops hub, an admin chat
ID, and n8n wired in.** The door is already installed. We just need to put the Vizier
behind it.

```
          YOU, anywhere on earth
                    │
        ┌───────────┴───────────┐
        │ voice note · text ·   │
        │ photo · document ·    │
        │ forwarded message     │
        └───────────┬───────────┘
                    ▼
        ┌───────────────────────┐
        │  Telegram  (the ONE   │  phone · PC · web · watch
        │  door, day one)       │
        └───────────┬───────────┘
                    ▼   Cloudflare Tunnel (already live)
        ┌───────────────────────┐
        │  THE VIZIER           │  Hetzner · always on
        │  memory + router +    │
        │  conscience + heart   │
        └───┬───────────────┬───┘
            ▼               ▼
    cloud brain      your Windows PC
    (thinking/deep)  (Ollama = private/offline brain
                      + hands on your own files)
```

Later, if you outgrow it: a PWA (installable on phone *and* PC from one codebase, no app
store) — and only then, if ever, a native app. Phone-native work is **Phase 7+**, not
Phase 1.

> **Second door worth having early:** a plain phone call is the only interface that works
> while driving with no data. Out of scope for v1, flagged as a real future want.

---

## 6. "Do everything for me" → the trust ladder

Taken literally, this is the most dangerous sentence in your request. An assistant with
your credentials, your money, your students and your reputation, acting without gates, will
eventually send one message that costs you a customer or a family relationship. Your own
history proves the shape of this risk: the learning bot **DM'd your best student that she
was inactive on a 43-day streak**, and it was *right by its own logic*.

So we don't build obedience. We build **earned autonomy**, per ministry, per task type:

```
 L0  OBSERVE      it watches and tells you.                    ← everything starts here
      │           "Hadeer hasn't submitted in 3 days."
      ▼
 L1  DRAFT        it prepares; you press send.
      │           "Here's the DM. [Send] [Edit] [Discard]"
      ▼
 L2  ACT + REPORT it does it, then tells you within the hour.
      │           "Sent Hadeer the nudge. Here's what I said."
      ▼
 L3  ACT SILENT   it just does it. Weekly summary only.
                  Only ever for: reversible · cheap · boring.
```

**The mechanism that makes this special — promotion by evidence.**

Every task type keeps a score. When you have approved **N consecutive drafts unchanged**,
the assistant *asks for its own promotion*, with the receipts:

> *"You've approved my last 12 student nudges without editing a word. Promote
> `empire.student_nudge` from L1 to L2? [Yes] [No] [Show me all 12]"*

And demotion is automatic and instant: **one edit, one rejection, or one complaint drops it
a level** and it says so. No silent drift.

**Ceilings that are absolute, written in code, not policy:**

| Never above L1 (always needs your press) | Always blocked outright |
|---|---|
| Spending or receiving money | Deleting anything irreversibly |
| Publishing publicly (your name on it) | Touching secrets/credentials beyond reading a path |
| Promising anything on your behalf | Modifying its own permission rules |
| First message to a person | Disabling its own audit log or kill switch |
| Anything involving a student's standing | Removing an approval gate |

That last row matters: your standing rule is **"never remove a payment approval gate."**
The assistant must be structurally incapable of removing its own gates. Not "configured not
to" — *incapable*, the way Aql's 3-tool-call bound was structural because no tool schema
existed on the final turn.

**Also required from day one, both directions:**
- **Kill switch** — one Telegram word (`/halt`) stops all hands instantly. Already the
  pattern in `macal-overseer`.
- **Staging/simulation mode** — "show me the diff of what you're about to do." Already in
  `agent.yaml` as `security.mode: staging`.
- **Audit journal** — every action, with the reason, queryable in plain language:
  *"why did you do that?"* must always be answerable. Your bot already learned this lesson:
  `nudge_decision()` returns a logged REASON.

---

## 7. The Spine — the only genuinely new thing we build

You have already solved the hardest problem in personal AI, for code, without realising it
generalises. `empire-chronicle` is a **cross-session memory system for an amnesiac
intelligence** — which is exactly what a personal assistant is.

So: **your life gets a chronicle.**

```
macal-memory/                    ← PRIVATE repo, encrypted backup, YOU own it
├── STATUS.md                    small, overwritten. "where I am right now."
├── LIFE-MAP.md                  the durable map: people, assets, accounts,
│                                recurring obligations, standing decisions
├── CONTINUITY.md                append-only journal, archived quarterly
├── DECISIONS/                   one file per real decision + why + what it ruled out
│                                (so it never re-litigates a settled question)
├── ministries/
│   ├── empire.md   time.md   treasury.md   body.md
│   └── mind.md     people.md  home.md      machine.md
└── memory.db                    SQLite: facts · commitments · events · embeddings
                                 (SQLite + numpy retrieval — Aql's proven choice,
                                  no vector DB, no vendor)
```

**Five design rules, each with a reason you already learned the hard way:**

1. **Plain text first, database second.** You must be able to read your own memory in a
   text editor with no software running. A memory you can only access through the assistant
   is a memory the assistant can hold hostage.
2. **Git-versioned.** You can see what it learned, when, and revert a wrong belief. An
   assistant that silently rewrites its beliefs about you is unfalsifiable.
3. **Facts are dated and sourced.** Every fact records *when* and *from where*. Your own
   rule: **counts in docs are claims** — a fact with no source is a rumour, and rumours are
   how your bot decided a 43-day-streak student was inactive.
4. **Derived numbers are never stored.** Store the submissions, compute the streak. Your
   `current_streak` bug — stale because it only recalculated on submit — is exactly this
   mistake, and it silently disabled the nudge for all seven students who needed it.
5. **Nothing gets forgotten silently.** Retention is explicit and logged. If it drops
   something, it says so.

**The Spine is also the exit hatch.** If in two years you want to move to whatever exists
then, you take this folder and walk. That is what makes this a life asset instead of a
subscription.

---

## 8. Out-of-the-box additions — the ideas that make it *yours*

These are not standard features. Each one comes from something specific in *your* system.

### 8.1 Learn when to talk to me — reuse your own algorithm
You already built, for students, a **learned per-person rhythm**: circular-mean of their own
submission hours in UTC, requiring both 24h of silence *and* their own usual slot to have
passed, refusing to assume an hour under 5 observed days. You built that because *"there is
no hour that is late for everyone."*

**Point it at yourself.** The assistant learns *your* rhythm from your own activity and
briefs you when you're actually awake and receptive — not at a hardcoded 07:00. Zero new
research; the code exists and is tested. It even fixes your open Dubai-vs-Egypt timezone
problem for your own notifications by never depending on a timezone at all.

### 8.2 The Mirror — evidence, not memory
Once a week it shows you **what you actually did**, derived from evidence (commits, PRs,
messages sent, submissions, hours) against **what you said you'd do** (your own stated
intentions). No judgement, just the diff.

This is your own epistemics — *"a green test suite is not evidence of correctness"*,
*"re-derive counts, don't quote them"* — applied to your life. You already apply this
standard to your code more rigorously than most companies. You currently do not apply it to
yourself at all.

### 8.3 "Ask me later" that actually comes back
Your chronicle is full of **open items left for the owner** — the timezone decision, the
sign-offs, the 11 scene recordings. They sit in a file nobody re-reads until it's urgent.

The Vizier gets a real deferral primitive: `/later`, `/later 3d`, `/later when I'm at the
PC`, `/later when Stage 3 ships`. It re-raises the question **with the full original
context reattached**, at the moment it becomes actionable. Deferring stops being the same
as forgetting.

### 8.4 Zero-friction capture
The #1 predictor of whether a personal system survives is whether capture is effortless.
One voice note, anywhere, mid-drive, in Arabic → transcribed → routed to the right ministry
→ confirmed in one line. No app to open, no form, no folder to choose. If capture takes
more than five seconds you will stop using this by week three, and everything else in this
document is then wasted.

### 8.5 Bilingual by default, and correct about it
You speak Arabic; your students are Egyptian; your content is bilingual. The assistant
replies in the language you wrote in, and Kokoro speaks English while Arabic stays text.
Critically: it must obey your **existing bidi rule** — never an Arabic line with 2+ embedded
LTR tokens — and run your `bidi_check.py`. You already have a script for this and it already
caught a bidi-correction hint that violated the bidi rule it was teaching.

### 8.6 Founder mode / human mode
Explicit boundaries the assistant *enforces on you*, not just observes: after a set hour it
declines to discuss work unless a real incident is firing, and it can tell the difference
because it monitors the server. You are a solo founder with 17 students; the failure mode
isn't laziness, it's that work eats every hour. An assistant that helps you work more is
half an assistant.

### 8.7 The digital twin, narrowly
It may answer **as you**, but only from sources that cannot lie: prices from
`empire-agora/src/commerce/pricing.ts` (already the CI-gated single source of truth), FAQs
from the curriculum, schedules from your calendar. **Bounded impersonation with a citation
for every claim** — and a hard rule: it never invents a price, a promise, or a date.
This is safe *specifically because* you already made your commercial model code instead of
conversation.

### 8.8 The dead man's switch
If you're unreachable for N days, it escalates on a schedule you set: pause student
suspensions, notify a designated person, flag renewals, hold anything irreversible. You are
a single point of failure for 17 students and 25 services. This costs a day to build and is
the highest-value hour in the project.

### 8.9 Immune-system memory: mistakes are first-class
Your chronicle's real superpower is that it records *why a rule exists* — the attribution
bugs, the audio-pace defect, the four-timezone class of bug. Your archive keeps findings
"because those are the mistakes most likely to return once nobody remembers them."

The Vizier gets a `MISTAKES/` namespace with the same rule, and it is **searched before
acting**, not after failing. When it's about to compare two timestamps as strings, it should
find that it already learned that lesson in August 2026.

### 8.10 It must justify its own existence
A weekly self-audit: for each ministry, what did it save you, what did it cost you in
attention, how many of its messages did you ignore. **Anything you ignored 3 weeks running
gets switched off automatically and says so.** The most likely way this project fails is
not technical — it's that it becomes a second job that generates noise you learn to
ignore, exactly like a check that is red when nothing is wrong.

---

## 9. Hard truths — read this section twice

I would rather lose the project here than in month four.

### 9.1 Your $7 server cannot run this brain
The CX23 is 2 vCPU / 4 GB RAM and already runs ~25 services including Postgres, n8n, three
bots, Kokoro and Puppeteer. **A useful LLM will not fit.** A 7–8B model needs ~6 GB and
would be painfully slow on 2 vCPU besides.

Therefore: **Hetzner is the switchboard, not the brain.** The brain is (a) a cloud API and
(b) Ollama on your Windows PC. This matches `macal-overseer`'s existing architecture
diagram — which was right.

### 9.2 "Offline" means three different things and you must pick
| You might mean | Reality | Answer |
|---|---|---|
| **(a) My phone has no internet** | A phone cannot usefully run a real model. | **Queue-and-sync**: capture always works offline (Telegram queues it), action happens on reconnect. Honest, and enough 95% of the time. |
| **(b) I don't want my life in a cloud API** | Legitimate and serious. | **Ollama on your PC** = private brain. Weaker, but yours. Route sensitive ministries (Body, Treasury, People) locally by policy. |
| **(c) It should help me in my offline life** | This is the real value. | Voice + proactive heartbeat + one door. Nothing to do with offline computing. |

**My read: you mostly mean (c), some (b), and (a) is a nice-to-have.** If I'm wrong, tell
me — it changes the whole architecture.

### 9.3 Your PC is not always on, and Egypt has power cuts
So "brain unavailable" is the **normal case**, not the exception. The router must degrade:
deep → thinking → reflex → *"I've queued this, your PC is off."* A system that only works
when everything is up will feel broken most of the time.

### 9.4 "Link it to everything" — three of them will hurt
- **WhatsApp: there is no legal personal API.** The unofficial libraries get your number
  banned, and yours is a business number. Options: don't link it, or use the paid Business
  API (breaks your $0 rule). **Flagging this now rather than discovering it in month two.**
- **Egyptian banks: no APIs.** Realistic path is parsing transaction SMS/email, which is
  fragile and touches your most sensitive data. Treasury should probably start manual.
- **Google (Calendar/Gmail): fine**, OAuth, real work but standard. Read-only first.

### 9.5 One assistant with every token is one catastrophic secret
Your own history is unambiguous: **5 leaked secrets**, one of which was a *live,
unmonitored, payment-collecting Telegram bot* nobody remembered existed. Now imagine one
credential store holding Google, GitHub, the server, Telegram, and your bank.

Non-negotiables: per-ministry credentials with least privilege · nothing in git, ever ·
env vars or a file outside the repo, referenced by path · full audit of every credential
use · rotation runbook written **before** the first token is issued (you already have
`SECRET-ROTATION-CHECKLIST.md`) · and the assistant may **never** read a secret's value
into a model prompt.

### 9.6 It will know everything about you
Encryption at rest. A written, honest list of **exactly what leaves the box** and to whom.
No third-party analytics, no logging provider, no "helpful" cloud sync. If a cloud brain is
used, sensitive ministries route local-only. And you should be able to ask *"what do you
know about me?"* and get the complete, actual answer.

### 9.7 The cost decision you can't dodge
Your standing constraint is **$7/month total, zero paid dependencies, no usage-capped
SaaS.** A good cloud brain used daily is roughly $5–25/month.

| Option | Cost | Trade-off |
|---|:--:|---|
| Groq free tier (you already use it, already primary) | $0 | rate limits; ToS could change |
| Gemini (dormant fallback — **your project is 403 Google-denied**) | $0 | currently blocked for you |
| Ollama on your PC | $0 | PC must be on; weaker reasoning |
| Paid API, top model | ~$5–25/mo | breaks your rule — **needs an explicit exception from you** |

**My recommendation:** free tiers + local for v1 with the model behind one config line, then
you decide from real usage data whether the best brain is worth breaking the $7 ceiling.
Don't decide now, but *know* you're deciding later.

### 9.8 This must never become a second job
Every hour maintaining it is an hour not teaching. Rule: **if a ministry doesn't earn its
keep in the weekly review, it gets switched off.** See §8.10.

### 9.9 A working demo is not a working system
Your own hardest-won lesson, and it applies here more than anywhere: *"a green test suite is
not evidence of correctness"* — real shipped bugs passed 29 tests and were only caught by
querying the live database. Four pages returned 404 in production while every gate was
green, found only by making a real account and clicking. **This assistant is only verified
by you living with it for a week.** Nothing else counts.

---

## 10. Repo strategy — decide this before any code

Right now you have `macal-ai-model` (empty, zero commits) and `macal-overseer` (Phase 0
scaffold, Windows desktop agent, unfinished since June). **The single most likely way this
project dies is two half-built agents that never meet.**

**Proposal:**

| Repo | Becomes | Runs on |
|---|---|---|
| **`macal-ai-model`** | **The Vizier** — brain router, Spine/memory, conscience, heartbeat, Telegram door. The always-on core. | Hetzner (+ cloud/local brains) |
| **`macal-overseer`** | **The Windows Hand** — one tool provider registered with the Vizier. Its permission guard and file ops are *kept and used*, not rewritten. | Your PC |
| **`macal-memory`** (new, **private**) | **The Spine** — your life record. Separate repo because its privacy rules and backup policy are different from code's. | git + encrypted backup |
| `empire-chronicle` | unchanged: the *work* memory hub. The Vizier **reads** it. | as today |

`macal-overseer` is demoted from "the project" to "an organ" — which is a promotion in
disguise, because as an organ it can actually ship.

---

## 11. Roadmap — talking to it in week one

Bias throughout: **something real and usable at the end of every phase.** No phase whose
deliverable is "infrastructure".

| Phase | Deliverable — what changes for you | Rough size | Proves |
|:--:|---|:--:|---|
| **0** | **This document, argued down to decisions.** A spec in `.kiro/specs/`, no code. | now | we're building the same thing |
| **1** | **You talk to it.** Telegram door + brain router + Spine v1 + audit + kill switch. It remembers you between messages, and forgets nothing silently. | ~1 week | the skeleton stands |
| **2** | **You talk to it *with your voice*.** Whisper in, Kokoro out (already live). Voice note from a car in Cairo → spoken reply. | ~3 days | the door is real anywhere |
| **3** | **It knows you.** Aql resurrected + re-verified, LIFE-MAP ingested, retrieval working. Ministry #1 (**Machine**) live end to end — the one where you can check every claim. | ~1 week | memory beats a chatbot |
| **4** | **It speaks first.** Heartbeat + one inbox + morning brief at *your* learned hour. Senses: server health, GitHub, Discord/EEC, calendar (read-only). | ~1 week | assistant, not tool |
| **5** | **It drafts.** All hands at L1 only: draft DMs, draft PRs, propose file ops via overseer, trigger n8n. Nothing sends without your press. | ~1.5 weeks | useful without risk |
| **6** | **It earns autonomy.** Trust ladder + promotion/demotion + per-ministry levels + weekly self-audit. Ministries 2–3 open. | ~1 week | "do everything" begins, safely |
| **7** | **It survives.** Ollama fallback brain, offline queue, degraded modes, encrypted backups, dead man's switch. | ~1 week | it's infrastructure now |
| **8+** | **It notices things.** Patterns, anomalies, the Mirror, remaining ministries, PWA if wanted. | ongoing | it gets better than you at remembering |

Every phase: its own branch, its own PR, merged only after you say so — your standing rule,
and the way the Aql build was run (ten phases, ten PRs, no phase skipped review).

---

## 12. Anti-goals — what this is deliberately NOT

- ❌ **Not a trained/fine-tuned model.** See §1.
- ❌ **Not a chatbot you visit.** If you have to remember to open it, it failed.
- ❌ **Not a mobile app** (Phase 1–6). See §5.
- ❌ **Not a vector database or a hosted AI platform.** SQLite + numpy, already proven in
  Aql, already the rejected-alternatives list in its own spec.
- ❌ **Not multi-agent.** Aql's spec explicitly rejected multi-agent for a bounded single
  orchestrator, and was right. One brain, many tools.
- ❌ **Not autonomous with money, ever.** Human-in-the-loop for all money is your standing
  rule and it does not get an exception.
- ❌ **Not a replacement for empire-chronicle.** That stays the work memory; this reads it.
- ❌ **Not a second `macal-overseer`.** See §10.
- ❌ **Not something that needs the internet to capture a thought.**
- ❌ **Not a system whose claims you must trust.** Every number it reports must be
  re-derivable, and it must say when it doesn't know.

---

## 13. Decisions I need from you before writing one line

Answer as briefly as you like — even "1a, 2 yes, 3 skip" works. Anything you leave blank, I
will come back and ask rather than assume.

**Architecture**
1. **Repo strategy (§10)** — Vizier here, overseer demoted to the Windows hand, new private
   `macal-memory`? Or all in one repo?
2. **Resurrect Aql (§3.2)** — do I pull `373c560c` into a branch here and re-verify it for
   real? (I'd do this *before* Phase 3 commits to it.)
3. **"Offline" (§9.2)** — which of (a) phone-offline, (b) private/no-cloud, (c) helps my
   offline life matters most? Rank them.

**Money and models**
4. **The $7 ceiling (§9.7)** — free tiers + local only, or may I plan for a paid brain and
   let you decide the exception later from real numbers?
5. **Which brain for v1** — Groq (you already use it, free) / Ollama on your PC / something
   else you already pay for?

**Doors and reach**
6. **Telegram-first (§5)** — agreed, or do you specifically want an app/website even knowing
   the cost? Which Telegram identity — a new dedicated bot, or extend the existing ops hub?
7. **Voice** — is voice essential in Phase 2, or a later luxury? (It's cheap for you:
   Kokoro is already running.)

**Trust and scope**
8. **Trust ladder (§6)** — accepted? Anything you want permanently pinned at L0/L1 that I
   didn't list? Anything you want at L3 immediately?
9. **First ministry (§4)** — I recommend **Machine** (verifiable claims, safe blast radius,
   builds trust). Would you rather start with **Empire** (highest immediate value, but it
   touches real students) or **Time**?
10. **Your PC** — is the Windows 11 machine from `macal-overseer` still the target? Is it on
    most of the day, or off overnight? RAM/GPU? (Decides whether local brain is real.)

**Reach and risk**
11. **What must it link to first?** Rank the top three: Google Calendar · Gmail · GitHub ·
    the Hetzner server · Discord/EEC · Telegram channels · n8n · your files.
12. **WhatsApp (§9.4)** — accept that it's out of scope, or is it a must-have (paid Business
    API, breaks $0)?
13. **Privacy line (§9.6)** — is there anything that must **never** leave your own hardware,
    even to a free API? (Health? Money? Family? Student data?)

**And one about you**
14. What is the **one thing** that, if this assistant did it well, would make you say "this
    was worth it"? I want to build that in Phase 1, even if it's out of order.

---

## 14. Why I think this works

Because it isn't a leap. Every hard part already exists in your own house:

- The **memory protocol** — you invented it (`empire-chronicle`) and it has already survived
  a lost session, a 176 KB rotation with zero lines lost, and parallel-session conflicts.
- The **cognitive core** — you built it (Aql), it's tested, and it's one `git checkout` away.
- The **voice** — running on port 8880, shared by three repos, 9,360 clips deep.
- The **door** — Telegram bots you already operate, with an ops hub and an admin chat.
- The **conscience** — GREEN/YELLOW/RED/BLACK, permission guard, kill switch, staging mode,
  all in `agent.yaml`, plus 51 feature flags that **fail closed**.
- The **proactive timing** — a per-person rhythm learner you built for students, that works
  without knowing anyone's timezone.
- The **discipline** — PR-per-phase, re-derive-don't-quote, verify-in-production,
  record-why-a-rule-exists. Most people building this have none of that and it's why theirs
  become abandoned toys.

The genuinely new work is **the Spine** (§7) and **the trust ladder** (§6). Everything else
is assembly.

---

## 15. Nothing has been done

To be explicit, because you asked:

- ❌ No code written.
- ❌ Nothing committed to `macal-ai-model` (it still has zero commits).
- ❌ No branch pushed, no PR opened, no server touched, no secret read.
- ✅ Read-only reconnaissance only: `empire-chronicle`, `macal-overseer`, and GitHub API
  reads against `empire-nexus` to verify the Aql commit exists.
- ✅ This document, written locally for your review.

**Next step is yours.** Answer §13 — even partially — and I'll turn the approved parts into
a proper spec under `.kiro/specs/` for a second review before any implementation begins.
