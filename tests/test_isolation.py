"""Ground-truth isolation: the agent and tool layer can never see the answers."""

import json
import re
from pathlib import Path

from agent.taxonomy import LABELS

ROOT = Path(__file__).resolve().parents[1]


def test_agent_and_mcp_server_never_reference_labels():
    for pkg in ("agent", "mcp_server"):
        for path in (ROOT / pkg).rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            assert "labels.json" not in text, path
            assert not re.search(r"^\s*(from|import)\s+evaluation", text, re.M), path


def test_scenarios_contain_no_answer_fields():
    forbidden = {"root_cause", "label", "fault", "split", "key_evidence", "variant", "red_herrings"}
    for path in (ROOT / "scenarios").glob("case_*.json"):
        scenario = json.loads(path.read_text(encoding="utf-8"))
        assert not forbidden & set(scenario), path
        # no taxonomy label appears verbatim anywhere in the observable data
        text = path.read_text(encoding="utf-8")
        for label in LABELS:
            assert label not in text, (path, label)


def test_labels_cover_every_scenario_with_dev_eval_split():
    labels = json.loads((ROOT / "evaluation" / "labels.json").read_text(encoding="utf-8"))
    scenarios = {p.stem for p in (ROOT / "scenarios").glob("case_*.json")}
    assert set(labels) == scenarios
    splits = [v["split"] for v in labels.values()]
    assert splits.count("dev") == 8 and splits.count("eval") == 12
    # every root cause appears in the dev set exactly once
    dev_causes = [v["root_cause"] for v in labels.values() if v["split"] == "dev"]
    assert sorted(dev_causes) == sorted(set(LABELS))


def test_v2_suite_is_isolated_and_balanced():
    labels = json.loads((ROOT / "evaluation" / "labels_v2.json").read_text(encoding="utf-8"))
    scenarios = {p.stem: p for p in (ROOT / "scenarios_v2").glob("case_*.json")}
    assert set(labels) == set(scenarios)
    forbidden = {"root_cause", "label", "fault", "split", "tier", "key_evidence", "red_herrings", "missing_data"}
    for case_id, path in scenarios.items():
        text = path.read_text(encoding="utf-8")
        assert not forbidden & set(json.loads(text)), path
        for label in LABELS:
            assert label not in text, (path, label)
    for split, tiers in (("dev", {"medium", "hard"}), ("heldout", {"easy", "medium", "hard"})):
        cases = [v for v in labels.values() if v["split"] == split]
        # every root cause (plus "unknown") appears exactly once per tier
        for tier in tiers:
            causes = sorted(v["root_cause"] for v in cases if v["tier"] == tier)
            assert causes == sorted(LABELS + ["unknown"]), (split, tier)
