"""Review-and-commit web app.

    streamlit run app.py

Upload a travel expense submission, review every proposed correction, pick
the right station where the tool cannot, and download a corrected workbook
with a change log. The uploaded file is never modified.
"""

from __future__ import annotations

import base64
import difflib
import hashlib
import io
from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st

from railvalidator.catalog import Catalog
from railvalidator.excel_io import build_commit_workbook, build_report_workbook, read_submission, workbook_bytes
from railvalidator.matcher import Matcher, Verdict
from railvalidator.normalise import normalise
from railvalidator.review import Change, Finding, apply_decisions, summarise, validate_submission

ROOT = Path(__file__).resolve().parent
SAMPLE = ROOT / "sample_submission.xlsx"
BANNER = ROOT / "assets" / "banner.png"
KEEP = "Leave unchanged"
TYPE_IT = "Type a station name"
NAVY = "#1F5F99"

# verdict: (hex for the stat cards, Streamlit colour name for tags, label, description)
VERDICT_STYLE = {
    "MATCH": ("#1F8A4C", "green", "Match", "Official name, nothing to do"),
    "ALIAS": ("#1C6FC7", "blue", "Alias", "Code, short form or former name"),
    "TYPO": ("#B15F00", "orange", "Typo", "Near-certain misspelling"),
    "AMBIGUOUS": ("#7B3FD1", "violet", "Ambiguous", "Several stations fit"),
    "UNKNOWN": ("#C83737", "red", "Unknown", "Nothing close in the catalog"),
}

CSS = f"""
<style>
/* Straight edges everywhere */
.stApp *, .stApp *::before, .stApp *::after {{ border-radius: 0 !important; }}
.block-container {{ padding-top: 2rem; }}

.banner {{ width: 100%; height: 260px; background-size: cover; background-position: center 55%; }}
.app-title {{ font-size: 52px; font-weight: 700; line-height: 1.1; letter-spacing: -0.5px; margin: 20px 0 10px; }}
.app-intro {{ font-size: 21px; line-height: 1.5; opacity: 0.8; margin-bottom: 8px; }}

/* Upload box: dashed, centred, big button */
.st-key-upload_box {{ border: 2px dashed #A9ADB7; background: #F4F5F7; padding: 36px 32px 28px; }}
.upload-head {{ text-align: center; }}
.upload-head .h {{ font-size: 24px; font-weight: 600; }}
.upload-head .s {{ font-size: 18px; opacity: 0.8; }}
.st-key-upload_box [data-testid="stFileUploaderDropzone"] {{
    flex-direction: column; align-items: center; justify-content: center; gap: 10px;
    background: transparent; border: none; padding: 8px 0 0; }}
.st-key-upload_box [data-testid="stFileUploaderDropzone"] button {{
    height: 60px; min-width: 300px; background: {NAVY}; border: none; color: #FFFFFF; }}
.st-key-upload_box [data-testid="stFileUploaderDropzone"] button p {{ font-size: 0; }}
.st-key-upload_box [data-testid="stFileUploaderDropzone"] button p::after {{
    content: "Choose file to upload"; font-size: 20px; font-weight: 700; }}
.st-key-upload_box [data-testid="stFileUploaderDropzoneInstructions"] {{ font-size: 15px; }}
.st-key-upload_box [data-testid="stElementContainer"]:has([data-testid="stCheckbox"]) {{
    align-self: center; width: auto !important; }}
.st-key-upload_box .stCheckbox p {{ font-size: 17px; }}

/* Loaded file line */
.file-line .name {{ font-size: 20px; font-weight: 600; }}
.file-line .meta {{ font-size: 15px; opacity: 0.75; }}

/* Stat cards */
.stat-grid {{ display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 16px; margin: 4px 0 12px; }}
@media (max-width: 800px) {{ .stat-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }} }}
.stat {{ padding: 18px 20px; border: 2px solid var(--c); display: flex; flex-direction: column; gap: 4px; }}
.stat .n {{ font-size: 40px; font-weight: 700; line-height: 1.05; color: var(--c); }}
.stat .l {{ font-size: 19px; font-weight: 700; color: var(--lc); }}
.stat .d {{ font-size: 15px; opacity: 0.75; }}
.bar {{ display: flex; height: 10px; overflow: hidden; background: #E4E6EA; }}
.bar span {{ display: block; height: 100%; }}
.bar-caption {{ font-size: 15px; opacity: 0.75; margin: 8px 0 4px; }}

/* Downloads, centred */
.dl-text {{ font-size: 19px; text-align: center; margin: 6px 0 10px; }}
.st-key-dl_corrected button, .st-key-dl_report button {{ height: 52px; }}
.st-key-dl_corrected button p, .st-key-dl_report button p {{ font-size: 17px; font-weight: 600; }}

/* Review bar */
.st-key-review_toggle button {{ width: 100%; padding: 20px 28px; height: auto; }}
.st-key-review_toggle button > div, .st-key-review_toggle button span {{ justify-content: flex-start; width: 100%; }}
.st-key-review_toggle button p {{ font-size: 17px; font-weight: 400; text-align: left; opacity: 0.85; }}
.st-key-review_toggle button p strong {{ font-size: 21px; font-weight: 700; opacity: 1; }}
.review-off {{ border: 1px solid #D3D5DB; padding: 20px 28px; display: flex; justify-content: space-between;
               align-items: center; }}
.review-off .t {{ font-size: 21px; font-weight: 700; opacity: 0.5; }}
.review-off .s {{ font-size: 16px; opacity: 0.7; }}

/* Diffs */
.diff {{ display: grid; grid-template-columns: 1fr auto 1fr; gap: 10px; align-items: stretch; margin: 4px 0 6px;
        font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 0.95rem; }}
.side {{ padding: 8px 12px; overflow-wrap: anywhere; border: 1px solid rgba(128, 128, 128, 0.4); }}
.side .label {{ display: block; font-family: inherit; font-size: 0.7rem; opacity: 0.55; margin-bottom: 2px; }}
.side del {{ opacity: 0.6; }}
.side ins {{ text-decoration: underline; font-weight: 700; }}
.side.pending {{ border-style: dashed; opacity: 0.7; }}
.arrow {{ align-self: center; opacity: 0.5; }}
.why {{ font-size: 0.9rem; opacity: 0.75; margin-bottom: 6px; }}
</style>
"""


@st.cache_resource
def load_catalog() -> tuple[Catalog, Matcher]:
    catalog = Catalog.load(ROOT / "data" / "stations.csv", ROOT / "data" / "aliases.csv")
    return catalog, Matcher(catalog)


# -- state ---------------------------------------------------------------------
# Decisions live in session state of their own, not in widget state, so they
# survive the review section being closed (Streamlit forgets hidden widgets).


def state() -> st.session_state:
    ss = st.session_state
    ss.setdefault("source", None)  # (bytes, file name) once a file is chosen
    ss.setdefault("uploader_n", 0)  # bumped to reset the uploader
    ss.setdefault("approved", set())  # {(row, column)}
    ss.setdefault("choices", {})  # {(row, column): station name}
    ss.setdefault("ver", 0)  # bumped to refresh checkboxes after Approve all / Clear all
    ss.setdefault("review_open", False)
    return ss


def reset_file() -> None:
    ss = st.session_state
    ss.source = None
    ss.uploader_n += 1
    ss.approved = set()
    ss.choices = {}
    ss.review_open = False
    ss.pop("key", None)


# -- helpers ------------------------------------------------------------------


def tag(verdict: str) -> str:
    """Coloured tag in Streamlit markdown, usable inside expander labels."""
    _, colour, label, _ = VERDICT_STYLE[verdict]
    return f":{colour}-badge[{label}]"


def cell_label(row: int, column: str) -> str:
    return f"Row {row + 2}, {column.replace('_', ' ')}"


def md_value(text: str) -> str:
    """A submitted value, quoted and escaped for use in a markdown label."""
    if not text:
        return "*(empty)*"
    for ch in "\\`*_[]":
        text = text.replace(ch, "\\" + ch)
    return f"'{text}'"


def diff_html(old: str, new: str | None) -> str:
    """Side-by-side diff with the changed characters struck through or underlined."""
    shown_old = escape(old) if old else "<em>(empty)</em>"
    if new is None:
        right = '<div class="side pending"><span class="label">Corrected</span><em>choose a station below</em></div>'
        left = f'<div class="side"><span class="label">Submitted</span>{shown_old}</div>'
        return f'<div class="diff">{left}<div class="arrow">\u2192</div>{right}</div>'

    matcher = difflib.SequenceMatcher(None, old.lower(), new.lower())
    if old and matcher.ratio() >= 0.6:
        left, right = [], []
        for op, i1, i2, j1, j2 in matcher.get_opcodes():
            if op == "equal":
                left.append(escape(old[i1:i2]))
                right.append(escape(new[j1:j2]))
                continue
            if i2 > i1:
                left.append(f"<del>{escape(old[i1:i2])}</del>")
            if j2 > j1:
                right.append(f"<ins>{escape(new[j1:j2])}</ins>")
        left_html, right_html = "".join(left), "".join(right)
    else:
        left_html = f"<del>{escape(old)}</del>" if old else shown_old
        right_html = f"<ins>{escape(new)}</ins>"
    return (
        f'<div class="diff"><div class="side"><span class="label">Submitted</span>{left_html}</div>'
        f'<div class="arrow">\u2192</div>'
        f'<div class="side"><span class="label">Corrected</span>{right_html}</div></div>'
    )


# -- sections -----------------------------------------------------------------


def render_header(catalog: Catalog) -> None:
    if BANNER.exists():
        data = base64.b64encode(BANNER.read_bytes()).decode()
        st.markdown(
            f'<div class="banner" role="img" aria-label="High-speed train on the track" '
            f'style="background-image:url(data:image/png;base64,{data})"></div>',
            unsafe_allow_html=True,
        )
    st.markdown(
        '<div class="app-title">Rail Station Validator</div>'
        f'<div class="app-intro">Checks station names in travel expense claims against {len(catalog):,} UK rail '
        "stations from NaPTAN. Nothing changes until you approve it.</div>",
        unsafe_allow_html=True,
    )


def render_upload(ss) -> None:
    """The big upload box. Stores the chosen file in session state and reruns."""
    with st.container(key="upload_box"):
        st.markdown(
            '<div class="upload-head"><div class="h">Upload a submission</div>'
            '<div class="s">Drag and drop an .xlsx file with from_station and to_station columns, '
            "or choose one</div></div>",
            unsafe_allow_html=True,
        )
        upload = st.file_uploader(
            "Upload a submission", type=["xlsx"], key=f"uploader-{ss.uploader_n}", label_visibility="collapsed"
        )
        sample = st.checkbox("Or try it with the sample submission", key=f"sample-{ss.uploader_n}")
    if upload is not None:
        ss.source = (upload.getvalue(), upload.name)
        st.rerun()
    if sample and SAMPLE.exists():
        ss.source = (SAMPLE.read_bytes(), SAMPLE.name)
        st.rerun()


def render_file_line(name: str, df: pd.DataFrame, findings: list[Finding]) -> None:
    with st.container(border=True):
        left, right = st.columns([4, 1], vertical_alignment="center")
        left.markdown(
            f'<div class="file-line"><div class="name">{escape(name)}</div>'
            f'<div class="meta">{len(df)} claims, {len(findings)} station cells checked</div></div>',
            unsafe_allow_html=True,
        )
        right.button("Replace file", on_click=reset_file, width="stretch")


def render_stats(counts: dict[str, int] | None) -> None:
    if counts is None:
        cards = "".join(
            f'<div class="stat" style="--c:#B4B8C1;--lc:inherit"><div class="n" style="color:#767A85">??</div>'
            f'<div class="l">{label}</div><div class="d">Upload to begin</div></div>'
            for _, _, label, _ in VERDICT_STYLE.values()
        )
        st.markdown(
            f'<div class="stat-grid">{cards}</div><div class="bar"></div>'
            '<div class="bar-caption">Results appear here once a file is uploaded</div>',
            unsafe_allow_html=True,
        )
        return
    total = sum(counts.values()) or 1
    cards = "".join(
        f'<div class="stat" style="--c:{VERDICT_STYLE[v][0]};--lc:{VERDICT_STYLE[v][0]}"><div class="n">{n}</div>'
        f'<div class="l">{VERDICT_STYLE[v][2]}</div><div class="d">{VERDICT_STYLE[v][3]}</div></div>'
        for v, n in counts.items()
    )
    bar = "".join(
        f'<span style="width:{n / total * 100:.2f}%;background:{VERDICT_STYLE[v][0]}" title="{v}: {n}"></span>'
        for v, n in counts.items()
        if n
    )
    clean = counts.get("MATCH", 0) / total * 100
    st.markdown(
        f'<div class="stat-grid">{cards}</div><div class="bar">{bar}</div>'
        f'<div class="bar-caption">{total} station cells checked, {clean:.0f}% already correct</div>',
        unsafe_allow_html=True,
    )


def render_downloads(slot, corrected=None, changes=None, df=None, findings=None, name: str = "") -> None:
    loaded = findings is not None
    changes = changes or []
    with slot.container(border=True):
        if loaded:
            noun = "change" if len(changes) == 1 else "changes"
            text = f"<strong>{len(changes)} {noun} approved.</strong> The original file stays as it is."
        else:
            text = "<strong>Nothing to download yet.</strong> Upload a file to begin."
        st.markdown(f'<div class="dl-text">{text}</div>', unsafe_allow_html=True)
        _, a, b, _ = st.columns([1, 1.3, 1.3, 1])
        a.download_button(
            "Download corrected workbook",
            data=workbook_bytes(build_commit_workbook(corrected, changes)) if loaded else b"",
            file_name=f"corrected_{name}",
            disabled=not changes,
            type="primary",
            width="stretch",
            key="dl_corrected",
        )
        b.download_button(
            "Download validation report",
            data=workbook_bytes(build_report_workbook(df, findings)) if loaded else b"",
            file_name=f"validation_{name}",
            disabled=not loaded,
            width="stretch",
            key="dl_report",
        )


def render_review_bar(ss, proposals: list[Finding] | None, manual: list[Finding] | None) -> None:
    if proposals is None:
        st.markdown(
            '<div class="review-off"><span class="t">\u203a&nbsp;&nbsp;Review changes</span>'
            '<span class="s">Available after upload</span></div>',
            unsafe_allow_html=True,
        )
        return
    arrow = "\u2304" if ss.review_open else "\u203a"
    hint = "click to hide" if ss.review_open else "click to show"
    label = (
        f"{arrow}\u2003**Review changes**\u2003\u2003{len(proposals)} proposed corrections, "
        f"{len(manual)} need your decision ({hint})"
    )

    def toggle() -> None:
        ss.review_open = not ss.review_open

    st.button(label, key="review_toggle", on_click=toggle, width="stretch")


def render_proposals(ss, proposals: list[Finding], key: str) -> None:
    if not proposals:
        st.info("No automatic corrections to review.")
        return

    def set_all(value: bool) -> None:
        ss.approved = {(f.row, f.column) for f in proposals} if value else set()
        ss.ver += 1

    left, right, _ = st.columns([1, 1, 4])
    left.button("Approve all", on_click=set_all, args=(True,), width="stretch")
    right.button("Clear all", on_click=set_all, args=(False,), width="stretch")

    def toggle(cell: tuple[int, str], widget: str) -> None:
        if st.session_state[widget]:
            ss.approved.add(cell)
        else:
            ss.approved.discard(cell)

    for f in proposals:
        cell = (f.row, f.column)
        widget = f"approve-{key}-{f.row}-{f.column}-{ss.ver}"
        status = " :gray-badge[Approved]" if cell in ss.approved else ""
        change = f"{md_value(f.value)} \u2192 {f.proposed_name}"
        label = f"{tag(f.verdict.value)} {cell_label(f.row, f.column)}: {change}{status}"
        with st.expander(label, key=f"exp-{key}-{f.row}-{f.column}"):
            st.markdown(diff_html(f.value, f.proposed_name), unsafe_allow_html=True)
            st.markdown(f'<div class="why">{escape(f.explanation)}</div>', unsafe_allow_html=True)
            st.checkbox(
                "Approve this correction", value=cell in ss.approved, key=widget, on_change=toggle, args=(cell, widget)
            )


def render_manual(ss, manual: list[Finding], key: str, catalog: Catalog) -> None:
    if not manual:
        st.info("Nothing needs a decision.")
        return

    def choose(cell: tuple[int, str], widget: str) -> None:
        value = st.session_state[widget]
        if value in (KEEP, TYPE_IT):
            ss.choices.pop(cell, None)
        else:
            ss.choices[cell] = value

    def typed(cell: tuple[int, str], widget: str) -> None:
        sid = catalog.by_name.get(normalise(st.session_state[widget]))
        if sid is None:
            ss.choices.pop(cell, None)
        else:
            ss.choices[cell] = catalog.station(sid).name

    for f in manual:
        cell = (f.row, f.column)
        current = ss.choices.get(cell)
        status = f" \u2192 {current} :gray-badge[Decided]" if current else ""
        label = f"{tag(f.verdict.value)} {cell_label(f.row, f.column)}: {md_value(f.value)}{status}"
        with st.expander(label, key=f"exp-{key}-{f.row}-{f.column}"):
            st.markdown(diff_html(f.value, current), unsafe_allow_html=True)
            st.markdown(f'<div class="why">{escape(f.explanation)}</div>', unsafe_allow_html=True)
            candidates = [c.name for c in f.result.candidates]
            options = [KEEP, *candidates, TYPE_IT]
            if current in candidates:
                index = options.index(current)
            elif current:
                index = len(options) - 1
            else:
                index = 0
            widget = f"choice-{key}-{f.row}-{f.column}"
            choice = st.selectbox("Correct to", options, index=index, key=widget, on_change=choose, args=(cell, widget))
            if choice == TYPE_IT:
                box = f"typed-{key}-{f.row}-{f.column}"
                entered = st.text_input(
                    "Official station name", value=current or "", key=box, on_change=typed, args=(cell, box)
                )
                if entered and catalog.by_name.get(normalise(entered)) is None:
                    st.warning(f"'{entered}' is not an official station name, so it will not be applied.")


def render_changes(changes: list[Change]) -> None:
    if not changes:
        st.info("No changes approved yet. Approve proposals or make decisions in the other tabs.")
        return
    for c in changes:
        st.markdown(f"{tag(c.verdict)} **{cell_label(c.row, c.column)}**")
        st.markdown(diff_html(c.old, c.new), unsafe_allow_html=True)


# -- page ---------------------------------------------------------------------


def main() -> None:
    st.set_page_config(page_title="Rail Station Validator", layout="wide", initial_sidebar_state="collapsed")
    st.markdown(CSS, unsafe_allow_html=True)
    catalog, matcher = load_catalog()
    ss = state()

    render_header(catalog)

    # Before a file is chosen: upload box, placeholder stats, nothing to download.
    if ss.source is None:
        render_upload(ss)
        render_stats(None)
        render_downloads(st.empty())
        render_review_bar(ss, None, None)
        return

    raw, name = ss.source
    key = hashlib.sha1(raw).hexdigest()[:12]
    if ss.get("key") != key:
        df = read_submission(io.BytesIO(raw))
        try:
            findings = validate_submission(df, catalog, matcher)
        except ValueError as exc:
            st.error(str(exc))
            st.button("Choose another file", on_click=reset_file)
            return
        ss.update(key=key, df=df, findings=findings)
    df: pd.DataFrame = ss["df"]
    findings: list[Finding] = ss["findings"]

    proposals = [f for f in findings if f.proposed_name is not None]
    manual = [f for f in findings if f.verdict in (Verdict.AMBIGUOUS, Verdict.UNKNOWN)]
    decisions = {cell: f.proposed_name for f in proposals if (cell := (f.row, f.column)) in ss.approved}
    decisions |= ss.choices
    corrected, changes = apply_decisions(df, findings, decisions)

    render_file_line(name, df, findings)
    render_stats(summarise(findings))
    render_downloads(st.empty(), corrected, changes, df, findings, name)
    render_review_bar(ss, proposals, manual)

    if ss.review_open:
        with st.container(border=True):
            tab_review, tab_decide, tab_log = st.tabs(
                [f"Proposed corrections ({len(proposals)})", f"Needs your decision ({len(manual)})", "Approved changes"]
            )
            with tab_review:
                render_proposals(ss, proposals, key)
            with tab_decide:
                render_manual(ss, manual, key, catalog)
            with tab_log:
                render_changes(changes)


main()
