import html
import io
import os
from datetime import date
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from PIL import Image
from dotenv import load_dotenv

import db
import gemini_env
import mailer
import text_llm
import workout_plan

load_dotenv(Path(__file__).resolve().parent / ".env")
db.init_db()

st.set_page_config(
    page_title="SID Fitness Assistant",
    page_icon="🏋️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

if "user_id" not in st.session_state:
    st.session_state.user_id = None
if "username" not in st.session_state:
    st.session_state.username = None
if "last_meal_context" not in st.session_state:
    st.session_state.last_meal_context = ""


def _compact_ui_css() -> str:
    """App-wide polish; guest auth uses stronger overrides via .sid-guest-auth."""
    return """
<style>
    @import url("https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap");
    /* Inter for UI text only — never force it on all [class*="st"] or Streamlit's Material
       icon ligatures break (e.g. _arrow_right on expanders, garbled file upload labels). */
    html, body {
        font-family: "Inter", "Segoe UI", system-ui, sans-serif;
    }
    .stApp {
        font-family: "Inter", "Segoe UI", system-ui, sans-serif;
    }
    div[data-testid="stButton"] button,
    div[data-testid="stFormSubmitButton"] button {
        padding: 0.3125rem 0.75rem !important;
        min-height: 1.875rem !important;
        font-size: 0.8125rem !important;
        line-height: 1.3 !important;
        border-radius: 0.5rem !important;
        font-weight: 600 !important;
    }
    div[data-testid="stButton"],
    div[data-testid="stFormSubmitButton"] {
        width: fit-content !important;
        max-width: 100%;
    }
    div[data-testid="stButton"] button,
    div[data-testid="stFormSubmitButton"] button {
        width: auto !important;
    }
    .stTabs [data-baseweb="tab"] {
        padding: 0.35rem 0.7rem !important;
        font-size: 0.8125rem !important;
        min-height: 2rem !important;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 0.25rem !important;
    }
    div[data-testid="stFileUploader"] [data-testid="stFileUploaderFileData"] {
        display: none !important;
    }
</style>
"""


def _guest_auth_body_class_add() -> None:
    components.html(
        """
<script>
(function(){
  try {
    var d = window.parent.document;
    if (d && d.body) d.body.classList.add("sid-guest-auth");
  } catch(e) {}
})();
</script>
""",
        height=0,
        width=0,
    )


def _guest_auth_body_class_remove() -> None:
    components.html(
        """
<script>
(function(){
  try {
    var d = window.parent.document;
    if (d && d.body) d.body.classList.remove("sid-guest-auth");
  } catch(e) {}
})();
</script>
""",
        height=0,
        width=0,
    )


def _guest_auth_theme_css() -> str:
    return """
<style>
    .sid-guest-auth .stApp {
        background: linear-gradient(160deg, #bfdbfe 0%, #dbeafe 35%, #e0f2fe 70%, #f0f9ff 100%) !important;
        color-scheme: light;
        color: #0f172a !important;
    }
    .sid-guest-auth header[data-testid="stHeader"] {
        background: rgba(255, 255, 255, 0.55) !important;
        border-bottom: 1px solid rgba(59, 130, 246, 0.2) !important;
    }
    .sid-guest-auth [data-testid="stToolbar"] {
        background: rgba(255, 255, 255, 0.45) !important;
    }
    .sid-guest-auth .main .block-container {
        padding: 1.5rem 1.75rem 2.5rem !important;
        max-width: 1180px !important;
        margin: 0 auto !important;
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
    }
    /* First row: hero | form */
    .sid-guest-auth .main .block-container > div > div[data-testid="stHorizontalBlock"]:first-of-type {
        align-items: stretch !important;
        gap: 0.5rem !important;
    }
    .sid-guest-auth .main .block-container > div > div[data-testid="stHorizontalBlock"]:first-of-type > div[data-testid="column"]:first-child {
        background: linear-gradient(165deg, #ffffff 0%, #f0f9ff 45%, #e0f2fe 100%);
        border: 1px solid rgba(59, 130, 246, 0.28);
        border-radius: 20px;
        padding: 0 !important;
        box-shadow:
            0 0 0 1px rgba(255, 255, 255, 0.8) inset,
            0 12px 40px rgba(37, 99, 235, 0.12),
            0 4px 16px rgba(14, 165, 233, 0.08);
        position: relative;
        overflow: hidden;
    }
    .sid-guest-auth .main .block-container > div > div[data-testid="stHorizontalBlock"]:first-of-type > div[data-testid="column"]:first-child::before {
        content: "";
        position: absolute;
        inset: 0;
        background-image:
            linear-gradient(rgba(59, 130, 246, 0.06) 1px, transparent 1px),
            linear-gradient(90deg, rgba(59, 130, 246, 0.06) 1px, transparent 1px);
        background-size: 24px 24px;
        pointer-events: none;
        opacity: 0.7;
    }
    .sid-guest-auth .main .block-container > div > div[data-testid="stHorizontalBlock"]:first-of-type > div[data-testid="column"]:nth-child(2) {
        background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%) !important;
        border-radius: 20px !important;
        padding: 1.35rem 1.5rem 1.75rem !important;
        box-shadow:
            0 4px 6px -1px rgba(37, 99, 235, 0.08),
            0 16px 40px -12px rgba(14, 165, 233, 0.15) !important;
        border: 1px solid rgba(59, 130, 246, 0.22) !important;
        color-scheme: light !important;
        color: #0f172a !important;
    }
    .sid-auth-hero {
        position: relative;
        z-index: 1;
        padding: 2rem 1.75rem 2.25rem;
        min-height: 420px;
        display: flex;
        flex-direction: column;
        justify-content: center;
    }
    .sid-auth-brand {
        display: flex;
        align-items: center;
        gap: 0.65rem;
        margin-bottom: 1.5rem;
    }
    .sid-auth-logo-box {
        width: 44px;
        height: 44px;
        border-radius: 12px;
        background: linear-gradient(135deg, #2dd4bf 0%, #2563eb 100%);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.35rem;
        box-shadow: 0 8px 24px rgba(37, 99, 235, 0.35);
    }
    .sid-auth-brand-name {
        font-size: 1.15rem;
        font-weight: 700;
        color: #0f172a;
        letter-spacing: -0.02em;
    }
    .sid-auth-pulse {
        width: 48px;
        height: 3px;
        border-radius: 2px;
        background: linear-gradient(90deg, transparent, #2dd4bf, #38bdf8, transparent);
        margin-bottom: 1.25rem;
        opacity: 0.9;
    }
    .sid-auth-hero h1 {
        font-size: clamp(1.65rem, 2.5vw, 2.15rem);
        font-weight: 700;
        color: #0c4a6e;
        line-height: 1.2;
        margin: 0 0 0.85rem 0;
        letter-spacing: -0.03em;
    }
    .sid-auth-gradient-text {
        background: linear-gradient(90deg, #2dd4bf, #38bdf8, #60a5fa);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }
    .sid-auth-lead {
        color: #334155;
        font-size: 0.95rem;
        line-height: 1.55;
        margin: 0 0 1.75rem 0;
        max-width: 32ch;
    }
    .sid-auth-features {
        display: flex;
        flex-direction: column;
        gap: 0.65rem;
    }
    .sid-auth-feat {
        display: flex;
        align-items: flex-start;
        gap: 0.75rem;
        padding: 0.65rem 0.85rem;
        background: rgba(255, 255, 255, 0.75);
        border: 1px solid rgba(59, 130, 246, 0.2);
        border-radius: 12px;
        backdrop-filter: blur(8px);
    }
    .sid-auth-feat-icon {
        font-size: 1.1rem;
        line-height: 1;
    }
    .sid-auth-feat strong {
        color: #0f172a;
        font-size: 0.875rem;
    }
    .sid-auth-feat small {
        color: #475569;
        opacity: 1;
        font-size: 0.75rem;
    }
    .sid-auth-form-heading h2 {
        margin: 0 0 0.35rem 0;
        font-size: 1.5rem;
        font-weight: 700;
        color: #0c4a6e;
        letter-spacing: -0.03em;
    }
    .sid-auth-form-heading p {
        margin: 0 0 1rem 0;
        font-size: 0.9rem;
        color: #334155;
        line-height: 1.45;
    }
    .sid-guest-auth div[data-testid="column"]:has(.sid-auth-form-heading) .sid-auth-form-heading h2 {
        color: #0c4a6e !important;
    }
    .sid-guest-auth div[data-testid="column"]:has(.sid-auth-form-heading) .sid-auth-form-heading p {
        color: #334155 !important;
    }
    .sid-guest-auth div[data-testid="column"]:has(.sid-auth-form-heading) [data-testid="stWidgetLabel"] p,
    .sid-guest-auth div[data-testid="column"]:has(.sid-auth-form-heading) [data-testid="stWidgetLabel"] label {
        color: #0f172a !important;
    }
    .sid-guest-auth div[data-testid="column"]:has(.sid-auth-form-heading) [data-testid="stCaption"],
    .sid-guest-auth div[data-testid="column"]:has(.sid-auth-form-heading) .stCaption {
        color: #475569 !important;
        opacity: 1;
    }
    .sid-guest-auth div[data-testid="column"]:has(.sid-auth-form-heading) .stMarkdown,
    .sid-guest-auth div[data-testid="column"]:has(.sid-auth-form-heading) .stMarkdown p {
        color: #0f172a !important;
    }
    .sid-guest-auth div[data-testid="column"]:has(.sid-auth-form-heading) .stMarkdown a {
        color: #1d4ed8 !important;
        text-decoration: underline;
        text-underline-offset: 2px;
    }
    .sid-guest-auth div[data-testid="column"]:has(.sid-auth-form-heading) [data-baseweb="input"] {
        border-radius: 10px !important;
        border-color: rgba(59, 130, 246, 0.35) !important;
        background: #ffffff !important;
        color: #0f172a !important;
        box-shadow: 0 1px 2px rgba(37, 99, 235, 0.06) !important;
    }
    .sid-guest-auth div[data-testid="column"]:has(.sid-auth-form-heading) .stTabs [data-baseweb="tab-list"] {
        background: rgba(191, 219, 254, 0.55) !important;
        border-radius: 12px !important;
        padding: 4px !important;
        gap: 4px !important;
    }
    .sid-guest-auth div[data-testid="column"]:has(.sid-auth-form-heading) .stTabs [data-baseweb="tab"] {
        border-radius: 10px !important;
        font-weight: 600 !important;
        color: #1e40af !important;
    }
    .sid-guest-auth div[data-testid="column"]:has(.sid-auth-form-heading) .stTabs [aria-selected="true"] {
        background: #ffffff !important;
        color: #0c4a6e !important;
        box-shadow: 0 1px 4px rgba(37, 99, 235, 0.15) !important;
    }
    .sid-guest-auth div[data-testid="column"]:has(.sid-auth-form-heading) div[data-testid="stButton"] button[kind="primary"],
    .sid-guest-auth div[data-testid="column"]:has(.sid-auth-form-heading) div[data-testid="stButton"] button[data-testid="baseButton-primary"] {
        background: linear-gradient(90deg, #2563eb 0%, #0891b2 55%, #14b8a6 100%) !important;
        border: none !important;
        color: #ffffff !important;
        box-shadow: 0 4px 14px rgba(37, 99, 235, 0.35) !important;
        padding: 0.55rem 1.1rem !important;
        min-height: 2.5rem !important;
        font-size: 0.9rem !important;
    }
    .sid-guest-auth div[data-testid="column"]:has(.sid-auth-form-heading) div[data-testid="stButton"] button[kind="primary"]:hover {
        filter: brightness(1.06);
        box-shadow: 0 6px 20px rgba(37, 99, 235, 0.4) !important;
    }
    .sid-guest-auth div[data-testid="column"]:has(.sid-auth-form-heading) div[data-testid="stButton"] button[kind="secondary"],
    .sid-guest-auth div[data-testid="column"]:has(.sid-auth-form-heading) div[data-testid="stButton"] button[data-testid="baseButton-secondary"] {
        background: #ffffff !important;
        border: 1px solid rgba(59, 130, 246, 0.45) !important;
        color: #0f172a !important;
        font-weight: 600 !important;
    }
    .sid-guest-auth div[data-testid="column"]:has(.sid-auth-form-heading) div[data-testid="stButton"] button[kind="secondary"] p,
    .sid-guest-auth div[data-testid="column"]:has(.sid-auth-form-heading) div[data-testid="stButton"] button[kind="secondary"] span,
    .sid-guest-auth div[data-testid="column"]:has(.sid-auth-form-heading) div[data-testid="stButton"] button[data-testid="baseButton-secondary"] p,
    .sid-guest-auth div[data-testid="column"]:has(.sid-auth-form-heading) div[data-testid="stButton"] button[data-testid="baseButton-secondary"] span {
        color: #0f172a !important;
    }
    .sid-guest-auth div[data-testid="column"]:has(.sid-auth-form-heading) div[data-testid="stExpander"] {
        border: 1px solid rgba(59, 130, 246, 0.22) !important;
        border-radius: 12px !important;
        background: rgba(240, 249, 255, 0.85) !important;
    }
    .sid-guest-auth div[data-testid="column"]:has(.sid-auth-form-heading) [data-testid="stRadio"] label,
    .sid-guest-auth div[data-testid="column"]:has(.sid-auth-form-heading) [data-testid="stRadio"] p,
    .sid-guest-auth div[data-testid="column"]:has(.sid-auth-form-heading) [data-testid="stRadio"] div,
    .sid-guest-auth div[data-testid="column"]:has(.sid-auth-form-heading) [data-testid="stCheckbox"] label,
    .sid-guest-auth div[data-testid="column"]:has(.sid-auth-form-heading) [data-testid="stCheckbox"] p {
        color: #0f172a !important;
    }
    .sid-guest-auth div[data-testid="column"]:has(.sid-auth-form-heading) [data-testid="stExpander"] p,
    .sid-guest-auth div[data-testid="column"]:has(.sid-auth-form-heading) [data-testid="stExpander"] span,
    .sid-guest-auth div[data-testid="column"]:has(.sid-auth-form-heading) [data-testid="stExpander"] label,
    .sid-guest-auth div[data-testid="column"]:has(.sid-auth-form-heading) [data-testid="stExpander"] summary,
    .sid-guest-auth div[data-testid="column"]:has(.sid-auth-form-heading) [data-testid="stExpander"] div {
        color: #0f172a !important;
    }
    .sid-guest-auth div[data-testid="column"]:has(.sid-auth-form-heading) [data-baseweb="input"]::placeholder {
        color: rgba(15, 23, 42, 0.45) !important;
    }
    .sid-guest-auth [data-testid="stAlert"] {
        background: rgba(255, 255, 255, 0.92) !important;
        border: 1px solid rgba(59, 130, 246, 0.25) !important;
    }
    .sid-guest-auth [data-testid="stAlert"] p,
    .sid-guest-auth [data-testid="stAlert"] div,
    .sid-guest-auth [data-testid="stAlert"] span {
        color: #0f172a !important;
    }
    .sid-guest-auth div[data-testid="column"]:has(.sid-auth-form-heading) [data-testid="stFileUploader"] section small,
    .sid-guest-auth div[data-testid="column"]:has(.sid-auth-form-heading) [data-testid="stFileUploader"] section p,
    .sid-guest-auth div[data-testid="column"]:has(.sid-auth-form-heading) [data-testid="stFileUploader"] label {
        color: #0f172a !important;
    }
    /* Tab labels (Sign in / Register) and all inner tab text */
    .sid-guest-auth div[data-testid="column"]:has(.sid-auth-form-heading) [data-baseweb="tab"],
    .sid-guest-auth div[data-testid="column"]:has(.sid-auth-form-heading) [data-baseweb="tab"] p,
    .sid-guest-auth div[data-testid="column"]:has(.sid-auth-form-heading) [data-baseweb="tab"] span,
    .sid-guest-auth div[data-testid="column"]:has(.sid-auth-form-heading) [data-baseweb="tab"] div {
        color: #1e40af !important;
    }
    .sid-guest-auth div[data-testid="column"]:has(.sid-auth-form-heading) [data-baseweb="tab"][aria-selected="true"] p,
    .sid-guest-auth div[data-testid="column"]:has(.sid-auth-form-heading) [data-baseweb="tab"][aria-selected="true"] span,
    .sid-guest-auth div[data-testid="column"]:has(.sid-auth-form-heading) [data-baseweb="tab"][aria-selected="true"] div {
        color: #0c4a6e !important;
    }
    /* Text inputs, radio groups: BaseWeb / Streamlit label lines */
    .sid-guest-auth div[data-testid="column"]:has(.sid-auth-form-heading) [data-testid="stTextInput"] label,
    .sid-guest-auth div[data-testid="column"]:has(.sid-auth-form-heading) [data-testid="stTextInput"] [data-testid="stWidgetLabel"] *,
    .sid-guest-auth div[data-testid="column"]:has(.sid-auth-form-heading) [data-baseweb="form-control-label"] {
        color: #0f172a !important;
    }
</style>
"""


def _auth_hero_html() -> str:
    return """
<div class="sid-auth-hero">
  <div class="sid-auth-brand">
    <div class="sid-auth-logo-box" aria-hidden="true">&#127947;</div>
    <span class="sid-auth-brand-name">SID Fitness Assistant</span>
  </div>
  <div class="sid-auth-pulse" aria-hidden="true"></div>
  <h1>Training &amp; nutrition, <span class="sid-auth-gradient-text">reimagined</span></h1>
  <p class="sid-auth-lead">
    Your intelligent fitness companion for calorie insights, meal logging, weekly plans,
    and coach-style guidance—personalized suited to your needs.
  </p>
  <div class="sid-auth-features">
    <div class="sid-auth-feat">
      <span class="sid-auth-feat-icon">&#128200;</span>
      <div><strong>Smart calorie targets</strong><br><small>Planning based on your activity level</small></div>
    </div>
    <div class="sid-auth-feat">
      <span class="sid-auth-feat-icon">&#129367;</span>
      <div><strong>Meal analysis</strong><br><small>Photo &amp; text estimates tuned to your diet</small></div>
    </div>
    <div class="sid-auth-feat">
      <span class="sid-auth-feat-icon">&#128172;</span>
      <div><strong>AI coach</strong><br><small>Assistance linked to your goals</small></div>
    </div>
  </div>
</div>
"""


st.markdown(_compact_ui_css(), unsafe_allow_html=True)


def _query_param_single(key: str) -> str | None:
    if key not in st.query_params:
        return None
    v = st.query_params[key]
    if isinstance(v, list):
        return v[0] if v else None
    return str(v)


_reset_tok = _query_param_single("reset_token")
if _reset_tok:
    st.title("Set a new password")
    uid_reset = db.verify_reset_token(_reset_tok)
    if uid_reset is None:
        st.error(
            "This reset link is invalid or has expired. Request a new one under "
            "**Forgot password** on the sign-in page."
        )
        st.stop()
    un_reset = db.get_username(uid_reset)
    st.caption(f"Sign-in email: **{un_reset}**")
    with st.form("password_reset_complete_form"):
        rp1 = st.text_input("New password", type="password")
        rp2 = st.text_input("Confirm new password", type="password")
        do_reset = st.form_submit_button("Update password", use_container_width=False)
    if do_reset:
        if rp1 != rp2:
            st.error("Passwords do not match.")
        else:
            ok_pw, msg_pw = db.update_user_password(uid_reset, rp1)
            if ok_pw:
                db.mark_reset_token_used(_reset_tok)
                try:
                    st.query_params.clear()
                except Exception:
                    pass
                st.success(f"{msg_pw} You can sign in from the main app.")
            else:
                st.error(msg_pw)
    st.stop()

# -----------------------
# API key + LLM (EURI OpenAI-compatible or Google Gemini)
# -----------------------
try:
    gemini_env.resolve_gemini_credentials()
except ValueError as exc:
    st.error(str(exc))
    st.caption(
        "Use **EURI_API_KEY** (OpenAI-compatible EURI; **BASE_URL** defaults to "
        "`https://api.euron.one/api/v1/euri` if unset), or **GEMINI_API_KEY** for Google. "
        "Put them in **.env** and restart."
    )
    st.stop()

model = text_llm.build_text_model()

OUTPUT_FORMAT = """
Return response in this format:

Food Items:
- Item 1: calories
- Item 2: calories

Total Calories: XXXX kcal

Notes:
- Mention assumptions

Recommendation:
- Overall: Is this meal generally a sensible choice, an occasional treat, or something to limit? One or two plain-language sentences.
- Fit for fitness goal: Explicitly tie to the user's **Primary goal** from the profile (e.g. fat loss, muscle gain, maintenance, performance). If the profile does not state a goal, say that and give neutral guidance.
- Diet & safety: Note alignment with diet pattern, allergies, or foods to avoid from the profile when relevant (or "no conflicts noted" if none apply).
- Practical tip: One concrete tweak for next time if useful (portion, swap, or timing)—optional if the meal already fits well.
  Do not recommend **beef** (or beef-based products) as an addition or swap.
"""

COACH_SYSTEM = """You are a supportive nutrition and lifestyle coach who sounds like a real person—warm,
direct, and human—not a bot or a lecture. Your answers must be:
- Realistic and practical; avoid extreme or magical claims.
- Grounded in the user's profile, weight log, meal log, and conversation history provided below.
- Clear that you are not a doctor or registered dietitian and this is not medical advice.

PROFILE & SAVED DATA (every message): **SAVED PROFILE**, **COMPLETE PROFILE RECORD**, weight history, meals,
**DAILY ACTIVITY LOG** (user-logged exercise / meals-food / other by calendar day), and energy context are
**reloaded from the database for this exact question**—they reflect the user's **latest saves** (including any
profile updates since earlier chat). If older chat messages disagree with the profile or logs below,
**follow the profile and logs** and do not assume outdated details from chat history. When helpful, you may
briefly acknowledge an update (e.g. goal or weight change) if it stands out.

HUMAN TONE: Write the way a good coach would talk out loud. Short opening empathy when it fits
("That happens," "Good you checked in," "Two days off is not the end of a plan"). Avoid guilt, shame,
or moral language about food or missed workouts. No bullet-only robotic dumps unless they asked for a
list; mix sentences and, where useful, light structure.

SETBACKS & MISSED WORK (exercise, routine, "duties," gaps of a few days or more): When the user says
they could not follow through, fell behind, or disappeared for a while—treat it as normal life, not
failure. Do NOT scold or pile on "you should have." Instead:
- Acknowledge briefly and validate (stress, work, sleep, motivation dips are common).
- Offer a **practical adjustment**: e.g. extend the timeline by about the days lost, shift this week's
  plan forward, or trade intensity for consistency (shorter sessions, fewer days, walking instead of a
  hard workout, one non-negotiable "anchor" habit to restart).
- If they mention a specific gap (e.g. "2 days"), mirror that concretely: e.g. add two lighter catch-up
  days, or roll the block two days, or trim this week to what's doable and resume next week—pick what
  fits their goal and profile and say it plainly.
- Prefer **small, humane steps** they can actually do this week over a perfect program they won't start.
- If prior chat discussed a plan, **revise that plan** gently rather than starting from zero unless
  they want a fresh start.

MEAL PLANS: When the user asks for a meal plan, eating plan, day or week of meals, grocery-style ideas,
or what to eat to reach a fitness goal:
- Use their **country / region** and **cuisine preferences** so dishes, ingredients, and meal patterns
  are familiar and realistically available (typical breakfast/lunch/dinner, staples, local options).
- Align calories and macros with their **primary fitness goal** (e.g. fat loss: sustainable deficit,
  protein and fiber for satiety; muscle gain: adequate protein and energy; maintenance: balance around
  maintenance calories). If **ENERGY CONTEXT** below includes saved BMR/TDEE, treat those as rough
  guides only and state assumptions; if missing, infer sensible ranges from goal and profile.
- Respect **diet pattern** strictly: if **Vegetarian**, no meat/fish/poultry—eggs/dairy allowed unless notes say otherwise; if the user says vegetarian **and eats eggs**, centre **lacto-ovo**-style proteins. Apply **Vegan** / **Pescatarian** / other pattern the same way. Use **coach notes** and **meal timing** text for nuances (e.g. eggs OK, no dairy).
- Respect allergies, foods to avoid, health notes, and meal timing from the profile.
- Structure the answer clearly (e.g. by day or by meal) with portion cues and approximate calories per
  day or meal when reasonable. Offer regional swaps if an item may be hard to find.
- If country or goal is unclear, ask briefly or offer a default and label it as such. Never prescribe
  clinical therapeutic diets.
- **Never recommend beef** (steak, ground beef, beef dishes, beef broth/stock, etc.) in meal ideas or swaps; use other proteins instead.

GOAL TIMELINE & PROGRESS: A **GOAL TIMELINE** section lists dated moments when the user changed **Primary nutrition goal** in their profile or sent a **goal-related message** in this chat. Each row may include a **weight/height snapshot** captured at that moment. Use it together with **WEIGHT HISTORY** and **WEIGHT TREND** to:
- Summarise how long they have been pursuing the current (or a past) goal and what changed over that **period**.
- Compare logged weight change (or stability) to a **rough, non-clinical** sense of whether the pace looks **modest, fast, slow, or stalled** for their stated goal—use careful wording (e.g. "on the quick side," "quite gradual," "roughly in line with many sustainable plans") and never claim medical certainty.
- If progress seems **higher or lower than might be expected** given the timeline and logs, say so kindly and offer one practical adjustment (food, training, sleep, consistency, or expectations)—or acknowledge solid progress when it fits.
- Do **not** invent dates, weights, or events that are not in the timeline or weight log.

If information is missing, say what would help. Reference weight trends only when the log supports it.
Keep replies readable; use more detail when the user requests full-day or multi-day plans."""


def profile_to_blurb(p: dict) -> str:
    if not p:
        return "(Profile not filled in yet.)"
    lines = []
    if p.get("full_name"):
        lines.append(f"Name: {p['full_name']}")
    if p.get("email"):
        lines.append(f"Email: {p['email']}")
    if p.get("gender"):
        lines.append(f"Gender (profile): {p['gender']}")
    bw = p.get("body_weight_kg")
    if bw is not None:
        try:
            bwf = float(bw)
            if bwf > 0:
                lines.append(f"Body weight (kg): {bwf:.1f}")
        except (TypeError, ValueError):
            pass
    hf = p.get("height_feet")
    if hf is not None:
        try:
            hff = float(hf)
            if hff > 0:
                lines.append(f"Height (feet): {hff:.2f}")
        except (TypeError, ValueError):
            pass
    if p.get("activity_level"):
        lines.append(f"Activity level (TDEE): {p['activity_level']}")
    if p.get("diet_pattern"):
        dp = p["diet_pattern"]
        if dp == "Omnivore":
            dp = "Non vegetarian"
        lines.append(f"Diet pattern: {dp}")
    if p.get("cuisine_preferences"):
        lines.append(f"Cuisine preferences: {p['cuisine_preferences']}")
    if p.get("meal_timing_notes"):
        lines.append(f"Meal timing / routine: {p['meal_timing_notes']}")
    if p.get("foods_to_avoid"):
        lines.append(f"Foods to limit or avoid: {p['foods_to_avoid']}")
    if p.get("allergy_alerts"):
        lines.append(f"Allergy alerts (user-reported): {p['allergy_alerts']}")
    if p.get("health_conditions"):
        lines.append(f"Health conditions (user-reported): {p['health_conditions']}")
    if p.get("medication_supplement_notes"):
        lines.append(f"Medications / supplements (user-reported): {p['medication_supplement_notes']}")
    if p.get("lifestyle_work_pattern"):
        lines.append(f"Work / daily movement: {p['lifestyle_work_pattern']}")
    if p.get("lifestyle_exercise_freq"):
        lines.append(f"Exercise frequency: {p['lifestyle_exercise_freq']}")
    sh = p.get("sleep_hours_avg")
    if sh is not None:
        lines.append(f"Typical sleep (hours): {sh}")
    if p.get("alcohol_caffeine_notes"):
        lines.append(f"Alcohol / caffeine: {p['alcohol_caffeine_notes']}")
    if p.get("primary_goal"):
        lines.append(f"Primary goal: {p['primary_goal']}")
    if p.get("country_or_region"):
        lines.append(f"Country / region (meal planning): {p['country_or_region']}")
    if p.get("coach_notes"):
        lines.append(f"Notes for coach: {p['coach_notes']}")
    ua = p.get("updated_at")
    if ua:
        lines.append(f"Profile last saved (UTC): {ua}")
    return "\n".join(lines) if lines else "(Profile exists but fields are empty.)"


def profile_all_fields_for_coach(p: dict) -> str:
    """Every column from the saved profile row so the coach misses nothing after user updates."""
    if not p:
        return "(No profile row in database yet.)"
    chunks: list[str] = []
    for key in sorted(p.keys()):
        if key == "user_id":
            continue
        val = p.get(key)
        if val is None or (isinstance(val, str) and not str(val).strip()):
            chunks.append(f"- {key}: (not set)")
        else:
            chunks.append(f"- {key}: {val}")
    return "\n".join(chunks)


def format_weight_log(rows: list) -> str:
    if not rows:
        return "(No weight entries saved yet.)"
    lines = []
    for r in rows:
        extra = ""
        if r.get("bmr_at_log") and r.get("tdee_at_log"):
            extra = f" | BMR~{r['bmr_at_log']} TDEE~{r['tdee_at_log']} kcal (at log time)"
        lines.append(
            f"- {r['recorded_at'][:19]}Z: {r['raw_value']} {r['source_unit']} "
            f"({r['weight_kg']:.2f} kg){extra}"
        )
    return "\n".join(lines)


def weight_trend_summary(rows: list) -> str:
    if len(rows) < 2:
        return "Not enough saved weights for a trend yet (log at least two entries on different occasions)."
    chrono = list(reversed(rows))
    first, last = chrono[0], chrono[-1]
    delta = last["weight_kg"] - first["weight_kg"]
    if delta > 0.15:
        direction = "increasing"
    elif delta < -0.15:
        direction = "decreasing"
    else:
        direction = "roughly stable"
    return (
        f"Across {len(chrono)} logged points from {first['recorded_at'][:10]} to "
        f"{last['recorded_at'][:10]}: {first['weight_kg']:.2f} kg → {last['weight_kg']:.2f} kg "
        f"(change {delta:+.2f} kg; overall {direction})."
    )


def format_goal_timeline(events: list) -> str:
    """Readable block for the coach from ``db.list_goal_tracking_events``."""
    if not events:
        return (
            "(No dated goal events yet. A row is added when the user **changes Primary nutrition goal** "
            "in their profile and saved, or when they mention goals in coach chat—e.g. targets, timelines, "
            "lose/gain weight.)"
        )
    lines: list[str] = []
    for ev in events:
        ts = (ev.get("recorded_at") or "")[:19].replace("T", " ")
        src = (ev.get("source") or "").strip()
        pg = (ev.get("primary_goal_at_time") or "").strip() or "—"
        bw = ev.get("body_weight_kg")
        hf = ev.get("height_feet")
        snap_parts: list[str] = []
        if bw is not None:
            try:
                snap_parts.append(f"weight ~{float(bw):.2f} kg")
            except (TypeError, ValueError):
                pass
        if hf is not None:
            try:
                snap_parts.append(f"height ~{float(hf):.2f} ft")
            except (TypeError, ValueError):
                pass
        snap = f" Snapshot: {', '.join(snap_parts)}." if snap_parts else ""
        cnx = (ev.get("coach_notes_excerpt") or "").strip()
        cn_line = f" Coach notes (excerpt): {cnx[:280]}{'…' if len(cnx) > 280 else ''}" if cnx else ""
        det = (ev.get("detail") or "").strip()
        lines.append(
            f"- [{ts} UTC] source={src} | profile goal at event: **{pg}**{snap}{cn_line}\n  {det}"
        )
    return "\n".join(lines)


def _activity_kind_label(kind: str) -> str:
    return {
        "exercise": "Exercise",
        "meal_food": "Meal/food",
        "other": "Other",
    }.get((kind or "").strip(), kind or "Other")


def format_daily_activities_for_coach(rows: list) -> str:
    if not rows:
        return "(No entries in the daily activity log yet.)"
    lines: list[str] = []
    last_date = ""
    for r in rows:
        d = str(r.get("activity_date") or "")
        if d != last_date:
            last_date = d
            lines.append(f"\n=== {d} ===")
        note = (r.get("notes") or "").strip().replace("\n", " ")
        lines.append(f"- [{_activity_kind_label(r.get('kind', ''))}] {note}")
    return "\n".join(lines).strip()


def _render_daily_activity_logger(user_id: int) -> None:
    """Popover body: log by calendar day; coach prompt includes recent rows."""
    _today = date.today()
    st.caption(
        "Log **exercise**, **meals or food**, or **other** notes for any day. Your coach sees roughly the "
        "**last 90 days**."
    )
    _log_d = st.session_state.get("sid_activity_log_date")
    if isinstance(_log_d, date) and _log_d > _today:
        st.session_state["sid_activity_log_date"] = _today
    picked = st.date_input(
        "Date",
        value=_today,
        max_value=_today,
        key="sid_activity_log_date",
    )
    kind = st.selectbox(
        "Type",
        options=["exercise", "meal_food", "other"],
        format_func=lambda x: {
            "exercise": "Exercise / training",
            "meal_food": "Meal or food consumed",
            "other": "Other",
        }[x],
        key="sid_activity_log_kind",
    )
    notes = st.text_area(
        "What did you do or eat?",
        placeholder="e.g. 40 min strength; or oats, fruit, coffee for breakfast",
        key="sid_activity_log_notes",
        height=90,
    )
    if st.button("Save entry", key="sid_btn_save_activity", type="primary"):
        t = (notes or "").strip()
        if not t:
            st.warning("Add a short description.")
        else:
            db.add_daily_activity(user_id, picked.isoformat(), kind, t)
            st.success("Saved.")
            # Drop widget state so reopening the popover shows empty fields (not the last saved text).
            for _k in (
                "sid_activity_log_notes",
                "sid_activity_log_date",
                "sid_activity_log_kind",
            ):
                st.session_state.pop(_k, None)
            st.rerun()
    st.divider()
    st.markdown("**View a day**")
    st.caption("Pick a date to see everything you logged that day.")
    # Apply jump *before* st.date_input: Streamlit forbids mutating a widget's session key after it runs.
    _pending_jump = st.session_state.pop("sid_activity_jump_pending", None)
    if _pending_jump:
        try:
            _pj = date.fromisoformat(str(_pending_jump).strip()[:10])
            st.session_state["sid_activity_lookup_day"] = _pj if _pj <= _today else _today
        except ValueError:
            pass
    if "sid_activity_lookup_day" not in st.session_state:
        st.session_state["sid_activity_lookup_day"] = _today
    else:
        _lk = st.session_state["sid_activity_lookup_day"]
        if isinstance(_lk, date) and _lk > _today:
            st.session_state["sid_activity_lookup_day"] = _today
    lookup = st.date_input("Day", max_value=_today, key="sid_activity_lookup_day")
    day_key = lookup.isoformat()
    day_entries = db.list_daily_activities_on_date(user_id, day_key)
    if not day_entries:
        st.info("No entries for this day.")
    else:
        st.caption(f"{len(day_entries)} entr{'y' if len(day_entries) == 1 else 'ies'} on **{day_key}**")
        for r in day_entries:
            ts = (r.get("created_at") or "")[:16].replace("T", " ")
            st.markdown(f"**{_activity_kind_label(r.get('kind', ''))}**" + (f" · saved {ts}" if ts.strip() else ""))
            st.write((r.get("notes") or "").strip() or "—")

    recent = db.list_daily_activities(user_id, days_back=120)
    if recent:
        st.divider()
        st.caption("**Jump to a recent day** (sets the day above)")
        distinct: list[str] = []
        for r in recent:
            dd = r["activity_date"]
            if dd not in distinct:
                distinct.append(dd)
            if len(distinct) >= 16:
                break
        ncols = min(4, max(1, len(distinct)))
        cols = st.columns(ncols)
        for i, dd in enumerate(distinct):
            with cols[i % ncols]:
                if st.button(dd, key=f"sid_act_jump_{dd}", use_container_width=True):
                    st.session_state["sid_activity_jump_pending"] = dd
                    st.rerun()
    elif not day_entries:
        st.caption("Save an entry above to start your log.")


def format_meal_log(rows: list) -> str:
    if not rows:
        return "(No saved meals yet.)"
    chunks = []
    for r in rows:
        snippet = (r.get("description_snippet") or "").strip() or "(no description)"
        body = (r.get("model_response") or "")[:900]
        chunks.append(f"- {r['logged_at'][:19]} | {snippet}\n  Summary/excerpt: {body}...")
    return "\n".join(chunks)


def energy_context_from_weights(rows: list) -> str:
    """Most recent weight log row that captured BMR/TDEE at save time."""
    for r in rows:
        tdee = r.get("tdee_at_log")
        bmr = r.get("bmr_at_log")
        if tdee is not None or bmr is not None:
            return (
                f"Latest saved snapshot (from weight log): BMR ~{bmr} kcal/day, "
                f"TDEE ~{tdee} kcal/day — use only as approximate planning context."
            )
    return (
        "No BMR/TDEE saved with weight entries yet. Base meal-plan calories on goal and profile, "
        "or suggest the user save weight with daily-needs once for rough targets."
    )


def _coach_image_mime(raw: str | None) -> str:
    m = (raw or "").strip().lower()
    if m in ("image/png", "image/x-png"):
        return "image/png"
    return "image/jpeg"


def _coach_progress_photo_instructions() -> str:
    return """
=== PROGRESS PHOTO (image attached to this request) ===
The user attached a **current body / progress photograph**. You receive it as pixels (not summarized in text).

How to respond:
- Be **warm and non-judgmental**; never shame appearance or tie worth to body shape.
- Give **cautious, approximate** impressions only: lighting, angle, pose, clothing, and camera distance make photos unreliable for true body composition. Do **not** claim exact body fat percentage, medical diagnosis, or definitive proof that a goal is fully "achieved."
- Use **primary goal**, **GOAL TIMELINE**, and **WEIGHT HISTORY** together: say whether progress **seems broadly consistent** with their goal when the visual and logs align, or say the picture alone is **inconclusive** and invite better data.
- If you cannot judge direction from the photo, or to sharpen the assessment, ask **1–3 concrete questions** (e.g. current scale weight, waist or how clothes fit, training frequency, weeks since last check-in photo).
- Prefer **habits and next steps** over appearance critique; celebrate effort where it fits.

"""


def build_coach_prompt(
    user_id: int, user_question: str, *, body_photo_attached: bool = False
) -> str:
    p = db.get_profile(user_id)
    weights = db.list_weight_entries(user_id, 30)
    goal_events = db.list_goal_tracking_events(user_id, 40)
    meals = db.list_meal_entries(user_id, 8)
    activities = db.list_daily_activities(user_id, 90)
    activity_block = format_daily_activities_for_coach(activities)
    history = db.list_chat_messages(user_id, 24)
    hist_lines = []
    for h in history:
        role = "User" if h["role"] == "user" else "Coach"
        ts = (h.get("created_at") or "")[:10]
        stamp = f"[{ts}] " if ts else ""
        hist_lines.append(f"{stamp}{role}: {h['content']}")
    hist_block = "\n".join(hist_lines) if hist_lines else "(No prior messages in this chat.)"
    last_meal = st.session_state.get("last_meal_context") or ""

    photo_note = (
        "yes (used for weekly plan imagery)"
        if db.has_profile_image(user_id)
        else "no"
    )
    login_id = db.get_username(user_id) or ""

    return f"""{COACH_SYSTEM}

=== PROFILE CONTEXT (this turn) ===
- Data below was read from the database when the user sent this message (latest saves apply).
- Account sign-in email: {login_id}
- Profile photo on file: {photo_note}

=== SAVED PROFILE (readable summary) ===
{profile_to_blurb(p)}

=== COMPLETE PROFILE RECORD (all stored fields; use for accuracy after any user update) ===
{profile_all_fields_for_coach(p)}

=== ENERGY CONTEXT (for meal-plan calorie alignment) ===
{energy_context_from_weights(weights)}

=== WEIGHT HISTORY (newest first in log below) ===
{format_weight_log(weights)}

=== WEIGHT TREND (from saved entries) ===
{weight_trend_summary(weights)}

=== GOAL TIMELINE (dated goal changes & goal-related chat; use with weight log for progress over time) ===
{format_goal_timeline(goal_events)}

=== RECENT SAVED MEALS ===
{format_meal_log(meals)}

=== DAILY ACTIVITY LOG (user-logged by calendar day; exercise, meals/food, other—~last 90 days) ===
{activity_block}

=== PRIOR CHAT (chronological; bracketed dates = when saved—use gaps to infer time away) ===
{hist_block}

=== LATEST MEAL ANALYSIS (current session; may be unsaved) ===
{last_meal if last_meal.strip() else "(None in this session yet.)"}
{_coach_progress_photo_instructions() if body_photo_attached else ""}
---
The user's new question:
{user_question}
"""


def build_analysis_prompt(
    has_image: bool, description: str, profile_context: str
) -> str:
    has_text = bool(description.strip())
    pc = (
        profile_context.strip()
        or "No personal profile was provided for this request."
    )
    profile_block = f"""
User-provided profile context (respect preferences; flag possible allergy conflicts in notes; not a medical diagnosis):
{pc}
"""
    tasks = """
1. Identify food items (from the image and/or description as applicable)
2. Estimate portion sizes
3. Provide total calorie estimate
4. Break down calories per item
5. Add the **Recommendation** section from the output format: judge in general terms whether items are
   relatively nutritious or better as occasional choices; align advice with the user's **Primary goal**,
   diet pattern, allergies, and foods to avoid from the profile. If **Vegetarian**, do not suggest meat or fish;
   if notes say vegetarian **with eggs** (or similar), eggs and dairy are acceptable in suggestions unless excluded elsewhere.
   Be supportive and non-judgmental; avoid moralizing about food. This is general information only, not medical advice.
6. Do not suggest **beef** or beef-based foods as improvements or alternatives.
"""
    if has_image and has_text:
        return f"""You are a nutrition expert.
{profile_block}
The user provided BOTH a photo and a written description. Use them together: the description
may clarify items, brands, or portions the photo alone cannot show; the photo may show amounts
or items not fully spelled out in text. If they conflict, note the conflict and explain how you
reconciled it.

User description:
\"\"\"{description.strip()}\"\"\"

Then complete these steps:
{tasks}
{OUTPUT_FORMAT}
"""
    if has_image:
        return f"""You are a nutrition expert.
{profile_block}
The user provided a photo only (no extra text description). Analyze the food in the image and:
{tasks}
{OUTPUT_FORMAT}
"""
    return f"""You are a nutrition expert.
{profile_block}
The user provided a text description only (no photo). Estimate calories from their description;
state reasonable assumptions where portions or preparation are unclear.

User description:
\"\"\"{description.strip()}\"\"\"

Complete these steps:
{tasks}
{OUTPUT_FORMAT}
"""


LBS_TO_KG = 0.45359237
FT_TO_CM = 30.48

ACTIVITY_LEVELS = [
    ("Sedentary (little or no exercise)", 1.2),
    ("Light (1-3 days/week)", 1.375),
    ("Moderate (3-5 days/week)", 1.55),
    ("Active (6-7 days/week)", 1.725),
    ("Very active (hard exercise / physical job)", 1.9),
]


def bmr_mifflin_st_jeor(weight_kg: float, height_cm: float, age: int, sex: str) -> float:
    male = 10 * weight_kg + 6.25 * height_cm - 5 * age + 5
    female = 10 * weight_kg + 6.25 * height_cm - 5 * age - 161
    if sex == "Male":
        return male
    if sex == "Female":
        return female
    return (male + female) / 2


def estimate_tdee_from_profile(
    p: dict, age_years: int = 30
) -> tuple[float | None, float | None]:
    """Return (bmr, tdee) from saved profile, or (None, None) if insufficient data."""
    try:
        wk = p.get("body_weight_kg")
        if wk is None or float(wk) <= 0:
            return None, None
        weight_kg = float(wk)
        hf = p.get("height_feet")
        if hf is None or float(hf) <= 0:
            return None, None
        height_cm = float(hf) * FT_TO_CM
        g = (p.get("gender") or "").strip()
        if g == "Male":
            sex = "Male"
        elif g == "Female":
            sex = "Female"
        else:
            sex = "Average (midpoint)"
        act = (p.get("activity_level") or "").strip()
        labels = [lab for lab, _ in ACTIVITY_LEVELS]
        if act not in labels:
            return None, None
        factor = dict(ACTIVITY_LEVELS)[act]
        bmr = bmr_mifflin_st_jeor(weight_kg, height_cm, age_years, sex)
        return bmr, bmr * factor
    except (TypeError, ValueError):
        return None, None


def _weekly_plan_diet_constraint_lines(p: dict) -> list[str]:
    """Hard rules injected into weekly plan nutrition instructions (matches profile diet_pattern)."""
    dp = (p.get("diet_pattern") or "").strip()
    if dp == "Omnivore":
        dp = "Non vegetarian"
    nuance = workout_plan.diet_nuance_blob_from_profile(p)
    out: list[str] = []

    if dp == "Vegetarian":
        out.append(
            "**Mandatory — Vegetarian:** Every breakfast, lunch, and dinner must be **fully vegetarian**: "
            "no meat, poultry, fish, shellfish, or other animal flesh. **Eggs and dairy are allowed** unless "
            "the profile or notes explicitly rule them out (e.g. vegan, no eggs, plant-based only). If the user "
            "states they are vegetarian **and still eat eggs** (or similar), treat as **lacto-ovo vegetarian**: "
            "use eggs and dairy as primary proteins where appropriate and reflect that in meal wording."
        )
    elif dp == "Vegan":
        out.append(
            "**Mandatory — Vegan:** No animal products of any kind—no meat, fish, poultry, dairy, eggs, or honey. "
            "Use legumes, tofu, tempeh, nuts, seeds, and plant-based alternatives only."
        )
    elif dp == "Pescatarian":
        out.append(
            "**Mandatory — Pescatarian:** Fish and seafood are allowed; **no poultry or red meat**. "
            "Eggs and dairy follow the profile and notes."
        )
    elif dp == "Flexitarian":
        out.append(
            "**Flexitarian:** Emphasize plant-forward meals; use fish or small amounts of animal protein only when "
            "consistent with the user's notes—not as the default every day unless their request says otherwise."
        )
    elif dp == "Other / mixed":
        out.append(
            "**Diet pattern — Other / mixed:** Follow every dietary detail in the profile summary and in the "
            "**User-stated dietary detail** line below; when instructions conflict, use the stricter or more "
            "specific user wording."
        )
    elif dp in ("Non vegetarian", ""):
        pass
    else:
        out.append(
            f"**Diet pattern ({dp}):** Align all meals with this pattern and with the user notes below."
        )

    if nuance:
        out.append(
            "**User-stated dietary detail (honour in every meal line, including protein choices and swaps):** "
            + nuance
        )
    return out


def build_week_plan_nutrition_block(p: dict, weight_rows: list) -> str:
    """TDEE anchor + goal-based calorie rules for the weekly meal section of the plan."""
    lines: list[str] = []
    bmr, tdee_prof = estimate_tdee_from_profile(p)
    log_tdee: float | None = None
    log_bmr: int | None = None
    for r in weight_rows:
        t = r.get("tdee_at_log")
        if t is not None:
            try:
                log_tdee = float(t)
            except (TypeError, ValueError):
                continue
            lb = r.get("bmr_at_log")
            if lb is not None:
                try:
                    log_bmr = int(round(float(lb)))
                except (TypeError, ValueError):
                    log_bmr = None
            break

    if log_tdee is not None:
        extra = f", BMR ≈ {log_bmr} kcal/day" if log_bmr is not None else ""
        lines.append(
            f"Primary **maintenance (TDEE)** reference: **~{round(log_tdee)} kcal/day** from the user's latest saved "
            f"weight log{extra}. Use this number when judging whether daily meal totals are below/at/above maintenance."
        )
    elif tdee_prof is not None and bmr is not None:
        lines.append(
            f"Estimated **maintenance (TDEE)** from profile: **~{round(tdee_prof)} kcal/day** "
            f"(BMR ~{round(bmr)} kcal/day via Mifflin–St Jeor, age {30}, activity from profile). "
            "Use this as the maintenance reference for meal-day calorie totals."
        )
    else:
        lines.append(
            "TDEE could not be computed from the profile; infer reasonable daily calorie levels from body weight, "
            "activity, and goal, and state briefly that figures are approximate."
        )

    goal = (p.get("primary_goal") or "").strip()
    if goal == "Fat loss":
        lines.append(
            "**Fat loss:** Each day's **Day total (food)** must be **clearly below** the maintenance/TDEE reference above "
            "(typically about **300–500 kcal/day** under TDEE unless the user's week request specifies a different deficit). "
            "Rest or light days can be slightly lower than heavy training days but still include adequate protein."
        )
    elif goal == "Muscle gain":
        lines.append(
            "**Muscle gain:** Daily food totals should be **at or modestly above** TDEE (often **~200–350 kcal** above), "
            "with **high protein** every day; align carbs somewhat with harder training days."
        )
    elif goal == "Maintain weight":
        lines.append(
            "**Maintain weight:** Keep each day's food total **close to** TDEE (roughly within **±150–200 kcal**)."
        )
    elif goal in ("Athletic performance", "General health", "Other"):
        lines.append(
            f"**{goal}:** Fuel training adequately; use TDEE as a rough anchor unless the user explicitly wants a cut or bulk."
        )
    else:
        lines.append(
            "**Primary goal not set:** Use balanced meals; if TDEE is known, keep days near maintenance unless the user request implies otherwise."
        )

    lines.extend(_weekly_plan_diet_constraint_lines(p))
    lines.append(
        "Obey **allergy alerts** and **foods to avoid** in every breakfast, lunch, and dinner."
    )
    lines.append(
        "**No beef:** Do not include beef, steak, ground beef, or beef-based broths/stocks/proteins in any meal suggestion."
    )
    lines.append(
        "**Human variety:** Day totals and the closing one-liner under **Day total** must differ across the seven days—vary calories slightly "
        "day to day (within goal rules) and rephrase; avoid repeating the same sentence or the same kcal total every day."
    )
    return "\n".join(lines)


def _dp_index(saved: str | None) -> int:
    opts = [
        "",
        "Non vegetarian",
        "Vegetarian",
        "Vegan",
        "Pescatarian",
        "Flexitarian",
        "Other / mixed",
    ]
    if saved == "Omnivore":
        saved = "Non vegetarian"
    return opts.index(saved) if saved in opts else 0


def _lw_index(saved: str | None) -> int:
    opts = [
        "",
        "Mostly seated / desk",
        "Mixed seated and standing",
        "On feet most of the day",
        "Physically demanding job",
    ]
    return opts.index(saved) if saved in opts else 0


def _ex_index(saved: str | None) -> int:
    opts = [
        "",
        "Rarely",
        "1–2 times per week",
        "3–4 times per week",
        "5+ times per week",
    ]
    return opts.index(saved) if saved in opts else 0


def _goal_index(saved: str | None) -> int:
    opts = [
        "",
        "Maintain weight",
        "Fat loss",
        "Muscle gain",
        "Athletic performance",
        "General health",
        "Other",
    ]
    return opts.index(saved) if saved in opts else 0


def _gender_index(saved: str | None) -> int:
    opts = ["", "Male", "Female", "Non-binary", "Prefer not to say"]
    return opts.index(saved) if saved in opts else 0


REQUIRED_GENDERS = frozenset({"Male", "Female", "Non-binary", "Prefer not to say"})


def _activity_level_index(saved: str | None) -> int:
    labels = [lab for lab, _ in ACTIVITY_LEVELS]
    s = (saved or "").strip()
    if s in labels:
        return labels.index(s)
    return 2


def _mandatory_field_label(label_plain: str) -> None:
    st.markdown(
        '<p style="margin:0 0 0.25rem 0;font-size:0.9rem;line-height:1.35;">'
        f'<span style="color:#dc2626;font-weight:700">*</span> {html.escape(label_plain)}</p>',
        unsafe_allow_html=True,
    )


def profile_has_required_fields(p: dict) -> bool:
    if not p:
        return False
    bw = p.get("body_weight_kg")
    try:
        if bw is None or float(bw) <= 0:
            return False
    except (TypeError, ValueError):
        return False
    hf = p.get("height_feet")
    try:
        if hf is None or float(hf) <= 0:
            return False
    except (TypeError, ValueError):
        return False
    if (p.get("gender") or "").strip() not in REQUIRED_GENDERS:
        return False
    act = (p.get("activity_level") or "").strip()
    labels = [lab for lab, _ in ACTIVITY_LEVELS]
    return act in labels


uid = st.session_state.user_id
active = uid is not None


def _signed_in_theme_css() -> str:
    return """
<style>
    /* Match guest login: light blue page gradient */
    .stApp {
        background: linear-gradient(160deg, #bfdbfe 0%, #dbeafe 35%, #e0f2fe 70%, #f0f9ff 100%) !important;
        color-scheme: light;
        color: #0f172a !important;
    }
    section.main > div {
        max-width: 100%;
    }
    .main .block-container {
        background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%) !important;
        border-radius: 20px !important;
        border: 1px solid rgba(59, 130, 246, 0.22) !important;
        box-shadow:
            0 4px 6px -1px rgba(37, 99, 235, 0.08),
            0 16px 40px -12px rgba(14, 165, 233, 0.15) !important;
        padding-top: 1.35rem !important;
        padding-bottom: 2.5rem !important;
        margin-top: 0.5rem !important;
    }
    header[data-testid="stHeader"] {
        background: rgba(255, 255, 255, 0.55) !important;
        backdrop-filter: blur(8px);
        border-bottom: 1px solid rgba(59, 130, 246, 0.2) !important;
    }
    [data-testid="stToolbar"] {
        background: rgba(255, 255, 255, 0.45) !important;
    }
    .main .block-container div[data-testid="stHorizontalBlock"]:first-of-type
        div[data-testid="column"]:last-child {
        background: linear-gradient(165deg, #ffffff 0%, #f0f9ff 45%, #e0f2fe 100%);
        border: 1px solid rgba(59, 130, 246, 0.28);
        border-radius: 16px;
        padding: 0.55rem 0.9rem 0.65rem;
        box-shadow: 0 4px 20px rgba(37, 99, 235, 0.12);
        margin-top: 0.15rem;
    }
    .main .block-container div[data-testid="stHorizontalBlock"]:first-of-type
        div[data-testid="column"]:last-child > div {
        display: flex !important;
        flex-direction: column !important;
        align-items: flex-end !important;
        gap: 0 !important;
        width: 100%;
    }
    .main .block-container div[data-testid="stHorizontalBlock"]:first-of-type
        div[data-testid="column"]:last-child div[data-testid="stButton"] > button {
        border-radius: 12px !important;
        border: none !important;
        background: linear-gradient(90deg, #2563eb 0%, #0d9488 100%) !important;
        color: #ffffff !important;
        font-weight: 600 !important;
        box-shadow: 0 4px 12px rgba(37, 99, 235, 0.25) !important;
    }
    .main .block-container div[data-testid="stHorizontalBlock"]:first-of-type
        div[data-testid="column"]:last-child div[data-testid="stButton"] > button:hover {
        filter: brightness(1.05);
        box-shadow: 0 6px 16px rgba(37, 99, 235, 0.32) !important;
    }
    .main .block-container h1 {
        color: #0f172a !important;
        font-weight: 800 !important;
        letter-spacing: -0.03em !important;
    }
</style>
"""


def render_main_content() -> None:
    if not active:
        st.info("Sign in or register (left) to use your profile, meal photos, saved logs, and coaching.")

    if uid:
        prof = db.get_profile(uid)
        _prof_ok = profile_has_required_fields(prof)

        def _render_profile_editor() -> None:
            # Streamlit expanders only use expanded= on first paint; after photo save + rerun the
            # section can stay collapsed and hide the form. When required fields are missing, render
            # outside an expander so fields stay visible.
            st.markdown("##### Profile photo")
            pimg_path = db.profile_image_path(uid)
            _has_prof_photo = db.has_profile_image(uid)
            # New key after each successful file save so Streamlit clears the uploader. Otherwise the
            # same file stays selected across reruns and we save+rerun every run—never reaching the form.
            _prof_upload_k = int(st.session_state.get("profile_photo_uploader_key", 0))
            _prof_up_key = f"profile_photo_uploader_{_prof_upload_k}"
            cam_shot = None
            if _has_prof_photo:
                st.image(str(pimg_path), width=140)
                up_prof = st.file_uploader(
                    "profile_file",
                    type=["jpg", "jpeg", "png"],
                    key=_prof_up_key,
                    label_visibility="collapsed",
                )
            else:
                st.session_state.setdefault("profile_camera_open", False)
                st.caption(
                    "Upload a picture, or tap **Take photo** when you want to use the camera (it does not open by itself)."
                )
                up_prof = st.file_uploader(
                    "profile_file",
                    type=["jpg", "jpeg", "png"],
                    key=_prof_up_key,
                    label_visibility="collapsed",
                )
                if st.button("Take photo", key="btn_profile_open_camera"):
                    st.session_state["profile_camera_open"] = True
                    st.rerun()
                if st.session_state.get("profile_camera_open"):
                    if st.button("Close camera", key="btn_profile_close_camera"):
                        st.session_state["profile_camera_open"] = False
                        st.session_state.profile_photo_cam_widget_key = (
                            int(st.session_state.get("profile_photo_cam_widget_key", 0)) + 1
                        )
                        st.rerun()
                    _cam_wkey = st.session_state.setdefault("profile_photo_cam_widget_key", 0)
                    cam_shot = st.camera_input(
                        "profile_cam",
                        key=f"profile_photo_camera_{_cam_wkey}",
                        label_visibility="collapsed",
                    )
            if _has_prof_photo:
                if st.button("Take profile photo", key="btn_remove_profile_photo"):
                    db.remove_profile_image(uid)
                    st.session_state["profile_camera_open"] = False
                    st.session_state.profile_photo_cam_widget_key = (
                        int(st.session_state.get("profile_photo_cam_widget_key", 0)) + 1
                    )
                    st.session_state["profile_photo_uploader_key"] = _prof_upload_k + 1
                    st.success("Profile photo removed.")
                    st.rerun()

            _photo_saved = False
            if up_prof is not None:
                try:
                    db.PROFILE_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
                    im = Image.open(up_prof).convert("RGB")
                    im.thumbnail((1024, 1024))
                    im.save(pimg_path, "JPEG", quality=88)
                    st.session_state["profile_photo_uploader_key"] = _prof_upload_k + 1
                    _photo_saved = True
                except Exception as exc:
                    st.error(f"Could not save photo: {exc}")
            if not _photo_saved and cam_shot is not None:
                try:
                    db.PROFILE_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
                    im = Image.open(cam_shot).convert("RGB")
                    im.thumbnail((1024, 1024))
                    im.save(pimg_path, "JPEG", quality=88)
                    st.session_state["profile_camera_open"] = False
                    st.session_state.profile_photo_cam_widget_key = (
                        int(st.session_state.get("profile_photo_cam_widget_key", 0)) + 1
                    )
                    st.session_state["profile_photo_uploader_key"] = _prof_upload_k + 1
                    _photo_saved = True
                except Exception as exc:
                    st.error(f"Could not save camera photo: {exc}")
            if _photo_saved:
                st.success("Profile photo saved.")
                st.rerun()

            with st.form("profile_form"):
                st.markdown("##### Personal")
                c1, c2 = st.columns(2)
                with c1:
                    full_name = st.text_input(
                        "Full name",
                        value=prof.get("full_name") or "",
                        placeholder="e.g. Alex Rivera",
                    )
                with c2:
                    _mandatory_field_label("Gender")
                    gender = st.selectbox(
                        "profile_gender",
                        ["", "Male", "Female", "Non-binary", "Prefer not to say"],
                        index=_gender_index(prof.get("gender")),
                        label_visibility="collapsed",
                    )
                login_mail = (db.get_username(uid) or "").strip()
                _ph_place = db.is_phone_placeholder_account(uid)
                if _ph_place:
                    profile_login_email = st.text_input(
                        "Email (sign-in)",
                        value=(prof.get("email") or "").strip(),
                        placeholder="you@example.com",
                        help="Add your email to sign in with email and password and to receive password resets.",
                        key="profile_editable_email",
                    )
                else:
                    profile_login_email = ""
                    st.text_input(
                        "Email (sign-in)",
                        value=login_mail,
                        disabled=True,
                        help="Your sign-in email (from registration).",
                        key="profile_readonly_email",
                    )
                profile_phone = st.text_input(
                    "Mobile number",
                    value=(prof.get("phone_e164") or "") or "",
                    placeholder="e.g. +91 98765 43210",
                    help="Sign in with this number (password or OTP). Changing it updates where OTP is sent.",
                    key="profile_phone_input",
                )
                country_or_region = st.text_input(
                    "Country / region",
                    value=prof.get("country_or_region") or "",
                    placeholder="e.g. India, Brazil, United Kingdom — used for local meal plans",
                )
                try:
                    _saved_bw = float(prof["body_weight_kg"])
                    if _saved_bw < 0:
                        _saved_bw = 0.0
                except (TypeError, ValueError, KeyError):
                    _saved_bw = 0.0
                _mandatory_field_label("Body weight (kg)")
                body_weight_kg = st.number_input(
                    "profile_body_weight_kg",
                    min_value=0.0,
                    value=float(_saved_bw),
                    step=0.1,
                    label_visibility="collapsed",
                    help="Must be greater than zero to use calorie estimates, coach, meal analysis, and workout plan.",
                )
                try:
                    _saved_hf = float(prof["height_feet"])
                    if _saved_hf < 0:
                        _saved_hf = 0.0
                except (TypeError, ValueError, KeyError):
                    _saved_hf = 0.0
                _mandatory_field_label("Height (feet)")
                height_feet = st.number_input(
                    "profile_height_feet",
                    min_value=0.0,
                    value=float(_saved_hf),
                    step=0.01,
                    label_visibility="collapsed",
                    help="Total height in feet (decimals allowed), e.g. 5.5 = 5′6″, 5.75 = 5′9″.",
                )
                _act_labels = [lab for lab, _ in ACTIVITY_LEVELS]
                _mandatory_field_label("Activity level")
                activity_level = st.selectbox(
                    "profile_activity_level",
                    _act_labels,
                    index=_activity_level_index(prof.get("activity_level")),
                    label_visibility="collapsed",
                    help="Used for your TDEE estimate (daily calorie needs).",
                )

                st.markdown("##### Meal preferences")
                diet_pattern = st.selectbox(
                    "Diet pattern",
                    [
                        "",
                        "Non vegetarian",
                        "Vegetarian",
                        "Vegan",
                        "Pescatarian",
                        "Flexitarian",
                        "Other / mixed",
                    ],
                    index=_dp_index(prof.get("diet_pattern")),
                )
                cuisine_preferences = st.text_area(
                    "Preferred cuisines & favorite foods",
                    value=prof.get("cuisine_preferences") or "",
                    placeholder="e.g. Mediterranean, Japanese; enjoys high-protein breakfasts",
                    height=68,
                )
                meal_timing_notes = st.text_input(
                    "Typical meal timing / routine",
                    value=prof.get("meal_timing_notes") or "",
                    placeholder="e.g. 16:8 window; lunch ~1pm; train evenings",
                )
                foods_to_avoid = st.text_area(
                    "Foods to limit or avoid (non-allergy)",
                    value=prof.get("foods_to_avoid") or "",
                    placeholder="e.g. deep-fried foods, sugary sodas",
                    height=68,
                )
                allergy_alerts = st.text_area(
                    "Allergy or intolerance alerts (self-reported)",
                    value=prof.get("allergy_alerts") or "",
                    placeholder="e.g. peanut anaphylaxis; lactose intolerance",
                    height=68,
                )
    
                st.markdown("##### Health (self-reported — not verified)")
                health_conditions = st.text_area(
                    "Health conditions relevant to diet or activity",
                    value=prof.get("health_conditions") or "",
                    placeholder="e.g. Type 2 diabetes (managed); hypertension",
                    height=72,
                )
                medication_supplement_notes = st.text_area(
                    "Medications or supplements",
                    value=prof.get("medication_supplement_notes") or "",
                    placeholder="e.g. vitamin D; discuss changes with your clinician",
                    height=68,
                )
    
                st.markdown("##### Lifestyle")
                lifestyle_work_pattern = st.selectbox(
                    "Typical workday movement",
                    [
                        "",
                        "Mostly seated / desk",
                        "Mixed seated and standing",
                        "On feet most of the day",
                        "Physically demanding job",
                    ],
                    index=_lw_index(prof.get("lifestyle_work_pattern")),
                )
                lifestyle_exercise_freq = st.selectbox(
                    "Structured exercise frequency",
                    [
                        "",
                        "Rarely",
                        "1–2 times per week",
                        "3–4 times per week",
                        "5+ times per week",
                    ],
                    index=_ex_index(prof.get("lifestyle_exercise_freq")),
                )
                sleep_hours_avg = st.number_input(
                    "Average sleep (hours/night)",
                    min_value=0.0,
                    max_value=16.0,
                    value=float(prof["sleep_hours_avg"])
                    if prof.get("sleep_hours_avg") is not None
                    else 7.0,
                    step=0.25,
                )
                alcohol_caffeine_notes = st.text_input(
                    "Alcohol & caffeine",
                    value=prof.get("alcohol_caffeine_notes") or "",
                    placeholder="e.g. 2 coffees/day; alcohol weekends only",
                )
                primary_goal = st.selectbox(
                    "Primary nutrition goal",
                    [
                        "",
                        "Maintain weight",
                        "Fat loss",
                        "Muscle gain",
                        "Athletic performance",
                        "General health",
                        "Other",
                    ],
                    index=_goal_index(prof.get("primary_goal")),
                )
                coach_notes = st.text_area(
                    "Anything else the coach should know",
                    value=prof.get("coach_notes") or "",
                    placeholder="e.g. travel weekly; prefers simple grocery lists",
                    height=68,
                )
    
                save_prof = st.form_submit_button("Save profile", use_container_width=False)
            if save_prof:
                _save_errs: list[str] = []
                if body_weight_kg <= 0:
                    _save_errs.append("body weight (kg) must be greater than zero")
                if height_feet <= 0:
                    _save_errs.append("height (feet) must be greater than zero")
                if not (gender or "").strip():
                    _save_errs.append("gender must be selected")
                elif (gender or "").strip() not in REQUIRED_GENDERS:
                    _save_errs.append("gender must be one of the listed options")
                if _save_errs:
                    st.error("Cannot save profile: " + "; ".join(_save_errs) + ".")
                else:
                    _acct_ok = True
                    _is_ph = db.is_phone_placeholder_account(uid)
                    if _is_ph and (profile_login_email or "").strip():
                        _e_ok, _e_msg = db.update_user_login_email(
                            uid, profile_login_email.strip()
                        )
                        if not _e_ok:
                            st.error(_e_msg)
                            _acct_ok = False
                    if _acct_ok:
                        _p_ok, _p_msg = db.set_user_phone_e164(uid, profile_phone)
                        if not _p_ok:
                            st.error(_p_msg)
                            _acct_ok = False
                    if _acct_ok:
                        _u = db.get_username(uid) or ""
                        if not db.is_phone_placeholder_account(uid):
                            sync_email = db.normalize_login_email(_u)
                        else:
                            sync_email = db.normalize_login_email(
                                (profile_login_email or "").strip()
                            )
                        db.upsert_profile(
                            uid,
                            {
                                "full_name": full_name.strip(),
                                "email": sync_email,
                                "gender": gender.strip(),
                                "body_weight_kg": float(body_weight_kg),
                                "height_feet": float(height_feet),
                                "activity_level": activity_level,
                                "country_or_region": country_or_region.strip(),
                                "diet_pattern": diet_pattern,
                                "cuisine_preferences": cuisine_preferences.strip(),
                                "meal_timing_notes": meal_timing_notes.strip(),
                                "foods_to_avoid": foods_to_avoid.strip(),
                                "allergy_alerts": allergy_alerts.strip(),
                                "health_conditions": health_conditions.strip(),
                                "medication_supplement_notes": medication_supplement_notes.strip(),
                                "lifestyle_work_pattern": lifestyle_work_pattern,
                                "lifestyle_exercise_freq": lifestyle_exercise_freq,
                                "sleep_hours_avg": sleep_hours_avg,
                                "alcohol_caffeine_notes": alcohol_caffeine_notes.strip(),
                                "primary_goal": primary_goal,
                                "coach_notes": coach_notes.strip(),
                            },
                        )
                        db.record_profile_primary_goal_change(
                            uid,
                            prof.get("primary_goal"),
                            primary_goal,
                            body_weight_kg=float(body_weight_kg),
                            height_feet=float(height_feet),
                            coach_notes=coach_notes.strip(),
                        )
                        st.success("Profile saved.")
                        st.rerun()

        if not _prof_ok:
            st.markdown("### My profile — preferences, health, and lifestyle")
            st.caption(
                "Scroll below your photo to **Personal** for weight, height, gender, and activity level, "
                "then **Save profile**."
            )
            _render_profile_editor()
        else:
            with st.expander("My profile — preferences, health, and lifestyle", expanded=False):
                _render_profile_editor()

        if not profile_has_required_fields(db.get_profile(uid)):
            st.warning("Please fill mandatory fields above to avail the services")
            return

        with st.expander("1-week training & meal plan", expanded=False):
            wo_ctx = st.text_area(
                "What should this week focus on?",
                placeholder=(
                    "e.g. Fat loss, 3 gym days; bad lower back so no heavy deadlifts; prefer dumbbells "
                    "and machines."
                ),
                height=88,
                key="workout_week_req",
            )
            gen_wo = st.button("Generate 7-day plan", key="btn_workout_week")
            if st.session_state.pop("workout_week_just_generated", False):
                st.success("Training plan, meals, and images updated below.")
            if gen_wo and not (wo_ctx or "").strip():
                st.warning("Describe your goals or constraints above, then generate again.")
            elif gen_wo:
                _prof = db.get_profile(uid)
                prof_blurb = profile_to_blurb(_prof)
                _weights = db.list_weight_entries(uid, 30)
                _nut_block = build_week_plan_nutrition_block(_prof, _weights)
                plan_md = ""
                try:
                    with st.spinner("Generating training + meal plan for the week…"):
                        plan_md = workout_plan.generate_week_plan_markdown(
                            model,
                            prof_blurb,
                            wo_ctx.strip(),
                            nutrition_instructions=_nut_block,
                        )
                except Exception as exc:
                    st.error(f"Workout text failed: {exc}")
                    plan_md = ""
                if plan_md:
                    st.session_state["workout_week_plan"] = plan_md
                    (img_api, img_base), (img_key_fallback, img_fb_base) = (
                        gemini_env.resolve_image_api_credentials()
                    )
                    if not img_api:
                        st.error(
                            "No API key for images. Set **EURI_API_KEY** (or **GEMINI_API_KEY**) "
                            "in `.env`."
                        )
                        st.session_state["workout_week_images"] = {}
                        st.session_state["workout_week_image_errors"] = {}
                    else:
                        blocks = workout_plan.parse_day_blocks(plan_md)
                        if not blocks and plan_md.strip():
                            blocks = {1: plan_md.strip()}
                        fb = next(iter(blocks.values()), plan_md)
                        days_list = workout_plan.ensure_seven_days(blocks, fb)
                        ref_bytes: bytes | None = None
                        ref_mime = "image/jpeg"
                        if db.has_profile_image(uid):
                            try:
                                ref_bytes = db.profile_image_path(uid).read_bytes()
                            except OSError:
                                ref_bytes = None
                        if ref_bytes and not (img_key_fallback or "").strip():
                            st.info(
                                "You have a **profile photo**. Add **GEMINI_API_KEY** to `.env` (alongside EURI) "
                                "so week images can use Google’s image model to **match your face**; with EURI only, "
                                "images are prompt-based without your photo."
                            )
                        img_model = workout_plan.default_image_model()
                        _p_img = db.get_profile(uid)
                        gender_p = (_p_img.get("gender") or "").strip()
                        _wk_float: float | None = None
                        _raw_wk = _p_img.get("body_weight_kg")
                        if _raw_wk is not None:
                            try:
                                _wf = float(_raw_wk)
                                if _wf > 0:
                                    _wk_float = _wf
                            except (TypeError, ValueError):
                                pass
                        if _wk_float is None:
                            for _wr in _weights:
                                try:
                                    _wf = float(_wr["weight_kg"])
                                    if _wf > 0:
                                        _wk_float = _wf
                                        break
                                except (TypeError, ValueError, KeyError):
                                    continue
                        _hf_img = _p_img.get("height_feet")
                        _physique = workout_plan.physique_descriptor_from_profile(
                            _hf_img,
                            _wk_float,
                            gender_p,
                        )
                        imgs: dict[int, bytes] = {}
                        errs: dict[int, str] = {}
                        bar = st.progress(0.0, text="Generating your personalised plan…")
                        for i, (dn, body) in enumerate(days_list):
                            _img_body = workout_plan.workout_body_for_image(body)
                            b, err = workout_plan.generate_day_image(
                                img_api,
                                img_model,
                                dn,
                                _img_body,
                                ref_bytes,
                                ref_mime,
                                gender_p,
                                base_url=img_base,
                                fallback_api_key=img_key_fallback,
                                fallback_base_url=img_fb_base,
                                physique_descriptor=_physique,
                            )
                            if b:
                                imgs[dn] = b
                            else:
                                errs[dn] = err or "Unknown error"
                            bar.progress(
                                (i + 1) / 7.0,
                                text="Generating day images…",
                            )
                        bar.empty()
                        st.session_state["workout_week_images"] = imgs
                        st.session_state["workout_week_image_errors"] = errs
                    st.session_state["workout_week_just_generated"] = True
                    st.rerun()

            plan_saved = (st.session_state.get("workout_week_plan") or "").strip()
            if plan_saved:
                st.markdown("##### Your week (training & meals)")
                imgs = st.session_state.get("workout_week_images") or {}
                errs = st.session_state.get("workout_week_image_errors") or {}
                blocks = workout_plan.parse_day_blocks(plan_saved)
                if not blocks and plan_saved:
                    blocks = {1: plan_saved}
                fb = next(iter(blocks.values()), plan_saved)
                for d, body in workout_plan.ensure_seven_days(blocks, fb):
                    st.markdown(f"###### Day {d}")
                    st.markdown(body or "_(No exercises parsed for this day.)_")
                    if d in imgs:
                        st.image(imgs[d], caption=f"Day {d}")
                    elif errs.get(d):
                        st.caption(f"Image unavailable: {errs[d]}")

    st.subheader("Daily calorie needs")
    _daily_bw_default = 0.0
    if uid and active:
        try:
            _wk = db.get_profile(uid).get("body_weight_kg")
            if _wk is not None and float(_wk) > 0:
                _daily_bw_default = float(_wk)
        except (TypeError, ValueError):
            pass
    col_w, col_u = st.columns(2)
    with col_w:
        body_weight = st.number_input(
            "Body weight",
            min_value=0.0,
            value=_daily_bw_default,
            step=0.1,
            help="Pre-filled from profile (kg). Change unit in the next column if needed.",
            disabled=not active,
        )
    with col_u:
        weight_unit = st.selectbox("Weight unit", ["kg", "lbs"], disabled=not active)

    activity_labels = [label for label, _ in ACTIVITY_LEVELS]
    if uid and active:
        _p_act = (db.get_profile(uid).get("activity_level") or "").strip()
        activity_choice = _p_act if _p_act in activity_labels else activity_labels[2]
    else:
        activity_choice = activity_labels[2]
    activity_factor = dict(ACTIVITY_LEVELS)[activity_choice]

    if st.button(
        "Estimate daily calorie needs",
        disabled=not active,
        key="btn_estimate_daily_calories",
    ):
        if body_weight <= 0:
            st.warning("Enter a body weight greater than zero first.")
        else:
            st.session_state["show_daily_calorie_results"] = True

    age_years = 30
    height_cm = 170.0
    sex_choice = "Average (midpoint)"
    if uid and active:
        _p_bmr = db.get_profile(uid)
        try:
            _hft = _p_bmr.get("height_feet")
            if _hft is not None and float(_hft) > 0:
                height_cm = float(_hft) * FT_TO_CM
        except (TypeError, ValueError):
            pass
        _g_bmr = (_p_bmr.get("gender") or "").strip()
        if _g_bmr == "Male":
            sex_choice = "Male"
        elif _g_bmr == "Female":
            sex_choice = "Female"
        else:
            sex_choice = "Average (midpoint)"

    bmr_val: float | None = None
    tdee_val: float | None = None
    weight_kg_calc: float | None = None
    
    if (
        st.session_state.get("show_daily_calorie_results")
        and body_weight > 0
        and active
    ):
        weight_kg_calc = body_weight if weight_unit == "kg" else body_weight * LBS_TO_KG
        bmr_val = bmr_mifflin_st_jeor(weight_kg_calc, height_cm, int(age_years), sex_choice)
        tdee_val = bmr_val * activity_factor
        c1, c2 = st.columns(2)
        with c1:
            st.metric("Estimated BMR", f"{round(bmr_val)} kcal/day")
        with c2:
            st.metric("Estimated maintenance (TDEE)", f"{round(tdee_val)} kcal/day")
        unit_note = f"{body_weight} {weight_unit}"
        if weight_unit == "lbs":
            unit_note += f" ({weight_kg_calc:.1f} kg)"
        st.caption(
            f"Based on {unit_note}, Mifflin-St Jeor BMR (height from profile feet→cm, age {age_years}, "
            f"sex from profile where applicable), and activity **{activity_choice}** (factor {activity_factor}). "
            "For planning only; not medical advice."
        )
        if uid:
            if st.button("Save this weight & estimates to my log", key="btn_log_weight"):
                db.add_weight_entry(
                    uid,
                    weight_kg_calc,
                    weight_unit,
                    body_weight,
                    bmr_at_log=round(bmr_val),
                    tdee_at_log=round(tdee_val),
                )
                st.success("Weight entry saved.")

    if uid:
        show_coach = st.checkbox(
            "Show coach chat (reloads your saved profile, weights & meals for every reply)",
            key="toggle_coach_chat",
        )
        if show_coach:
            st.markdown("##### Progress photo for coach")
            st.caption(
                "Optional: upload a **current body / progress** picture so the coach can comment in context of "
                "your goal, goal timeline, and weight log. Photos are only a rough guide—lighting and angle matter; "
                "use your scale log for hard numbers. Not medical advice."
            )
            _cup = int(st.session_state.get("coach_progress_uploader_key", 0))
            prog_up = st.file_uploader(
                "Upload progress / body photo",
                type=["jpg", "jpeg", "png"],
                key=f"coach_progress_upload_{_cup}",
            )
            coach_photo_note = st.text_input(
                "Optional note for the coach (pose, lighting, how long since last photo, etc.)",
                key="coach_progress_photo_note",
            )
            attach_photo_to_next = st.checkbox(
                "Include this photo with my next message in the chat below",
                key="coach_attach_photo_next_msg",
            )
            _coach_review_default_q = (
                "Please review my progress photo together with my profile goal, goal timeline, and weight log. "
                "From what you can see (knowing photos are imperfect), does it seem I'm moving in a reasonable "
                "direction for my goal—or is that unclear? If you need more to judge, ask for current scale weight, "
                "a measurement, or training consistency."
            )
            if st.button(
                "Ask coach to review this photo",
                key="btn_coach_review_photo",
                use_container_width=True,
                type="secondary",
            ):
                if prog_up is None:
                    st.warning("Choose a photo first.")
                else:
                    b = prog_up.getvalue()
                    mime = _coach_image_mime(getattr(prog_up, "type", None))
                    note = (coach_photo_note or "").strip()
                    full_q = (
                        f"{note}\n\n{_coach_review_default_q}" if note else _coach_review_default_q
                    )
                    db.record_chat_goal_mention_if_relevant(uid, full_q)
                    coach_prompt = build_coach_prompt(
                        uid, full_q, body_photo_attached=True
                    )
                    answer = ""
                    try:
                        with st.spinner("Coach is reviewing your photo…"):
                            coach_resp = model.generate_content(
                                coach_prompt,
                                image_bytes=b,
                                image_mime=mime,
                            )
                        try:
                            answer = (coach_resp.text or "").strip()
                        except ValueError:
                            answer = ""
                    except Exception as exc:
                        answer = (
                            "Sorry, the coach request failed (network, quota, API, or this model may not support "
                            f"images). Details: {exc}"
                        )
                    if not answer:
                        answer = (
                            "No text response (content may have been blocked or the model returned no text)."
                        )
                    user_line = "📷 Progress photo — coach review."
                    if note:
                        user_line += f"\nNote: {note}"
                    db.add_chat_message(uid, "user", user_line)
                    db.add_chat_message(uid, "assistant", answer)
                    st.session_state["coach_progress_uploader_key"] = _cup + 1
                    st.rerun()

            msgs = db.list_chat_messages(uid, 40)
            for m in msgs:
                with st.chat_message("user" if m["role"] == "user" else "assistant"):
                    st.write(m["content"])

            if coach_q := st.chat_input("Ask the coach…"):
                img_bytes: bytes | None = None
                img_mime = "image/jpeg"
                if prog_up is not None and attach_photo_to_next:
                    img_bytes = prog_up.getvalue()
                    img_mime = _coach_image_mime(getattr(prog_up, "type", None))
                db.record_chat_goal_mention_if_relevant(uid, coach_q)
                coach_prompt = build_coach_prompt(
                    uid, coach_q, body_photo_attached=img_bytes is not None
                )
                answer = ""
                try:
                    with st.spinner("Coach is thinking…"):
                        coach_resp = model.generate_content(
                            coach_prompt,
                            image_bytes=img_bytes,
                            image_mime=img_mime,
                        )
                    try:
                        answer = (coach_resp.text or "").strip()
                    except ValueError:
                        answer = ""
                except Exception as exc:
                    answer = (
                        "Sorry, the coach request failed (network, quota, or API). "
                        f"Details: {exc}"
                    )
                if not answer:
                    answer = "No text response (content may have been blocked)."
                user_chat_line = (
                    f"📷 [Photo attached] {coach_q}" if img_bytes else coach_q
                )
                db.add_chat_message(uid, "user", user_chat_line)
                db.add_chat_message(uid, "assistant", answer)
                if img_bytes is not None and attach_photo_to_next:
                    st.session_state["coach_progress_uploader_key"] = _cup + 1
                st.rerun()
    
        st.divider()
    
    food_description = st.text_area(
        "Describe your meal",
        placeholder=(
            "e.g. Large bowl of vegetable stir-fry with tofu, about 1 cup rice; or brand names and "
            "sizes if you know them. Optional if you add a photo below."
        ),
        height=110,
        disabled=not active,
    )
    description_text = food_description.strip()

    if "meal_camera_open" not in st.session_state:
        st.session_state.meal_camera_open = False
    if not active:
        st.session_state.meal_camera_open = False

    if active:
        st.caption(
            "Optional: upload a food photo, or tap **Take food photo** to open the camera—combined "
            "with your description when both are provided."
        )
    else:
        st.caption("Sign in or register to upload meal photos and run calorie estimates.")
    _fu, _cam_btn = st.columns(2, gap="small")
    with _fu:
        meal_up = st.file_uploader(
            "meal_photo_file",
            type=["jpg", "jpeg", "png"],
            key="meal_estimate_photo_file",
            label_visibility="collapsed",
            disabled=not active,
        )
    with _cam_btn:
        if not st.session_state.meal_camera_open:
            if st.button("Take food photo", key="btn_meal_cam_open", disabled=not active):
                st.session_state.meal_camera_open = True
                st.rerun()
        else:
            if st.button("Close camera", key="btn_meal_cam_close", disabled=not active):
                st.session_state.meal_camera_open = False
                st.session_state.meal_estimate_cam_widget_key = (
                    int(st.session_state.get("meal_estimate_cam_widget_key", 0)) + 1
                )
                st.rerun()

    meal_cam = None
    if active and st.session_state.meal_camera_open:
        _meal_cam_k = st.session_state.setdefault("meal_estimate_cam_widget_key", 0)
        meal_cam = st.camera_input(
            "Food photo",
            key=f"meal_estimate_camera_{_meal_cam_k}",
            label_visibility="collapsed",
        )

    has_text = bool(description_text)
    profile_ctx = profile_to_blurb(db.get_profile(uid)) if uid else ""

    if st.button("Estimate Calories 🔍", disabled=not active):
        meal_img_bytes: bytes | None = None
        meal_img_mime = "image/jpeg"
        if meal_up is not None:
            meal_img_bytes = meal_up.getvalue()
            meal_img_mime = (meal_up.type or "").strip() or "image/jpeg"
        elif meal_cam is not None:
            meal_img_bytes = meal_cam.getvalue()
            meal_img_mime = (getattr(meal_cam, "type", None) or "").strip() or "image/jpeg"
        if meal_img_bytes:
            head = meal_img_bytes[:12]
            if head.startswith(b"\x89PNG\r\n\x1a\n"):
                meal_img_mime = "image/png"
            elif head.startswith(b"\xff\xd8"):
                meal_img_mime = "image/jpeg"

        if not has_text and not meal_img_bytes:
            st.warning("Add a short description and/or a food photo (upload or camera), then try again.")
            st.stop()

        with st.spinner("Analyzing your food..."):
            prompt = build_analysis_prompt(bool(meal_img_bytes), food_description, profile_ctx)

            try:
                response = (
                    model.generate_content(
                        prompt,
                        image_bytes=meal_img_bytes,
                        image_mime=meal_img_mime,
                    )
                    if meal_img_bytes
                    else model.generate_content(prompt)
                )
            except Exception as exc:
                st.error(
                    "The model request failed. Check your API key, network, and quota."
                )
                st.caption(str(exc))
                st.stop()
    
            try:
                result_text = response.text
            except ValueError:
                st.error(
                    "No text response returned. The content may have been blocked by "
                    "safety filters."
                )
                if getattr(response, "prompt_feedback", None) is not None:
                    st.caption(str(response.prompt_feedback))
                st.stop()
    
            st.session_state.last_meal_context = result_text or ""
            st.session_state.meal_camera_open = False
            if meal_cam is not None:
                st.session_state.meal_estimate_cam_widget_key = (
                    int(st.session_state.get("meal_estimate_cam_widget_key", 0)) + 1
                )

            st.subheader("📊 Result")
            if not (result_text or "").strip():
                st.warning("The model returned an empty response.")
            else:
                st.write(result_text)
    
    if uid and (st.session_state.get("last_meal_context") or "").strip():
        if st.button("Save latest meal analysis to my log", key="btn_save_meal"):
            _meal_snip = (
                description_text[:2000]
                if description_text.strip()
                else "(meal photo / image estimate)"
            )
            db.add_meal_entry(
                uid,
                _meal_snip,
                st.session_state.last_meal_context,
            )
            st.success("Meal saved to your log.")


if active:
    _guest_auth_body_class_remove()
    st.markdown(_signed_in_theme_css(), unsafe_allow_html=True)
    head_l, head_mid, head_r = st.columns([4.2, 2.2, 1.2])
    with head_l:
        st.title("🏋️ SID Fitness Assistant")
    with head_mid:
        with st.popover(
            "Register your activity",
            icon=":material/calendar_month:",
            use_container_width=True,
        ):
            _render_daily_activity_logger(int(st.session_state.user_id))
    with head_r:
        if st.button("Log out", use_container_width=False, key="btn_logout"):
            st.session_state.user_id = None
            st.session_state.username = None
            st.session_state.last_meal_context = ""
            st.session_state.meal_camera_open = False
            st.session_state.pop("show_daily_calorie_results", None)
            st.rerun()
    render_main_content()
else:
    _guest_auth_body_class_add()
    st.markdown(_guest_auth_theme_css(), unsafe_allow_html=True)

    hero_col, form_col = st.columns([1.22, 1], gap="large")
    with hero_col:
        st.markdown(_auth_hero_html(), unsafe_allow_html=True)
    with form_col:
        st.markdown(
            '<div class="sid-auth-form-heading"><h2>Welcome</h2></div>',
            unsafe_allow_html=True,
        )
        tab_in, tab_reg = st.tabs(["Sign in", "Register"])
        with tab_in:
            lu = st.text_input(
                "Email",
                key="login_user",
                autocomplete="username",
                placeholder="you@example.com",
            )
            lp = st.text_input(
                "Password",
                type="password",
                key="login_pass",
                autocomplete="current-password",
            )
            st.markdown(
                '<p style="text-align:right;font-size:0.8rem;margin:-0.5rem 0 0.5rem 0;">'
                '<span style="color:#475569;">Forgot password?</span> '
                '<span style="color:#1d4ed8;font-weight:600;">Use the section below</span></p>',
                unsafe_allow_html=True,
            )
            if st.button(
                "Sign in", use_container_width=True, key="btn_signin", type="primary"
            ):
                raw_e = (lu or "").strip()
                if not db.is_valid_login_email(raw_e):
                    st.error("Enter a valid sign-in email address.")
                else:
                    found = db.verify_user_identifier(raw_e, lp)
                    if found:
                        st.session_state.user_id = found
                        st.session_state.username = db.get_username(found)
                        st.rerun()
                    else:
                        st.error("Invalid email or password.")

            with st.expander("Email a reset link", expanded=False):
                st.caption(
                    "Enter the **email you use to sign in**, or the **email saved on your profile**. "
                    "Password reset works by email only—the link is sent to that address."
                )
                base_url = (os.getenv("PASSWORD_RESET_APP_URL") or "http://localhost:8501").rstrip(
                    "/"
                )
                if st.button("Send reset link", use_container_width=False, key="btn_forgot_send"):
                    fid = (lu or "").strip()
                    if not fid:
                        st.warning("Enter your email in the field above first.")
                    elif not mailer.smtp_configured():
                        st.error(
                            "SMTP is not configured. Add SMTP_SERVER, SMTP_PORT, SMTP_USERNAME, "
                            "SMTP_PASSWORD, and MAIL_DEFAULT_SENDER to `.env`."
                        )
                    else:
                        uid_f, email_f = db.resolve_user_for_password_reset(fid)
                        send_error: str | None = None
                        if uid_f and email_f:
                            try:
                                token_f = db.create_password_reset_token(uid_f)
                                link_f = f"{base_url}?reset_token={token_f}"
                                mailer.send_password_reset_email(
                                    email_f,
                                    link_f,
                                    username_hint=db.get_username(uid_f),
                                )
                            except Exception as exc:
                                send_error = str(exc)
                        if send_error:
                            st.error(f"Could not send email: {send_error}")
                        elif uid_f and email_f:
                            st.success(
                                "Message sent. Check that inbox and spam; the link expires in **1 hour**."
                            )
                        else:
                            st.info(
                                "If an account matches, a reset goes to your **sign-in** or **profile** email. "
                                "Nothing else is shown for privacy."
                            )
        with tab_reg:
            st.caption("Create an account with your **email** and a password.")
            reg_em = st.text_input(
                "Email",
                key="reg_unified_email",
                autocomplete="email",
                placeholder="you@example.com",
            )
            rp = st.text_input("Password", type="password", key="reg_unified_pass")
            rp2 = st.text_input(
                "Confirm password", type="password", key="reg_unified_pass2"
            )
            if st.button(
                "Create account", use_container_width=True, key="btn_reg_unified", type="primary"
            ):
                if rp != rp2:
                    st.error("Passwords do not match.")
                else:
                    em = (reg_em or "").strip()
                    if not em:
                        st.error("Enter your email address.")
                    elif not db.is_valid_login_email(em):
                        st.error("Please enter a valid email address.")
                    else:
                        ok, msg = db.create_user(em, rp)
                        if ok:
                            uid_new = db.get_user_id_by_login_email(em)
                            if uid_new:
                                db.upsert_profile(
                                    uid_new,
                                    {"email": db.normalize_login_email(em)},
                                )
                            st.success(msg)
                        else:
                            st.error(msg)
