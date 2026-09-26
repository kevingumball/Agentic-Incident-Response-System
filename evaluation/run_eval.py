"""Benchmark runner: ReAct baseline vs Planner + Hypothesis + Verifier.

This is the ONLY module that reads evaluation/labels.json.

    python -m evaluation.run_eval --split dev --runs 1           # while tuning
    python -m evaluation.run_eval --split eval --runs 3          # final, held-out
    python -m evaluation.report evaluation/results/<run_dir>     # re-render a summary
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeElapsedColumn

from agent import config
from agent.runner import run_incident
from evaluation.report import render_summary

ROOT = Path(__file__).resolve().parent
LABELS_PATH = ROOT / "labels.json"
RESULTS_DIR = ROOT / "results"

console = Console()


def load_labels() -> dict[str, dict]:
    return json.loads(LABELS_PATH.read_text(encoding="utf-8"))


async def run_benchmark(split: str, runs: int, architectures: list[str], concurrency: int,
                        model: str | None, out_dir: Path) -> list[dict]:
    labels = load_labels()
    cases = sorted(c for c, v in labels.items() if split == "all" or v["split"] == split)
    jobs = [(case, arch, i) for arch in architectures for case in cases for i in range(runs)]
    sem = asyncio.Semaphore(concurrency)
    records: list[dict] = []
    runs_path = out_dir / "runs.jsonl"

    with Progress(TextColumn("{task.description}"), BarColumn(), MofNCompleteColumn(), TimeElapsedColumn(),
                  console=console) as progress:
        task = progress.add_task(f"{split} set", total=len(jobs))

        async def one(case: str, arch: str, repeat: int) -> None:
            async with sem:
                result = await run_incident(case, arch, model=model)
            record = result.to_dict() | {"repeat": repeat}
            records.append(record)
            with runs_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
            mark = "[green]OK[/]" if record["predicted"] == labels[case]["root_cause"] else "[red]X [/]"
            if record["error"]:
                mark = "[yellow]ERR[/]"
            progress.console.print(f"{mark} {arch:8s} {case} r{repeat}: predicted {record['predicted']:22s} "
                                   f"truth {labels[case]['root_cause']:22s} calls={len(record['tool_calls'])}"
                                   + (f" error={record['error']}" if record["error"] else ""))
            progress.advance(task)

        await asyncio.gather(*(one(*job) for job in jobs))
    return records


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=["dev", "eval", "all"], default="dev")
    parser.add_argument("--runs", type=int, default=1, help="repeats per case (robustness)")
    parser.add_argument("--arch", default="react,verifier", help="comma-separated: react,verifier")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--model", default=None)
    args = parser.parse_args()

    architectures = [a.strip() for a in args.arch.split(",") if a.strip()]
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = RESULTS_DIR / f"{args.split}_{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    meta = {"split": args.split, "runs_per_case": args.runs, "architectures": architectures,
            "model": args.model or config.MODEL, "max_steps": config.MAX_STEPS,
            "confidence_threshold": config.CONFIDENCE_THRESHOLD,
            "competitor_threshold": config.COMPETITOR_THRESHOLD, "started": stamp}
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    records = asyncio.run(run_benchmark(args.split, args.runs, architectures, args.concurrency, args.model, out_dir))
    summary = render_summary(records, load_labels(), meta)
    (out_dir / "summary.md").write_text(summary, encoding="utf-8")
    console.print(summary)
    console.print(f"[dim]results written to {out_dir}[/]")


if __name__ == "__main__":
    main()
