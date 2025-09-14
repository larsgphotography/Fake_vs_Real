import os
import pandas as pd
import streamlit as st
from PIL import Image

# ── Config ─────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Spot the Manipulation", layout="wide")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WWW_DIR = os.path.join(BASE_DIR, "www")  # images live in www/fake and www/real
ROUNDS = 10  # how many per game

# ── Helpers ────────────────────────────────────────────────────────────────────
def _norm_rel_path(rel: str) -> str:
    """Normalize a CSV relative path like 'fake/fake1.jpg' for OS joins."""
    rel = rel.replace("\\", "/").strip()
    # join each segment to be safe on Windows
    return os.path.join(*rel.split("/")) if rel else rel

def _abs_from_rel(rel: str) -> str:
    """Absolute path under www/ for a CSV relative path."""
    return os.path.join(WWW_DIR, _norm_rel_path(rel))

@st.cache_data
def load_metadata(csv_path: str, rounds: int) -> pd.DataFrame:
    """
    Read CSV robustly, clean rows, ensure files exist, shuffle, return up to 'rounds'.
    CSV must have columns: fake_path, real_path, comment (comment optional).
    Paths must be relative to 'www' (e.g., fake/fake1.jpg, real/real1.jpg).
    """
    # Read everything as string to avoid NaN floats
    df = pd.read_csv(csv_path, dtype=str)

    # Standardize column names (lowercase) and trim
    df.columns = [c.strip().lower() for c in df.columns]

    required = {"fake_path", "real_path"}
    missing_cols = required - set(df.columns)
    if missing_cols:
        raise ValueError(f"CSV missing required columns: {sorted(missing_cols)}")

    # Trim whitespace in string cells
    df = df.applymap(lambda x: x.strip() if isinstance(x, str) else x)

    # Drop rows with missing/empty paths
    df = df.dropna(subset=["fake_path", "real_path"])
    df = df[(df["fake_path"] != "") & (df["real_path"] != "")]

    # Keep only rows where files actually exist
    def exists_row(row):
        fake_abs = _abs_from_rel(row["fake_path"])
        real_abs = _abs_from_rel(row["real_path"])
        return os.path.exists(fake_abs) and os.path.exists(real_abs)

    if len(df) == 0:
        return df

    df = df[df.apply(exists_row, axis=1)].reset_index(drop=True)

    if len(df) == 0:
        return df

    df = df.sample(frac=1, random_state=None).reset_index(drop=True)  # shuffle
    return df.head(min(rounds, len(df)))

def load_image(rel_path: str, max_width: int = 450):
    """
    Load image from www/ + rel_path and scale to max_width while keeping aspect ratio.
    Returns a PIL Image or None if missing.
    """
    if not isinstance(rel_path, str) or rel_path.strip() == "":
        return None
    abs_path = _abs_from_rel(rel_path)
    if not os.path.exists(abs_path):
        st.warning(f"Missing image: {abs_path}")
        return None
    img = Image.open(abs_path)
    if img.width > max_width:
        ratio = max_width / float(img.width)
        img = img.resize((max_width, int(img.height * ratio)), Image.LANCZOS)
    return img

def next_round():
    st.session_state.step += 1
    st.session_state.show_real = False

def record_answer():
    # This is a new function to be called by the 'Next' button's on_click
    # We need to grab the current state of the widgets before the script re-runs
    guess_text = st.session_state[f"guess_{st.session_state.step}"]
    correct_choice = st.session_state[f"correct_{st.session_state.step}"]
    st.session_state.answers.append({"guess": guess_text, "correct": correct_choice == "Yes"})
    next_round()

# ── Session state init ─────────────────────────────────────────────────────────
if "df" not in st.session_state:
    st.session_state.df = load_metadata("manipulation_info.csv", ROUNDS)
if "step" not in st.session_state:
    st.session_state.step = 0
if "answers" not in st.session_state:
    st.session_state.answers = []
if "show_real" not in st.session_state:
    st.session_state.show_real = False

df = st.session_state.df
total = len(df)

st.title("🕵️ Spot the Manipulation")

# Guard: no valid rows
if total == 0:
    st.error(
        "No valid rows to play.\n\n"
        "• Ensure CSV has columns: fake_path, real_path (comment optional)\n"
        "• Paths must be relative to 'www' (e.g., 'fake/fake1.jpg')\n"
        "• Files must exist in 'www/fake' and 'www/real'"
    )
    st.stop()

# ── Game loop ──────────────────────────────────────────────────────────────────
if st.session_state.step < total:
    row = df.iloc[st.session_state.step]
    fake_rel = row["fake_path"]
    real_rel = row["real_path"]
    comment = row.get("comment", "")

    st.markdown(f"### Round {st.session_state.step + 1} of {total}")

    # Top: input + fake image
    left, right = st.columns([1, 2], gap="large")

    with left:
        st.text_input("What was manipulated?", key=f"guess_{st.session_state.step}")
        if not st.session_state.show_real:
            if st.button("Reveal Original", type="primary"):
                st.session_state.show_real = True

    with right:
        fake_img = load_image(fake_rel)
        if fake_img:
            st.image(fake_img, caption="Fake Image")

    # Reveal: side-by-side comparison + correctness
    if st.session_state.show_real:
        if comment:
            st.markdown(f"**Comment:** {comment}")

        col_fake, col_real = st.columns(2, gap="large")
        with col_fake:
            fi = load_image(fake_rel)
            if fi:
                st.image(fi, caption="Fake")
        with col_real:
            ri = load_image(real_rel)
            if ri:
                st.image(ri, caption="Real")

        st.radio(
            "Were you correct?",
            ["Yes", "No"],
            index=0,
            horizontal=True,
            key=f"correct_{st.session_state.step}",
        )
        # The 'Next' button now uses a callback to ensure a single-click action
        st.button("Next", on_click=record_answer)

else:
    # Summary
    correct_answers = sum(1 for a in st.session_state.answers if a["correct"])
    st.success(f"🎉 You got {correct_answers} out of {total} correct!")
    st.write("### Summary")
    st.table(pd.DataFrame(st.session_state.answers))

    if st.button("🔁 Play Again"):
        st.session_state.df = load_metadata("manipulation_info.csv", ROUNDS)
        st.session_state.step = 0
        st.session_state.answers = []
        st.session_state.show_real = False