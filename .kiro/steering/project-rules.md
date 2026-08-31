# macal-ai-model — steering

Rules for any agent or human working in this repository. Read this before touching anything.

## 1. Read the hub first

`empire-chronicle` is the canonical memory for this ecosystem. At session start read, in
order: its `STATUS.md` in full → `SYSTEM-MAP.md` → `README.md` → **only the newest dated
section** of `SESSION_CONTINUITY.md`. This repo's own docs are secondary.

Then read, in this repo: [`BLUEPRINT.md`](../../BLUEPRINT.md) →
[`.kiro/specs/vizier-core/requirements.md`](../specs/vizier-core/requirements.md) →
`design.md` → `tasks.md`.

## 2. ⚠️ This repository is PUBLIC

Never commit: personal data, memory contents, life records, real names of students, tokens,
keys, chat IDs, or server credentials. Reference secrets by **env-var name or server path
only**. Memory lives in the separate **private** `macal-memory` repository.

A committed secret is a **live incident**: it requires rotation, because removing it from
`HEAD` does not remove it from history.

## 3. Progress: read the status header, not the checkboxes

`tasks.md` opens with a status header. That header is the only trustworthy progress signal.
Checkboxes in this ecosystem have read "0/28, in progress" for work live in production for a
week, and "45/45" for work never deployed. **Update the header before closing any session.**

## 4. A task is done when its verification command has been run

Every task in `tasks.md` carries a `✔ Verify` line. Done means that command was executed and
its **real output** pasted into the PR body. Code that looks right is not done.

## 5. Counts are claims — re-derive them

Never copy a number out of a document into a report. Re-derive it and paste the command you
used. This rule exists because a documented test count here was **507 tests stale**, and
because two shipped initiatives appeared in zero docs while a doc described tables that did
not exist.

## 6. A green suite is not evidence of correctness

Real shipped bugs here passed 29 tests. Four production pages returned 404 while every gate
was green — found only by making a real account and clicking. Phases 1–5 each end with a
**live** gate, not a test run.

Corollaries, all learned the expensive way:
- New tests must be shown **failing on the pre-fix source**; say so in the PR.
- A check that is green because it did not look is worse than no check.
- Never pipe a remote deploy through `tail` — it hides the exit code. Capture it separately
  and check the container's start time.
- Every CI step carries `if: ${{ !cancelled() }}`; otherwise a first failure means later
  checks never ran.
- Never put `[skip ci]` in a commit message. It has suppressed runs three different ways,
  including by a squash merge inheriting a bot commit's message.

## 7. Git and PR workflow

- **Never push to `main`.** Branch + PR for everything, including docs.
- Branches: `component/description`. Commits: `type(scope): description`.
- PRs are created with `gh api repos/{owner}/{repo}/pulls -f title=... -f body=... -f head=...
  -f base=main`. `gh pr create` and other GraphQL-backed `gh pr`/`gh issue` subcommands fail
  in this sandbox — use `gh api` REST endpoints.
- If a module, flag, table or scheduled job changes, update `SYSTEM-MAP.md` in
  `empire-chronicle` **in the same PR**.

## 8. Safety rules that outrank convenience

- The Vizier runs **in a container, non-root**, never on the host.
- **`BLACK` actions are refused unconditionally** and are listed in `requirements.md` R7.2.
- The Vizier may **never** modify its own permission rules, flags, ceilings, or audit log.
- **Never overwrite `/root/.ssh/authorized_keys`** — append with `>>`, keep the owner's
  `empire-n8n` key, and `grep empire-n8n` before disconnecting. Overwriting locks the owner
  out of the box and requires Hetzner Rescue Mode.
- **Never expose port 5678** (n8n) publicly. Containers bind `127.0.0.1` — Docker bypasses
  UFW, so localhost binding *is* the firewall.
- Never run destructive git commands on the VPS without explicit permission.
- Rebuild by **service name** (`docker compose up -d --build macal-vizier`); a bare `--build`
  fails on this box.
- Human-in-the-loop for all money. **Never remove an approval gate.**

## 9. Model names live in config, never in code

Adding a provider must be one adapter plus one config entry. `grep -rniE
'(gpt|claude|llama|qwen|gemini|kimi|deepseek)' src/` must return **0 hits**. The model is the
most replaceable part of this system and the code must not know its name.

## 10. Environment

- **`python3.12`** for tests — 3.9 fails collection on `X|Y` unions.
- Reinstall requirements in a fresh sandbox; SSH keys and API tokens **never** survive
  between sessions. Re-verify rather than assuming.
- Feature flags **fail closed**, and a new flag is registered in the same commit that creates
  it.

## 11. Language and typography

Replies mirror the owner's language (Arabic or English). **Never write an Arabic line
containing 2 or more embedded left-to-right tokens** (bidi). Outbound text passes script
conformance before delivery; a failing message is regenerated once, then falls back to a
template — it is never sent malformed.

## 12. When you do not know, say so

Fabricating a value is the most serious non-safety defect class in this project. "I don't
know" is a correct answer and is present in the golden set as such. State limits plainly
rather than glossing them — including "I could not verify this."
