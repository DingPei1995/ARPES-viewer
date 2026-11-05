"""
tools/runtime/naming.py
=======================
How a processed dataset is named, and how names are sorted by what was done.

Every step that makes a new dataset names it after its source with one tag
in square brackets added at the end -- ``Map80eV [norm] [E-E_F] [k]`` -- so
a name reads as the history of the data, oldest step first, and the list
can be sorted by what the data now *is*: the last tag. The tags are the
short words of :data:`TAGS`, in the order a processing usually runs (the
order "Sort by data type" groups the list in). An agent naming a row
itself (``new_name=``) follows the same rule.

Names written before this table (``_s_nor``, ``_sm``, ``[E-Ef]`` ...) are
still understood: :func:`tags_in` reads their old suffixes as the tags they
mean, so an old session sorts with a new one.

Nothing here imports Qt.
"""
from __future__ import annotations

import re

__all__ = ["TAGS", "STEP_TAGS", "tag_for", "tagged", "tags_in", "last_tag",
           "tag_rank", "type_sort_key", "naming_rule"]

#: The tags, in processing order: (tag, what it means). A dataset's
#: "type" is its last tag; a name with none is a measurement as read.
TAGS = (
    ("combined", "datasets joined, stacked or summed into one"),
    ("degrid", "the detector's grid pattern removed"),
    ("grid", "the grid pattern itself (what degrid removed)"),
    ("det", "detector correction (keystone, regions)"),
    ("crop", "cut to a range of its axes (truncate)"),
    ("bin", "points summed in blocks (compress)"),
    ("despike", "spikes removed"),
    ("norm", "normalised (self-normalise, per-spectrum or per-plane)"),
    ("bg", "background subtracted"),
    ("E-E_F", "energy referred to the Fermi level"),
    ("dFD", "divided by the Fermi-Dirac function"),
    ("FS corr", "Fermi-surface (band) straightening"),
    ("sm", "smoothed"),
    ("symm", "symmetrised"),
    ("k", "converted to momentum (k_par)"),
    ("kz", "converted to k_z (photon-energy scan)"),
    ("d2", "second derivative"),
    ("grad", "gradient"),
    ("cur", "curvature"),
    ("ridge", "ridge (band-position) detection"),
    ("arb cut", "a cut along a line of one's own, out of a map"),
    ("slice", "a plane or cut taken out of a map or viewer"),
    ("EDC", "an energy distribution curve taken out"),
    ("MDC", "a momentum distribution curve taken out"),
    ("shifted", "a curve shifted along its axis"),
    ("sigma", "a curve's Poisson uncertainty"),
    ("fit", "a fit result"),
    ("LD", "linear dichroism of two cuts"),
    ("CD", "circular dichroism of two cuts"),
    ("diff", "difference of two cuts"),
    ("asym", "asymmetry of two cuts"),
    ("ratio", "ratio of two cuts"),
    ("sum", "sum of two cuts"),
    ("calc", "a calculation (spectral function, bands), not a measurement"),
)

_RANK = {tag.casefold(): index for index, (tag, _what) in enumerate(TAGS)}

#: What an operation (as a tool, an agent's step or a processing history
#: names it) is tagged with.
STEP_TAGS = {
    "combine": "combined", "stack": "combined", "sum_scans": "combined",
    "degrid": "degrid", "grid": "grid", "detector": "det",
    "truncate": "crop", "crop": "crop", "compress": "bin", "bin": "bin",
    "despike": "despike", "normalise": "norm", "normalize": "norm",
    "self_normalise": "norm", "background": "bg",
    "shift_energy": "E-E_F", "fermi": "dFD", "divide_fermi": "dFD",
    "fs_correction": "FS corr", "smooth": "sm", "symmetry": "symm",
    "symmetrise": "symm", "map_to_k": "k", "cut_to_k": "k", "kz_to_k": "kz",
    "derivative": "d2", "gradient": "grad", "curvature": "cur",
    "ridge": "ridge", "arbitrary_cut": "arb cut", "fit": "fit",
    "linear_dichroism": "LD", "circular_dichroism": "CD",
    "difference": "diff", "asymmetry": "asym", "ratio": "ratio",
    "sum": "sum", "reference": "norm", "calculation": "calc",
}

#: Older ways of writing a tag: bracketed words that mean a tag of the
#: table, and the underscore suffixes names used to end in.
_ALIASES = {
    "e-ef": "E-E_F", "e-e_f": "E-E_F", "e - e_f": "E-E_F", "e-ef ": "E-E_F",
    "core-level edc": "EDC", "deflector_vs_e": "slice", "slit_vs_e": "slice",
    "σ": "sigma", "calculation": "calc", "norm": "norm",
}
_OLD_SUFFIXES = {
    "_s_nor": "norm", "_nor": "norm", "_tk": "crop", "_comb": "bin",
    "_sm": "sm", "_d2": "d2", "_cur": "cur", "_grad": "grad", "_bg": "bg",
    "_fd": "dFD", "_fix": "despike", "_symm": "symm", "_rd": "ridge",
    "_det": "det", "_proc": "",
}
_OLD = re.compile(r"(" + "|".join(sorted((re.escape(s) for s in _OLD_SUFFIXES),
                                         key=len, reverse=True))
                  + r")\d*(?=$|[\s\[(_])")
_BRACKET = re.compile(r"\[([^\[\]]+)\]")


def tag_for(step: str) -> str:
    """The tag an operation's result is named with: ``"normalise"`` ->
    ``"norm"``. A name of the table is returned as it is; anything else
    too, so a new operation still gets a bracketed tag."""
    step = str(step or "").strip()
    if step.casefold() in _RANK:
        return TAGS[_RANK[step.casefold()]][0]
    return STEP_TAGS.get(step.casefold(), STEP_TAGS.get(step, step))


def tagged(base: str, step: str, detail: str = "") -> str:
    """``base`` named for one more step: ``tagged("Map1", "normalise")`` ->
    ``"Map1 [norm]"``; ``detail`` goes inside the brackets after the tag
    (``tagged("Map1", "EDC", "@ 0.1")`` -> ``"Map1 [EDC @ 0.1]"``)."""
    tag = tag_for(step)
    inside = f"{tag} {detail}".strip() if detail else tag
    return f"{str(base).rstrip()} [{inside}]"


def _canonical(word: str) -> str:
    text = word.strip()
    folded = text.casefold()
    if folded in _RANK:
        return TAGS[_RANK[folded]][0]
    if folded in _ALIASES:
        return _ALIASES[folded]
    first = folded.split(" ")[0]
    if first in _RANK:                      # "EDC @ 0.1 ±0.02" -> "EDC"
        return TAGS[_RANK[first]][0]
    if first in _ALIASES:
        return _ALIASES[first]
    match = re.fullmatch(r"bin\d+", first)
    if match:
        return "bin"
    return text


def tags_in(name: str) -> "list[str]":
    """The tags of a name, oldest first: the bracketed words (an alias read
    as its tag) and the underscore suffixes of older names, in the order
    they appear. ``"Map_s_nor [k] [E-Ef]"`` -> ``["norm", "k", "E-E_F"]``."""
    name = str(name or "")
    found = []
    for match in sorted(list(_BRACKET.finditer(name)) + list(_OLD.finditer(name)),
                        key=lambda m: m.start()):
        if match.re is _OLD:
            tag = _OLD_SUFFIXES[match.group(1)]
        else:
            tag = _canonical(match.group(1))
        if tag:
            found.append(tag)
    return found


def last_tag(name: str) -> str:
    """What a dataset now is: the last tag of its name; "" for one as read."""
    tags = tags_in(name)
    return tags[-1] if tags else ""


def tag_rank(tag: str) -> int:
    """Where a tag stands in :data:`TAGS`: -1 for none (a measurement as
    read, first), past the table for a tag it does not have."""
    if not tag:
        return -1
    return _RANK.get(str(tag).casefold(), len(TAGS))


def _natural(text: str):
    return [(0, int(part), "") if part.isdigit() else (1, 0, part.lower())
            for part in re.split(r"(\d+)", str(text)) if part]


def type_sort_key(name: str, kind: str = ""):
    """The key that groups a list by processing type: the last tag (in the
    table's order, measurements first), then the kind (cut, map ...), then
    the name, numbers compared as numbers."""
    tag = last_tag(name)
    return (tag_rank(tag), tag.casefold(), str(kind or "").lower(),
            _natural(name))


def naming_rule() -> str:
    """The rule in a few lines, with the table: what an agent is shown."""
    lines = ["A processed dataset is named after its source with one tag in "
             "square brackets per step, oldest first, e.g. "
             "'Map80eV [norm] [E-E_F] [k]'. Use these tags (in processing "
             "order); one not in the table still goes in brackets:"]
    lines += [f"  [{tag}]  {what}" for tag, what in TAGS]
    return "\n".join(lines)
