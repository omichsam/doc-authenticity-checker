"""
PWD Document Checker — Streamlit showcase for the tampering CNN.

Install the dependencies with `python -m pip install -r requirements.txt`.
    python -m streamlit run app.py
"""
from __future__ import annotations

import json
import random
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

from tamper_core import (FORGERY_INFO, QUALITY_CUTOFFS, QUALITY_FACTORS, TEST_TYPES, Checker,
                         draw_boxes, heat_overlay, load_image, make_forgery, mask_outline, post_process,
                         quality, resize_long, suspicious_regions)

HERE = Path(__file__).resolve().parent
MODEL_PATH = HERE / "tamper_cnn.pt"
SAMPLES = HERE / "samples"
REPORTS = HERE / "reports"

st.set_page_config(page_title="PWD Document Checker", page_icon="🔎", layout="wide")

st.markdown("""
<style>
  .block-container {padding-top: 2rem; max-width: 1300px;}
  .pill {display:inline-block; padding: .25rem .75rem; border-radius: 999px; font-weight: 600; font-size: .9rem;}
  .ok   {background:#dcfce7; color:#166534;}
  .warn {background:#fef3c7; color:#92400e;}
  .bad  {background:#fee2e2; color:#991b1b;}
  .muted {color:#6b7280; font-size:.9rem;}
  .big {font-size: 2.6rem; font-weight: 700; line-height: 1.1;}
  .card {border:1px solid rgba(128,128,128,.25); border-radius: 12px; padding: 1rem 1.2rem; margin-bottom: .8rem;}
</style>
""", unsafe_allow_html=True)


# --------------------------------------------------------------------------- model
@st.cache_resource(show_spinner="Loading model …")
def get_checker(path: str, mtime: float) -> Checker:  # mtime busts the cache after retraining
    return Checker.load(path)


checker = None
model_error = None
if MODEL_PATH.exists():
    try:
        checker = get_checker(str(MODEL_PATH), MODEL_PATH.stat().st_mtime)
    except (OSError, RuntimeError, ValueError) as exc:
        model_error = str(exc)


def pill(text, kind):
    return f'<span class="pill {kind}">{text}</span>'


QUAL_KIND = {"GOOD": "ok", "ACCEPTABLE": "warn", "POOR": "bad"}
CHANGE_NAMES = {"field_edit": "Replace writing", "copy_move": "Copy within the page",
                "splice": "Paste from another page", "erase": "Erase writing (new to the checker)"}
QUAL_LABEL = {"GOOD": "Good — the picture is clear", "ACCEPTABLE": "Acceptable — the picture can be used",
              "POOR": "Poor — the picture is not clear enough"}

# --------------------------------------------------------------------------- sidebar
with st.sidebar:
    st.header("Checker")
    if checker:
        m = checker.meta
        t = m.get("test", {})
        st.markdown(pill("Ready", "ok"), unsafe_allow_html=True)
        st.caption(f"File: `{MODEL_PATH.name}` · trained: {m.get('trained_at', 'unknown').replace('T', ' ')}"
                   f" · {'short practice run' if m.get('config', {}).get('quick') else 'full training'}"
                   f" · running on: {checker.device.type.upper()}")
        if t:
            c1, c2 = st.columns(2)
            c1.metric("Test AUC", f"{t['auc']:.2f}",
                      help="How well the checker tells real pages from changed pages in testing. 1.00 is perfect, "
                           "0.50 is no better than guessing.")
            c2.metric("Test F1", f"{t['f1']:.2f}",
                      help="How well the checker balances catching changes against false alarms. 1.00 is perfect.")
        st.divider()
        thr = st.slider("Warning level", 0.01, 0.999, float(checker.threshold), 0.001, format="%.3f",
                        help="Pages that score at or above this level get a red warning. "
                             "The starting value was chosen when the checker was tested. "
                             "Lower = catches more changes, but more real pages get a warning by mistake.")
        alpha = st.slider("Colour strength on the map", 0.2, 0.9, 0.6, 0.05,
                          help="Only changes how strong the colours look. It does not change any result.")
    elif model_error:
        st.markdown(pill("Checker could not start", "bad"), unsafe_allow_html=True)
        st.error(f"The file `{MODEL_PATH.name}` could not be opened: {model_error}")
        thr, alpha = 0.5, 0.6
    else:
        st.markdown(pill("Checker not set up yet", "bad"), unsafe_allow_html=True)
        st.write("The picture-clarity check still works. To turn on the check for changes, "
                 "run the training notebook first:")
        st.code("PWD_Tamper_CNN_Simple.ipynb", language="text")
        thr, alpha = 0.5, 0.6
    st.divider()
    st.caption("This tool only helps you decide what to look at. It cannot prove that a document is real or fake. "
               "A trained person always makes the final decision.")

# --------------------------------------------------------------------------- header
st.title("🔎 PWD Document Checker")
st.markdown("Upload a picture of a document. The app checks two things: **is the picture clear enough**, and "
            "**does any part of the page look changed**. If something looks changed, it shows you *where*.")

tab_check, tab_lab, tab_how = st.tabs(["📄 Check a document", "🧪 Forgery lab", "⚙️ How it works"])


def sample_files():
    return sorted(SAMPLES.glob("*.jpg")) if SAMPLES.exists() else []


def show_quality(img):
    score, cat, parts = quality(img)
    st.markdown(f'<div class="card"><div class="muted">How clear is the picture?</div>'
                f'<div class="big">{score:.0f}%</div>{pill(QUAL_LABEL[cat], QUAL_KIND[cat])}</div>',
                unsafe_allow_html=True)
    for k, (_, desc) in QUALITY_FACTORS.items():
        st.progress(parts[k], text=f"**{k.title()}** {parts[k] * 100:.0f}% — {desc}")
    if cat == "POOR":
        st.warning("The picture is not clear enough. Please ask for a clearer scan or photo. "
                   "On an unclear picture, the check for changes can easily be wrong.")
    return score, cat, parts


# Share of real pages in each band at the default warning level, measured on 122 real test pages.
REAL_PAGE_SHARE = {"low": "about 1 in 5", "mid": "about 3 in 4", "high": "about 1 in 14"}


def explain_scores(q_score, q_parts, score=None):
    with st.expander("ℹ️ What do these scores mean?"):
        calc = " + ".join(f"{w:.0%} × {q_parts[k] * 100:.0f}% {k}" for k, (w, _) in QUALITY_FACTORS.items())
        st.markdown(f"""
**How clear is the picture?** — looks only at the picture, not at what is written.

Four checks each give a score from 0% to 100%, and they are added up. Sharpness counts the most,
because blur hides signs of changes more than anything else.
Your picture: {calc} = **{q_score:.0f}%**.

- **{QUALITY_CUTOFFS['GOOD']}% or more — Good:** clear enough to check.
- **{QUALITY_CUTOFFS['POOR']}% to {QUALITY_CUTOFFS['GOOD'] - 1}% — Acceptable:** usable, but read the change score with some care.
- **Below {QUALITY_CUTOFFS['POOR']}% — Poor:** ask for a clearer picture. Don't trust the change score.
""")
        if score is None:
            return
        band = "high" if score >= thr else "mid" if score >= thr * 0.7 else "low"
        default = abs(thr - checker.threshold) < 1e-6
        rows = [("low", f"Below {thr * 70:.0f}%", "✔ No signs of changes found"),
                ("mid", f"{thr * 70:.0f}% to {thr * 100:.1f}%", "Nothing clear found, but close to the warning level"),
                ("high", f"{thr * 100:.1f}% or more", "⚠ Possible changes found")]
        table = ("| Change score | Message | How often real pages get it |\n|---|---|---|\n" if default else
                 "| Change score | Message |\n|---|---|\n")
        for key, rng, msg in rows:
            mark = " **◀ your page**" if key == band else ""
            table += f"| {rng}{mark} | {msg} |" + (f" {REAL_PAGE_SHARE[key]} |\n" if default else "\n")
        st.markdown(f"""
**Change score** — how unusual the most unusual spot on the page looks.

The checker gives every small spot on the page a score for how much it looks changed. The change score is the
score of the **single most unusual spot**. That's why one small change can give the whole page a high score.

**It is not the chance that the document is fake.** A score of 90% does *not* mean "90% likely to be fake".
Real pages often score high too, because almost every page has a few spots that look a little unusual:
a logo, a stamp, handwriting, a fold or a shadow. That's why the warning level is set very high.

Your page: **{score * 100:.0f}%**.

{table}
{"" if default else "*You changed the warning level, so the table uses your new level.*"}

**Scores on the zoomed spots** (for example "score 98%") belong to those single spots. A box is drawn around every
spot that scores 50% or more, so boxes appear on real pages too. A spot's score can be a little higher than the
page's change score, because the page score ignores very tiny specks.
""")


def verdict(score):
    if score >= thr:
        return pill("⚠ Possible changes found — a person should check this page", "bad")
    if score >= thr * 0.7:
        return pill("Nothing clear found, but the score is close to the warning level", "warn")
    return pill("✔ No signs of changes found", "ok")


def verdict_note(score):
    if score >= thr:
        return "Look at the boxed spots on the colour map. This is a warning, not proof."
    if score >= thr * 0.7:
        return "This is common for real pages. Look at the boxed spots only if something seems wrong."
    return "Some kinds of changes can still be missed."


# --------------------------------------------------------------------------- tab 1: check
with tab_check:
    src_col, _ = st.columns([2, 1])
    with src_col:
        up = st.file_uploader("Upload a scan or photo of the document (PNG, JPG, WEBP, TIFF or BMP — not PDF)",
                              type=["png", "jpg", "jpeg", "webp", "tif", "tiff", "bmp"])
        samples = sample_files()
        pick = None
        if not up and samples:
            pick = st.selectbox("…or try one of our example pages", ["—"] + [s.name for s in samples])
    img = None
    if up:
        try:
            img = load_image(up.getvalue())
        except ValueError as exc:
            st.error(str(exc))
        else:
            st.session_state["last_upload"] = (up.name, img)
    elif pick and pick != "—":
        img = load_image(SAMPLES / pick)

    if img is not None:
        left, right = st.columns([3, 2], gap="large")
        with right:
            q_score, _, q_parts = show_quality(img)
            if checker:
                with st.spinner("Checking the page for changes …"):
                    work, prob, score = checker.predict(img)
                st.markdown(f'<div class="card"><div class="muted">Change score (higher = more likely changed)</div>'
                            f'<div class="big">{score * 100:.0f}%</div>{verdict(score)}'
                            f'<div class="muted" style="margin-top:.4rem">{verdict_note(score)}<br>'
                            f'Warning level: {thr * 100:.1f}%</div></div>',
                            unsafe_allow_html=True)
            explain_scores(q_score, q_parts, score if checker else None)
        with left:
            if checker:
                regions = suspicious_regions(prob, thr=0.5)
                v1, v2 = st.columns(2)
                v1.image(work, caption="Your page", width="stretch")
                v2.image(draw_boxes(heat_overlay(work, prob, alpha), regions), width="stretch",
                         caption="Colour map: blue = looks normal · yellow to red = may have been changed · "
                                 "boxes = spots to look at")
                if regions:
                    st.markdown("**Spots to look at first** (zoomed in, most likely first)")
                    cols = st.columns(min(3, len(regions)))
                    for c, (x, y, w, h, p) in zip(cols, regions[:3]):
                        pad = 25
                        y0, x0 = max(0, y - pad), max(0, x - pad)
                        c.image(work[y0:y + h + pad, x0:x + w + pad], caption=f"score {p:.0%}", width="stretch")
            else:
                st.image(img, caption="Your page", width="stretch")
                st.info("The check for changes is not set up yet. Run the training notebook to turn it on.")
    else:
        st.info("Upload a scan or photo of a document to start.")

# --------------------------------------------------------------------------- tab 2: lab
with tab_lab:
    st.markdown("Practise here to see what the checker can and can't find. The app **changes a real page on "
                "purpose**, so we know exactly what was changed. Then it checks whether the checker finds the change.  \n"
                "**Green outline** = what was really changed · **Colour map** = what the checker found.")
    if not checker:
        st.warning("The checker is not set up yet. Run the training notebook first, then come back here.")
    else:
        opts = [s.name for s in sample_files()]
        if "last_upload" in st.session_state:
            opts = [f"Your upload: {st.session_state['last_upload'][0]}"] + opts
        if not opts:
            st.info("There is no page to practise on yet. Upload a document in the first tab, then come back here.")
        else:
            c1, c2, c3 = st.columns([2, 2, 1])
            page = c1.selectbox("Real page to change", opts)
            kind = c2.radio("Type of change", TEST_TYPES, horizontal=True, format_func=CHANGE_NAMES.get)
            if "seed" not in st.session_state:
                st.session_state.seed = 7
            c3.write("")
            if c3.button("🎲 Try a different change", width="stretch"):
                st.session_state.seed = random.randint(0, 10**6)
            st.caption(FORGERY_INFO[kind])

            base = (st.session_state["last_upload"][1] if page.startswith("Your upload")
                    else load_image(SAMPLES / page))
            base = resize_long(base)
            others = [s for s in sample_files() if s.name != page]
            donor = resize_long(load_image(others[st.session_state.seed % len(others)])) if others else base

            rng = random.Random(st.session_state.seed)
            forged, mask = make_forgery(base, kind, rng, donor=donor)
            if not mask.any():
                st.warning(
                    "The app could not find suitable writing to change on this page. "
                    "Choose another page, or press 🎲 Try a different change."
                )
            else:
                # Apply the same JPEG re-save to both versions for a fair comparison.
                orig_pp = post_process(base, random.Random(st.session_state.seed + 1))
                forged_pp = post_process(forged, random.Random(st.session_state.seed + 1))

                with st.spinner("Checking the page before and after the change …"):
                    _, prob_o, s_o = checker.predict(orig_pp)
                    _, prob_f, s_f = checker.predict(forged_pp)

                m1, m2, m3 = st.columns(3)
                m1.markdown(f'<div class="card"><div class="muted">Before the change (should be low)</div>'
                            f'<div class="big">{s_o * 100:.0f}%</div>{verdict(s_o)}</div>', unsafe_allow_html=True)
                m2.markdown(f'<div class="card"><div class="muted">After the change (should be high)</div>'
                            f'<div class="big">{s_f * 100:.0f}%</div>{verdict(s_f)}</div>', unsafe_allow_html=True)
                pred = prob_f > 0.5
                inter, union = (pred & (mask > 0)).sum(), (pred | (mask > 0)).sum()
                hit = s_f >= thr and s_o < thr
                m3.markdown(f'<div class="card"><div class="muted">Did it find the right spot? '
                            f'(0% = missed it, 100% = exactly right)</div>'
                            f'<div class="big">{inter / max(1, union):.0%}</div>'
                            f'{pill("✔ Change found, and the real page passed" if hit else "✖ Change missed, or the real page got a warning", "ok" if hit else "warn")}'
                            f'</div>', unsafe_allow_html=True)
                with st.expander("ℹ️ What do these scores mean?"):
                    st.markdown(f"""
**Before the change** and **After the change** are change scores, the same score as on the *Check a document*
tab: how unusual the most unusual spot on the page looks. A good result is **before below the warning level
({thr * 100:.1f}%)** and **after at or above it**. Here: before **{s_o * 100:.0f}%**, after **{s_f * 100:.0f}%**.

**Did it find the right spot?** compares two areas:
- the area the checker marked (every spot scoring 50% or more), and
- the area that was really changed (the green outline).

It is the part where both areas overlap, divided by the two areas together.
**100%** = exactly the same area. **0%** = no overlap at all. **Above about 50%** is a good match.
A red warning with a low number means the checker noticed something, but pointed at the wrong place,
or marked a much bigger or smaller area than the real change.
""")

                ys, xs = np.nonzero(mask)
                pad = 60
                y0, y1 = max(0, ys.min() - pad), min(mask.shape[0], ys.max() + pad)
                x0, x1 = max(0, xs.min() - 2 * pad), min(mask.shape[1], xs.max() + 2 * pad)
                st.markdown("**Close-up of the changed spot**")
                z1, z2, z3 = st.columns(3)
                z1.image(orig_pp[y0:y1, x0:x1], caption="Before", width="stretch")
                z2.image(mask_outline(forged_pp, mask)[y0:y1, x0:x1], caption="After (green = what was changed)",
                         width="stretch")
                z3.image(heat_overlay(forged_pp, prob_f, alpha)[y0:y1, x0:x1], caption="What the checker found",
                         width="stretch")

                st.markdown("**Whole page**")
                w1, w2, w3 = st.columns(3)
                w1.image(forged_pp, caption="Page after the change", width="stretch")
                w2.image(mask_outline(forged_pp, mask), caption="What was changed (green)", width="stretch")
                w3.image(heat_overlay(forged_pp, prob_f, alpha), caption="What the checker found", width="stretch")

# --------------------------------------------------------------------------- tab 3: how
with tab_how:
    st.subheader("How the checker was made")
    st.markdown("""
1. **Real pages to learn from.** The checker learned only from real, unchanged forms: medical-style forms
   (*ClinOCR-Bench*) and real scanned forms (*FUNSD*). The pages were split into three groups: one to learn
   from, one to fine-tune with, and one for the final test. A form's layout appears in only one group,
   so the test is fair.
2. **Picture clarity.** A simple fixed rule, explained in the table below. No learning is involved.
3. **Practice changes.** The app made its own fake changes to the real pages: *replace writing*,
   *copy within the page* and *paste from another page*. A fourth kind, **erase writing**, was kept
   back and used only in the final test, to see if the checker can spot a kind of change it never practised on.
   Real and changed pages were saved in the same way, so the checker can't cheat by spotting a difference in file type.
4. **The checker.** A small computer model looks at the page and at its fine "grain" (scanners and
   cameras leave a grain pattern, and changes often break it). For every spot on the page it gives a
   score, which becomes the **colour map**. The page's **change score** comes from its most unusual spot.
5. **The test.** The checker was tested on pages it had never seen, both as real pages and with each kind of change.
""")
    st.subheader("How picture clarity is measured")
    st.dataframe(pd.DataFrame([{"What we check": k.title(), "How much it counts": f"{w:.0%}", "Question": d}
                               for k, (w, d) in QUALITY_FACTORS.items()]), hide_index=True, width="stretch")
    st.caption(f"Poor: below {QUALITY_CUTOFFS['POOR']}% · Acceptable: {QUALITY_CUTOFFS['POOR']}% to "
               f"{QUALITY_CUTOFFS['GOOD'] - 1}% · Good: {QUALITY_CUTOFFS['GOOD']}% and above")

    if checker and checker.meta.get("test"):
        t = checker.meta["test"]
        st.subheader("Test results")
        c = st.columns(5)
        for col, (lab, key, tip) in zip(c, [
                ("AUC", "auc", "How well it tells real from changed pages. 1.000 is perfect, 0.500 is guessing."),
                ("Correct", "accuracy", "Share of test pages it got right."),
                ("Warnings that were right", "precision", "Of the pages it warned about, the share that were really changed."),
                ("Changes found", "recall", "Of the changed pages, the share it found."),
                ("False alarms", "false_alarm_rate", "Of the real pages, the share that got a warning by mistake.")]):
            col.metric(lab, f"{t[key]:.0%}" if key != "auc" else f"{t[key]:.3f}", help=tip)
        rows = [{"Type of change": CHANGE_NAMES.get(k, k.replace("_", " ")),
                 "Practised in training": "yes" if r["seen_in_training"] else "no (new)",
                 "AUC": round(r["auc"], 3), "Found at the warning level": f"{r['detected']:.0%}",
                 "Found the right spot (pixel F1)": round(r["pixel_f1"], 3)} for k, r in t["per_type"].items()]
        a, b = st.columns([3, 2])
        a.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        cm = t["confusion_matrix"]
        a.caption(f"At warning level {t['threshold']:.2f}: real pages — {cm[0][0]} passed, {cm[0][1]} warned by mistake · "
                  f"changed pages — {cm[1][1]} found, {cm[1][0]} missed · {t['n_images']} test pages in total")
        if (REPORTS / "roc.png").exists():
            b.image(str(REPORTS / "roc.png"), width="stretch")
        hist = pd.DataFrame(checker.meta.get("history", []))
        if len(hist):
            st.markdown("**Training progress** (loss should go down, val_auc should go up)")
            st.line_chart(hist.set_index("epoch")[["loss", "val_auc"]])
        cfg = checker.meta.get("config", {})
        st.caption("Training settings: " + json.dumps(cfg))

    st.subheader("What the checker can't do")
    st.markdown("""
- It practised only on **changes the app made itself**. Real fake documents made with other tools may look different.
- On **unclear or heavily compressed pictures**, signs of changes get hidden. Always check picture clarity first.
- Results from a *short practice run* of training are only a test of the setup. Don't rely on them.
- **It only helps you decide what to look at.** A trained person always makes the final decision.
""")
