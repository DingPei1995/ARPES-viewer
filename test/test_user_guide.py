"""The user guides: assembled from their parts, every link and picture in
place."""
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "devtools"))
import build_guide  # noqa: E402

LANGS = build_guide.LANGS


def _anchors(text):
    """Every anchor the headings of ``text`` make, as GitHub numbers
    repeated ones."""
    seen, out, fenced = {}, set(), False
    for line in text.splitlines():
        if line.startswith("```"):
            fenced = not fenced
            continue
        match = None if fenced else re.match(r"^#{1,6} (.+?)\s*$", line)
        if match:
            base = build_guide.slug(match.group(1))
            count = seen.get(base, 0)
            out.add(base if count == 0 else f"{base}-{count}")
            seen[base] = count + 1
    return out


@pytest.mark.parametrize("lang", LANGS)
def test_the_guide_is_what_its_parts_make(lang):
    with open(build_guide.target(lang), encoding="utf-8") as handle:
        assert handle.read() == build_guide.build(lang), (
            "run python devtools/build_guide.py")


@pytest.mark.parametrize("lang", LANGS)
def test_every_link_in_the_guide_leads_somewhere(lang):
    text = build_guide.build(lang)
    anchors = _anchors(text)
    missing = sorted({a for a in re.findall(r"\]\(#([^)\s]+)\)", text)
                      if a not in anchors})
    assert not missing, f"{lang}: no heading for {missing}"
    docs = build_guide.DOCS
    for target in re.findall(r'(?:\]\(|src=")([^)"\s#]+)', text):
        if re.match(r"^(https?:|mailto:)", target):
            continue
        assert os.path.exists(os.path.normpath(os.path.join(docs, target))), (
            f"{lang}: {target} does not exist")


def test_the_parts_are_the_same_in_every_language():
    names = {lang: [os.path.basename(p) for p in build_guide.parts(lang)]
             for lang in LANGS}
    assert names["zh"] == names["en"] == names["fr"]
    numbers = {lang: re.findall(r"^## (\d+\.\d+) ", build_guide.build(lang), re.M)
               for lang in LANGS}
    assert numbers["zh"] == numbers["en"] == numbers["fr"]
