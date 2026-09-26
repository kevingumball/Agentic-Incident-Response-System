"""CLI demo: watch the agent investigate one incident step by step.

    python main.py --case case_010                 # Planner + Hypothesis + Verifier (asks for approval)
    python main.py --case case_010 --auto-approve
    python main.py --case case_010 --agent react   # ReAct baseline
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Confirm
from rich.table import Table

from agent.graph import fmt_call
from agent.mcp_client import content_to_text
from agent.runner import auto_approve, run_incident

console = Console()
REPORT_DIR = Path(__file__).parent / "reports"


def _truncate(text: str, n: int = 900) -> str:
    return text if len(text) <= n else text[:n] + "\n..."


def show_event(node: str, update: dict) -> None:
    if node == "triage":
        console.print(Panel(
            f"service: [bold]{update['service']}[/]   severity: [bold]{update['severity']}[/]\n"
            + "\n".join(f"- {s}" for s in update["symptoms"]),
            title="[1] Triage", border_style="cyan"))
    elif node == "planner":
        a = update["next_action"]
        console.print(f"\n[bold magenta]Action[/] {fmt_call(a)}\n[dim]  why: {a['reason']}[/]")
    elif node == "executor":
        console.print(Panel(_truncate(update["last_observation"]), title="Observation", border_style="dim"))
    elif node == "hypothesis" and update:
        for e in update.get("evidence", []):
            tags = []
            if e["supports"]:
                tags.append("[green]+" + ", +".join(e["supports"]) + "[/]")
            if e["contradicts"]:
                tags.append("[red]-" + ", -".join(e["contradicts"]) + "[/]")
            console.print(f"  [yellow]evidence[/] [{e['source']}] {e['observation']} {' '.join(tags)}")
        table = Table(show_header=False, box=None, padding=(0, 2))
        for h in update.get("hypotheses", [])[:4]:
            bar = "#" * int(h["confidence"] * 20)
            table.add_row(f"  {h['label']}", f"{h['confidence']:.2f}", f"[cyan]{bar}[/]")
        console.print(table)
    elif node == "verifier":
        status = update.get("status")
        if status == "diagnosed":
            rc = update["root_cause"]
            console.print(Panel(f"[bold green]{rc['label']}[/]  confidence {rc['confidence']:.2f}\n{update['verifier_feedback']}",
                                title="Verified root cause", border_style="green"))
        elif status == "undetermined":
            console.print(Panel(update.get("verifier_feedback", ""), title="Step budget exhausted", border_style="red"))
        else:
            console.print(f"  [bold red]verifier:[/] not sufficient - {update.get('verifier_feedback', '')}")
    elif node == "remediation":
        r = update["remediation"]
        console.print(Panel(f"[bold]{r['action']}[/] on {r['service']} (risk: {r['risk']})\n"
                            + "\n".join(f"{i}. {s}" for i, s in enumerate(r["steps"], 1)),
                            title="Proposed remediation", border_style="yellow"))
    elif node == "apply_fix":
        console.print(f"[green]{update['fix_result']}[/]")
    # ReAct baseline events
    elif node == "react:agent":
        for msg in update.get("messages", []):
            for tc in getattr(msg, "tool_calls", []):
                console.print(f"\n[bold magenta]Action[/] {fmt_call({'tool': tc['name'], 'args': tc['args']})}")
            if msg.content:
                console.print(f"[dim]{_truncate(str(msg.content), 600)}[/]")
    elif node == "react:tools":
        for msg in update.get("messages", []):
            console.print(Panel(_truncate(content_to_text(msg.content)), title="Observation", border_style="dim"))
    elif node == "react:diagnose":
        d = update["diagnosis"]
        console.print(Panel(f"[bold]{d['root_cause']}[/] confidence {d['confidence']:.2f}\n{d['reasoning']}",
                            title="ReAct diagnosis", border_style="green"))


async def ask_human(request: dict) -> bool:
    console.print("\n[bold yellow]Human approval required[/] - this action changes the (simulated) system.")
    return await asyncio.to_thread(Confirm.ask, "Apply the proposed remediation?", default=False)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Agentic incident response demo")
    parser.add_argument("--case", required=True, help="scenario id, e.g. case_010")
    parser.add_argument("--agent", choices=["verifier", "react"], default="verifier")
    parser.add_argument("--model", default=None)
    parser.add_argument("--auto-approve", action="store_true")
    args = parser.parse_args()

    console.rule(f"[bold]Incident {args.case} - {args.agent}")
    result = await run_incident(
        args.case, args.agent, model=args.model, on_event=show_event,
        approver=auto_approve if args.auto_approve else ask_human,
    )
    if result.error:
        console.print(f"[bold red]Run failed:[/] {result.error}")
        return

    console.rule("Summary")
    console.print(f"diagnosis: [bold]{result.predicted}[/] ({result.confidence:.2f}) | status: {result.status} | "
                  f"tool calls: {len(result.tool_calls)} | tokens: {result.input_tokens}+{result.output_tokens} | "
                  f"cost: ${result.cost_usd or 0:.4f} | {result.seconds}s")
    if args.agent == "verifier" and result.report:
        REPORT_DIR.mkdir(exist_ok=True)
        path = REPORT_DIR / f"{args.case}.md"
        path.write_text(result.report, encoding="utf-8")
        console.print(Markdown(result.report))
        console.print(f"[dim]report saved to {path}[/]")


if __name__ == "__main__":
    asyncio.run(main())
