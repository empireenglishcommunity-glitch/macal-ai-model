"""The minimal turn handler: one message in, one answer out.

This is **not** the orchestrator (task 1.7). It has no memory, no retrieval and no
tools. It exists so the door can be verified the only way that counts — the owner
sending a message from his phone and getting a real answer — without waiting five
more tasks for deployment.

Two properties are deliberate and worth keeping when the orchestrator replaces
this:

* **It tells the owner what it cannot do.** The system prompt states outright that
  there is no memory yet, because an assistant that quietly forgets looks broken
  rather than unfinished, and the owner would reasonably assume a bug.
* **It never claims a number it did not derive.** ``/status`` reads the real
  config, the real queue and the real audit log, in that moment. Requirement R10.1
  is a property of the code here, not an instruction in a prompt.
"""

from __future__ import annotations

from vizier.brains.base import BrainRequest, Message
from vizier.clock import to_stamp, utcnow
from vizier.conscience.audit import AuditLog
from vizier.core.queue import PendingQueue
from vizier.core.router import Router
from vizier.door.telegram import InboundMessage

#: Kept short on purpose: every token here is spent on every single turn, and the
#: reflex tier has a 512-token budget.
SYSTEM_PROMPT = """You are the Vizier, a personal assistant for Mahmoud Ashri \
(MACAL / Empire English).

Rules you must not break:
- Answer in the SAME language the user wrote in. Arabic in, Arabic out.
- Never invent a number, a date, a status or a fact. If you do not know, say you do not know.
- Be concise. He reads on a phone.
- You are an early build: you have NO memory of previous messages, no access to his
  files, repositories, server or database, and you cannot perform actions yet.
  If he asks for something needing those, say plainly that it is not built yet
  rather than pretending or guessing.
"""

HELP_EN = """Vizier — early build (task 1.3 + deployment)

/status  what is actually wired up right now
/help    this message

Anything else is answered by the brain router.

Not built yet: memory between messages, tools, repository access, server access,
voice, the daily brief. Those are tasks 1.4-1.7 and Phase 2."""

HELP_AR = """الوزير — إصدار مبكر

/status لعرض ما تم توصيله فعلياً
/help لعرض هذه الرسالة

أي رسالة أخرى يجيب عليها موجّه العقول.

غير مبني بعد: الذاكرة بين الرسائل، الأدوات، الوصول إلى المستودعات والسيرفر،
الصوت، والتقرير اليومي."""


class Conversation:
    """Turns one inbound message into one reply."""

    def __init__(
        self,
        router: Router,
        audit: AuditLog,
        queue: PendingQueue,
        *,
        tier: str = "thinking",
        max_tokens: int = 1024,
    ) -> None:
        self._router = router
        self._audit = audit
        self._queue = queue
        self._tier = tier
        self._max_tokens = max_tokens

    def __call__(self, message: InboundMessage) -> str:
        arabic = message.language == "ar"

        if message.kind != "text":
            # Honest refusal rather than a silent drop. Voice arrives in task 4.2.
            return (
                "لا أستطيع معالجة هذا النوع من الرسائل بعد. النص فقط في الوقت الحالي."
                if arabic
                else f"I cannot handle a {message.kind} message yet — text only for now. "
                "Voice notes arrive in task 4.2."
            )

        command = message.text.strip().lower()
        if command in {"/help", "/start", "help"}:
            return HELP_AR if arabic else HELP_EN
        if command == "/status":
            return self._status()

        result = self._router.ask(
            self._tier,
            BrainRequest(
                messages=[
                    Message(role="system", content=SYSTEM_PROMPT),
                    Message(role="user", content=message.text),
                ],
                max_tokens=self._max_tokens,
            ),
            queue_payload={
                "chat_id": message.chat_id,
                "user_id": message.user_id,
                "text": message.text,
                "language": message.language,
            },
        )

        if result.queued:
            # R11.2: acknowledged, not lost. Say so precisely, so he does not
            # wonder whether to send it again.
            return (
                "كل العقول غير متاحة الآن. رسالتك محفوظة وسأعالجها عند عودة الخدمة."
                if arabic
                else "Every brain is unavailable right now. Your message is saved and will be "
                "processed when one comes back — you do not need to resend it."
            )

        if result.reply is None:
            return (
                "لم أستطع معالجة هذا الطلب. السبب مكتوب في سجل التدقيق."
                if arabic
                else "I could not process that request. The reason is written to the audit log."
            )

        answer = result.reply.text.strip()

        # Only mention the route when it was NOT the requested tier. Reporting it
        # every time is noise that trains him to stop reading; reporting it only on
        # a fallback makes a degraded system visible.
        if result.answered_by != self._tier:
            note = (
                f"\n\n_(answered by the {result.answered_by} brain — {self._tier} was unavailable)_"
            )
            answer += note

        if result.reply.truncated:
            answer += (
                "\n\n_(cut off at the token limit — ask for a shorter answer or a specific part)_"
            )

        return answer

    def _status(self) -> str:
        """Every number here is derived in this moment, never remembered (R10.1)."""
        tiers = self._router.available_tiers
        rows = [f"  {name}" for name in tiers] or ["  (none)"]
        audit_rows = self._audit.read_all()
        refused = sum(1 for row in audit_rows if row.get("action") == "door.inbound.refused")
        return "\n".join(
            [
                "Vizier status — derived now, not cached",
                f"time (UTC):     {to_stamp(utcnow())}",
                "",
                "brain tiers enabled:",
                *rows,
                "",
                f"pending queue:  {self._queue.depth()} item(s)",
                f"audit rows:     {len(audit_rows)}",
                f"refused senders: {refused}",
                "",
                "wired up:       door, allowlist, audit, brain router, fallback, queue",
                "NOT wired yet:  memory (1.5), conscience/halt (1.4), orchestrator (1.7),",
                "                tools + repo access (Phase 2), voice (4.2), daily brief (5.x)",
            ]
        )
