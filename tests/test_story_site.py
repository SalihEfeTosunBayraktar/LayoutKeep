"""Every link and image a generated story page points at must exist on disk.

WHY THIS EXISTS: the pages live in three directories (`docs/story/`, `docs/story/en/`,
`docs/story/de/`), and a translated page is one level deeper than the original - so a bare asset
path that is correct in Turkish (`architecture.png`, the file right beside the page) is broken in
English. The first run of this check found exactly that: three images 404ed while the markup looked
perfect. A page that renders is the only page worth publishing, and this is the cheap way to know.

The check resolves every `src`/`href` of every generated page against the file system. It runs the
real generator over the real sources into a temporary directory, so it tests what is published, not
a fixture.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STORY = ROOT / "docs/story"


def _copy_sources(tmp_path: Path) -> Path:
    """The real Markdown sources in a temporary story directory."""
    story = tmp_path / "story"
    if story.exists():
        shutil.rmtree(story)
    shutil.copytree(STORY, story, ignore=shutil.ignore_patterns("*.html"))
    return story


def _run_generator(story: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools/story_site.py"),
            "--source",
            str(ROOT / "docs/STORY.md"),
            "--story-dir",
            str(story),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def _generate(tmp_path: Path) -> Path:
    """Run the real generator into `tmp_path`, with the real Markdown sources."""
    story = _copy_sources(tmp_path)
    _run_generator(story)
    return story


def test_every_generated_link_resolves(tmp_path) -> None:
    story = _generate(tmp_path)
    broken: list[str] = []
    checked = 0
    for page in sorted(story.rglob("*.html")):
        html = page.read_text(encoding="utf-8")
        for attr in ("src", "href"):
            for target in re.findall(rf'{attr}="([^"]+)"', html):
                if target.startswith(("http", "#", "mailto:")):
                    continue
                resolved = (page.parent / target).resolve()
                if not resolved.is_relative_to(story.resolve()):
                    # The footer points at the comparison site, which is a sibling of the story
                    # directory in the published tree - not something this temporary copy has.
                    continue
                checked += 1
                if not resolved.exists():
                    broken.append(f"{page.relative_to(story)} -> {target}")

    assert checked > 100, f"only {checked} local links found - the generator changed shape"
    assert broken == [], "broken links in the published pages: " + ", ".join(broken)


def test_a_missing_translation_falls_back_visibly(tmp_path) -> None:
    """A half-finished translation must read as half-finished, not as a broken page.

    Deterministic on purpose: the translation is deleted from the temporary copy rather than
    relying on some chapter not being translated yet (which changes as translations land).
    """
    story = _copy_sources(tmp_path)
    (story / "en" / "04-hatalar.md").unlink()
    _run_generator(story)
    translated = story / "en" / "04-hatalar.html"
    assert translated.exists()
    html = translated.read_text(encoding="utf-8")
    assert "has not been translated yet" in html
    assert "Hata kataloğu" in html, "the Turkish original must be what is shown"


def test_the_language_switcher_points_at_the_other_languages(tmp_path) -> None:
    story = _generate(tmp_path)
    html = (story / "en" / "04-hatalar.html").read_text(encoding="utf-8")
    assert "story-langs" in html
    # The generator's own markup uses single quotes for these; assert the target, not the quoting.
    assert "../04-hatalar.html" in html, "back to the Turkish page"
    assert "../de/04-hatalar.html" in html, "and on to the German one"
