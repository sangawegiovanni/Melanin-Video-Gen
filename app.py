# app.py
# Run with: streamlit run app.py

from __future__ import annotations

import hashlib, math, os, sqlite3, time
from pathlib import Path
from datetime import datetime

import requests
import streamlit as st
from PIL import Image

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
MODAL_WORKSPACE = os.getenv("MODAL_WORKSPACE", "mchilisangawe")
BASE            = f"https://{MODAL_WORKSPACE}--ltx23"

SUBMIT_T2V_URL = os.getenv("LTX_SUBMIT_URL",     f"{BASE}-submit.modal.run")
SUBMIT_I2V_URL = os.getenv("LTX_SUBMIT_IMG_URL", f"{BASE}-submit-image.modal.run")
STATUS_URL     = os.getenv("LTX_STATUS_URL",     f"{BASE}-status.modal.run")
RESULT_URL     = os.getenv("LTX_RESULT_URL",     f"{BASE}-result.modal.run")

DB_PATH         = Path("users.db")
VIDEO_STORE_DIR = Path("generated_videos")
VIDEO_STORE_DIR.mkdir(exist_ok=True)

POLL_INTERVAL_SEC  = 5
CHUNK_DURATION_SEC = 73 / 24.0   # ≈ 3.04 s per chunk

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="LTX-2.3 Studio",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Mono:ital,wght@0,300;0,400;0,500;1,400&display=swap');
:root{--bg:#09090e;--bg2:#101018;--bg3:#16161f;--border:#252535;--accent:#e8ff47;--audio:#47ffe0;--text:#e2e2f0;--muted:#62627a;--danger:#ff4f6a;--success:#47ffb3;--radius:12px;}
html,body,[class*="css"]{font-family:'Syne',sans-serif;background:var(--bg)!important;color:var(--text);}
.stApp{background:var(--bg);}
#MainMenu,footer,header{visibility:hidden;}
.stDeployButton{display:none;}
[data-testid="stSidebar"]{background:var(--bg2)!important;border-right:1px solid var(--border);}
.stTextInput input,.stTextArea textarea{background:var(--bg3)!important;border:1px solid var(--border)!important;border-radius:var(--radius)!important;color:var(--text)!important;font-family:'DM Mono',monospace!important;font-size:0.9rem!important;}
.stTextInput input:focus,.stTextArea textarea:focus{border-color:var(--accent)!important;box-shadow:0 0 0 2px rgba(232,255,71,0.12)!important;}
.stButton>button{background:var(--accent)!important;color:#09090e!important;border:none!important;border-radius:var(--radius)!important;font-family:'Syne',sans-serif!important;font-weight:700!important;font-size:0.95rem!important;padding:0.6rem 1.6rem!important;transition:transform .15s ease,box-shadow .15s ease!important;cursor:pointer!important;}
.stButton>button:hover{transform:translateY(-2px)!important;box-shadow:0 6px 24px rgba(232,255,71,0.3)!important;}
.stButton>button:disabled{opacity:0.5!important;transform:none!important;cursor:not-allowed!important;}
.stTabs [data-baseweb="tab-list"]{background:var(--bg3);border-radius:var(--radius);padding:4px;gap:4px;border-bottom:none!important;}
.stTabs [data-baseweb="tab"]{border-radius:8px!important;color:var(--muted)!important;font-family:'Syne',sans-serif!important;font-weight:600!important;padding:0.45rem 1.2rem!important;background:transparent!important;}
.stTabs [aria-selected="true"]{background:var(--accent)!important;color:#09090e!important;}
.stat-card{background:var(--bg3);border:1px solid var(--border);border-radius:var(--radius);padding:1.1rem 1.4rem;text-align:center;}
.stat-card .value{font-size:2rem;font-weight:800;color:var(--accent);line-height:1;}
.stat-card .label{font-size:0.75rem;color:var(--muted);margin-top:4px;font-family:'DM Mono',monospace;text-transform:uppercase;letter-spacing:.08em;}
.video-card{background:var(--bg3);border:1px solid var(--border);border-radius:var(--radius);padding:1rem;margin-bottom:1rem;}
.video-card .video-meta{font-size:.76rem;color:var(--muted);font-family:'DM Mono',monospace;margin-top:.5rem;}
.video-card .video-prompt{font-size:.86rem;color:var(--text);margin-top:.25rem;line-height:1.45;}
.badge{display:inline-block;border-radius:100px;padding:.15rem .65rem;font-size:.7rem;font-family:'DM Mono',monospace;text-transform:uppercase;letter-spacing:.08em;}
.badge-video{background:rgba(232,255,71,.1);color:var(--accent);border:1px solid rgba(232,255,71,.3);}
.badge-audio{background:rgba(71,255,224,.1);color:var(--audio);border:1px solid rgba(71,255,224,.3);}
.badge-mode{background:rgba(139,92,246,.12);color:#a78bfa;border:1px solid rgba(139,92,246,.3);}
.timer-card{background:var(--bg3);border:1px solid var(--border);border-radius:var(--radius);padding:1.2rem 1.5rem;text-align:center;margin-bottom:.8rem;}
.timer-card .timer-value{font-size:2.8rem;font-weight:800;color:var(--accent);font-family:'DM Mono',monospace;line-height:1;}
.timer-card .timer-label{font-size:.72rem;color:var(--muted);font-family:'DM Mono',monospace;text-transform:uppercase;letter-spacing:.1em;margin-top:4px;}
.timer-card .timer-sub{font-size:.68rem;color:#47ffe0;font-family:'DM Mono',monospace;margin-top:6px;}
.timer-card .timer-cold{font-size:.72rem;color:#e8ff47;font-family:'DM Mono',monospace;margin-top:8px;line-height:1.5;}
.stage-log{background:var(--bg3);border:1px solid var(--border);border-radius:var(--radius);padding:.9rem 1.1rem;font-family:'DM Mono',monospace;font-size:.78rem;line-height:1.85;}
.stage-active{color:var(--accent);}
.error-card{background:rgba(255,79,106,.08);border:1px solid rgba(255,79,106,.4);border-radius:var(--radius);padding:1rem 1.2rem;font-family:'DM Mono',monospace;font-size:.82rem;color:#ff8fa3;line-height:1.6;}
.error-card .error-title{color:var(--danger);font-weight:700;font-size:.9rem;margin-bottom:.4rem;}
.resume-card{background:rgba(232,255,71,.05);border:1px solid rgba(232,255,71,.25);border-radius:var(--radius);padding:.9rem 1.1rem;font-family:'DM Mono',monospace;font-size:.78rem;color:#c8df40;margin-bottom:.8rem;}
.reconnect-banner{background:rgba(71,255,224,.07);border:1px solid rgba(71,255,224,.3);border-radius:var(--radius);padding:.75rem 1.1rem;font-family:'DM Mono',monospace;font-size:.8rem;color:#47ffe0;margin-bottom:.8rem;}
.audio-wave{display:flex;align-items:flex-end;gap:3px;height:28px;padding:4px 0;}
.audio-wave span{display:inline-block;width:4px;border-radius:2px;background:var(--audio);opacity:.85;animation:wave 1.2s ease-in-out infinite alternate;}
.audio-wave span:nth-child(2){animation-delay:.10s;}
.audio-wave span:nth-child(3){animation-delay:.20s;}
.audio-wave span:nth-child(4){animation-delay:.30s;}
.audio-wave span:nth-child(5){animation-delay:.15s;}
.audio-wave span:nth-child(6){animation-delay:.25s;}
.audio-wave span:nth-child(7){animation-delay:.05s;}
@keyframes wave{from{height:4px}to{height:20px}}
::-webkit-scrollbar{width:5px;height:5px;}
::-webkit-scrollbar-track{background:var(--bg2);}
::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px;}
.hero-title{font-size:clamp(2.4rem,5.5vw,5rem);font-weight:800;line-height:1.06;letter-spacing:-.03em;}
.hero-accent{color:var(--accent);}
.hero-audio{color:var(--audio);}
.hero-sub{font-size:1.1rem;color:var(--muted);font-family:'DM Mono',monospace;margin-top:1rem;max-width:560px;line-height:1.65;}
.feature-pill{display:inline-block;background:var(--bg3);border:1px solid var(--border);border-radius:100px;padding:.3rem .9rem;font-size:.8rem;font-family:'DM Mono',monospace;color:var(--muted);margin:.2rem;}
hr{border-color:var(--border)!important;}
</style>
""", unsafe_allow_html=True)

WAVEFORM_HTML = (
    '<div class="audio-wave">'
    + "".join(f'<span style="height:{h}px"></span>' for h in [8,14,20,12,18,10,16])
    + "</div>"
)

# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------
def get_db():
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL, email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )""")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS generations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL, mode TEXT NOT NULL,
                prompt TEXT NOT NULL, video_path TEXT NOT NULL,
                width INTEGER, height INTEGER, num_frames INTEGER,
                duration_sec REAL, has_audio INTEGER NOT NULL DEFAULT 1,
                job_id TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )""")
        existing = {r[1] for r in conn.execute("PRAGMA table_info(generations)").fetchall()}
        for col, defn in [("has_audio","INTEGER NOT NULL DEFAULT 1"),("job_id","TEXT")]:
            if col not in existing:
                conn.execute(f"ALTER TABLE generations ADD COLUMN {col} {defn}")
        conn.commit()

def hash_password(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def create_user(username, email, password):
    username, email = username.strip().lower(), email.strip().lower()
    if len(username) < 3: return False, "Username must be at least 3 characters."
    if len(password) < 6: return False, "Password must be at least 6 characters."
    if "@" not in email:  return False, "Enter a valid e-mail address."
    try:
        with get_db() as conn:
            conn.execute(
                "INSERT INTO users (username,email,password_hash) VALUES (?,?,?)",
                (username, email, hash_password(password)),
            )
            conn.commit()
        return True, "Account created!"
    except sqlite3.IntegrityError as exc:
        return False, ("Username already taken." if "username" in str(exc) else "E-mail already registered.")

def verify_user(ident, password):
    ident = ident.strip().lower()
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE (username=? OR email=?) AND password_hash=?",
            (ident, ident, hash_password(password)),
        ).fetchone()

def save_generation(user_id, mode, prompt, video_bytes, width, height,
                    duration_sec, frame_rate, has_audio=True, job_id=""):
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    path = VIDEO_STORE_DIR / f"{mode}_{user_id}_{ts}.mp4"
    path.write_bytes(video_bytes)
    with get_db() as conn:
        conn.execute(
            "INSERT INTO generations (user_id,mode,prompt,video_path,width,height,"
            "num_frames,duration_sec,has_audio,job_id) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (user_id, mode, prompt, str(path), width, height,
             int(duration_sec * frame_rate), duration_sec, int(has_audio), job_id),
        )
        conn.commit()
    return path

def get_user_generations(user_id):
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM generations WHERE user_id=? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()

def count_user_generations(user_id):
    with get_db() as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM generations WHERE user_id=?", (user_id,)
        ).fetchone()[0]

def row_has_audio(row):
    try:    return bool(row["has_audio"])
    except: return True

# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------
def api_submit_t2v(params):
    r = requests.post(SUBMIT_T2V_URL, json=params, timeout=45)
    r.raise_for_status()
    return r.json()

def api_submit_i2v(params, image_bytes, image_name, image_type):
    r = requests.post(
        SUBMIT_I2V_URL,
        data=params,
        files={"image": (image_name, image_bytes, image_type)},
        timeout=45,
    )
    r.raise_for_status()
    return r.json()

def api_poll_status(job_id: str) -> dict:
    safe = {"status": "running", "stage": "waiting_for_gpu", "chunk": 0, "total": 0, "error": ""}
    for attempt in range(3):
        try:
            r = requests.get(STATUS_URL, params={"job_id": job_id}, timeout=45)
            if r.status_code == 200:
                return r.json()
            return {**safe, "stage": f"http_{r.status_code}"}
        except requests.exceptions.Timeout:
            if attempt < 2: time.sleep(5); continue
            return safe
        except requests.exceptions.ConnectionError:
            if attempt < 2: time.sleep(5); continue
            return {**safe, "stage": "reconnecting"}
        except Exception:
            if attempt < 2: time.sleep(5); continue
            return safe
    return safe

def api_fetch_result(job_id):
    r = requests.get(RESULT_URL, params={"job_id": job_id}, timeout=180)
    r.raise_for_status()
    return r.content

def format_elapsed(s):
    return f"{int(s)//60:02d}:{int(s)%60:02d}"

def estimate_remaining(elapsed, duration_sec):
    n = max(1, math.ceil(duration_sec / CHUNK_DURATION_SEC))
    rem = max(0, 35 + n * 90 + 20 - elapsed)
    return "almost done…" if rem < 10 else f"~{int(rem)//60:02d}:{int(rem)%60:02d} left"

def stage_label(stage, chunk, total):
    m = {
        "encoding_text":   "Encoding text prompt…",
        "starting":        "Starting GPU container…",
        "waiting_for_gpu": "Waiting for GPU…",
        "reconnecting":    "Reconnecting…",
        "enhancing_audio": "Enhancing audio (44.1 kHz · loudnorm · EQ)…",
        "stitching":       f"Stitching {total} chunk(s) → final MP4…",
        "done":            "Complete ✔",
        "error":           "Error ✖",
    }
    if stage.startswith("chunk_"):
        return f"Chunk {stage.replace('chunk_','')}/{total} — generating video + audio…"
    if stage.startswith("http_"):
        return f"Status endpoint returned {stage.replace('http_','')} — retrying…"
    return m.get(stage, stage)

def build_progress_html(chunk, total, stage):
    if total == 0:                   pct = 5
    elif stage == "done":            pct = 100
    elif stage == "enhancing_audio": pct = 88
    elif stage == "stitching":       pct = 94
    elif stage.startswith("chunk_"):
        n = int(stage.replace("chunk_","") or 1)
        pct = min(85, int((n / max(total,1)) * 82) + 3)
    else:                            pct = 3

    bar   = "var(--success)" if stage == "done" else "var(--accent)"
    label = stage_label(stage, chunk, total)
    ctxt  = (
        f'<div style="font-size:.7rem;color:var(--muted);margin-top:.4rem;">Chunk {chunk}/{total}</div>'
        if total > 0 and stage not in ("done","error") else ""
    )
    return (
        f'<div class="stage-log">'
        f'<div style="margin-bottom:.6rem;">'
        f'<div style="background:var(--border);border-radius:6px;height:7px;overflow:hidden;">'
        f'<div style="width:{pct}%;height:100%;background:{bar};transition:width .5s ease;border-radius:6px;"></div>'
        f'</div></div><div class="stage-active">▶ &nbsp;{label}</div>{ctxt}</div>'
    )

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
init_db()

for k, v in {
    "user": None, "last_video": None, "gen_mode": "Text-to-Video",
    "gen_error": None, "active_job": None, "job_done": False,
    "network_lost": False, "network_lost_since": None,
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown(
        '<h2 style="font-size:1.55rem;font-weight:800;color:#e8ff47;margin-bottom:0;">🎬 LTX-2.3</h2>'
        '<p style="font-size:.75rem;color:#47ffe0;font-family:\'DM Mono\',monospace;margin-top:0;">AUDIO · VIDEO STUDIO</p>',
        unsafe_allow_html=True,
    )
    st.markdown("---")

    if st.session_state.user is None:
        login_tab, signup_tab = st.tabs(["Log In", "Sign Up"])
        with login_tab:
            st.markdown("##### Welcome back")
            li_ident = st.text_input("Username or Email", key="li_ident", placeholder="you@example.com")
            li_pass  = st.text_input("Password", key="li_pass", type="password", placeholder="••••••••")
            if st.button("Log In", key="btn_login", use_container_width=True):
                if not li_ident or not li_pass:
                    st.error("Please fill in all fields.")
                else:
                    row = verify_user(li_ident, li_pass)
                    if row:
                        st.session_state.user = dict(row)
                        st.success(f"Welcome, {row['username']}!")
                        time.sleep(0.3); st.rerun()
                    else:
                        st.error("Invalid credentials.")
        with signup_tab:
            st.markdown("##### Create your account")
            su_user  = st.text_input("Username", key="su_user",  placeholder="coolcreator")
            su_email = st.text_input("Email",    key="su_email", placeholder="you@example.com")
            su_pass  = st.text_input("Password", key="su_pass",  type="password", placeholder="Min 6 chars")
            su_pass2 = st.text_input("Confirm",  key="su_pass2", type="password", placeholder="Repeat password")
            if st.button("Create Account", key="btn_signup", use_container_width=True):
                if not all([su_user, su_email, su_pass, su_pass2]):
                    st.error("Fill in all fields.")
                elif su_pass != su_pass2:
                    st.error("Passwords do not match.")
                else:
                    ok, msg = create_user(su_user, su_email, su_pass)
                    (st.success if ok else st.error)(msg)
    else:
        user = st.session_state.user
        st.markdown(
            f'<div class="stat-card"><div class="value">👤</div><div class="label">@{user["username"]}</div></div>',
            unsafe_allow_html=True,
        )
        st.markdown("")
        st.markdown(
            f'<div class="stat-card"><div class="value">{count_user_generations(user["id"])}</div>'
            f'<div class="label">Videos Generated</div></div>',
            unsafe_allow_html=True,
        )
        st.markdown("")
        st.markdown("---")
        st.markdown("**Generation Mode**")
        st.session_state.gen_mode = st.radio(
            "Mode", ["Text-to-Video", "Image-to-Video"],
            index=0 if st.session_state.gen_mode == "Text-to-Video" else 1,
            label_visibility="collapsed",
        )
        st.markdown("---")

        if st.session_state.active_job and not st.session_state.job_done:
            aj = st.session_state.active_job
            st.markdown(
                f'<div class="resume-card"><strong>🔄 Job running</strong><br>'
                f'ID: <code>{aj["job_id"][:16]}…</code><br>Network drops won\'t stop it.</div>',
                unsafe_allow_html=True,
            )

        st.markdown(
            f'<div style="background:rgba(71,255,224,.06);border:1px solid rgba(71,255,224,.2);'
            f'border-radius:10px;padding:.8rem 1rem;margin-bottom:.8rem;">'
            f'{WAVEFORM_HTML}'
            f'<div style="font-size:.72rem;color:#47ffe0;font-family:\'DM Mono\',monospace;'
            f'margin-top:.35rem;line-height:1.5;"><strong>Audio sync ON</strong><br>'
            f'44.1 kHz · EBU R128 · EQ<br>Multilingual · Swahili ✓</div></div>',
            unsafe_allow_html=True,
        )
        if st.button("Sign Out", key="btn_signout", use_container_width=True):
            for k in ("user","last_video","gen_error","active_job","network_lost","network_lost_since"):
                st.session_state[k] = None
            st.session_state.job_done = st.session_state.network_lost = False
            st.rerun()

        st.markdown(
            '<p style="font-size:.7rem;color:#2a2a3a;font-family:\'DM Mono\',monospace;margin-top:1rem;">'
            'LTX-2.3 · Lightricks · Modal A100-80GB<br>Distilled 8-step · Network-drop safe<br>'
            'Up to 60 s videos</p>',
            unsafe_allow_html=True,
        )

# ===========================================================================
# LANDING
# ===========================================================================
if st.session_state.user is None:
    st.markdown("""
        <div style="padding:4rem 1rem 2rem;">
            <div style="margin-bottom:1rem;">
                <span class="badge badge-video">✦ LTX-2.3</span>&nbsp;
                <span class="badge badge-audio">🔊 Enhanced Audio</span>&nbsp;
                <span class="badge badge-mode">🌍 Multilingual</span>
            </div>
            <div class="hero-title">
                Generate cinematic<br>
                <span class="hero-accent">video</span> &amp;
                <span class="hero-audio">sound</span><br>together.
            </div>
            <p class="hero-sub">
                LTX-2.3 Studio generates synchronized audio+video MP4s up to 60 seconds
                using the 8-step DistilledPipeline. Jobs run entirely on Modal —
                close your browser, come back, your video will be waiting.
            </p>
        </div>""", unsafe_allow_html=True)

    st.markdown(
        '<div style="padding:0 1rem 2rem;">'
        + " ".join(
            f'<span class="feature-pill">{f}</span>'
            for f in ["⚡ A100-80GB · 8-step","🎥 Up to 60 s","🔊 44.1 kHz audio",
                      "🌍 Swahili + 9 langs","🔄 Auto-reconnect","🖼️ Image-to-Video","⬇️ MP4 download"]
        ) + "</div>", unsafe_allow_html=True)
    st.markdown("---")
    for col, (num, title, desc) in zip(
        st.columns(3),
        [("01","Sign Up for Free","Create your account in seconds."),
         ("02","Submit & Disconnect","Jobs run on Modal — safe to close your browser."),
         ("03","Watch & Download","Reconnect anytime and collect your MP4.")],
    ):
        with col:
            st.markdown(
                f'<div class="stat-card" style="text-align:left;padding:1.5rem;">'
                f'<div style="font-size:.68rem;font-family:\'DM Mono\',monospace;color:#e8ff47;'
                f'letter-spacing:.1em;margin-bottom:.5rem;">STEP {num}</div>'
                f'<div style="font-size:1.05rem;font-weight:700;margin-bottom:.4rem;">{title}</div>'
                f'<div style="font-size:.83rem;color:#62627a;line-height:1.5;">{desc}</div></div>',
                unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)
    st.info("👈 Use the sidebar to **Sign Up** or **Log In** to start generating.")

# ===========================================================================
# DASHBOARD
# ===========================================================================
else:
    user = st.session_state.user
    mode = st.session_state.gen_mode

    st.markdown(
        f'<div style="display:flex;align-items:baseline;gap:.75rem;margin-bottom:.2rem;">'
        f'<span style="font-size:1.95rem;font-weight:800;">Generation Studio</span>'
        f'<span class="badge badge-mode">{"✦ T2V" if mode=="Text-to-Video" else "🖼 I2V"}</span>'
        f'<span class="badge badge-audio">🔊 Enhanced</span>'
        f'<span class="badge badge-video">🔄 Resume-safe</span></div>'
        f'<p style="color:#62627a;font-family:\'DM Mono\',monospace;font-size:.82rem;margin-top:0;">'
        f'{mode} · LTX-2.3 · A100-80GB · 8-step distilled · Network-drop safe</p>',
        unsafe_allow_html=True,
    )
    st.markdown("---")

    ctrl_col, out_col = st.columns([1, 1], gap="large")

    with ctrl_col:
        st.markdown("#### ✍️ Prompt")
        prompt = st.text_area(
            "Prompt", label_visibility="collapsed", height=120, key="prompt_input",
            placeholder=(
                "A roaring waterfall crashing into a jungle pool, tropical birds chirping, "
                "mist rising, golden afternoon light, cinematic slow motion…\n\n"
                "Swahili: Mwanamke anaimba pwani, mawimbi yakipigana, sauti ya bahari."
                if mode == "Text-to-Video" else
                "Describe animation + sounds…\nSwahili: Msitu ukisogea, ndege wakiimba, upepo."
            ),
        )
        negative_prompt = st.text_area(
            "Negative Prompt", height=60, key="neg_prompt_input",
            value="shaky, glitchy, low quality, worst quality, deformed, distorted, "
                  "motion smear, motion artifacts, ugly, watermark, blurry, silence, muted.",
        )

        with st.expander("🔊 Audio Prompt Tips", expanded=False):
            st.markdown("""
| Scene | English | Swahili |
|---|---|---|
| Waterfall | *roaring waterfall* | *mto ukivuma* |
| Ocean | *ocean waves* | *mawimbi ya bahari* |
| Birds | *birds chirping* | *ndege wakiimba* |
| Crowd | *crowd cheering* | *umati ukishangilia* |
| Music | *jazz piano* | *muziki wa jazz* |
""")

        if mode == "Image-to-Video":
            st.markdown("#### 🖼️ Source Image")
            uploaded_file = st.file_uploader(
                "Upload Image", type=["jpg","jpeg","png","webp"],
                label_visibility="collapsed", key="image_uploader",
            )
            if uploaded_file:
                st.image(Image.open(uploaded_file), caption="Source image", use_container_width=True)
        else:
            uploaded_file = None

        with st.expander("⚙️ Advanced Settings", expanded=False):
            a1, a2 = st.columns(2)
            with a1:
                width        = st.select_slider("Width",  options=[512,640,768,1024], value=768)
                height       = st.select_slider("Height", options=[512,640,768,1024], value=512)
                duration_sec = st.slider(
                    "Duration (seconds)", min_value=3, max_value=60, value=5, step=1,
                    help="3–60 s. Each ~3 s chunk ≈ 90 s GPU time.",
                )
            with a2:
                frame_rate     = st.slider("Frame Rate (fps)", 8.0, 30.0, 24.0, 1.0)
                guidance_scale = st.slider(
                    "Guidance Scale", 1.0, 3.0, 1.0, 0.1,
                    help="Keep at 1.0 for DistilledPipeline.",
                )
                seed = st.number_input("Seed (-1=random)", min_value=-1, max_value=2**31-1, value=-1, step=1)

            width  = (width  // 32) * 32
            height = (height // 32) * 32
            num_chunks = max(1, math.ceil(duration_sec / CHUNK_DURATION_SEC))
            est_min    = round(num_chunks * 1.5 + 1)
            st.caption(f"📦 {num_chunks} chunk(s) · Est. ~{est_min} min · 8 distilled steps")

        st.markdown(
            f'<p style="font-size:.78rem;color:#62627a;font-family:\'DM Mono\',monospace;">'
            f'Video: {duration_sec}s · {width}×{height} · ~{int(duration_sec*frame_rate)}f'
            f' @ {int(frame_rate)}fps · <span style="color:#47ffe0;">🔊 44.1kHz</span></p>',
            unsafe_allow_html=True,
        )

        is_busy = st.session_state.active_job is not None and not st.session_state.job_done
        generate_clicked = st.button(
            "🎬  Generate Video + Audio" if not is_busy else "⏳  Job Running…",
            key="btn_generate", use_container_width=True, disabled=is_busy,
        )

        with st.expander("🔄 Resume a job by ID", expanded=False):
            resume_id = st.text_input("Job ID", key="resume_id_input", placeholder="paste job_id here")
            if st.button("Resume", key="btn_resume"):
                if resume_id.strip():
                    st.session_state.active_job = {
                        "job_id":       resume_id.strip(),
                        "submitted_at": time.time() - 30,
                        "num_chunks":   num_chunks,
                        "params":       {},
                    }
                    st.session_state.job_done = st.session_state.network_lost = False
                    st.session_state.last_video = st.session_state.gen_error = None
                    st.rerun()

    with out_col:
        st.markdown("#### 🎞️ Output")

        if st.session_state.active_job and not st.session_state.job_done:
            aj      = st.session_state.active_job
            job_id  = aj["job_id"]
            elapsed = time.time() - aj["submitted_at"]
            total_c = aj.get("num_chunks", num_chunks)

            timer_slot    = st.empty()
            progress_slot = st.empty()
            banner_slot   = st.empty()
            jobid_slot    = st.empty()

            status = api_poll_status(job_id)
            stage  = status.get("stage", "waiting_for_gpu")
            chunk  = int(status.get("chunk", 0))
            total  = int(status.get("total", total_c)) or total_c
            error  = status.get("error", "")

            if stage == "reconnecting":
                if not st.session_state.network_lost:
                    st.session_state.network_lost       = True
                    st.session_state.network_lost_since = time.time()
                lost_for = time.time() - (st.session_state.network_lost_since or time.time())
                banner_slot.markdown(
                    f'<div class="reconnect-banner">📡 <strong>Connection lost</strong> — retrying… ({int(lost_for)}s)<br>'
                    f'Your job is still running safely on Modal.</div>',
                    unsafe_allow_html=True,
                )
            else:
                if st.session_state.network_lost:
                    st.session_state.network_lost = False
                    st.session_state.network_lost_since = None
                banner_slot.empty()

            if status.get("status") == "error" and error:
                st.session_state.gen_error  = {"title": "Generation Failed", "body": error.replace("\n","<br>")}
                st.session_state.active_job = None
                st.rerun()

            elif status.get("status") == "done":
                progress_slot.info("⬇️ Downloading your video from Modal…")
                try:
                    video_bytes = api_fetch_result(job_id)
                    params      = aj.get("params", {})
                    save_generation(
                        user_id      = user["id"],
                        mode         = params.get("mode", "t2v"),
                        prompt       = params.get("prompt", ""),
                        video_bytes  = video_bytes,
                        width        = params.get("width", 768),
                        height       = params.get("height", 512),
                        duration_sec = params.get("duration_seconds", 5.0),
                        frame_rate   = params.get("frame_rate", 24.0),
                        has_audio    = True,
                        job_id       = job_id,
                    )
                    st.session_state.last_video = {
                        "bytes":        video_bytes,
                        "mode":         params.get("mode", "t2v"),
                        "prompt":       params.get("prompt", ""),
                        "width":        params.get("width", 768),
                        "height":       params.get("height", 512),
                        "duration_sec": params.get("duration_seconds", 5.0),
                        "frame_rate":   params.get("frame_rate", 24.0),
                        "ts":           datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "elapsed":      elapsed,
                        "audio_synced": True,
                        "job_id":       job_id,
                    }
                    st.session_state.active_job = None
                    st.session_state.job_done   = True
                    progress_slot.empty()
                    st.rerun()
                except Exception as exc:
                    st.session_state.gen_error  = {"title": "Failed to download result", "body": str(exc)}
                    st.session_state.active_job = None
                    st.rerun()

            else:
                is_cold  = stage in ("waiting_for_gpu","starting","queued","encoding_text") or elapsed < 60
                rem_str  = estimate_remaining(elapsed, float(aj.get("params",{}).get("duration_seconds", 5.0)))
                cold_html = (
                    '<div class="timer-cold">⚠️ GPU container starting up.<br>'
                    'Takes 3–5 min on first run. Your job is safe.</div>'
                    if is_cold else f'<div class="timer-sub">{rem_str}</div>'
                )
                timer_slot.markdown(
                    f'<div class="timer-card">'
                    f'<div class="timer-value">{format_elapsed(elapsed)}</div>'
                    f'<div class="timer-label">elapsed · job running on Modal</div>'
                    f'{cold_html}</div>',
                    unsafe_allow_html=True,
                )
                progress_slot.markdown(build_progress_html(chunk, total, stage), unsafe_allow_html=True)
                jobid_slot.markdown(
                    f'<div class="resume-card">📋 <strong>Job ID</strong> (save to resume after disconnect):<br>'
                    f'<code style="font-size:.78rem;user-select:all;">{job_id}</code></div>',
                    unsafe_allow_html=True,
                )
                time.sleep(POLL_INTERVAL_SEC)
                st.rerun()

        elif st.session_state.last_video is not None:
            lv = st.session_state.last_video
            st.video(lv["bytes"])
            dl_col, info_col = st.columns([1, 2])
            with dl_col:
                st.download_button(
                    "⬇️ Download MP4", data=lv["bytes"],
                    file_name=f"ltx23_{lv['mode']}_{int(time.time())}.mp4",
                    mime="video/mp4", use_container_width=True,
                )
            with info_col:
                badge_audio = (
                    '<span class="badge badge-audio">🔊 44.1kHz Enhanced</span>'
                    if lv.get("audio_synced") else
                    '<span class="badge" style="color:#ff4f6a;border:1px solid rgba(255,79,106,.3);">⚠️ No Audio</span>'
                )
                st.markdown(
                    f'<div style="font-size:.77rem;color:#62627a;font-family:\'DM Mono\',monospace;line-height:1.7;">'
                    f"Mode: {lv['mode'].upper()}<br>Size: {lv['width']}×{lv['height']}<br>"
                    f"Duration: {lv['duration_sec']:.1f}s<br>FPS: {lv['frame_rate']}<br>"
                    f"Generated: {lv['ts']}<br>{badge_audio}</div>",
                    unsafe_allow_html=True,
                )
            st.success(f"✅ Done in {lv.get('elapsed',0):.1f}s — {len(lv['bytes'])/1024:.0f} KB — 🔊 Audio enhanced")

        elif st.session_state.gen_error is not None:
            err = st.session_state.gen_error
            st.markdown(
                f'<div class="error-card"><div class="error-title">❌ {err["title"]}</div>{err["body"]}</div>',
                unsafe_allow_html=True,
            )
            if st.button("Dismiss", key="btn_dismiss"):
                st.session_state.gen_error = None
                st.rerun()

        else:
            st.markdown(
                '<div style="border:1px dashed #252535;border-radius:12px;padding:3.5rem 1rem;text-align:center;">'
                '<div style="color:#2a2a3a;font-size:1.8rem;margin-bottom:.5rem;">◎</div>'
                '<div style="color:#3a3a5a;font-family:\'DM Mono\',monospace;font-size:.82rem;">'
                'Your audio+video will appear here</div></div>',
                unsafe_allow_html=True,
            )

    if generate_clicked:
        errors = []
        if not prompt.strip():
            errors.append("A prompt is required.")
        if mode == "Image-to-Video" and uploaded_file is None:
            errors.append("Please upload a source image.")
        if errors:
            for e in errors: st.error(e)
        else:
            st.session_state.last_video = st.session_state.gen_error = None
            st.session_state.job_done   = st.session_state.network_lost = False

            mode_key = "t2v" if mode == "Text-to-Video" else "i2v"
            params = {
                "mode": mode_key, "prompt": prompt.strip(),
                "negative_prompt": negative_prompt.strip(),
                "width": width, "height": height,
                "duration_seconds": float(duration_sec),
                "frame_rate": float(frame_rate),
                "guidance_scale": float(guidance_scale),
                "seed": int(seed),
            }
            try:
                if mode == "Text-to-Video":
                    resp = api_submit_t2v(params)
                else:
                    uploaded_file.seek(0)
                    resp = api_submit_i2v(params, uploaded_file.read(), uploaded_file.name, uploaded_file.type)

                st.session_state.active_job = {
                    "job_id":       resp["job_id"],
                    "submitted_at": time.time(),
                    "num_chunks":   resp.get("num_chunks", num_chunks),
                    "params":       params,
                }
                st.info(f"✅ Job submitted — est. ~{resp.get('estimated_minutes','?')} min. GPU warming up…")
                st.rerun()
            except Exception as exc:
                st.session_state.gen_error = {
                    "title": "Failed to submit job",
                    "body": f"Could not reach Modal backend.<br>Run <code>modal deploy backend.py</code> first.<br><br>Detail: {exc}",
                }
                st.rerun()

    # Gallery
    st.markdown("---")
    st.markdown("### 📽️ Your Video Gallery")
    generations = get_user_generations(user["id"])

    if not generations:
        st.markdown(
            '<p style="color:#2a2a3a;font-family:\'DM Mono\',monospace;font-size:.83rem;">'
            'No videos yet — generate your first one above.</p>',
            unsafe_allow_html=True,
        )
    else:
        t2v_c  = sum(1 for g in generations if g["mode"] == "t2v")
        i2v_c  = sum(1 for g in generations if g["mode"] == "i2v")
        aud_c  = sum(1 for g in generations if row_has_audio(g))
        tot_d  = sum((g["duration_sec"] or 0) for g in generations)

        for col, val, label in zip(
            st.columns(5),
            [len(generations), t2v_c, i2v_c, aud_c, f"{tot_d:.0f}s"],
            ["Total","T2V","I2V","🔊 Audio","Duration"],
        ):
            with col:
                st.markdown(
                    f'<div class="stat-card"><div class="value">{val}</div>'
                    f'<div class="label">{label}</div></div>',
                    unsafe_allow_html=True,
                )

        st.markdown("<br>", unsafe_allow_html=True)
        g_list = list(generations)
        for row_idx in range(0, len(g_list), 2):
            for col, gen in zip(st.columns(2, gap="medium"), g_list[row_idx:row_idx+2]):
                with col:
                    vpath = Path(gen["video_path"])
                    if not vpath.exists():
                        st.markdown(
                            '<div class="video-card"><div style="color:#2a2a3a;font-size:.8rem;">'
                            'Video file missing on disk.</div></div>',
                            unsafe_allow_html=True,
                        )
                        continue
                    vbytes = vpath.read_bytes()
                    st.markdown('<div class="video-card">', unsafe_allow_html=True)
                    st.video(vbytes)
                    mode_badge  = "T2V" if gen["mode"] == "t2v" else "I2V"
                    audio_badge = (
                        '<span class="badge badge-audio">🔊 Enhanced</span>'
                        if row_has_audio(gen) else
                        '<span class="badge" style="color:#ff4f6a;border:1px solid #ff4f6a;">Mute</span>'
                    )
                    dur = gen["duration_sec"] or 0.0
                    st.markdown(
                        f'<div class="video-meta">'
                        f'<span class="badge badge-mode">{mode_badge}</span> {audio_badge} &nbsp;'
                        f'{gen["created_at"]} · {gen["width"]}×{gen["height"]} · {dur:.1f}s</div>'
                        f'<div class="video-prompt">'
                        f'{gen["prompt"][:130]}{"…" if len(gen["prompt"])>130 else ""}</div>',
                        unsafe_allow_html=True,
                    )
                    dl_col, _ = st.columns([1, 2])
                    with dl_col:
                        st.download_button(
                            "⬇️ Download", data=vbytes,
                            file_name=f"ltx23_{gen['mode']}_{gen['id']}.mp4",
                            mime="video/mp4", key=f"dl_{gen['id']}",
                            use_container_width=True,
                        )
                    st.markdown("</div>", unsafe_allow_html=True)