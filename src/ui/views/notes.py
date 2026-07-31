"""Page: Technical notes — renders docs/journal/notes/ inside the app.

These notes are the most carefully researched material in the project: every
figure carries its provenance, every model states its boundary, and corrections
are written out rather than silently applied. They existed only as files in the
repository, which meant nobody using the demo ever saw them.

Rendered from the markdown source rather than duplicated, so the files stay the
single copy. Frontmatter is parsed for the title, one-line summary, audience and
prerequisites, and presented as a header card instead of being dumped as YAML.
"""

from __future__ import annotations

import re
from pathlib import Path

import streamlit as st

from src.ui import components as ui

NOTES_DIR = Path(__file__).resolve().parents[3] / "docs" / "journal" / "notes"


def _split_frontmatter(text: str) -> tuple[dict, str]:
    """Return (frontmatter, body). Deliberately minimal — no YAML dependency for
    four scalar fields and one list."""
    if not text.startswith("---"):
        return {}, text
    _, fm, body = text.split("---", 2)
    meta: dict[str, str] = {}
    key = None
    for line in fm.splitlines():
        if not line.strip():
            continue
        m = re.match(r"^(\w+):\s*(.*)$", line)
        if m:
            key, val = m.group(1), m.group(2).strip()
            meta[key] = val.strip('"')
        elif key and line.startswith(("  -", "-")):
            meta[key] = (meta.get(key, "") + " " + line.lstrip(" -")).strip()
    return meta, body.lstrip()


@st.cache_data(ttl=300, show_spinner=False)
def _load_notes() -> list[dict]:
    out = []
    for f in sorted(NOTES_DIR.glob("[0-9]*.md")):
        meta, body = _split_frontmatter(f.read_text())
        out.append({
            "file": f.name,
            "num": f.name.split("-")[0],
            "title": meta.get("title", f.stem),
            "one_line": meta.get("one_line", ""),
            "date": meta.get("date", ""),
            "tags": meta.get("tags", "").strip("[]"),
            "prereq": meta.get("prerequisites", ""),
            "body": body,
        })
    return out


def render() -> None:
    notes = _load_notes()
    if not notes:
        st.warning(f"No notes found at {NOTES_DIR}.")
        return

    st.markdown("""
<div class="callout">
  <div class="h">Technical notes</div>
  <p>Applied notes written from this demonstrator, for readers evaluating quantum
  optimization. Every figure is <b>measured</b>, <b>computed from first principles</b>,
  or <b>cited</b> — and says which. Every model states its boundary where its results
  are presented. Where a claim here was wrong, the correction is written out rather
  than quietly edited, because how a number was fixed is usually more instructive
  than the number.</p>
</div>""", unsafe_allow_html=True)

    labels = [f"{n['num']} · {n['title']}" for n in notes]
    choice = st.radio("Note", labels, label_visibility="collapsed")
    note = notes[labels.index(choice)]

    meta_bits = []
    if note["date"]:
        meta_bits.append(note["date"])
    if note["prereq"]:
        meta_bits.append(f"Prerequisites: {note['prereq']}")
    if note["tags"]:
        meta_bits.append(note["tags"].replace(",", " ·"))

    st.markdown(ui.card_html(
        "In one paragraph",
        f"<p>{note['one_line']}</p>"
        + (f"<p class='fine'>{' &nbsp;·&nbsp; '.join(meta_bits)}</p>" if meta_bits else "")),
        unsafe_allow_html=True)

    # The body already opens with its own H1; drop it so it does not repeat the
    # title the selector just showed.
    body = re.sub(r"^#\s+.*\n", "", note["body"], count=1)
    st.markdown(body)

    st.markdown("---")
    st.caption(f"Source: `docs/journal/notes/{note['file']}` — "
               "these render from the repository files, which stay the single copy.")
