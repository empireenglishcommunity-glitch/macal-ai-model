# The Vizier — one container, no inbound ports, non-root.
#
# It reaches Telegram by LONG-POLLING, so it needs no published port, no webhook,
# no Cloudflare tunnel ingress rule, and no firewall change. On this
# infrastructure Docker bypasses UFW, which makes an unnecessary published port an
# unnecessary hole in the only real firewall there is.

FROM python:3.12-slim AS base

# Fail fast and log immediately: buffered stdout in a container means the log you
# need is the log still sitting in a buffer when the process dies.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Deliberately NO `ENV TZ`. The container clock stays UTC.
# This ecosystem has a live, dated timezone problem, and three latent
# naive-local-minus-UTC bugs in another service were latent ONLY because its
# container set no TZ — adding one here is a plausible-looking change that would
# activate that whole family of defects. `vizier/clock.py` is UTC-only by design.

WORKDIR /app

# uid:gid must match the `user:` in the compose file and the ownership of the
# mounted data/log directories on the host, or a read-only rootfs turns into a
# permission error at the first audit write.
RUN groupadd --gid 10001 vizier \
 && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin vizier

# Dependencies first, so a source change does not reinstall them.
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

COPY config.yaml ./config.yaml

USER 10001:10001

# No HEALTHCHECK that calls out to Telegram: a health probe that fails when a
# third party is briefly down would restart a perfectly healthy container, and a
# check that goes red on a healthy system teaches you to stop reading the colour.
# Liveness is the process; readiness is the audit log.

ENTRYPOINT ["python", "-m", "vizier.main"]
