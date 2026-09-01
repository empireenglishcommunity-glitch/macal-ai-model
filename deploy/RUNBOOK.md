# Deploy runbook — the Vizier

Everything here has been executed against a real build of this image before being
written down. Where a step exists because of a past incident, it says so.

> **Read first:** this box runs the learning bot for real students. Nothing in this
> runbook touches that stack, and nothing here needs a firewall change, a port, or
> a tunnel rule. If a step seems to require one, stop — it is wrong.

---

## 0. Preconditions

- The env file exists: `/opt/macal-vizier/.env`, mode `600`, with all four variables
- You have pressed **Start** on `@macal_ai_assisstant_bot` at least once
  *(a Telegram bot cannot message a user who has never messaged it first — skip this
  and the daily brief can never be delivered, which will look like a bug)*

Verify the env file without printing any secret:

```bash
ls -l /opt/macal-vizier/.env
for v in VIZIER_TELEGRAM_TOKEN VIZIER_TELEGRAM_OWNER_ID VIZIER_GROQ_API_KEY VIZIER_GITHUB_TOKEN; do printf '%s ' "$v"; grep -c "^$v=." /opt/macal-vizier/.env; done
```

Expect `-rw-------` and then `1` on all four lines.

---

## 1. Create the writable directories

The container runs with a **read-only root filesystem**, so these two host
directories are the only places it can write. They must be owned by uid `10001`,
which is the unprivileged user inside the image.

```bash
mkdir -p /opt/macal-vizier/data /opt/macal-vizier/logs
chown -R 10001:10001 /opt/macal-vizier/data /opt/macal-vizier/logs
ls -ld /opt/macal-vizier/data /opt/macal-vizier/logs
```

Get this wrong and the first audit write fails, which — by design — stops the
process rather than letting it act without a record.

---

## 2. Get the code

```bash
cd /opt/macal-vizier
git clone https://github.com/empireenglishcommunity-glitch/macal-ai-model.git app
cd app
git log --oneline -1
```

Public repo, so no credential is needed for the clone.

---

## 3. Build and start — by service name

```bash
cd /opt/macal-vizier/app
docker compose -f deploy/docker-compose.yml up -d --build macal-vizier
echo "exit=$?"
```

**Name the service.** A bare `docker compose up --build` already fails on this box
because of another service's relative build context — and worse, it would rebuild
things you did not intend to touch.

**And never pipe a deploy through `tail`.** It hides the exit code: a rebuild here
once silently did not apply while the old container kept running and the output
looked perfectly fine. Capture the exit code separately, as above, and then confirm
the container is actually new (step 4).

---

## 4. Verify — four checks, in this order

```bash
# a) it is running, and STARTED JUST NOW (proves the rebuild applied)
docker ps --filter name=macal-vizier --format '{{.Status}}  {{.Image}}'

# b) what it thinks is wired — a redacted summary, no secrets
docker logs macal-vizier 2>&1 | head -5

# c) it wrote its own start row to the host volume
tail -3 /opt/macal-vizier/logs/audit.jsonl

# d) it is inside its budget, and the learning bot still has headroom
docker stats --no-stream --format '{{.Name}}  {{.MemUsage}}  {{.CPUPerc}}'
```

**(a)** must show a start time of seconds ago. A rebuild that did not apply looks
identical in every other way.
**(b)** should contain `enabled_tiers` and `polling telegram (long-poll, no inbound
port)`.
**(d)** the Vizier must sit well under **400 MB**. Check the learning bot's number
too — this box is 4 GB total.

### Then the only check that really counts

Open Telegram, message the bot, and get an answer.

```
/status     -> what is actually wired, with numbers derived at that moment
/help       -> the same, in your language
"hello"     -> a real answer from the brain router
```

**Anonymous or scripted checks cannot verify this.** A container that is `Up` and a
log that says `polling` prove only that the process started.

---

## 5. If it will not start

It exits with code `2` and a plain-English reason rather than a traceback. The two
you are most likely to hit:

| Message | Cause | Fix |
|---|---|---|
| `missing required environment variable(s): …` | a variable absent or empty in `.env` | the message names it and gives the `grep -c` to check it without printing it |
| `… produced an EMPTY allowlist. Refusing to start` | `VIZIER_TELEGRAM_OWNER_ID` is set but not a number — usually a typo | set it to your numeric ID from `@userinfobot` |

That second refusal is deliberate. A Vizier that starts while obeying nobody looks
perfectly healthy and is useless; one that obeys everybody would be a disaster.
Refusing is the only honest third option.

**If it starts but never answers**, read the audit log:

```bash
grep poll.error /opt/macal-vizier/logs/audit.jsonl | tail -3
```

A `RED` row saying `TELEGRAM REJECTED THE CREDENTIAL` means the bot token is wrong
or revoked. It will keep retrying at the 60-second ceiling rather than spinning, and
it will not fill the disk with duplicate rows — but it will not recover on its own
either.

---

## 6. Update to a new version

```bash
cd /opt/macal-vizier/app
git pull
docker compose -f deploy/docker-compose.yml up -d --build macal-vizier
echo "exit=$?"
docker ps --filter name=macal-vizier --format '{{.Status}}'
```

Then repeat step 4. **Merged is not deployed**, and a container that is `Up 3 days`
after a "deploy" is a deploy that did not happen.

---

## 7. Stop, restart, remove

```bash
docker compose -f deploy/docker-compose.yml stop macal-vizier
docker compose -f deploy/docker-compose.yml restart macal-vizier
docker compose -f deploy/docker-compose.yml down            # container only
```

`down` removes the container. It does **not** touch `/opt/macal-vizier/data`,
`/opt/macal-vizier/logs`, or `.env` — the audit log and the pending queue survive,
which is the point of keeping them on the host.

A stop takes about **2 seconds**, even mid-backoff: the wait is sliced so a
`SIGTERM` is noticed within a second. It was 29 seconds before that fix, which is
past Docker's 10-second grace period, so it was being `SIGKILL`ed mid-write.

---

## 8. Rollback

The image is tagged `macal-vizier:latest` on each build. Before an update you care
about, keep the previous one:

```bash
docker tag macal-vizier:latest macal-vizier:rollback-$(date +%F)
docker images macal-vizier
```

To roll back, check out the previous commit and rebuild — the image is built from
source, so the commit *is* the version:

```bash
cd /opt/macal-vizier/app
git log --oneline -5
git checkout <previous-sha>
docker compose -f deploy/docker-compose.yml up -d --build macal-vizier
```

---

## 9. What this deployment deliberately does not do

- **No published ports.** Long-polling is outbound only. Publishing a port would
  open a hole in the only real firewall on this host, since Docker bypasses UFW.
- **No webhook, no tunnel ingress rule, no DNS record.**
- **No `HEALTHCHECK` that calls Telegram.** A probe failing because a third party is
  briefly down would restart a healthy container — and a check that goes red on a
  healthy system teaches you to stop reading the colour.
- **No `ENV TZ`.** The container clock stays UTC on purpose. Three latent
  naive-local-minus-UTC bugs in another service on this box were latent *only*
  because its container set no `TZ`; adding one here is a plausible-looking change
  that would activate that whole family of defects.
- **No access to the host, the students' database, or any repository.** Those are
  the Conscience and the hands, tasks 1.4 and Phase 2. Today it can only talk.
