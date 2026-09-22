"""One registry of every translation run already on disk, with what can be established about each.

WHY THIS EXISTS: the runs are spread over five directories and two repositories, each named
differently and each recorded in whatever form the tool that made it happened to use - a
`commit.txt` here, a `bench.json` there, an arm directory named after its commit, a `.lkproj` with
the languages in it. "Which version, with what, and with which methods was this translated?" cannot
be answered by looking, and a folder of outputs with no answer is a folder of files nobody can
compare.

Two rules:

  * **Never guess silently.** Every field carries how it was established: `recorded` (the run
    itself says so), `inferred` (read off a name or a filename) or `unknown`. An unknown stays
    unknown rather than being filled in with something plausible.
  * **Read only.** Nothing under `_artifacts` is touched; the registry is written next to the
    campaign journal.

    python tools/audit/run_registry.py            # scan, write docs/campaign/RUNS.md and RUNS.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

#: Repository root, resolved from this file (tools/audit/run_registry.py -> ../..).
REPO = Path(__file__).resolve().parents[2]
#: The bench ran from its own worktree; its artifacts are not under this repository.
BENCH_REPO = REPO.parent / "LayoutKeep_bench"


def _main_worktree(start: Path) -> Path | None:
    """The primary checkout this one shares a repository with, or None for a plain checkout.

    A linked worktree keeps a `gitdir:` pointer and a `commondir` file instead of a `.git`
    directory; the primary checkout is the parent of the directory those point at.
    """
    marker = start / ".git"
    try:
        if marker.is_dir():
            return start
        if not marker.is_file():
            return None
        text = marker.read_text(encoding="utf-8", errors="replace").strip()
        if not text.startswith("gitdir:"):
            return None
        git_dir = Path(text.split(":", 1)[1].strip())
        if not git_dir.is_absolute():
            git_dir = (start / git_dir).resolve()
        common = git_dir / "commondir"
        if common.is_file():
            target = Path(common.read_text(encoding="utf-8", errors="replace").strip())
            git_dir = target if target.is_absolute() else (git_dir / target).resolve()
        return git_dir.parent if git_dir.name == ".git" else None
    except OSError:
        return None


def _artifacts_dir() -> Path:
    """Where the runs are: this checkout's `_artifacts`, else the primary checkout's.

    The artifacts are not committed, so a linked worktree - where most of this project's
    measurements are taken from - has none of its own and the runs sit in the primary checkout.
    Resolved from git rather than hard-coded, so the registry runs from any checkout.

    A worktree can still hold an `_artifacts` of its own: the test suite writes its scratch under
    `_artifacts/epub_work`. That is why a candidate has to hold one of the run roots to count,
    rather than merely exist.
    """
    candidates = [REPO / "_artifacts", (_main_worktree(REPO) or REPO) / "_artifacts"]
    for candidate in candidates:
        if any((candidate / name).is_dir() for name in ("heldout", "campaign", "bench")):
            return candidate
    return candidates[0]


ARTIFACTS = _artifacts_dir()

#: label, directory. The label is what the run's id is prefixed with in the table.
ROOTS: tuple[tuple[str, Path], ...] = (
    ("heldout/live", ARTIFACTS / "heldout" / "live"),
    ("heldout/runs", ARTIFACTS / "heldout" / "runs"),
    ("campaign", ARTIFACTS / "campaign"),
    ("bench", ARTIFACTS / "bench"),
    ("bench-repo", BENCH_REPO / "_artifacts" / "bench"),
)

OUT_MD = REPO / "docs" / "campaign" / "RUNS.md"
OUT_JSON = REPO / "docs" / "campaign" / "RUNS.json"

#: Directories inside a run that hold working files rather than being runs of their own.
_WORK_DIRS = frozenset({"out", "src", "run", "sources", "incoming"})

#: A directory is a run when one of these is in it, or when it holds per-chunk output.
_RUN_MARKERS = ("audit.json", "bench.json", "run.log", "translate.log", "commit.txt")

LOSS_KEYS = [f"L{n}" for n in range(1, 11)]
DIAG_KEYS = ["D1", "D2", "D3"]

#: A bench arm directory is named after the commit it measured, optionally with an arm label.
_ARM_NAME = re.compile(r"[0-9a-f]{7,40}(?:-[A-Za-z0-9]+)?")

#: The model the CLI prints when it builds its provider: "provider  ProtectedProvider model=X".
_MODEL_IN_LOG = re.compile(r"model=([^\s|]+)")

#: A written output names its target language: "report.tr.pdf".
_TARGET_IN_NAME = re.compile(r"\.([a-z]{2,3})\.(?:pdf|docx|epub)$")

RECORDED, INFERRED, UNKNOWN = "recorded", "inferred", "unknown"


# --------------------------------------------------------------------------------------
# Reading what is on disk
# --------------------------------------------------------------------------------------


def _field(value: object, status: str, source: str) -> dict:
    return {"value": value, "status": status, "from": source}


def _unknown(why: str) -> dict:
    return _field(None, UNKNOWN, why)


def _json(path: Path) -> dict:
    """The JSON object in `path`, or {} - a half-written file is not a reason to stop."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _is_run(path: Path) -> bool:
    if any((path / marker).is_file() for marker in _RUN_MARKERS):
        return True
    # A translated document at the top of the directory is proof a run happened there, whatever
    # the tool that made it named its log: `heldout/live/gutenberg_56464` has `run_log.txt` and
    # `gutenberg_56464.tr.epub` and was being read as "not a run" for the missing log alone.
    if any(path.glob("*.tr.*")):
        return True
    out = path / "out"
    return out.is_dir() and any(out.glob("t_*.pdf"))


def _why_not(path: Path) -> str:
    entries = sorted(p.name for p in path.iterdir())
    shown = ", ".join(entries[:6]) + (" ..." if len(entries) > 6 else "")
    return (
        "no audit.json, no log and no translated output at its top; "
        f"holds: {shown}"
    )


def _arm_record(directory: Path) -> dict | None:
    """What a bench arm pinned: its own provenance.json and the settings it ran under."""
    record = {}
    for name in ("provenance.json", "tunables.json"):
        payload = _json(directory / name)
        if payload:
            record[name] = payload
    return record or None


def _recorded(path: Path, arm: dict | None, key: str) -> tuple[object, str | None]:
    """(value, where it came from) for `key`, from the run's own record or its arm's."""
    own = _json(path / "provenance.json")
    if own.get(key) not in (None, ""):
        return own[key], "provenance.json"
    arm_provenance = (arm or {}).get("provenance.json") or {}
    if arm_provenance.get(key) not in (None, ""):
        return arm_provenance[key], "the bench arm's provenance.json"
    return None, None


def _source(path: Path, name: str) -> dict:
    """The document that was translated, as far as the directory says."""
    direct = path / "source.pdf"
    if direct.is_file():
        return _field("source.pdf", RECORDED, "the run directory")
    src_dir = path / "src"
    chunks = sorted(src_dir.glob("*.pdf")) if src_dir.is_dir() else []
    named = [p for p in chunks if not p.name.startswith("chunk_")]
    if len(named) == 1:
        return _field(named[0].name, RECORDED, "the run directory")
    if chunks:
        for folder in (
            REPO / "_artifacts" / "heldout" / "sources",
            REPO / "_artifacts" / "campaign" / "books",
        ):
            hit = folder / f"{name}.pdf"
            if hit.is_file():
                return _field(
                    hit.name, INFERRED, f"the run's name matches {folder.name}/{hit.name}"
                )
        return _field(
            f"{len(chunks)} chunk files", RECORDED,
            "src/ holds chunk_*.pdf - the original document is not in the run directory",
        )
    return _unknown("no source file in the run directory")


def _projects(path: Path) -> list[Path]:
    return sorted(p for p in path.rglob("*.lkproj") if p.is_file())


def _project(path: Path) -> tuple[dict, Path | None]:
    """The first project file of the run, parsed: (payload, path).

    A run writes a `.lkproj` per chunk, all of them by the same run, so the first one answers for
    all of them. Read once per run: these files carry whole pages, and parsing one per field would
    be the expensive part of the scan.
    """
    projects = _projects(path)
    if not projects:
        return {}, None
    return _json(projects[0]), projects[0]


def _direction(path: Path, arm: dict | None, payload: dict, project: Path | None) -> dict:
    """The language pair, from a record if there is one, else off a filename."""
    value, where = _recorded(path, arm, "target_lang")
    source_lang, _ = _recorded(path, arm, "source_lang")
    if value and source_lang:
        return _field(f"{source_lang}->{value}", RECORDED, str(where))
    bench = _json(path / "bench.json")
    if bench.get("direction"):
        return _field(str(bench["direction"]), RECORDED, "bench.json")
    for candidate in (payload.get("provenance") or {}, payload):
        if candidate.get("source_lang") and candidate.get("target_lang"):
            return _field(
                f"{candidate['source_lang']}->{candidate['target_lang']}",
                RECORDED,
                f"{project.name}",
            )
    for output in sorted(path.glob("*.*")):
        found = _TARGET_IN_NAME.search(output.name)
        if found:
            return _field(
                f"?->{found.group(1)}", INFERRED, f"the output's name ({output.name})"
            )
    return _unknown("no project, no bench record and no named output")


def _date(path: Path) -> dict:
    """When the run finished, from the newest file in it. File times are what the disk has."""
    newest = None
    for entry in path.rglob("*"):
        try:
            if entry.is_file():
                newest = max(newest or 0.0, entry.stat().st_mtime)
        except OSError:
            continue
    if newest is None:
        return _unknown("nothing on disk to date")
    stamp = datetime.fromtimestamp(newest).strftime("%Y-%m-%d %H:%M")
    return _field(stamp, RECORDED, "the newest file in the run directory")


def _commit(path: Path, arm: dict | None, record: dict, project: Path | None) -> dict:
    value, where = _recorded(path, arm, "commit")
    if value:
        return _field(str(value), RECORDED, str(where))
    if record.get("commit"):
        # The run's own record, written into its project file by a build that records one
        # (`core/provenance.py`) - the most direct answer there is.
        return _field(str(record["commit"]), RECORDED, f"{project.name}: the run's own record")
    bench = _json(path / "bench.json").get("provenance") or {}
    if isinstance(bench, dict) and bench.get("commit"):
        return _field(str(bench["commit"]), RECORDED, "bench.json's own provenance")
    stamp = path / "commit.txt"
    if stamp.is_file():
        text = stamp.read_text(encoding="utf-8", errors="replace").strip()
        if text:
            return _field(text, RECORDED, "commit.txt")
    for candidate in (path, path.parent):
        found = _ARM_NAME.fullmatch(candidate.name)
        if found:
            return _field(
                found.group(0).split("-")[0], INFERRED, f"the directory name ({candidate.name})"
            )
    return _unknown("no record, no commit.txt and no commit in the directory name")


def _model(path: Path, arm: dict | None, record: dict, project: Path | None) -> dict:
    value, where = _recorded(path, arm, "model")
    if value:
        return _field(str(value), RECORDED, str(where))
    if record.get("model"):
        return _field(str(record["model"]), RECORDED, f"{project.name}: the run's own record")
    logs = sorted(path.rglob("*.log"))[:3]
    for log in logs:
        try:
            text = log.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for found in _MODEL_IN_LOG.finditer(text):
            model = found.group(1).strip()
            if model and model != "-":
                return _field(model, RECORDED, f"{log.name}: the provider line the CLI prints")
    if logs:
        return _unknown("the logs name no model (the test provider has none)")
    return _unknown("no log to read a model from")


def _settings(arm: dict | None, record: dict, project: Path | None) -> dict:
    arm_provenance = (arm or {}).get("provenance.json") or {}
    if arm_provenance.get("settings"):
        return _field(arm_provenance["settings"], RECORDED, "the bench arm's provenance.json")
    pinned = (arm or {}).get("tunables.json")
    if pinned:
        return _field(pinned, RECORDED, "the bench arm's tunables.json")
    if record.get("settings"):
        return _field(record["settings"], RECORDED, f"{project.name}: the run's own record")
    return _unknown("no pinned settings for this run")


def _audit(path: Path) -> dict:
    audit = _json(path / "audit.json")
    if not audit:
        return _unknown("no audit.json")
    counts = audit.get("counts") or {}
    losses = sum(int(counts.get(key, 0)) for key in LOSS_KEYS)
    return _field(
        {
            "blocks": audit.get("blocks"),
            "losses": losses,
            "lossless": bool(audit.get("lossless")),
            "counts": {
                key: int(counts.get(key, 0)) for key in (*LOSS_KEYS, *DIAG_KEYS)
            },
        },
        RECORDED,
        "audit.json",
    )


def describe(path: Path, label: str, arm: dict | None) -> dict:
    """Everything that can be established about one run, field by field, with its provenance."""
    payload, project = _project(path)
    record = payload.get("provenance") or {}
    return {
        "id": f"{label}/{path.name}",
        "path": str(path),
        "arm": path.parent.name if arm else None,
        "source": _source(path, path.name),
        "direction": _direction(path, arm, payload, project),
        "date": _date(path),
        "commit": _commit(path, arm, record, project),
        "model": _model(path, arm, record, project),
        "settings": _settings(arm, record, project),
        "audit": _audit(path),
    }


def scan_root(label: str, root: Path) -> tuple[list[dict], list[dict], list[str]]:
    """(runs, directories examined and rejected, loose files) under one root."""
    runs: list[dict] = []
    others: list[dict] = []
    if not root.is_dir():
        return runs, [{"path": str(root), "why": "directory does not exist"}], []
    for child in sorted(p for p in root.iterdir() if p.is_dir()):
        if child.name in _WORK_DIRS:
            continue
        if _is_run(child):
            runs.append(describe(child, label, None))
            continue
        arm = _arm_record(child)
        inner = [p for p in sorted(child.iterdir()) if p.is_dir() and p.name not in _WORK_DIRS]
        if not inner:
            why = "a bench arm with no run inside" if arm is not None else _why_not(child)
            others.append({"path": f"{label}/{child.name}", "why": why})
            continue
        # A bench arm: every source inside it is listed, finished or not. A source that was
        # started and left without an output is a fact about the campaign, and dropping it would
        # make the registry look complete when it is not.
        for source in inner:
            if _is_run(source):
                runs.append(describe(source, label, arm))
            else:
                others.append({
                    "path": f"{label}/{child.name}/{source.name}",
                    "why": _why_not(source),
                })
    loose = sorted(p.name for p in root.iterdir() if p.is_file())
    return runs, others, loose


# --------------------------------------------------------------------------------------
# Writing the registry
# --------------------------------------------------------------------------------------


def _cell(field: dict) -> str:
    """One table cell: `?` when nothing could be established, `~` when it was inferred."""
    value = field["value"]
    if field["status"] == UNKNOWN or value in (None, "", {}):
        return "?"
    if isinstance(value, dict):
        value = ", ".join(f"{key}={value[key]}" for key in sorted(value))
    text = str(value).replace("|", "\\|")
    return f"~{text}" if field["status"] == INFERRED else text


def _audit_cell(field: dict) -> str:
    if field["status"] == UNKNOWN:
        return "?"
    value = field["value"]
    counts = value["counts"]
    reported = sum(counts[key] for key in DIAG_KEYS)
    verdict = "lossless" if value["lossless"] else f"L={value['losses']}"
    return f"{value['blocks']} blk, {verdict}, D={reported}"


def _coverage(runs: list[dict]) -> list[str]:
    fields = ("source", "direction", "date", "commit", "model", "settings", "audit")
    lines = ["| field | recorded | inferred | unknown |", "|---|---|---|---|"]
    for name in fields:
        statuses = [run[name]["status"] for run in runs]
        lines.append(
            f"| {name} | {statuses.count(RECORDED)} | {statuses.count(INFERRED)} "
            f"| {statuses.count(UNKNOWN)} |"
        )
    return lines


def write_markdown(runs: list[dict], others: list[dict], loose: dict[str, list[str]]) -> Path:
    order = {label: index for index, (label, _root) in enumerate(ROOTS)}
    # Newest first, and by id inside a date so the table is stable between runs. Sorting by id
    # first and then by date (a stable sort) keeps the roots in a readable order.
    runs = sorted(runs, key=lambda run: (order.get(run["id"].split("/", 1)[0], 99), run["id"]))
    runs = sorted(runs, key=lambda run: run["date"]["value"] or "", reverse=True)
    lines = [
        "# Translation runs on disk",
        "",
        "Written by `tools/audit/run_registry.py`; regenerate it rather than editing it. Every run",
        "under `_artifacts/{heldout/live, heldout/runs, campaign, bench}` and",
        "`LayoutKeep_bench/_artifacts/bench` is listed with what can be established about it.",
        "",
        "How each cell was established: plain = **recorded** (the run itself says so), `~` =",
        "**inferred** (read off a directory or file name), `?` = **unknown** - nothing on disk",
        "establishes it, and nothing has been filled in to look complete. The evidence behind every",
        "field is in `RUNS.json`, which carries the same table as data.",
        "",
        "A run that records no commit of its own is left unknown on purpose. The held-out",
        "campaign's code versions were written down by hand, not per run -",
        "`_artifacts/heldout/code_versions.log` (which document, and from which time on) and",
        "`_artifacts/heldout/run_heldout.sh` (the worktree frozen at `bad981a`). Prose is not",
        "parsed into this table: a sentence covering \"every later document\" is not a per-run",
        "record, and reading it as one would put a commit next to a run that may not have used it.",
        "",
        f"Runs listed: **{len(runs)}**. Scanned {datetime.now().strftime('%Y-%m-%d %H:%M')}.",
        "",
        "## How much of each field is known",
        "",
        *_coverage(runs),
        "",
        "## The runs",
        "",
        "| run | source | direction | date | commit | model | settings | audit |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for run in runs:
        settings = _cell(run["settings"])
        if len(settings) > 60:
            settings = settings[:57] + "..."
        lines.append(
            "| " + " | ".join(
                [
                    run["id"],
                    _cell(run["source"]),
                    _cell(run["direction"]),
                    _cell(run["date"]),
                    _cell(run["commit"]),
                    _cell(run["model"]),
                    settings,
                    _audit_cell(run["audit"]),
                ]
            ) + " |"
        )
    lines += ["", "## Directories that are not runs", ""]
    if others:
        lines += ["| directory | why |", "|---|---|"]
        lines += [f"| {item['path']} | {item['why']} |" for item in others]
    else:
        lines.append("None - every directory under the scanned roots is a run.")
    lines += ["", "## Loose files beside the runs (not runs, listed so they are not missed)", ""]
    for label, names in loose.items():
        if names:
            lines.append(f"- `{label}`: {', '.join(f'`{name}`' for name in names)}")
    lines.append("")
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    return OUT_MD


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--md", default=str(OUT_MD), help="where the table goes")
    parser.add_argument("--json", dest="json_path", default=str(OUT_JSON),
                        help="where the same table as data goes")
    args = parser.parse_args()

    runs: list[dict] = []
    others: list[dict] = []
    loose: dict[str, list[str]] = {}
    roots: list[dict] = []
    for label, root in ROOTS:
        found, rejected, files = scan_root(label, root)
        runs.extend(found)
        others.extend(rejected)
        loose[label] = files
        roots.append({
            "label": label,
            "path": str(root),
            "exists": root.is_dir(),
            "runs": len(found),
            "not_runs": len(rejected),
        })
        print(f"{label:<14} {len(found):>3} runs, {len(rejected)} other directories  {root}")

    payload = {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "generator": "tools/audit/run_registry.py",
        "roots": roots,
        "runs": runs,
        "not_runs": others,
        "loose_files": loose,
    }
    Path(args.json_path).parent.mkdir(parents=True, exist_ok=True)
    Path(args.json_path).write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    written = write_markdown(runs, others, loose)
    print(f"{len(runs)} runs -> {written}")
    print(f"{len(runs)} runs -> {args.json_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
