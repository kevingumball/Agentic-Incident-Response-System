import pytest

from mcp_server.backend import ScenarioBackend, summarize_series

TIMES = [f"14:{m:02d}" for m in range(10)]


def test_summarize_detects_step_anomaly_and_onset():
    s = summarize_series([180, 182, 179, 181, 3300, 3310, 3290, 3305, 3300, 3320], TIMES, "ms")
    assert s["status"] == "ANOMALOUS"
    assert s["since"] == "14:04"
    assert s["baseline"] == 180


def test_summarize_ignores_small_noise():
    s = summarize_series([30, 31, 29, 30, 32, 31, 30, 29, 31, 30], TIMES, "%")
    assert s["status"] == "normal"
    assert s["since"] is None


def test_summarize_missing_data_is_anomalous():
    s = summarize_series([3, 3, 3, 3, 3, None, None, None, None, None], TIMES, "count")
    assert s["status"] == "ANOMALOUS"
    assert "no data" in s["change"]


@pytest.fixture(scope="module")
def backend():
    return ScenarioBackend.load("case_001")


def test_unknown_service_lists_known_services(backend):
    out = backend.get_service_metrics("does-not-exist")
    assert "Known services" in out and "checkout" in out


def test_unknown_metric_lists_available(backend):
    assert "Available" in backend.get_service_metrics("checkout", "nope")


def test_log_search_is_keyword_or(backend):
    everything = backend.search_logs("checkout", "")
    health = backend.search_logs("checkout", "health")
    assert "health check ok" in health
    assert everything.count("\n- ") >= health.count("\n- ")


def test_datastore_has_no_trace(backend):
    assert "datastore" in backend.get_trace("orders-db")


def test_apply_fix_is_simulated(backend):
    out = backend.apply_fix("checkout", "PAYMENT_TIMEOUT_MS: 50 -> 3000")
    assert out.startswith("SIMULATED") and backend.applied_fixes


def test_rejects_path_traversal():
    with pytest.raises(ValueError):
        ScenarioBackend.load("../evaluation/labels")
