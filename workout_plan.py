"""One-week gym plan (text) plus day images: Google Gemini native or EURI OpenAI ``images/generations``."""

from __future__ import annotations

import os
import re
from typing import Any

DAY_MARKER = re.compile(r"---\s*DAY\s*(\d+)\s*---", re.IGNORECASE)

# Coach-chat phrases that imply the user eats meat / is not vegetarian (typos included).
_NONVEG_CHAT_RE = re.compile(
    r"(?:"
    r"non[-\s]?veget\w*|nonveget\w*|\bomnivore\b|"
    r"i['\s]?m not (a )?veget\w*|not (a )?vegetarian|"
    r"not vegan|"
    r"\b(?:i|we)\s+eat\s+(?:chicken|meat|fish|pork|turkey|seafood|shellfish|eggs)\b|"
    r"\beat\s+(?:chicken|meat|fish|pork|turkey|seafood)\b|"
    r"includes? (?:chicken|meat|fish)|"
    r"\bnon[-\s]?veg\b|"
    r"with (?:chicken|meat|fish|pork|turkey|eggs)"
    r")",
    re.IGNORECASE,
)
# Strip diet section when generating workout imagery (prompt-only meals below this heading).
_MEALS_SECTION_START = re.compile(r"(?i)\n\s*(?:#{1,4}\s*)meals\s*(?:\n|$)")
_TRAINING_UNTIL_MEALS = re.compile(
    r"(?is)####\s*Training\s*\n(.*?)(?=^\s*####\s*Meals\b|\Z)",
    re.MULTILINE,
)

# Free-text fields scanned for diet nuance (eggs while vegetarian, etc.) in weekly plan nutrition block.
_DIET_NUANCE_KEYS = (
    "coach_notes",
    "meal_timing_notes",
    "cuisine_preferences",
    "foods_to_avoid",
    "allergy_alerts",
)


def workout_body_for_image(day_body: str) -> str:
    """Training-only text for image prompts; drops ``#### Meals`` and everything after."""
    body = (day_body or "").strip()
    m = _MEALS_SECTION_START.search(body)
    if m:
        return body[: m.start()].strip()
    return body


def training_section_text(day_body: str) -> str:
    """Body of ``#### Training`` through ``#### Meals`` (or end)."""
    w = (day_body or "").strip()
    m = _TRAINING_UNTIL_MEALS.search(w)
    if m:
        return m.group(1).strip()
    return workout_body_for_image(day_body)


def meal_plan_diet_scope_lines(profile: dict, user_chat_texts: list[str]) -> list[str]:
    """Rules for which proteins/meal types appear in the 7-day plan (profile + user coach-chat)."""
    dp = (profile.get("diet_pattern") or "").strip()
    if dp == "Omnivore":
        dp = "Non vegetarian"

    user_blob = "\n".join((t or "").strip() for t in user_chat_texts if (t or "").strip()).lower()
    chat_nonveg = bool(_NONVEG_CHAT_RE.search(user_blob)) if user_blob else False
    chat_vegan = (
        bool(re.search(r"\bvegan\b|whole-food plant|plant-based only|no animal products", user_blob))
        and "not vegan" not in user_blob
        if user_blob
        else False
    )

    nuance = diet_nuance_blob_from_profile(profile)
    out: list[str] = []

    if dp == "Vegan":
        out.append(
            "**MEAL PROTEIN SCOPE — VEGAN (profile):** Every breakfast, lunch, and dinner must be **fully vegan**: "
            "no meat, fish, poultry, dairy, eggs, or honey. Use legumes, tofu, tempeh, seitan, nuts, seeds, and plant milks only."
        )
    elif dp == "Vegetarian":
        out.append(
            "**MEAL PROTEIN SCOPE — VEGETARIAN (profile):** Meals must be **lacto-ovo vegetarian**: no meat, poultry, fish, or shellfish. "
            "**Eggs and dairy are allowed** unless profile/notes rule them out. Across the week, include **both typical vegetarian plates** and "
            "**vegan-friendly options or swaps** (e.g. tofu, legumes, plant milk) so vegan and vegetarian styles appear."
        )
    elif dp == "Non vegetarian":
        out.append(
            "**MEAL PROTEIN SCOPE — NON-VEGETARIAN (profile):** Use **animal proteins** through the week: **poultry, fish, eggs, dairy** as fits "
            "the goal and calories. **No beef** (global rule below). Respect allergies and foods to avoid."
        )
    elif dp == "Pescatarian":
        out.append(
            "**MEAL PROTEIN SCOPE — PESCATARIAN:** Fish and seafood are allowed; **no poultry or red meat**. Eggs and dairy per profile/notes."
        )
    elif dp == "Flexitarian":
        out.append(
            "**MEAL PROTEIN SCOPE — FLEXITARIAN:** **Plant-forward** meals by default; add **modest fish, poultry, or eggs** only when it matches "
            "the user’s notes or week request—not a meat-heavy plan every day unless they asked for it."
        )
    elif dp == "Other / mixed":
        out.append(
            "**MEAL PROTEIN SCOPE — OTHER / MIXED:** Follow the profile summary, **MEAL PROTEIN SCOPE** cues from coach chat, and the week request; "
            "when instructions conflict, use the **stricter** food rules or the **most recent explicit user statement**."
        )
    else:
        # Diet pattern not set — default vegetarian unless chat clearly says otherwise.
        if chat_nonveg:
            out.append(
                "**MEAL PROTEIN SCOPE — NON-VEGETARIAN (from coach chat):** The user indicated **omnivore / non-vegetarian** eating in coach chat "
                "(e.g. eats chicken, eggs, fish, or said they are not vegetarian). Plan meals with **poultry, fish, eggs, and dairy** as appropriate. "
                "**No beef.** Still obey allergies and foods to avoid."
            )
        elif chat_vegan:
            out.append(
                "**MEAL PROTEIN SCOPE — VEGAN (from coach chat):** The user identified **vegan** (or fully plant-based only) in coach chat. "
                "Use **only vegan** meals for the week."
            )
        else:
            out.append(
                "**MEAL PROTEIN SCOPE — VEGETARIAN (default):** Profile **diet pattern is not set** and chat does not establish omnivore. "
                "Use **lacto-ovo vegetarian** meals for the whole week: **no meat, poultry, fish, or shellfish**; **eggs and dairy allowed**. "
                "Include **vegan swaps or full vegan days** where natural. **Do not** add chicken, fish, or other meats unless the **week request** "
                "explicitly asks for them."
            )

    if chat_nonveg and dp == "Vegetarian":
        out.append(
            "**Note:** Coach chat hints at eating meat while the profile is **Vegetarian**—keep this week’s meals **vegetarian** unless the **week request** "
            "explicitly overrides; you may add one short line suggesting they update their profile if their diet changed."
        )
    if chat_vegan and dp in ("Non vegetarian", "Pescatarian", "Flexitarian"):
        out.append(
            "**Note:** Coach chat mentions **vegan**-style eating while the profile allows animal foods—**follow the profile’s protein scope** for this plan "
            "unless the week request clearly asks for a vegan week."
        )

    if nuance:
        out.append(
            "**User-stated dietary detail (honour in every meal line, including protein choices and swaps):** "
            + nuance
        )
    return out


def format_coach_chat_for_week_plan(
    messages: list[dict[str, Any]],
    *,
    max_messages: int = 36,
    max_total_chars: int = 4500,
) -> str:
    """Chronological excerpt of coach chat for the weekly-plan model (diet preferences, constraints)."""
    if not messages:
        return ""
    tail = messages[-max_messages:]
    parts: list[str] = []
    for r in tail:
        role = (r.get("role") or "").strip()
        if role not in ("user", "assistant"):
            continue
        c = (r.get("content") or "").strip().replace("\n", " ")
        if len(c) > 520:
            c = c[:520] + "…"
        parts.append(f"- **{role}:** {c}")
    blob = "\n".join(parts)
    if len(blob) > max_total_chars:
        blob = "…(older messages omitted)\n" + blob[-max_total_chars:]
    return blob


def diet_nuance_blob_from_profile(profile: dict) -> str:
    """Concatenate user free-text that may refine diet (e.g. vegetarian + eggs)."""
    parts: list[str] = []
    for key in _DIET_NUANCE_KEYS:
        v = (profile.get(key) or "").strip()
        if v:
            label = key.replace("_", " ")
            parts.append(f"{label}: {v}")
    return "; ".join(parts)


def physique_descriptor_from_profile(
    height_feet: float | None,
    weight_kg: float | None,
    gender: str = "",
) -> str:
    """Clause for image prompts: approximate build from height/weight (respectful, photorealistic)."""
    try:
        hf = float(height_feet) if height_feet is not None else 0.0
        wk = float(weight_kg) if weight_kg is not None else 0.0
    except (TypeError, ValueError):
        hf, wk = 0.0, 0.0
    if hf <= 0 or wk <= 0:
        return (
            "Natural, believable adult body for their apparent age; realistic proportions—not an exaggerated "
            "fitness-model physique unless the workout clearly implies elite athletics."
        )

    height_m = hf * 0.3048
    if height_m <= 0:
        return (
            "Natural, believable adult body; realistic proportions."
        )
    bmi = wk / (height_m * height_m)
    g = (gender or "").strip().lower()

    # Tall + moderate-to-high weight: user-requested "stocky / slight belly" (not BMI-only).
    tall_soft = hf >= 6.0 and wk >= 80.0
    nearly_tall_soft = hf >= 5.92 and wk >= 82.0  # ~5'11" and heavier

    if bmi < 18.5:
        base = "Slim or lean build; light frame; realistic muscle tone for someone who trains."
    elif bmi < 23.0:
        base = "Healthy weight range; average, realistic muscle definition—not overly shredded."
    elif tall_soft or nearly_tall_soft:
        base = (
            "Sturdy or slightly bulky build for their height; **mild softness at the midsection** "
            "(natural belly area—not athletic-cut abs). Looks like a regular person who trains, "
            "not underweight; photorealistic and respectful."
        )
    elif bmi < 25.0:
        base = (
            "Average to slightly sturdy build; natural waistline—avoid extreme leanness or bodybuilder definition."
        )
    elif bmi < 30.0:
        base = (
            "Clearly in the overweight range for height; fuller torso and **visible midsection fullness**; "
            "realistic skin and proportions; respectful depiction."
        )
    else:
        base = (
            "Higher body weight for height; fuller figure with **noticeable abdominal fullness**; "
            "realistic, dignified portrayal—not caricatured."
        )

    if g == "female":
        base += " Adult woman; same build cues apply with typical female fat distribution where relevant."
    elif g == "male":
        base += " Adult man; same build cues apply with typical male fat distribution where relevant."

    return base


def generate_week_plan_markdown(
    text_model: Any,
    profile_blurb: str,
    user_request: str,
    nutrition_instructions: str = "",
    coach_chat_block: str = "",
) -> str:
    nut = (
        f"\n\n=== NUTRITION / CALORIE RULES FOR THIS WEEK ===\n{nutrition_instructions.strip()}\n"
        if (nutrition_instructions or "").strip()
        else ""
    )
    chat_sec = ""
    if (coach_chat_block or "").strip():
        chat_sec = (
            "\n\n=== RECENT COACH CHAT (newest at bottom; use for diet preferences, dislikes, and constraints) ===\n"
            f"{coach_chat_block.strip()}\n"
        )
    prompt = f"""You are a strength and conditioning coach and practical meal-planning assistant
(informational only; not medical advice; user should verify allergens and medical diet with a professional).

User profile (respect injuries, health conditions, exercise frequency, diet pattern, allergies):
{profile_blurb}

User request for this week:
{user_request}
{nut}{chat_sec}

Produce EXACTLY a **7-day** block. Each day MUST use this exact outer delimiter and **inner structure**:

---DAY 1---
#### Training
- Exercise lines (e.g. "- Barbell deadlift: 3 sets x 6 reps" or "- Bodyweight squat: 20 reps")
- **At least 4** concrete exercises with sets/reps or time on each training day (so each can be illustrated); 4–8 total unless this is a rest/recovery day.
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
- **Meal protein scope is mandatory:** The block **NUTRITION / CALORIE RULES** includes a **MEAL PROTEIN SCOPE** line—follow it **exactly** for every breakfast, lunch, and dinner (vegan-only, vegetarian with optional vegan swaps, default vegetarian when unset, or non-vegetarian with poultry/fish/eggs/dairy when scope says so). **Coach chat** may refine wording and swaps; do not contradict the scope unless the **week request** explicitly overrides.
- **Indian-first meals and fats:** Apply **Cuisine — Indian-first** and **Cooking oils** from **NUTRITION / CALORIE RULES**: mostly Indian dishes and methods; **cold-pressed** oils (mustard, groundnut, sesame, coconut as fits); **no refined oil** as the default; **do not use olive oil** for typical **high-heat Indian cooking** (tadka, bhuna, deep-fry)—it is a poor match for that style.
- Respect **allergy alerts** and **foods to avoid**; use **cuisine / country** hints when helpful. Merge **coach notes**, **meal timing**, and **coach chat** details into actual meal choices.
- **Never include beef** in any meal suggestion (no beef, steak, ground beef, beef mince, beef jerky, beef broth/stock from beef, or beef-based
  sauces as the main protein). When meat is allowed, use poultry, fish, eggs, dairy (if diet allows), legumes, tofu/tempeh, lamb, pork, or other proteins instead.
- **No standalone tips block:** Do **not** add a separate section (e.g. "Tips," "General advice") to the 7-day output. Follow **sugar / processing / embedded habits** rules in **NUTRITION / CALORIE RULES** by working them **into** meal lines only.
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


def four_exercise_focus_lines(day_body: str) -> list[str]:
    """Exactly four short strings for image prompts (exercises or rest-day variations)."""
    w_img = workout_body_for_image(day_body)
    if is_likely_rest_or_home_day(w_img):
        base = (w_img.strip()[:900] or "Light recovery or rest at home.").strip()
        return [
            f"{base}\n\n(Variation {i + 1}/4: different calm pose or area of the home; same person.)"
            for i in range(4)
        ]
    t = training_section_text(day_body)
    bullets: list[str] = []
    for line in t.splitlines():
        s = line.strip()
        bm = re.match(r"^[-*•]\s+(.+)$", s)
        if bm:
            txt = bm.group(1).strip()
            if txt:
                bullets.append(txt[:400])
        elif s.startswith("**") and (
            "REST" in s.upper()
            or "RECOVERY" in s.upper()
        ):
            bullets.append(s[:400])
    if len(bullets) >= 4:
        return bullets[:4]
    if not bullets:
        fb = (t[:550] or w_img[:550]).strip() or "Gym strength training."
        return [
            f"{fb}\n\n(Panel {i + 1}/4: one clear exercise or station from this day.)"
            for i in range(4)
        ]
    while len(bullets) < 4:
        bullets.append(f"{bullets[-1]} (different angle or equipment setup.)")
    return bullets[:4]


def _gender_phrase(gender: str) -> str:
    g = (gender or "").strip().lower()
    if g == "male":
        return "male"
    if g == "female":
        return "female"
    return "adult (neutral presentation)"


def build_image_prompt(
    day_num: int,
    exercise_text: str,
    has_reference_face: bool,
    gender: str,
    physique_descriptor: str = "",
) -> str:
    ex = (exercise_text or "")[:1200]
    at_home = is_likely_rest_or_home_day(exercise_text)
    phys = (physique_descriptor or "").strip()
    body_line = (
        f"\n\nBody build (keep **consistent** across all seven day images for this same person): {phys}"
        if phys
        else ""
    )

    if at_home:
        scene = f"""Photorealistic photo at home — NOT a gym. Day {day_num}: rest, recovery, or light activity in a believable home setting
(living room, bedroom, balcony, or quiet residential space). No barbells, racks, or commercial gym equipment.
Show the person in comfortable casual or light activewear doing gentle movement that fits this plan:
{ex}
{body_line}

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
{body_line}

Natural lighting, sharp focus, authentic gym background, full-body or three-quarter view. No text overlays, no readable logos."""

    if has_reference_face:
        return (
            scene
            + " The first image is a reference portrait: keep this same person's face and general age/skin tone in the gym scene; **match the reference person's body size and shape** to the build description above. Invented gym scenario only; same individual."
        )
    gp = _gender_phrase(gender)
    return (
        scene
        + f" Single anonymous fictional person of Indian ethnicity, typical {gp} presentation; generic invented face, not resembling any real celebrity; photorealistic."
    )


def build_single_exercise_image_prompt(
    day_num: int,
    slot_1_to_4: int,
    exercise_focus: str,
    has_reference_face: bool,
    gender: str,
    physique_descriptor: str = "",
    *,
    at_home: bool = False,
) -> str:
    """One panel of a 4-up day: single movement or rest variation, same person/build as other panels."""
    ex = (exercise_focus or "").strip()[:700]
    phys = (physique_descriptor or "").strip()
    body_line = (
        f"\n\nBody build (match other panels this week for the same person): {phys}"
        if phys
        else ""
    )
    panel = f"Panel {slot_1_to_4}/4 for Day {day_num}."

    if at_home:
        scene = f"""Photorealistic photo at home — NOT a gym. {panel}
Focus on this moment only:
{ex}
{body_line}

Comfortable casual or light activewear, believable residential space, warm natural light.
Full-body or three-quarter view. No text overlays, no readable logos."""
        face_suffix = (
            " The first reference image is a portrait: keep this same person's face and age; same individual."
            if has_reference_face
            else (
                f" Single anonymous fictional person of Indian ethnicity, typical {_gender_phrase(gender)} presentation; "
                "generic invented face; photorealistic."
            )
        )
        return scene + " " + face_suffix

    scene = f"""Photorealistic photo in a modern, well-lit gym. {panel}
Show one clear exercise or setup that matches:
{ex}
{body_line}

Authentic equipment and background, natural lighting, full-body or three-quarter view. No text overlays, no readable logos."""
    if has_reference_face:
        return (
            scene
            + " Reference portrait provided: match face, age, and skin tone; **match body size to the build line**; same individual."
        )
    gp = _gender_phrase(gender)
    return (
        scene
        + f" Single anonymous fictional person of Indian ethnicity, typical {gp} presentation; generic invented face; photorealistic."
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
    prompt: str,
    *,
    size: str = "1024x1024",
) -> tuple[bytes | None, str | None]:
    """EURI images API (OpenAI-style); prompt-only, no reference photo."""
    import base64
    import urllib.error
    import urllib.request

    from openai import OpenAI

    client = OpenAI(api_key=api_key, base_url=base_url.rstrip("/"))
    try:
        resp = client.images.generate(
            model=model_id,
            prompt=prompt,
            n=1,
            size=size,
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
    prompt: str,
    reference_image_bytes: bytes | None,
    reference_mime: str,
) -> tuple[bytes | None, str | None]:
    """Google Gemini native image output (multimodal; optional reference face)."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    has_ref = bool(reference_image_bytes)
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


def _generate_routed_image(
    prompt: str,
    api_key: str,
    model_id: str,
    reference_image_bytes: bytes | None,
    reference_mime: str,
    base_url: str | None,
    fallback_api_key: str | None,
    fallback_base_url: str | None,
    *,
    euri_size: str = "1024x1024",
) -> tuple[bytes | None, str | None]:
    """Shared EURI vs Gemini routing (reference face prefers Gemini when both keys exist)."""
    prim = (api_key or "").strip()
    fb = (fallback_api_key or "").strip()
    has_ref = bool(reference_image_bytes)
    bu = (base_url or "").strip() or None

    if bu:
        if has_ref and fb:
            img, err = _generate_day_image_once(
                fb, model_id, prompt, reference_image_bytes, reference_mime
            )
            if img:
                return img, None
            img2, err2 = _generate_day_image_euri_openai(
                prim, bu, model_id, prompt, size=euri_size
            )
            if img2:
                return img2, None
            return None, (err2 or err or "Image generation failed.")

        img, err = _generate_day_image_euri_openai(
            prim, bu, model_id, prompt, size=euri_size
        )
        if img:
            return img, None
        return None, err

    img, err = _generate_day_image_once(
        prim, model_id, prompt, reference_image_bytes, reference_mime
    )
    if img:
        return img, None
    if fb and fb != prim and err and _looks_like_invalid_google_api_key(err):
        img2, err2 = _generate_day_image_once(
            fb, model_id, prompt, reference_image_bytes, reference_mime
        )
        if img2:
            return img2, None
        return None, err2 or err
    return None, err


def build_coach_illustration_prompt(
    user_subject: str, *, has_reference_face: bool = False
) -> str:
    """Educational exercise or food illustration; optional user portrait for same-person renders."""
    subj = (user_subject or "").strip()[:900]
    lines = [
        "Create one clear educational illustration for a fitness and nutrition coaching app.",
        f"User request (focus on this subject only): {subj}",
        "",
    ]
    if has_reference_face:
        lines.append(
            "A **reference portrait** of the user is attached: keep the **same recognizable face**, age, "
            "skin tone, and plausible body build. **Exercise requests:** that same person demonstrating "
            "correct form in a gym or studio. **Food / meal requests:** that same person at a table or "
            "counter with an appetizing **plated, bowl, or thali-style** presentation of the described dish, "
            "or a clear **hero shot** of the food alone if that fits the wording better. "
            "Respect vegetarian/vegan cues from the user text. Photorealistic."
        )
    else:
        lines.append(
            "If exercise/movement: correct form in a clean gym or neutral studio; anonymous person, "
            "side or back view preferred; no identifiable faces."
        )
        lines.append(
            "If food or drink: appetizing **photo-style** image—plated meal, bowl, glass, or spread; "
            "respect vegetarian/vegan cues in the wording if any."
        )
    lines.append("No text overlays, watermarks, or readable brand logos.")
    return "\n".join(lines)


def generate_coach_educational_image(
    user_question: str,
    *,
    reference_image_bytes: bytes | None = None,
    reference_mime: str = "image/jpeg",
) -> tuple[bytes | None, str | None]:
    """Optional illustration when the coach chat detects a visual request (exercise or food)."""
    import gemini_env

    try:
        (pk, pbase), (fk, fbbase) = gemini_env.resolve_image_api_credentials()
    except ValueError:
        return None, None
    prim = (pk or "").strip()
    if not prim:
        return None, None
    model_id = default_image_model()
    prompt = build_coach_illustration_prompt(
        user_question,
        has_reference_face=bool(reference_image_bytes),
    )
    euri_sz = os.getenv("COACH_ILLUSTRATION_EURI_SIZE", "1024x1024").strip() or "1024x1024"
    return _generate_routed_image(
        prompt,
        prim,
        model_id,
        reference_image_bytes,
        reference_mime or "image/jpeg",
        pbase,
        fk,
        fbbase,
        euri_size=euri_sz,
    )


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
    physique_descriptor: str = "",
) -> tuple[bytes | None, str | None]:
    """One composite day image (legacy / optional). Uses full-day prompt and 1024 EURI size."""
    has_ref = bool(reference_image_bytes)
    prompt = build_image_prompt(
        day_num,
        exercise_text,
        has_ref,
        gender,
        physique_descriptor=physique_descriptor,
    )
    return _generate_routed_image(
        prompt,
        api_key,
        model_id,
        reference_image_bytes,
        reference_mime,
        base_url,
        fallback_api_key,
        fallback_base_url,
        euri_size="1024x1024",
    )


def generate_workout_slot_image(
    api_key: str,
    model_id: str,
    day_num: int,
    slot_1_to_4: int,
    exercise_focus: str,
    reference_image_bytes: bytes | None,
    reference_mime: str,
    gender: str,
    base_url: str | None = None,
    fallback_api_key: str | None = None,
    fallback_base_url: str | None = None,
    physique_descriptor: str = "",
    *,
    at_home: bool,
    euri_size: str = "512x512",
) -> tuple[bytes | None, str | None]:
    """One of four exercise panels for a day; smaller default EURI size for a 2×2 layout."""
    has_ref = bool(reference_image_bytes)
    prompt = build_single_exercise_image_prompt(
        day_num,
        slot_1_to_4,
        exercise_focus,
        has_ref,
        gender,
        physique_descriptor=physique_descriptor,
        at_home=at_home,
    )
    return _generate_routed_image(
        prompt,
        api_key,
        model_id,
        reference_image_bytes,
        reference_mime,
        base_url,
        fallback_api_key,
        fallback_base_url,
        euri_size=euri_size,
    )


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
