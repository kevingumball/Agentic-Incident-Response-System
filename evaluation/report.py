"""Render a markdown summary from runs.jsonl.

    python -m evaluation.report evaluation/results/<run_dir>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from evaluation.metrics import aggregate, confusions, per_root_cause, score_run

ARCH_NAMES = {
    "react": "A. ReAct baseline",
    "plan_hyp": "B. Planner + Hypothesis (no verifier)",
    "plan_hyp_rules": "C. B + hard rules",
    "verifier": "D. C + LLM skeptic (phase-1 system)",
    "plan_hyp_checklist": "E. B + checklist & margin rules",
    "verifier_v2": "F. E + LLM skeptic",
}


def _pct(x: float) -> str:
    return f"{100 * x:.0f}%"


def render_summary(records: list[dict], labels: dict[str, dict], meta: dict) -> str:
    archs = [a for a in meta["architectures"] if any(r["architecture"] == a for r in records)]
    per_arch = {a: [r for r in records if r["architecture"] == a] for a in archs}
    stats = {a: aggregate(per_arch[a], labels) for a in archs}

    out = [f"# Benchmark results (suite {meta.get('suite', 'v1')}, {meta['split']} split)", "",
           f"Model `{meta['model']}` | {meta['runs_per_case']} run(s) per case | "
           f"step budget {meta['max_steps']} tool calls | started {meta['started']}", "",
           "| Architecture | Accuracy | Cases correct in every run | False Diagnosis | Premature Diagnosis "
           "| Unknown | Avg Tool Calls | Avg Tokens | Cost / Case | Avg Time |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for a in archs:
        s = stats[a]
        cost = f"${s['avg_cost_usd']:.4f}" if s["avg_cost_usd"] is not None else "n/a"
        out.append(
            f"| {ARCH_NAMES.get(a, a)} | {s['correct_runs']}/{s['runs']} ({_pct(s['accuracy'])}) "
            f"| {s['cases_always_correct']}/{s['cases']} | {_pct(s['false_diagnosis_rate'])} "
            f"| {_pct(s['premature_diagnosis_rate'])} | {_pct(s['unknown_rate'])} | {s['avg_tool_calls']:.1f} "
            f"| {s['avg_tokens']:,.0f} | {cost} | {s['avg_seconds']:.1f}s |"
        )
    errors = {a: stats[a]["errors"] for a in archs if stats[a]["errors"]}
    if errors:
        out += ["", f"Runs that errored (counted as wrong): {errors}"]

    tiers = sorted({v.get("tier") for v in labels.values() if v.get("tier")}, key=["easy", "medium", "hard"].index)
    if tiers:
        out += ["", "## Accuracy by difficulty tier", "",
                "| Tier | " + " | ".join(ARCH_NAMES.get(a, a) for a in archs) + " |", "|---|" + "---|" * len(archs)]
        for tier in tiers:
            cells = []
            for a in archs:
                rs = [r for r in per_arch[a] if labels[r["case_id"]].get("tier") == tier]
                ok = sum(score_run(r, labels[r["case_id"]])["correct"] for r in rs)
                cells.append(f"{ok}/{len(rs)}" if rs else "-")
            out.append(f"| {tier} | " + " | ".join(cells) + " |")

    out += ["", "## Accuracy by root cause", "",
            "| Root cause | " + " | ".join(ARCH_NAMES.get(a, a) for a in archs) + " |",
            "|---|" + "---|" * len(archs)]
    rc_tables = {a: per_root_cause(per_arch[a], labels) for a in archs}
    for rc in sorted({rc for t in rc_tables.values() for rc in t}):
        cells = [f"{rc_tables[a][rc][0]}/{rc_tables[a][rc][1]}" if rc in rc_tables[a] else "-" for a in archs]
        out.append(f"| {rc} | " + " | ".join(cells) + " |")

    out += ["", "## Misdiagnoses (truth -> predicted)", ""]
    for a in archs:
        conf = confusions(per_arch[a], labels)
        items = ", ".join(f"{t} -> {p} x{n}" for (t, p), n in conf.items()) or "none"
        out.append(f"- **{ARCH_NAMES.get(a, a)}:** {items}")

    out += ["", "Definitions: *False Diagnosis* = wrong label with confidence >= 0.8. "
            "*Premature Diagnosis* = a (non-unknown) diagnosis given before the case's key discriminating "
            "evidence was queried, regardless of correctness. *Unknown* = the run answered 'unknown' (correct only "
            "when the true cause is outside the taxonomy). *Avg Time* is wall-clock under concurrent runs and "
            "includes API rate-limit waits."]
    return "\n".join(out) + "\n"


def main() -> None:
    run_dir = Path(sys.argv[1])
    records = [json.loads(line) for line in (run_dir / "runs.jsonl").read_text(encoding="utf-8").splitlines() if line]
    meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
    label_file = "labels.json" if meta.get("suite", "v1") == "v1" else f"labels_{meta['suite']}.json"
    labels = json.loads((Path(__file__).parent / label_file).read_text(encoding="utf-8"))
    summary = render_summary(records, labels, meta)
    (run_dir / "summary.md").write_text(summary, encoding="utf-8")
    print(summary)


if __name__ == "__main__":
    main()
