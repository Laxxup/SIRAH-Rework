from __future__ import annotations

import importlib.util
from pathlib import Path

BENCH = Path(__file__).resolve().parents[1] / "bench" / "eval_llm.py"


def _bench():
    spec = importlib.util.spec_from_file_location("bench_eval_llm", BENCH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_empty_response_counts_as_failure() -> None:
    summary = _bench()._summary(
        [
            {
                "ttft_ms": 1.0,
                "total_ms": 2.0,
                "chars": 0,
                "words": 0,
                "actions": [],
                "error": "respuesta vacía",
            },
            {
                "ttft_ms": 1.0,
                "total_ms": 2.0,
                "chars": 5,
                "words": 1,
                "actions": ["blink"],
                "error": None,
            },
        ]
    )
    assert summary["failed"] == 1
    assert summary["actions"] == {"blink": 1}


def test_default_output_uses_configured_data_dir(tmp_path: Path) -> None:
    class _Config:
        data_dir = tmp_path / "sirah-data"

    path = _bench()._default_output(_Config())
    assert path.parent == tmp_path / "sirah-data" / "llm-eval"
