"""
Historial — ObraDocs
Persists every agent run to disk as a timestamped JSON file and provides
utilities for retrieving and comparing past analyses.

Storage layout:
    .historial/
        obra/
            2026-03-31T14-05-22.json
            ...
        ventas/
            ...
        corretaje/
            ...
        viabilidad/
            ...
        supervisor/
            ...

Usage:
    from agents.historial import save, get_history, compare_runs, summary

    # Save a run
    run_id = save("obra", data=agent_output, meta={"proyecto": "Torre Cumbres"})

    # Retrieve last N runs
    runs = get_history("obra", limit=5)

    # Compare two runs
    diff = compare_runs("obra", runs[0]["id"], runs[1]["id"])

    # Print a one-line summary of each recent run
    summary("ventas")
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path


# ── Config ────────────────────────────────────────────────────────────────────

DEFAULT_BASE_DIR = Path(os.getenv("OBRADOCS_HISTORIAL_DIR", ".historial"))
VALID_AGENTS = {"obra", "ventas", "corretaje", "viabilidad", "supervisor"}


# ── Internal helpers ──────────────────────────────────────────────────────────

def _agent_dir(agent: str, base_dir: Path = DEFAULT_BASE_DIR) -> Path:
    if agent not in VALID_AGENTS:
        raise ValueError(f"Unknown agent '{agent}'. Valid: {sorted(VALID_AGENTS)}")
    path = base_dir / agent
    path.mkdir(parents=True, exist_ok=True)
    return path


def _run_id() -> str:
    """Generate a sortable, filesystem-safe unique timestamp ID (microsecond precision)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S-%f")


def _load(file: Path) -> dict:
    with open(file, encoding="utf-8") as f:
        return json.load(f)


# ── Public API ────────────────────────────────────────────────────────────────

def save(
    agent: str,
    data: dict | str,
    meta: dict = None,
    base_dir: Path = DEFAULT_BASE_DIR,
) -> str:
    """
    Persist an agent run to disk.

    Args:
        agent: Agent name ("obra", "ventas", "corretaje", "viabilidad", "supervisor").
        data: The agent's output — either a parsed dict (structured mode) or raw text.
        meta: Optional dict of extra metadata to store alongside (e.g. project name,
              thresholds used, data source filename).
        base_dir: Root directory for the historial (default: .historial/).

    Returns:
        The run ID (timestamp string), usable with get_run() and compare_runs().
    """
    run_id = _run_id()
    record = {
        "id": run_id,
        "agent": agent,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "meta": meta or {},
        "data": data,
    }
    out_file = _agent_dir(agent, base_dir) / f"{run_id}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    return run_id


def get_run(agent: str, run_id: str, base_dir: Path = DEFAULT_BASE_DIR) -> dict:
    """
    Retrieve a specific run by ID.

    Args:
        agent: Agent name.
        run_id: The ID returned by save().

    Returns:
        The full record dict including metadata and data.

    Raises:
        FileNotFoundError: If no run with that ID exists.
    """
    path = _agent_dir(agent, base_dir) / f"{run_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"No run '{run_id}' found for agent '{agent}'")
    return _load(path)


def get_history(
    agent: str,
    limit: int = 10,
    base_dir: Path = DEFAULT_BASE_DIR,
) -> list[dict]:
    """
    Retrieve the most recent runs for an agent, newest first.

    Args:
        agent: Agent name.
        limit: Maximum number of runs to return (default 10, 0 = all).

    Returns:
        List of record dicts sorted descending by timestamp.
    """
    agent_dir = _agent_dir(agent, base_dir)
    files = sorted(agent_dir.glob("*.json"), reverse=True)
    if limit:
        files = files[:limit]
    return [_load(f) for f in files]


def compare_runs(
    agent: str,
    run_id_a: str,
    run_id_b: str,
    base_dir: Path = DEFAULT_BASE_DIR,
) -> dict:
    """
    Compare two runs side by side.

    For structured JSON data, returns a dict of key differences.
    For text data, returns character-level change stats.

    Args:
        agent: Agent name.
        run_id_a: ID of the older run (baseline).
        run_id_b: ID of the newer run.

    Returns:
        Dict with comparison metadata and data diff.
    """
    rec_a = get_run(agent, run_id_a, base_dir)
    rec_b = get_run(agent, run_id_b, base_dir)

    def _flatten(obj, prefix="") -> dict:
        """Flatten a nested dict to dot-separated keys for comparison."""
        items = {}
        if isinstance(obj, dict):
            for k, v in obj.items():
                items.update(_flatten(v, f"{prefix}{k}."))
        elif isinstance(obj, list):
            items[prefix.rstrip(".")] = f"[{len(obj)} items]"
        else:
            items[prefix.rstrip(".")] = obj
        return items

    diff: dict = {
        "agent": agent,
        "run_a": {"id": run_id_a, "timestamp": rec_a["timestamp"]},
        "run_b": {"id": run_id_b, "timestamp": rec_b["timestamp"]},
        "changes": [],
    }

    data_a = rec_a.get("data", {})
    data_b = rec_b.get("data", {})

    if isinstance(data_a, dict) and isinstance(data_b, dict):
        flat_a = _flatten(data_a)
        flat_b = _flatten(data_b)
        all_keys = set(flat_a) | set(flat_b)
        for key in sorted(all_keys):
            val_a = flat_a.get(key, "<ausente>")
            val_b = flat_b.get(key, "<ausente>")
            if val_a != val_b:
                diff["changes"].append({"campo": key, "antes": val_a, "despues": val_b})
    else:
        # Text comparison: count lines added/removed
        lines_a = str(data_a).splitlines()
        lines_b = str(data_b).splitlines()
        diff["changes"] = {
            "lineas_antes": len(lines_a),
            "lineas_despues": len(lines_b),
            "delta_chars": len(str(data_b)) - len(str(data_a)),
        }

    return diff


def summary(agent: str, limit: int = 5, base_dir: Path = DEFAULT_BASE_DIR) -> None:
    """
    Print a one-line summary of the most recent runs for an agent.

    Args:
        agent: Agent name.
        limit: Number of recent runs to show.
    """
    runs = get_history(agent, limit=limit, base_dir=base_dir)
    if not runs:
        print(f"No hay historial guardado para '{agent}'.")
        return

    print(f"\n── Historial: {agent} (últimos {len(runs)}) ──────────────────────────")
    for r in runs:
        ts = r.get("timestamp", "?")[:19].replace("T", " ")
        meta = r.get("meta", {})
        meta_str = ", ".join(f"{k}={v}" for k, v in meta.items()) if meta else "—"
        data = r.get("data", {})
        # Try to extract a meaningful one-liner from the data
        if isinstance(data, dict):
            hint = (
                data.get("resumen_ejecutivo")
                or data.get("resumen_general")
                or data.get("veredicto_resumen")
                or f"{len(data)} campos JSON"
            )
        else:
            hint = str(data)[:80].replace("\n", " ")
        print(f"  {r['id']}  [{ts}]  meta: {meta_str}")
        print(f"            {hint[:90]}")
    print()


def delete_run(agent: str, run_id: str, base_dir: Path = DEFAULT_BASE_DIR) -> None:
    """Delete a specific run from disk."""
    path = _agent_dir(agent, base_dir) / f"{run_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"No run '{run_id}' found for agent '{agent}'")
    path.unlink()


def clear_history(agent: str, keep_last: int = 0, base_dir: Path = DEFAULT_BASE_DIR) -> int:
    """
    Remove old runs for an agent.

    Args:
        agent: Agent name.
        keep_last: Number of most recent runs to keep (0 = delete all).

    Returns:
        Number of files deleted.
    """
    agent_dir = _agent_dir(agent, base_dir)
    files = sorted(agent_dir.glob("*.json"), reverse=True)
    to_delete = files[keep_last:] if keep_last else files
    for f in to_delete:
        f.unlink()
    return len(to_delete)


if __name__ == "__main__":
    import tempfile

    # Demo with a temp directory so we don't pollute the repo
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)

        # Save two fake runs
        run1 = save("obra", data={"resumen_ejecutivo": "Todo en orden.", "alertas_criticas_total": 0}, base_dir=base)
        run2 = save("obra", data={"resumen_ejecutivo": "Resi. Bosques en riesgo.", "alertas_criticas_total": 2}, base_dir=base)

        summary("obra", base_dir=base)

        diff = compare_runs("obra", run1, run2, base_dir=base)
        print("Diferencias:")
        for c in diff["changes"]:
            print(f"  {c['campo']}: {c['antes']} → {c['despues']}")
