"""The settings registry's shape: eight groups, in the order the work happens, each one contiguous.

The dialog builds its collapsible sections by walking the registry, so a group split across the list
becomes two headings with the same name - which is exactly how the settings screen came to read as
a mess: sixteen groups, nine of them holding a single row, and eight rows belonging to no group at
all. These rules keep the registry organised; the dialog then cannot help but follow.
"""

from __future__ import annotations

import collections

from layoutkeep.core import tunables

#: The groups, in the order the pipeline runs: what gets translated, with what context, through
#: which provider, how the page is read, how its tables and lines are put together, how the text is
#: fitted and written, what the window does, and the extra test tools.
GROUP_ORDER = (
    "TRANSLATION",
    "PROMPT",
    "PROVIDER",
    "READING",
    "TABLES",
    "FITTING",
    "INTERFACE",
    "TEST_TOOLS",
)


def test_every_setting_has_a_group():
    orphans = [spec.key for spec in tunables.TUNABLES if not spec.group]
    assert orphans == [], f"these would fall under a generic heading: {orphans}"


def test_groups_come_from_the_agreed_set_in_pipeline_order():
    seen: list[str] = []
    for spec in tunables.TUNABLES:
        if not seen or seen[-1] != spec.group:
            seen.append(spec.group)
    assert seen == list(GROUP_ORDER), "groups must appear once each, in the pipeline order"


def test_no_group_is_a_single_row():
    """A heading with one setting under it is noise; those rows belong with their neighbours."""
    counts = collections.Counter(spec.group for spec in tunables.TUNABLES)
    lonely = {group: n for group, n in counts.items() if n < 2}
    assert lonely == {}, f"one-row groups: {lonely}"


def test_a_warning_stays_a_warning():
    """A warning is read in a settings row, not in a report.

    Measured on 2026-09-22: thirty-six warnings ran to about 230 characters each, and three had
    grown past 375, one of them to 520 - those three read as a wall of orange and the numbers in
    them stopped being read. The measurement belongs in `evidence`, which the dialog prints under
    the warning in a muted, smaller style.
    """
    long_ones = {spec.key: len(spec.warning) for spec in tunables.TUNABLES if len(spec.warning) > 300}
    assert long_ones == {}, f"move the measurement into evidence=: {long_ones}"


def test_evidence_keeps_the_numbers_when_it_is_used():
    """An entry with evidence must still carry a warning: the evidence explains, it does not replace."""
    broken = [spec.key for spec in tunables.TUNABLES if spec.evidence and not spec.warning]
    assert broken == [], f"evidence without a warning: {broken}"


def test_every_group_key_has_a_heading_in_every_language():
    """The headings are the only part of the dialog that is not written inline, so they are the
    part a missing translation can hide in: the registry stores `TRANSLATION`, and the dialog asks
    the strings for `TWEAKS_GROUP_TRANSLATION`. If that key is absent the fallback prints the key
    itself - the same failure the model search box had."""
    from layoutkeep.ui.strings import _TRANSLATIONS

    missing = {}
    for language, table in _TRANSLATIONS.items():
        absent = [g for g in GROUP_ORDER if f"TWEAKS_GROUP_{g}" not in table]
        if absent:
            missing[language] = absent
    assert missing == {}, f"baslik cevirisi eksik: {missing}"
