"""Tests for historial — uses a temp directory, no disk side effects."""

import json
import pytest
from pathlib import Path

from agents.historial import save, get_run, get_history, compare_runs, summary, delete_run, clear_history


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_base(tmp_path: Path) -> Path:
    return tmp_path


# ── save / get_run ────────────────────────────────────────────────────────────

def test_save_returns_string_id(tmp_base):
    run_id = save("obra", data={"test": True}, base_dir=tmp_base)
    assert isinstance(run_id, str)
    assert len(run_id) > 0


def test_save_creates_file(tmp_base):
    run_id = save("obra", data="texto de prueba", base_dir=tmp_base)
    expected = tmp_base / "obra" / f"{run_id}.json"
    assert expected.exists()


def test_get_run_returns_record(tmp_base):
    run_id = save("ventas", data={"mrr": 100000}, base_dir=tmp_base)
    record = get_run("ventas", run_id, base_dir=tmp_base)
    assert record["id"] == run_id
    assert record["agent"] == "ventas"
    assert record["data"]["mrr"] == 100000


def test_get_run_raises_for_missing(tmp_base):
    with pytest.raises(FileNotFoundError):
        get_run("obra", "nonexistent-id", base_dir=tmp_base)


def test_save_stores_meta(tmp_base):
    run_id = save("corretaje", data="ok", meta={"proyecto": "Punta Norte"}, base_dir=tmp_base)
    record = get_run("corretaje", run_id, base_dir=tmp_base)
    assert record["meta"]["proyecto"] == "Punta Norte"


def test_save_text_data(tmp_base):
    run_id = save("obra", data="Análisis completo en texto.", base_dir=tmp_base)
    record = get_run("obra", run_id, base_dir=tmp_base)
    assert "texto" in record["data"]


def test_save_invalid_agent_raises(tmp_base):
    with pytest.raises(ValueError, match="Unknown agent"):
        save("invalid_agent", data={}, base_dir=tmp_base)


# ── get_history ───────────────────────────────────────────────────────────────

def test_get_history_returns_list(tmp_base):
    save("obra", data={"run": 1}, base_dir=tmp_base)
    save("obra", data={"run": 2}, base_dir=tmp_base)
    history = get_history("obra", base_dir=tmp_base)
    assert isinstance(history, list)
    assert len(history) == 2


def test_get_history_newest_first(tmp_base):
    import time
    id1 = save("obra", data={"run": 1}, base_dir=tmp_base)
    time.sleep(0.01)  # ensure different timestamps
    id2 = save("obra", data={"run": 2}, base_dir=tmp_base)
    history = get_history("obra", base_dir=tmp_base)
    assert history[0]["id"] >= history[1]["id"]


def test_get_history_limit(tmp_base):
    for i in range(5):
        save("ventas", data={"run": i}, base_dir=tmp_base)
    history = get_history("ventas", limit=3, base_dir=tmp_base)
    assert len(history) == 3


def test_get_history_empty(tmp_base):
    history = get_history("viabilidad", base_dir=tmp_base)
    assert history == []


# ── compare_runs ──────────────────────────────────────────────────────────────

def test_compare_runs_dict_data(tmp_base):
    id1 = save("obra", data={"alertas_criticas_total": 0, "semaforo": "Verde"}, base_dir=tmp_base)
    id2 = save("obra", data={"alertas_criticas_total": 2, "semaforo": "Rojo"}, base_dir=tmp_base)
    diff = compare_runs("obra", id1, id2, base_dir=tmp_base)
    assert diff["run_a"]["id"] == id1
    assert diff["run_b"]["id"] == id2
    changed_fields = {c["campo"] for c in diff["changes"]}
    assert "alertas_criticas_total" in changed_fields
    assert "semaforo" in changed_fields


def test_compare_runs_no_changes(tmp_base):
    data = {"score": 75, "estado": "Normal"}
    id1 = save("obra", data=data, base_dir=tmp_base)
    id2 = save("obra", data=data, base_dir=tmp_base)
    diff = compare_runs("obra", id1, id2, base_dir=tmp_base)
    assert diff["changes"] == []


def test_compare_runs_text_data(tmp_base):
    id1 = save("ventas", data="Texto corto.", base_dir=tmp_base)
    id2 = save("ventas", data="Texto más largo con más información.", base_dir=tmp_base)
    diff = compare_runs("ventas", id1, id2, base_dir=tmp_base)
    assert isinstance(diff["changes"], dict)
    assert diff["changes"]["delta_chars"] > 0


# ── delete_run / clear_history ────────────────────────────────────────────────

def test_delete_run(tmp_base):
    run_id = save("supervisor", data={}, base_dir=tmp_base)
    delete_run("supervisor", run_id, base_dir=tmp_base)
    with pytest.raises(FileNotFoundError):
        get_run("supervisor", run_id, base_dir=tmp_base)


def test_clear_history_removes_all(tmp_base):
    for _ in range(4):
        save("corretaje", data={}, base_dir=tmp_base)
    deleted = clear_history("corretaje", keep_last=0, base_dir=tmp_base)
    assert deleted == 4
    assert get_history("corretaje", base_dir=tmp_base) == []


def test_clear_history_keeps_last_n(tmp_base):
    import time
    for i in range(5):
        save("obra", data={"i": i}, base_dir=tmp_base)
        time.sleep(0.01)
    deleted = clear_history("obra", keep_last=2, base_dir=tmp_base)
    assert deleted == 3
    remaining = get_history("obra", base_dir=tmp_base)
    assert len(remaining) == 2


# ── summary ───────────────────────────────────────────────────────────────────

def test_summary_no_crash_empty(tmp_base, capsys):
    summary("viabilidad", base_dir=tmp_base)
    captured = capsys.readouterr()
    assert "No hay historial" in captured.out


def test_summary_prints_runs(tmp_base, capsys):
    save("obra", data={"resumen_ejecutivo": "Todo en orden."}, base_dir=tmp_base)
    summary("obra", limit=1, base_dir=tmp_base)
    captured = capsys.readouterr()
    assert "Todo en orden." in captured.out
