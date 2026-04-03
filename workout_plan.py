"""One-week gym plan (text) plus day images: Google Gemini native or EURI OpenAI ``images/generations``."""

from __future__ import annotations

import os
import re
from typing import Any

DAY_MARKER = re.compile(r"---\s*DAY\s*(\d+)\s*---", re.IGNORECASE)
# Strip diet section when generating workout imagery (prompt-only meals below this heading).
_MEALS_SECTION_START = re.compile(r"(?i)\n\s*(?:#{1,4}\s*)meals\s*(?:\n|$)")


def workout_body_for_image(day_body: str) -> str:
    """Training-only text for image prompts; drops ``#### Meals`` and everything after."""
    body = (day_body or "").strip()
    m = _MEALS_SECTION_START.search(body)
    if m:
        return body[: m.start()].strip()
    return body


def generate_week_plan_markdown(
    text_model: Any,
    profile_blurb: str,
    user_request: str,
    nutrition_instructions: str = "",
) -> str:
    nut = (
        f"\n\n=== NUTRITION / CALORIE RULES FOR THIS WEEK ===\n{nutrition_instructions.strip()}\n"
        if (nutrition_instructions or "").strip()
        else ""
    )
    prompt = f"""You are a strength and conditioning coach and practical meal-planning assistant
(informational only; not medical advice; user should verify allergens and medical diet with a professional).

User profile (respect injuries, health conditions, exercise frequency, diet pattern, allergies):
{profile_blurb}

User request for this week:
{user_request}
{nut}

Produce EXACTLY a **7-day** block. Each day MUST use this exact outer delimiter and **inner structure**:

---DAY 1---
#### Training
- Exercise lines (e.g. "- Barbell deadlift: 3 sets x 6 reps" or "- Bodyweight squat: 20 reps")
- 4–8 concrete exercises with sets/reps or time unless this is a rest/recovery day.
- Optional: one short line on rest or RPE.

#### Meals
- **Breakfast:** Specific foods with rough portion cues and **~XXX kcal** (one clear option or two swaps).
- **Lunch:** Same style with **~XXX kcal**.
- **Dinner:** Same style with **~XXX kcal**.
- **Day total (food, approximate):** ~XXXX kcal — **one short line** (different wording every day; sound like a person, not a template).
  Relate informally to TDEE / goal (e.g. fat loss: under maintenance) without repeating the same sentence structure across days.

---DAY 2---
(same #### Training / #### Meals structure)

Continue through ---DAY 7---.

Rules (training):
- Tailor volume to the user's exercise frequency and goals in the profile and their week request.
- At most **one** rest or active recovery day in the **entire** week (never two or more).
- **Day 1 and Day 2 must be regular training days** with concrete exercises — never rest or recovery on Day 1 or Day 2.
- If you include a rest/recovery day, use only one and place it on **Day 3 or later**.
- For that single rest/recovery day, put **REST** or **RECOVERY** on the **first line under #### Training**
  (e.g. "**REST** — complete rest" or "**RECOVERY** — light walk and stretching at home").

Rules (meals):
- Every day must include **Breakfast, Lunch, Dinner** under #### Meals with approximate calories each and a **Day total** line.
- Follow **NUTRITION / CALORIE RULES** above when choosing portion sizes and day totals; on **fat loss**, each day's food total must stay
  **below** the stated maintenance/TDEE reference (sustainable deficit unless the user asked otherwise).
- **Vary day-to-day calories naturally:** do **not** use the same **Day total** number every day. Let totals drift (e.g. ±80–220 kcal vs your
  weekly average) based on training load, rest day, appetite-friendly swaps, and realism—while still meeting the goal (e.g. fat loss: every day
  still below TDEE, but not identical totals or copy-pasted explanations).
- **Vary the Day total sentence** each day: different verbs, length, and tone (sometimes one clause, sometimes two; never paste the same
  explanation seven times).
- Align meals with **training vs rest** (e.g. slightly more carbs around harder training days when appropriate; still respect calorie rules).
- Respect profile **diet pattern** (vegetarian, vegan, etc.), **allergy alerts**, and **foods to avoid**; use **cuisine / country** hints when helpful.
- **Never include beef** in any meal suggestion (no beef, steak, ground beef, beef mince, beef jerky, beef broth/stock from beef, or beef-based
  sauces as the main protein). Use poultry, fish, eggs, dairy (if diet allows), legumes, tofu/tempeh, lamb, pork, or other proteins instead when
  meat is appropriate.
- Keep language practical (grocery-realistic); no medical claims.

Formatting:
- Use exactly the headings **#### Training** and **#### Meals** (four hashes) so the layout parses reliably.
- No text before ---DAY 1--- or after the ---DAY 7--- day's content."""
    resp = text_model.generate_content(prompt)
    return (getattr(resp, "text", None) or "").strip()


def parse_day_blocks(text: str) -> dict[int, str]:
    parts = DAY_MARKER.split(text)
    out: dict[int, str] = {}
    if len(parts) < 2:
        return out
    i = 1
    while i < len(parts):
        try:
            d = int(parts[i])
        except (ValueError, IndexError):
            i += 2
            continue
        body = parts[i + 1] if i + 1 < len(parts) else ""
        out[d] = body.strip()
        i += 2
    return out


def ensure_seven_days(blocks: dict[int, str], fallback_body: str) -> list[tuple[int, str]]:
    fb = (fallback_body or "").strip() or (
        "Compound lifts and accessories suited to profile; ~45–60 minutes moderate intensity."
    )
    return [(d, blocks.get(d, fb)) for d in range(1, 8)]


def is_likely_rest_or_home_day(body: str) -> bool:
    """True when the day's text describes rest / recovery / home — avoid gym imagery."""
    b = (body or "").lower()
    if re.search(r"\*\*rest\*\*|\*\*recovery\*\*", b):
        return True
    if "rest day" in b or "full rest" in b or "complete rest" in b:
        return True
    if "day off" in b or "off day" in b or "no gym" in b:
        return True
    if "active recovery" in b and "gym" not in b[:400]:
        return True
    gym_signals = (
        "barbell",
        "squat rack",
        "leg press",
        "bench press",
        "cable machine",
        "lat pulldown",
        "deadlift",
        "smith machine",
        "gym floor",
        "treadmill at gym",
    )
    if any(g in b for g in gym_signals):
        return False
    home_recovery = (
        "light walk",
        "walking only",
        "stretching",
        "mobility",
        "foam roll",
        "yoga",
        "at home",
        "living room",
        "recovery walk",
    )
    return any(h in b for h in home_recovery)


def _gender_phrase(gender: str) -> str:
    g = (gender or "").strip().lower()
    if g == "male":
        return "male"
    if g == "female":
        return "female"
    return "adult (neutral presentation)"


def build_image_prompt(
    day_num: int, exercise_text: str, has_reference_face: bool, gender: str
) -> str:
    ex = (exercise_text or "")[:1200]
    at_home = is_likely_rest_or_home_day(exercise_text)

    if at_home:
        scene = f"""Photorealistic photo at home — NOT a gym. Day {day_num}: rest, recovery, or light activity in a believable home setting
(living room, bedroom, balcony, or quiet residential space). No barbells, racks, or commercial gym equipment.
Show the person in comfortable casual or light activewear doing gentle movement that fits this plan:
{ex}

Warm natural indoor light, calm atmosphere, full-body or three-quarter view. No text overlays, no readable logos."""
        face_suffix = (
            " The first image is a reference portrait: keep this same person's face and general age/skin tone; same individual at home."
            if has_reference_face
            else (
                f" Single anonymous fictional person of Indian ethnicity, typical {_gender_phrase(gender)} presentation; "
                "generic invented face, not resembling any real celebrity; photorealistic."
            )
        )
        return scene + " " + face_suffix

    scene = f"""Photorealistic photo in a modern, well-lit gym. Visualize Day {day_num} training.
Show a person in workout clothes with equipment that fits this plan (barbell, rack, bench, cables, etc. as appropriate):
{ex}

Natural lighting, sharp focus, authentic gym background, full-body or three-quarter view. No text overlays, no readable logos."""

    if has_reference_face:
        return (
            scene
            + " The first image is a reference portrait: keep this same person's face and general age/skin tone in the gym scene. Invented gym scenario only; same individual."
        )
    gp = _gender_phrase(gender)
    return (
        scene
        + f" Single anonymous fictional person of Indian ethnicity, typical {gp} presentation; generic invented face, not resembling any real celebrity; photorealistic."
    )


def extract_image_bytes_from_genai_response(response: Any) -> bytes | None:
    cands = getattr(response, "candidates", None) or []
    for c in cands:
        content = getattr(c, "content", None)
        if not content:
            continue
        parts = getattr(content, "parts", None) or []
        for part in parts:
            inline = getattr(part, "inline_data", None)
            if inline is not None:
                data = getattr(inline, "data", None)
                if data:
                    return data
    return None


def _looks_like_invalid_google_api_key(error_text: str) -> bool:
    t = (error_text or "").lower()
    return (
        "api key not valid" in t
        or "api_key_invalid" in t
        or ("invalid_argument" in t and "api key" in t)
        or "please pass a valid api key" in t
    )


def _generate_day_image_euri_openai(
    api_key: str,
    base_url: str,
    model_id: str,
    day_num: int,
    exercise_text: str,
    gender: str,
) -> tuple[bytes | None, str | None]:
    """EURI images API (OpenAI-style); prompt-only, no reference photo."""
    import base64
    import urllib.error
    import urllib.request

    from openai import OpenAI

    prompt = build_image_prompt(day_num, exercise_text, False, gender)
    client = OpenAI(api_key=api_key, base_url=base_url.rstrip("/"))
    try:
        resp = client.images.generate(
            model=model_id,
            prompt=prompt,
            n=1,
            size="1024x1024",
            response_format="b64_json",
        )
    except Exception as exc:
        return None, str(exc)
    if not getattr(resp, "data", None):
        return None, "No image in response."
    item = resp.data[0]
    b64 = getattr(item, "b64_json", None)
    if b64:
        try:
            return base64.b64decode(b64), None
        except Exception as exc:
            return None, f"Invalid base64 image: {exc}"
    url = getattr(item, "url", None)
    if url:
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "SIDFitnessAssistant/1.0"},
            )
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read(), None
        except (urllib.error.URLError, OSError) as exc:
            return None, f"Download image URL failed: {exc}"
    return None, "Empty image payload (no b64_json or url)."


def _generate_day_image_once(
    api_key: str,
    model_id: str,
    day_num: int,
    exercise_text: str,
    reference_image_bytes: bytes | None,
    reference_mime: str,
    gender: str,
) -> tuple[bytes | None, str | None]:
    """Google Gemini native image output (multimodal; optional reference face)."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    has_ref = bool(reference_image_bytes)
    prompt = build_image_prompt(day_num, exercise_text, has_ref, gender)
    parts: list[Any] = []
    if has_ref:
        parts.append(
            types.Part.from_bytes(
                data=reference_image_bytes,
                mime_type=reference_mime or "image/jpeg",
            )
        )
    parts.append(types.Part.from_text(text=prompt))
    config = types.GenerateContentConfig(
        response_modalities=[types.Modality.TEXT, types.Modality.IMAGE],
    )
    try:
        response = client.models.generate_content(
            model=model_id,
            contents=parts,
            config=config,
        )
    except Exception as exc:
        return None, str(exc)
    img = extract_image_bytes_from_genai_response(response)
    if not img:
        return None, "No image in response (safety filter or text-only output)."
    return img, None


def generate_day_image(
    api_key: str,
    model_id: str,
    day_num: int,
    exercise_text: str,
    reference_image_bytes: bytes | None,
    reference_mime: str,
    gender: str,
    base_url: str | None = None,
    fallback_api_key: str | None = None,
    fallback_base_url: str | None = None,
) -> tuple[bytes | None, str | None]:
    """Images: EURI uses OpenAI-style ``images/generations`` (no reference face).

    If a **profile reference photo** is present and **GEMINI_API_KEY** is available as
    ``fallback_api_key`` while the primary route is EURI, we call **Google multimodal**
    first so the generated face can match the reference; then fall back to EURI on failure.
    """
    prim = (api_key or "").strip()
    fb = (fallback_api_key or "").strip()
    has_ref = bool(reference_image_bytes)

    if base_url:
        if has_ref and fb:
            img, err = _generate_day_image_once(
                fb,
                model_id,
                day_num,
                exercise_text,
                reference_image_bytes,
                reference_mime,
                gender,
            )
            if img:
                return img, None
            img2, err2 = _generate_day_image_euri_openai(
                prim,
                base_url,
                model_id,
                day_num,
                exercise_text,
                gender,
            )
            if img2:
                return img2, None
            return None, (err2 or err or "Image generation failed.")

        img, err = _generate_day_image_euri_openai(
            prim,
            base_url,
            model_id,
            day_num,
            exercise_text,
            gender,
        )
        if img:
            return img, None
        return None, err

    img, err = _generate_day_image_once(
        prim,
        model_id,
        day_num,
        exercise_text,
        reference_image_bytes,
        reference_mime,
        gender,
    )
    if img:
        return img, None
    if fb and fb != prim and err and _looks_like_invalid_google_api_key(err):
        img2, err2 = _generate_day_image_once(
            fb,
            model_id,
            day_num,
            exercise_text,
            reference_image_bytes,
            reference_mime,
            gender,
        )
        if img2:
            return img2, None
        return None, err2 or err
    return None, err


def default_image_model() -> str:
    """Nano Banana Pro is gemini-3-pro-image-preview on the Gemini API."""
    return os.getenv("GEMINI_IMAGE_MODEL", "gemini-3-pro-image-preview")


def resolve_image_api_key() -> str | None:
    """Primary API key for Gemini image calls (same rules as :mod:`gemini_env`)."""
    try:
        import gemini_env

        (k, _), _ = gemini_env.resolve_image_api_credentials()
        return k
    except ValueError:
        return None


def resolve_image_api_key_pair() -> tuple[str | None, str | None]:
    """(primary_key, fallback_key) for Gemini image calls."""
    try:
        import gemini_env

        (pk, _), (fk, _) = gemini_env.resolve_image_api_credentials()
        return pk, fk
    except ValueError:
        return None, None
