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

from tamper_core import (FORGERY_INFO, QUALITY_CUTOFFS, QUALITY_FACTORS, TEST_TYPES, TRAIN_TYPES, Checker,
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

# --------------------------------------------------------------------------- sidebar
with st.sidebar:
    st.header("Model")
    if checker:
        m = checker.meta
        t = m.get("test", {})
        st.markdown(pill("Loaded", "ok"), unsafe_allow_html=True)
        st.caption(f"`{MODEL_PATH.name}` · trained {m.get('trained_at', '?').replace('T', ' ')}"
                   f" · {'quick test run' if m.get('config', {}).get('quick') else 'full run'}"
                   f" · {checker.device.type.upper()}")
        if t:
            c1, c2 = st.columns(2)
            c1.metric("Test AUC", f"{t['auc']:.2f}")
            c2.metric("Test F1", f"{t['f1']:.2f}")
        st.divider()
        thr = st.slider("Flag threshold", 0.01, 0.99, float(round(checker.threshold, 2)), 0.01,
                        help="Pages scoring at or above this are flagged for review. The default was picked "
                             "on the validation set. Lower = catches more edits but more false alarms.")
        alpha = st.slider("Heat-map strength", 0.2, 0.9, 0.6, 0.05)
    elif model_error:
        st.markdown(pill("Model could not be loaded", "bad"), unsafe_allow_html=True)
        st.error(f"Could not load `{MODEL_PATH.name}`: {model_error}")
        thr, alpha = 0.5, 0.6
    else:
        st.markdown(pill("No model yet", "bad"), unsafe_allow_html=True)
        st.write("Train one first (the quality check works without it):")
        st.code("python train.py --quick", language="bash")
        thr, alpha = 0.5, 0.6
    st.divider()
    st.caption("Screening aid only. A result never proves a document is genuine or forged — "
               "a qualified person makes the decision.")

# --------------------------------------------------------------------------- header
st.title("🔎 PWD Document Checker")
st.markdown("Checks an uploaded document image for **image quality** and **signs of editing**, "
            "and shows *where* any editing is likely.")

tab_check, tab_lab, tab_how = st.tabs(["📄 Check a document", "🧪 Forgery lab", "⚙️ How it works"])


def sample_files():
    return sorted(SAMPLES.glob("*.jpg")) if SAMPLES.exists() else []


def show_quality(img):
    score, cat, parts = quality(img)
    st.markdown(f'<div class="card"><div class="muted">Image quality</div>'
                f'<div class="big">{score:.0f}%</div>{pill(cat, QUAL_KIND[cat])}</div>', unsafe_allow_html=True)
    for k, (w, desc) in QUALITY_FACTORS.items():
        st.progress(parts[k], text=f"**{k.title()}** {parts[k] * 100:.0f}% · weight {w:.0%} — {desc}")
    if cat == "POOR":
        st.warning("Quality is poor — ask for a clearer scan. Tampering results on poor images are less reliable.")
    return score, cat


def verdict(score):
    if score >= thr:
        return pill("Signs of editing — send for manual review", "bad")
    if score >= thr * 0.7:
        return pill("Borderline — no clear signs, but close to the threshold", "warn")
    return pill("No signs of editing found", "ok")


# --------------------------------------------------------------------------- tab 1: check
with tab_check:
    src_col, _ = st.columns([2, 1])
    with src_col:
        up = st.file_uploader("Upload a document image", type=["png", "jpg", "jpeg", "webp", "tif", "tiff", "bmp"])
        samples = sample_files()
        pick = None
        if not up and samples:
            pick = st.selectbox("…or try a sample page (from the untouched test set)", ["—"] + [s.name for s in samples])
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
            show_quality(img)
            if checker:
                with st.spinner("Looking for edits …"):
                    work, prob, score = checker.predict(img)
                st.markdown(f'<div class="card"><div class="muted">Tampering score</div>'
                            f'<div class="big">{score * 100:.0f}%</div>{verdict(score)}'
                            f'<div class="muted" style="margin-top:.4rem">Flag threshold: {thr * 100:.0f}%</div></div>',
                            unsafe_allow_html=True)
        with left:
            if checker:
                regions = suspicious_regions(prob, thr=0.5)
                v1, v2 = st.columns(2)
                v1.image(work, caption="Uploaded page", width="stretch")
                v2.image(draw_boxes(heat_overlay(work, prob, alpha), regions), width="stretch",
                         caption="Heat map: brighter = more likely edited; boxes = most suspicious areas")
                if regions:
                    st.markdown("**Most suspicious areas** (zoomed)")
                    cols = st.columns(min(3, len(regions)))
                    for c, (x, y, w, h, p) in zip(cols, regions[:3]):
                        pad = 25
                        y0, x0 = max(0, y - pad), max(0, x - pad)
                        c.image(work[y0:y + h + pad, x0:x + w + pad], caption=f"peak {p:.0%}", width="stretch")
            else:
                st.image(img, caption="Uploaded page", width="stretch")
                st.info("Train the model to see the tampering check: `python train.py --quick`")
    else:
        st.info("Upload a scanned or photographed document to start.")

# --------------------------------------------------------------------------- tab 2: lab
with tab_lab:
    st.markdown("Make a **known** edit to a genuine page, then see whether the model finds it. "
                "The green outline is the truth; the heat map is the model's guess.")
    if not checker:
        st.warning("Train the model first: `python train.py --quick`")
    else:
        opts = [s.name for s in sample_files()]
        if "last_upload" in st.session_state:
            opts = [f"Your upload: {st.session_state['last_upload'][0]}"] + opts
        if not opts:
            st.info("No sample pages found. Upload a document in the first tab, then come back here.")
        else:
            c1, c2, c3 = st.columns([2, 2, 1])
            page = c1.selectbox("Genuine page", opts)
            kind = c2.radio("Edit to make", TEST_TYPES, horizontal=True,
                            format_func=lambda k: k.replace("_", " ") + ("  (unseen)" if k not in TRAIN_TYPES else ""))
            if "seed" not in st.session_state:
                st.session_state.seed = 7
            c3.write("")
            if c3.button("🎲 New random edit", width="stretch"):
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
                    "Could not create this edit because no suitable text region was found. "
                    "Choose another page or try a new random edit."
                )
            else:
                # Apply the same JPEG re-save to both versions for a fair comparison.
                orig_pp = post_process(base, random.Random(st.session_state.seed + 1))
                forged_pp = post_process(forged, random.Random(st.session_state.seed + 1))

                with st.spinner("Scoring both versions …"):
                    _, prob_o, s_o = checker.predict(orig_pp)
                    _, prob_f, s_f = checker.predict(forged_pp)

                m1, m2, m3 = st.columns(3)
                m1.markdown(f'<div class="card"><div class="muted">Original page</div><div class="big">{s_o * 100:.0f}%</div>'
                            f'{verdict(s_o)}</div>', unsafe_allow_html=True)
                m2.markdown(f'<div class="card"><div class="muted">Edited page</div><div class="big">{s_f * 100:.0f}%</div>'
                            f'{verdict(s_f)}</div>', unsafe_allow_html=True)
                pred = prob_f > 0.5
                inter, union = (pred & (mask > 0)).sum(), (pred | (mask > 0)).sum()
                hit = s_f >= thr and s_o < thr
                m3.markdown(f'<div class="card"><div class="muted">Overlap with true edit (IoU)</div>'
                            f'<div class="big">{inter / max(1, union):.0%}</div>'
                            f'{pill("Edit caught, original passed" if hit else "Not a clean result", "ok" if hit else "warn")}'
                            f'</div>', unsafe_allow_html=True)

                ys, xs = np.nonzero(mask)
                pad = 60
                y0, y1 = max(0, ys.min() - pad), min(mask.shape[0], ys.max() + pad)
                x0, x1 = max(0, xs.min() - 2 * pad), min(mask.shape[1], xs.max() + 2 * pad)
                st.markdown("**Close-up of the edited spot**")
                z1, z2, z3 = st.columns(3)
                z1.image(orig_pp[y0:y1, x0:x1], caption="Before", width="stretch")
                z2.image(mask_outline(forged_pp, mask)[y0:y1, x0:x1], caption="After (green = true edit)", width="stretch")
                z3.image(heat_overlay(forged_pp, prob_f, alpha)[y0:y1, x0:x1], caption="Model heat map", width="stretch")

                st.markdown("**Whole page**")
                w1, w2, w3 = st.columns(3)
                w1.image(forged_pp, caption="Edited page", width="stretch")
                w2.image(mask_outline(forged_pp, mask), caption="True edit", width="stretch")
                w3.image(heat_overlay(forged_pp, prob_f, alpha), caption="Model heat map", width="stretch")

# --------------------------------------------------------------------------- tab 3: how
with tab_how:
    st.subheader("Pipeline")
    st.markdown("""
1. **Data** — genuine pages only: *ClinOCR-Bench* (synthetic clinical forms, closest to medical/disability paperwork)
   and *FUNSD* (real scanned forms). Split 70/15/15 **by source template**, so no layout appears in two splits.
2. **Quality score** — a transparent rule, no training (table below).
3. **Synthetic forgeries** — edits made on the fly: *field edit*, *copy-move*, *splice*. A fourth, **erase**,
   is held back for testing only, to check the model generalises to edits it never saw.
   Genuine and edited images get the same JPEG re-saving, so the model can't cheat by spotting compression.
4. **CNN** — a small U-Net that sees the page plus fixed noise-residual filters (edits leave seams in the
   scanner/JPEG noise). It outputs a per-pixel “edited” probability → the **heat map**.
   The page **tampering score** is the average of its most suspicious ~0.05 % of pixels, and training
   optimises that score directly so genuine pages stay low everywhere.
5. **Evaluation** — on the untouched test pages, each scored as genuine and once per edit type.
""")
    st.subheader("Quality score")
    st.dataframe(pd.DataFrame([{"Factor": k.title(), "Weight": f"{w:.0%}", "Measures": d}
                               for k, (w, d) in QUALITY_FACTORS.items()]), hide_index=True, width="stretch")
    st.caption(f"POOR < {QUALITY_CUTOFFS['POOR']} ≤ ACCEPTABLE < {QUALITY_CUTOFFS['GOOD']} ≤ GOOD")

    if checker and checker.meta.get("test"):
        t = checker.meta["test"]
        st.subheader("Test-set results")
        c = st.columns(5)
        for col, (lab, key) in zip(c, [("AUC", "auc"), ("Accuracy", "accuracy"), ("Precision", "precision"),
                                       ("Recall", "recall"), ("False alarms", "false_alarm_rate")]):
            col.metric(lab, f"{t[key]:.0%}" if key != "auc" else f"{t[key]:.3f}")
        rows = [{"Edit type": k.replace("_", " "), "Seen in training": "yes" if r["seen_in_training"] else "no (unseen)",
                 "AUC": round(r["auc"], 3), "Caught at threshold": f"{r['detected']:.0%}",
                 "Pixel F1 (location)": round(r["pixel_f1"], 3)} for k, r in t["per_type"].items()]
        a, b = st.columns([3, 2])
        a.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        cm = t["confusion_matrix"]
        a.caption(f"Confusion matrix at threshold {t['threshold']:.2f} — genuine: {cm[0][0]} passed, {cm[0][1]} flagged · "
                  f"edited: {cm[1][1]} caught, {cm[1][0]} missed · {t['n_images']} test images")
        if (REPORTS / "roc.png").exists():
            b.image(str(REPORTS / "roc.png"), width="stretch")
        hist = pd.DataFrame(checker.meta.get("history", []))
        if len(hist):
            st.markdown("**Training history**")
            st.line_chart(hist.set_index("epoch")[["loss", "val_auc"]])
        cfg = checker.meta.get("config", {})
        st.caption("Training config: " + json.dumps(cfg))

    st.subheader("Limitations")
    st.markdown("""
- Trained on **synthetic** edits; real forgeries made in other tools may look different.
- Very poor or heavily compressed images hide editing traces — check the quality score first.
- A *quick* run is only a smoke test; use the full run before relying on the numbers.
- **Screening aid only.** A qualified person makes the decision.
""")
