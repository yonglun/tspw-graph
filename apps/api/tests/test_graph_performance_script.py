import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts/check-graph-performance.py"


def load_script():
    spec = importlib.util.spec_from_file_location("check_graph_performance", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_performance_script_prints_metrics_and_prefers_exact_match(monkeypatch, capsys):
    module = load_script()
    calls: list[str] = []

    def fake_get_json(url: str):
        calls.append(url)
        if "/api/graph/search" in url:
            return [
                {"id": "xiaoao:Person:other", "name": "令狐"},
                {"id": "xiaoao:Person:linghu", "name": "令狐冲"},
            ]
        if "/api/graph/neighborhood" in url:
            return {"nodes": [], "edges": []}
        if "/api/entities/" in url:
            return {"id": "xiaoao:Person:linghu"}
        raise AssertionError(url)

    monkeypatch.setattr(module, "get_json", fake_get_json)
    monkeypatch.setattr(module.time, "perf_counter", iter(range(20)).__next__)

    status = module.main(
        [
            "--base-url",
            "http://localhost:5173",
            "--project-id",
            "xiaoao",
            "--query",
            "令狐冲",
        ]
    )

    output = capsys.readouterr().out
    assert status == 0
    assert "search_p50_ms=" in output
    assert "search_p95_ms=" in output
    assert "one_hop_ms=" in output
    assert "detail_ms=" in output
    assert "two_hop_ms=" in output
    assert "entity_id=xiaoao:Person:linghu" in output
    assert any("depth=1" in call for call in calls)
    assert any("depth=2" in call for call in calls)


def test_performance_script_fails_when_search_returns_no_entity(monkeypatch, capsys):
    module = load_script()

    monkeypatch.setattr(module, "get_json", lambda _url: [])
    monkeypatch.setattr(module.time, "perf_counter", iter(range(20)).__next__)

    status = module.main(
        [
            "--base-url",
            "http://localhost:5173",
            "--project-id",
            "xiaoao",
            "--query",
            "不存在",
        ]
    )

    assert status == 1
    assert "no search result" in capsys.readouterr().err
