import argparse
import threading
import time

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.layout import Layout
from rich import box

from arena.graph import build_app
from arena import persistence, phases

console = Console()


# ==========================================================
# Rendering
# ==========================================================

def render_header():
    console.print(
        Panel.fit(
            "[bold cyan]AI DEBATE ARENA[/bold cyan]\n"
            "Evidence-Driven Multi-Agent Debate",
            border_style="cyan",
        )
    )


def render_dashboard(state):
    """
    A single side-by-side dashboard: phase, weighted composite (the score
    that decides the winner), evidence grounding, and activity score for
    both agents at a glance.
    """

    phase_name = state.get("phase") or phases.get_phase(state.get("turn_count", 0))["name"]

    weighted = state.get("weighted_scores", {"elena": 0, "marcus": 0})
    grounding = state.get("grounding_scores", {"elena": 0, "marcus": 0})
    judge = state.get("scores", {"elena": 0, "marcus": 0})
    activity = state.get("momentum_scores", {"elena": 0, "marcus": 0})

    table = Table(
        title=f"Debate Dashboard — Phase: {phase_name} — Turn {state.get('turn_count', 0)}/{state.get('max_turns', 0)}",
        box=box.ROUNDED,
    )

    table.add_column("Metric")
    table.add_column("Elena", style="cyan", justify="right")
    table.add_column("Marcus", style="green", justify="right")

    table.add_row(
        "[bold]Composite Score (decides winner)[/bold]",
        f"[bold]{weighted.get('elena', 0):.1f}[/bold]",
        f"[bold]{weighted.get('marcus', 0):.1f}[/bold]",
    )
    table.add_row("Evidence Grounding %", f"{grounding.get('elena', 0):.0f}%", f"{grounding.get('marcus', 0):.0f}%")
    table.add_row("AI Judge (subjective, /30 per turn)", f"{judge.get('elena', 0):.1f}", f"{judge.get('marcus', 0):.1f}")
    table.add_row("Activity Score (tool use/numbers/verbosity)", f"{activity.get('elena', 0):.1f}", f"{activity.get('marcus', 0):.1f}")

    console.print(table)

    contradictions = state.get("contradictions", [])
    unresolved = [c for c in contradictions if not c.get("resolved")]

    if unresolved:
        console.print(
            f"[yellow]⚠ {len(unresolved)} unresolved contradiction(s) detected "
            f"- moderator can use 'Expose Contradiction'[/yellow]"
        )


def render_evidence(state):
    evidence = state.get("evidence_log", [])

    if not evidence:
        return

    table = Table(title="Sources Used (most recent)", box=box.SIMPLE)
    table.add_column("Agent")
    table.add_column("Turn")
    table.add_column("Title")
    table.add_column("URL")

    for record in evidence[-5:]:
        table.add_row(
            str(record.get("agent", "")),
            str(record.get("turn", "")),
            str(record.get("title", ""))[:40],
            str(record.get("url", ""))[:50],
        )

    console.print(table)


def render_tools(state):

    logs = state.get("tool_log", [])

    if not logs:
        return

    table = Table(
        title="Tool Usage",
        box=box.ROUNDED,
    )

    table.add_column("Agent")
    table.add_column("Tool")
    table.add_column("Arguments")
    table.add_column("Result")

    for log in logs[-5:]:

        table.add_row(
            str(log.agent),
            str(log.tool),
            str(log.args)[:40],
            str(log.result)[:80],
        )

    console.print(table)


def render_summary(state):

    summary = state.get("final_summary")

    if summary is None:
        summary = "No summary available."

    console.print(
        Panel(
            str(summary),
            title="Final Summary",
            border_style="green",
        )
    )


def stream_text(text, delay=0.02):

    for word in text.split():
        console.print(
            word,
            end=" ",
            soft_wrap=True,
        )
        time.sleep(delay)

    console.print()


def invoke_with_timeout(
    app,
    state,
    timeout=60,
):

    result = {}

    error = None

    def worker():

        nonlocal result
        nonlocal error

        try:
            result = app.invoke(state)

        except Exception as e:
            error = e

    thread = threading.Thread(target=worker)

    thread.start()

    thread.join(timeout)

    if thread.is_alive():

        console.print(
            "[red]Invocation timed out.[/red]"
        )

        return state

    if error:
        raise error

    return result


def render_messages(state, since_index=0):

    messages = state.get(
        "messages",
        [],
    )

    for msg in messages[since_index:]:

        speaker = getattr(
            msg,
            "name",
            "Unknown",
        )

        if speaker is None:
            speaker = "Moderator"

        console.print(
            f"[bold cyan]{speaker}[/bold cyan]"
        )

        stream_text(msg.content)

        console.print()


# ==========================================================
# Structured moderator action menu
# ==========================================================

MODERATOR_MENU = {
    "1": ("CONTINUE", None),
    "2": ("CHALLENGE_ELENA", "action"),
    "3": ("CHALLENGE_MARCUS", "action"),
    "4": ("REQUEST_EVIDENCE", "action"),
    "5": ("REQUEST_REBUTTAL", "action"),
    "6": ("ASK_CLARIFICATION", "action"),
    "7": ("EXPOSE_CONTRADICTION", "special"),
    "8": ("END", "special"),
}


def print_moderator_menu():
    console.print(
        "\n[bold]Moderator[/bold] — [1] Continue  [2] Challenge Elena  "
        "[3] Challenge Marcus  [4] Request Evidence  [5] Request Rebuttal  "
        "[6] Ask Clarification  [7] Expose Contradiction  [8] End Debate\n"
        "(or just type a free-form challenge question)"
    )


def prompt_moderator(state):
    print_moderator_menu()
    choice = input("> ").strip()

    if choice in MODERATOR_MENU:
        action, kind = MODERATOR_MENU[choice]

        if kind is None:
            return {"moderator_prompt": ""}

        if action == "END":
            return {"exit_requested": True}

        if action == "EXPOSE_CONTRADICTION":
            unresolved = [c for c in state.get("contradictions", []) if not c.get("resolved")]

            if not unresolved:
                console.print("[yellow]No contradictions detected yet.[/yellow]")
                return prompt_moderator(state)

            latest = unresolved[-1]
            latest["resolved"] = True

            challenge_text = (
                f"{latest['agent'].capitalize()}, your latest claim appears "
                f"inconsistent with what you said earlier "
                f"(\"{latest['conflicting_claim']}\"). {latest['explanation']} "
                f"Please clarify."
            )

            return {
                "moderator_prompt": challenge_text,
                "contradictions": state.get("contradictions", []),
            }

        return {"moderator_action": action}

    # Free-form text (unchanged legacy behavior)
    if choice.lower() in ["exit", "quit"]:
        return {"exit_requested": True}

    return {"moderator_prompt": choice}


# ==========================================================
# Live debate
# ==========================================================

def build_initial_state(topic: str, max_turns: int = None) -> dict:
    return {
        "topic": topic,
        "messages": [],
        "current_speaker": "elena",
        "last_speaker": None,
        "pending_interrupt": None,
        "moderator_prompt": "",
        "moderator_action": "",
        "turn_count": 0,
        "max_turns": max_turns or phases.total_turns(),
        "should_continue": True,
        "scores": {"elena": 0, "marcus": 0},
        "last_score": None,
        "judge_history": [],
        "momentum_scores": {"elena": 0, "marcus": 0},
        "last_momentum": None,
        "momentum_history": [],
        "evidence_log": [],
        "claims_log": [],
        "grounding_scores": {"elena": 0, "marcus": 0},
        "grounding_history": {"elena": [], "marcus": []},
        "last_verification": None,
        "contradictions": [],
        "weighted_scores": {"elena": 0, "marcus": 0},
        "last_weighted": None,
        "phase": "Opening",
        "debate_id": persistence.new_debate_id(),
        "winner": None,
        "winning_margin": None,
        "judge_winner": None,
        "confidence": None,
        "tool_log": [],
        "recent_tools": [],
        "tool_context": None,
        "argument_memory": {"elena": [], "marcus": []},
        "strategy_memory": {"elena": "", "marcus": ""},
        "final_summary": None,
        "exit_requested": False,
    }


def run_debate(state: dict):
    app = build_app()

    while True:

        result = invoke_with_timeout(app, state)

        # Autosave every turn - a crash or Ctrl-C won't lose the transcript.
        persistence.autosave(result.get("debate_id", "unknown"), result)

        console.clear()

        render_header()

        render_dashboard(result)

        render_evidence(result)

        render_tools(result)

        render_messages(result)

        if result.get("final_summary"):
            render_summary(result)
            break

        if result.get("exit_requested"):
            render_summary(result)
            break

        update = prompt_moderator(result)
        result.update(update)

        if result.get("exit_requested"):
            persistence.autosave(result.get("debate_id", "unknown"), result)
            render_summary(result)
            break

        state = result


def main_new_debate():
    render_header()
    topic = input("Enter debate topic: ")
    state = build_initial_state(topic)
    console.print(f"[dim]Debate ID: {state['debate_id']} (autosaved to data/debates/)[/dim]")
    run_debate(state)


# ==========================================================
# Debate history / replay
# ==========================================================

def main_history():
    debates = persistence.list_debates()

    if not debates:
        console.print("[yellow]No saved debates found.[/yellow]")
        return

    table = Table(title="Debate History", box=box.ROUNDED)
    table.add_column("ID")
    table.add_column("Topic")
    table.add_column("Turns")
    table.add_column("Winner")
    table.add_column("Finished")
    table.add_column("Saved At")

    for d in debates:
        table.add_row(
            d["id"],
            (d["topic"] or "")[:40],
            str(d.get("turn_count", "?")),
            str(d.get("winner") or "-"),
            "Yes" if d.get("final_summary") else "No",
            str(d.get("saved_at", ""))[:19],
        )

    console.print(table)
    console.print("\nRun with --replay <ID> to step through a saved debate.")
    console.print("Run with --resume <ID> to continue an unfinished debate.")


def main_replay(debate_id: str):
    data = persistence.load_debate_raw(debate_id)

    render_header()
    console.print(
        Panel.fit(
            f"[bold]Replaying debate:[/bold] {data.get('topic')}\n"
            f"Turns: {data.get('turn_count')} | Winner: {data.get('winner') or 'N/A'}",
            border_style="magenta",
        )
    )

    messages = data.get("messages", [])

    for i, m in enumerate(messages, 1):
        speaker = m.get("name") or "Moderator"
        console.print(f"\n[bold cyan]Turn message {i} — {speaker}[/bold cyan]")
        console.print(m.get("content", ""))
        input("\n[Enter for next] ")

    console.print("\n[bold]Weighted Scores:[/bold]", data.get("weighted_scores"))
    console.print("[bold]Evidence Grounding:[/bold]", data.get("grounding_scores"))

    if data.get("final_summary"):
        console.print(
            Panel(str(data["final_summary"]), title="Final Summary", border_style="green")
        )


def main_resume(debate_id: str):
    state = persistence.load_debate_for_resume(debate_id)

    if state.get("final_summary"):
        console.print("[yellow]This debate has already finished - use --replay instead.[/yellow]")
        return

    state["debate_id"] = debate_id
    console.print(f"[dim]Resuming debate {debate_id} from turn {state.get('turn_count', 0)}[/dim]")
    run_debate(state)


# ==========================================================
# Entry point
# ==========================================================

def main():
    parser = argparse.ArgumentParser(description="AI Debate Arena")
    parser.add_argument("--history", action="store_true", help="List saved debates")
    parser.add_argument("--replay", metavar="ID", help="Replay a finished debate")
    parser.add_argument("--resume", metavar="ID", help="Resume an unfinished debate")
    args = parser.parse_args()

    if args.history:
        main_history()
    elif args.replay:
        main_replay(args.replay)
    elif args.resume:
        main_resume(args.resume)
    else:
        main_new_debate()


if __name__ == "__main__":
    main()
