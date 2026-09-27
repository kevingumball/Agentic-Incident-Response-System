"""Failure attribution: for every wrong run, find the first node that went wrong.

Uses the per-node trace (phase 2, Step 0) and the per-case key evidence.

Categories
  planner_missed_key_evidence   the run concluded without ever querying the discriminating evidence
  hypothesis_never_ranked_truth key evidence was queried, but the true cause never became the top hypothesis
  hypothesis_drifted_away       the true cause was on top at some step, later evidence pulled it down
  verifier_accepted_wrong       (C/D) the verification stage accepted a wrong top hypothesis
  blocked_correct_by_rules      budget exhausted while the TRUE cause was on top; hard rules kept failing
  blocked_correct_by_skeptic    budget exhausted while the TRUE cause was on top; the skeptic kept rejecting
  budget_exhausted_wrong_top    budget exhausted and the top hypothesis was wrong anyway
  react_misread                 (ReAct) key evidence was queried but the final answer was wrong
  forced_unknown_wrong          answered unknown although the true cause is in the taxonomy (other cases)

    python -m evaluation.attribution evaluation/results/<run_dir>
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from evaluation.metrics import key_evidence_covered
from evaluation.report import ARCH_NAMES


def first_covering_step(tool_calls: list[dict], key_evidence: list[dict]) -> int | None:
    for k in range(1, len(tool_calls) + 1):
        if key_evidence_covered(tool_calls[:k], key_evidence):
            return k
    return None


def top_by_step(trace: list[dict]) -> dict[int, str]:
    """step -> top hypothesis label after the hypothesis node of that step."""
    out = {}
    for e in trace:
        if e.get("node") == "hypothesis" and e.get("hypotheses"):
            out[e["step"]] = e["hypotheses"][0]["label"]
    return out


def last_verifier_feedback(trace: list[dict]) -> str:
    fb = [e.get("feedback", "") for e in trace if e.get("node") == "verifier"]
    return fb[-1] if fb else ""


def attribute(run: dict, label: dict) -> tuple[str, str]:
    """Return (category, explanation) for a wrong run."""
    truth, pred = label["root_cause"], run["predicted"]
    calls, trace = run["tool_calls"], run.get("trace", [])
    covered_at = first_covering_step(calls, label["key_evidence"])

    if run["architecture"] == "react":
        if covered_at is None:
            return "planner_missed_key_evidence", f"never queried key evidence; answered {pred}"
        return "react_misread", f"key evidence queried at step {covered_at}, still answered {pred}"

    tops = top_by_step(trace)
    final_top = tops[max(tops)] if tops else None
    truth_top_steps = sorted(s for s, top in tops.items() if top == truth)

    if pred == "unknown" and run["status"] == "undetermined" and truth != "unknown":
        if final_top == truth:
            fb = last_verifier_feedback(trace)
            if fb.startswith("Reviewer rejected"):
                return "blocked_correct_by_skeptic", f"truth on top at the end; skeptic: {fb[:160]}"
            return "blocked_correct_by_rules", f"truth on top at the end; rules: {fb[:160]}"
        return "budget_exhausted_wrong_top", f"budget exhausted with top={final_top}"

    if covered_at is None:
        return "planner_missed_key_evidence", f"concluded {pred} without key evidence"
    if truth_top_steps:
        return "hypothesis_drifted_away", (f"truth was top at steps {truth_top_steps}, final top {final_top} "
                                           f"(key evidence at step {covered_at})")
    if run["architecture"] in ("plan_hyp_rules", "verifier") and pred != "unknown":
        return "verifier_accepted_wrong", (f"key evidence at step {covered_at}; truth never top; "
                                           f"verifier accepted {pred}")
    return "hypothesis_never_ranked_truth", f"key evidence at step {covered_at}; truth never top; final {pred}"


def render(records: list[dict], labels: dict[str, dict]) -> str:
    by_arch: dict[str, list] = defaultdict(list)
    for r in records:
        label = labels[r["case_id"]]
        if r["predicted"] != label["root_cause"] and not r.get("error"):
            by_arch[r["architecture"]].append((r, label, *attribute(r, label)))

    order = [a for a in ARCH_NAMES if a in {r["architecture"] for r in records}]
    categories = sorted({c for fails in by_arch.values() for _, _, c, _ in fails})
    out = ["# Failure attribution", "", "| Category | " + " | ".join(ARCH_NAMES[a] for a in order) + " |",
           "|---|" + "---|" * len(order)]
    counts = {a: Counter(c for _, _, c, _ in by_arch[a]) for a in order}
    for c in categories:
        out.append(f"| {c} | " + " | ".join(str(counts[a][c] or "") for a in order) + " |")
    out.append("| **total wrong** | " + " | ".join(str(len(by_arch[a])) for a in order) + " |")

    for a in order:
        out += ["", f"## {ARCH_NAMES[a]}", ""]
        for r, label, cat, why in sorted(by_arch[a], key=lambda x: (x[2], x[0]["case_id"])):
            out.append(f"- `{r['case_id']}` ({label.get('tier', '-')}) truth **{label['root_cause']}** -> "
                       f"{r['predicted']} | {cat}: {why}")
    return "\n".join(out) + "\n"


def main() -> None:
    run_dir = Path(sys.argv[1])
    meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
    label_file = "labels.json" if meta.get("suite", "v1") == "v1" else f"labels_{meta['suite']}.json"
    labels = json.loads((Path(__file__).parent / label_file).read_text(encoding="utf-8"))
    records = [json.loads(line) for line in (run_dir / "runs.jsonl").read_text(encoding="utf-8").splitlines() if line]
    text = render(records, labels)
    (run_dir / "attribution.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
