"""Benchmark runner: ReAct baseline vs Planner + Hypothesis + Verifier.

This is the ONLY module (with report.py) that reads the ground-truth label files.

    python -m evaluation.run_eval --split dev --runs 1                       # v1, while tuning
    python -m evaluation.run_eval --split eval --runs 3                      # v1, held-out
    python -m evaluation.run_eval --suite v2 --split dev --arch react,plan_hyp,plan_hyp_rules,verifier
    python -m evaluation.run_eval --suite v2 --split heldout --runs 3        # v2 final
    python -m evaluation.run_eval --resume evaluation/results/<run_dir>      # rerun missing/errored runs
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
from evaluation.metrics import score_run
from evaluation.report import render_summary

ROOT = Path(__file__).resolve().parent
LABEL_FILES = {"v1": ROOT / "labels.json", "v2": ROOT / "labels_v2.json"}
RESULTS_DIR = ROOT / "results"

console = Console()


def load_labels(suite: str = "v1") -> dict[str, dict]:
    return json.loads(LABEL_FILES[suite].read_text(encoding="utf-8"))


QUOTA_ERROR = "insufficient_quota"


async def run_benchmark(suite: str, split: str, runs: int, architectures: list[str], concurrency: int,
                        model: str | None, out_dir: Path, existing: list[dict] | None = None) -> list[dict]:
    """Run every (case, architecture, repeat) job. With `existing` (resume), successful runs are kept
    and only missing or errored jobs are run again."""
    labels = load_labels(suite)
    cases = sorted(c for c, v in labels.items() if split == "all" or v["split"] == split)
    records: list[dict] = [r for r in (existing or []) if not r["error"]]
    done = {(r["case_id"], r["architecture"], r["repeat"]) for r in records}
    jobs = [(case, arch, i) for arch in architectures for case in cases for i in range(runs)
            if (case, arch, i) not in done]
    sem = asyncio.Semaphore(concurrency)
    runs_path = out_dir / "runs.jsonl"
    runs_path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    out_of_credits = asyncio.Event()
    if existing is not None:
        console.print(f"resuming: {len(records)} successful runs kept, {len(jobs)} to run")

    with Progress(TextColumn("{task.description}"), BarColumn(), MofNCompleteColumn(), TimeElapsedColumn(),
                  console=console) as progress:
        task = progress.add_task(f"{suite}/{split}", total=len(jobs))

        async def one(case: str, arch: str, repeat: int) -> None:
            async with sem:
                if out_of_credits.is_set():
                    return  # not recorded: it will run on --resume once credits are added
                result = await run_incident(case, arch, model=model, suite=suite)
            if result.error and QUOTA_ERROR in result.error:
                if not out_of_credits.is_set():
                    progress.console.print("[bold red]API credits exhausted: stopping; rerun with --resume[/]")
                out_of_credits.set()
                return
            record = result.to_dict() | {"repeat": repeat}
            records.append(record)
            with runs_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
            mark = "[green]OK[/]" if score_run(record, labels[case])["correct"] else "[red]X [/]"
            if record["error"]:
                mark = "[yellow]ERR[/]"
            progress.console.print(f"{mark} {arch:14s} {case} r{repeat}: predicted {record['predicted']:22s} "
                                   f"truth {labels[case]['root_cause']:22s} calls={len(record['tool_calls'])}"
                                   + (f" error={record['error']}" if record["error"] else ""))
            progress.advance(task)

        await asyncio.gather(*(one(*job) for job in jobs))
    return records


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", choices=["v1", "v2"], default="v1")
    parser.add_argument("--split", choices=["dev", "eval", "heldout", "all"], default="dev")
    parser.add_argument("--runs", type=int, default=1, help="repeats per case (robustness)")
    parser.add_argument("--arch", default="react,verifier",
                        help="comma-separated: react, plan_hyp, plan_hyp_rules, verifier")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--model", default=None)
    parser.add_argument("--resume", default=None,
                        help="existing results dir: keep its successful runs, rerun missing/errored ones "
                             "with the same settings (other options are taken from its meta.json)")
    args = parser.parse_args()

    existing = None
    if args.resume:
        out_dir = Path(args.resume)
        meta = json.loads((out_dir / "meta.json").read_text(encoding="utf-8"))
        runs_file = out_dir / "runs.jsonl"
        existing = [json.loads(line) for line in runs_file.read_text(encoding="utf-8").splitlines() if line]
        meta.setdefault("resumed", []).append(datetime.now().strftime("%Y%m%d-%H%M%S"))
        suite, split, runs, architectures = meta["suite"], meta["split"], meta["runs_per_case"], meta["architectures"]
        model = None if meta["model"] == config.MODEL else meta["model"]
    else:
        suite, split, runs, model = args.suite, args.split, args.runs, args.model
        architectures = [a.strip() for a in args.arch.split(",") if a.strip()]
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        prefix = "" if suite == "v1" else f"{suite}_"
        out_dir = RESULTS_DIR / f"{prefix}{split}_{stamp}"
        out_dir.mkdir(parents=True, exist_ok=True)
        meta = {"suite": suite, "split": split, "runs_per_case": runs, "architectures": architectures,
                "model": model or config.MODEL, "max_steps": config.MAX_STEPS,
                "confidence_threshold": config.CONFIDENCE_THRESHOLD,
                "competitor_threshold": config.COMPETITOR_THRESHOLD, "started": stamp}
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    records = asyncio.run(run_benchmark(suite, split, runs, architectures, args.concurrency, model, out_dir, existing))
    summary = render_summary(records, load_labels(suite), meta)
    (out_dir / "summary.md").write_text(summary, encoding="utf-8")
    console.print(summary)
    console.print(f"[dim]results written to {out_dir}[/]")


if __name__ == "__main__":
    main()
