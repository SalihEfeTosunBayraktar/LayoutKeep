"""The run registry: what it reads off a run, and what it refuses to invent.

The registry's whole value is that a field is either established or marked unknown. A field filled
in with something plausible would be worse than an empty one, because the table is what a comparison
rests on - so these tests pin both halves: the reading, and the refusal.
"""

from __future__ import annotations

import json
from pathlib import Path

from tools.audit.run_registry import INFERRED, RECORDED, UNKNOWN, describe, scan_root


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = payload if isinstance(payload, str) else json.dumps(payload)
    path.write_text(text, encoding="utf-8")


def _cli_log(model: str) -> str:
    return (
        "reading   out\\src\\chunk_0000.pdf\n"
        "segments  12 (3284 chars)\n"
        f"provider  ProtectedProvider model={model}\n"
        "translated 12/12 in 197.3s  cached=0\n"
    )


def test_a_run_directory_is_read_for_what_it_recorded(tmp_path: Path) -> None:
    run = tmp_path / "nasa_scan"
    _write(run / "commit.txt", "6390410\n")
    _write(run / "audit.json", {"blocks": 13, "lossless": False,
                                "counts": {"L2": 1, "D1": 5}})
    _write(run / "out" / "t_0000.lkproj", {"source_lang": "en", "target_lang": "tr"})
    _write(run / "out" / "t_0000.log", _cli_log("google/gemma-4-e4b"))
    (run / "src").mkdir()
    (run / "src" / "chunk_0000.pdf").write_bytes(b"%PDF-1.4\n")

    found = describe(run, "heldout/live", arm=None)

    assert found["id"] == "heldout/live/nasa_scan"
    assert found["direction"] == {"value": "en->tr", "status": RECORDED,
                                  "from": "t_0000.lkproj"}
    assert found["commit"]["value"] == "6390410"
    assert found["commit"]["status"] == RECORDED
    assert found["model"] == {"value": "google/gemma-4-e4b", "status": RECORDED,
                              "from": "t_0000.log: the provider line the CLI prints"}
    assert found["source"]["status"] == RECORDED
    assert found["audit"]["value"]["losses"] == 1
    assert found["audit"]["value"]["lossless"] is False
    # Nothing pinned any settings for this run, and that is what it says.
    assert found["settings"]["status"] == UNKNOWN


def test_a_bench_arm_gives_its_sources_what_they_cannot_say_themselves(tmp_path: Path) -> None:
    arm = tmp_path / "a1b2c3d-b0"
    _write(arm / "provenance.json", {
        "app_version": "0.9.10", "commit": "a1b2c3d", "model": "google/gemma-4-e4b",
        "settings": {"translation.workers": 8},
    })
    _write(arm / "tunables.json", {"translation.workers": 8})
    source = arm / "arxiv_19113"
    _write(source / "source.pdf", "%PDF-1.4\n")
    _write(source / "bench.json", {"name": "arxiv_19113", "direction": "en->tr"})
    _write(source / "audit.json", {"blocks": 30, "lossless": True, "counts": {}})

    runs, others, loose = scan_root("bench-repo", tmp_path)

    assert [run["id"] for run in runs] == ["bench-repo/arxiv_19113"]
    assert others == []
    assert loose == []
    found = runs[0]
    assert found["arm"] == "a1b2c3d-b0"
    assert found["commit"] == {"value": "a1b2c3d", "status": RECORDED,
                               "from": "the bench arm's provenance.json"}
    assert found["settings"] == {"value": {"translation.workers": 8}, "status": RECORDED,
                                 "from": "the bench arm's provenance.json"}
    assert found["direction"] == {"value": "en->tr", "status": RECORDED, "from": "bench.json"}
    assert found["source"]["value"] == "source.pdf"


def test_a_directory_that_says_nothing_records_nothing(tmp_path: Path) -> None:
    """Every field it cannot establish stays unknown rather than being filled in."""
    run = tmp_path / "mystery"
    _write(run / "out" / "t_0000.pdf", "%PDF-1.4\n")

    found = describe(run, "campaign", arm=None)

    for name in ("source", "direction", "commit", "model", "settings", "audit"):
        assert found[name]["status"] == UNKNOWN, name
        assert found[name]["value"] is None, name
    # The date is not a guess: the file times are on disk.
    assert found["date"]["status"] == RECORDED


def test_a_run_that_recorded_itself_is_read_from_its_own_project(tmp_path: Path) -> None:
    """A build that records the run writes it into the .lkproj as well as the output.

    That makes the project file the most direct answer there is - version, commit, model and the
    settings that differed - so the registry reads it before it reads any log.
    """
    run = tmp_path / "recorded"
    _write(run / "out" / "t_0000.lkproj", {
        "source_lang": "en",
        "target_lang": "tr",
        "provenance": {
            "app_version": "0.9.10",
            "commit": "c" * 40,
            "provider": "openai",
            "model": "google/gemma-4-e4b",
            "source_lang": "en",
            "target_lang": "tr",
            "settings": {"translation.workers": 3},
        },
    })
    _write(run / "out" / "t_0000.pdf", "%PDF-1.4\n")

    found = describe(run, "heldout/live", arm=None)

    assert found["direction"]["value"] == "en->tr"
    assert found["commit"] == {"value": "c" * 40, "status": RECORDED,
                               "from": "t_0000.lkproj: the run's own record"}
    assert found["model"]["value"] == "google/gemma-4-e4b"
    assert found["settings"] == {"value": {"translation.workers": 3}, "status": RECORDED,
                                 "from": "t_0000.lkproj: the run's own record"}


def test_a_commit_read_off_a_directory_name_is_marked_inferred(tmp_path: Path) -> None:
    """A bench arm is named after the commit it measured - a good inference, still an inference."""
    run = tmp_path / "deadbee"
    _write(run / "out" / "t_0000.pdf", "%PDF-1.4\n")

    found = describe(run, "bench", arm=None)

    assert found["commit"] == {"value": "deadbee", "status": INFERRED,
                               "from": "the directory name (deadbee)"}


def test_a_directory_that_is_not_a_run_is_listed_with_its_reason(tmp_path: Path) -> None:
    (tmp_path / "books").mkdir()
    (tmp_path / "books" / "time_machine.pdf").write_bytes(b"%PDF-1.4\n")

    runs, others, _loose = scan_root("campaign", tmp_path)

    assert runs == []
    assert [item["path"] for item in others] == ["campaign/books"]
    assert "holds: time_machine.pdf" in others[0]["why"]
