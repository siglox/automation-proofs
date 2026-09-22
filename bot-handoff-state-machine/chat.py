#!/usr/bin/env python3
"""Talk to the state machine yourself.

This is a terminal REPL, not a bot: you play both the customer and the
human agent, typing commands to switch roles and advance the clock, and
watch the exact same `Conversation` class the tests exercise react in
real time. There is no NLP here - the bot's "brain" is a keyword lookup,
deliberately trivial, because the point of this project is the handoff
logic underneath, not conversational AI.

    python3 chat.py

Type as the customer by default. Say something with "human" or "agent" in
it to trigger an escalation. Switch roles with /agent <name> to answer as
that person, and /tick <minutes> to fast-forward the clock - the idle
re-escalation and reopen-after-close rules only show themselves once time
has actually passed, and nobody wants to wait 15 real minutes to see it.

This file is a thin wrapper: it is not covered by the 18 automated tests
in test_demo.py, and it isn't meant to be - that suite covers Conversation
itself. This just gives it a voice.
"""

from __future__ import annotations

from demo import Conversation, InvalidTransition, State

HELP = """
Commands:
  /agent <name>     speak as this human agent from now on
  /customer         switch back to speaking as the customer
  /claim            (as an agent) claim an escalated conversation
  /close            (as an agent) close the conversation you own
  /tick <minutes>   advance the clock without anyone saying anything
  /state            show the current state
  /log              show every transition so far
  /reset            start a brand new conversation
  /help             this message
  /quit             leave
Anything else you type is sent as a message from whoever you're speaking as.
""".strip()

# A deliberately tiny "bot brain": keyword lookup, not NLP. The point of
# this project is what happens around the bot, not inside it.
TRIGGER_WORDS = ("human", "person", "agent", "representative", "someone real")

CANNED_REPLIES = {
    "hours": "We're open Monday to Friday, 9am to 6pm.",
    "price": "Plans start at $29/month - want the full breakdown?",
    "refund": "Refunds usually take 3-5 business days once approved.",
}
DEFAULT_REPLY = "I'm not sure about that one - you can also ask to talk to a human."


def wants_human(text: str) -> bool:
    lowered = text.lower()
    return any(word in lowered for word in TRIGGER_WORDS)


def bot_reply(text: str) -> str:
    lowered = text.lower()
    for keyword, reply in CANNED_REPLIES.items():
        if keyword in lowered:
            return reply
    return DEFAULT_REPLY


def format_log(conv: Conversation) -> str:
    if not conv.log:
        return "(nothing yet)"
    lines = [f"  [t={e.at:>3}] {e.kind}: {e.detail}" for e in conv.log]
    return "\n".join(lines)


def format_state(conv: Conversation) -> str:
    return (
        f"state={conv.state.value}  assigned_to={conv.assigned_to}  "
        f"unanswered_since={conv.unanswered_since}"
    )


def main() -> None:
    print(__doc__.split("\n\n")[0])
    print()
    print(HELP)
    print()

    conv = Conversation()
    now = 0
    role: str | None = None  # None = customer, otherwise the agent's name

    while True:
        speaker = role or "customer"
        try:
            line = input(f"[t={now}] {speaker}> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not line:
            continue
        now += 1

        if line in ("/quit", "/exit"):
            break
        if line == "/help":
            print(HELP)
            continue
        if line == "/reset":
            conv = Conversation()
            now = 0
            role = None
            print("(new conversation started)")
            continue
        if line == "/state":
            print(format_state(conv))
            continue
        if line == "/log":
            print(format_log(conv))
            continue
        if line == "/customer":
            role = None
            print("(you are now speaking as the customer)")
            continue
        if line.startswith("/agent "):
            role = line[len("/agent ") :].strip()
            print(f"(you are now speaking as agent '{role}')")
            continue

        try:
            if line == "/claim":
                if role is None:
                    print("only an agent can claim - try /agent <name> first")
                    continue
                claimed = conv.human_claim(now, role)
                print("claimed it." if claimed else "too late - someone already owns this.")
                continue

            if line == "/close":
                if role is None:
                    print("only an agent can close - try /agent <name> first")
                    continue
                conv.human_close(now, role)
                print("closed.")
                continue

            if line.startswith("/tick"):
                parts = line.split()
                minutes = int(parts[1]) if len(parts) > 1 else 5
                now += minutes
                fired = conv.check_idle(now)
                if fired:
                    print(
                        f"{minutes} minutes pass with no reply...\n"
                        "  [!] the conversation went idle and re-escalated "
                        "(a customer message was left unanswered)"
                    )
                else:
                    print(f"{minutes} minutes pass. (nothing happens)")
                continue

            # Not a command: an actual message from whoever is speaking.
            if role is None:
                if conv.state == State.BOT and wants_human(line):
                    conv.request_human(now, reason=line)
                    print("bot: Let me get you a human for that - one moment.")
                else:
                    handler = conv.customer_message(now, line)
                    if handler == "bot":
                        print(f"bot: {bot_reply(line)}")
                    elif handler == "queued":
                        print("(queued - a human will see this, the bot stays quiet)")
                    elif handler == "human":
                        print(f"(reopened straight to {conv.assigned_to}, no bot in between)")
            else:
                conv.human_reply(now, role)
                print(f"({role} replied - sent to the customer)")

        except InvalidTransition as e:
            print(f"can't do that right now: {e}")


if __name__ == "__main__":
    main()
