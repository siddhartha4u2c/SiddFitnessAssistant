"""Text generation: Google ``GenerativeModel`` or EURI (OpenAI-compatible) client."""

from __future__ import annotations

import base64
import os
from io import BytesIO
from typing import Any


class _TextResponse:
    """Minimal shape compatible with ``google.generativeai`` responses (``.text``)."""

    __slots__ = ("_text", "prompt_feedback")

    def __init__(self, text: str) -> None:
        self._text = text
        self.prompt_feedback: Any = None

    @property
    def text(self) -> str:
        return self._text


def _pil_from_bytes(image_bytes: bytes) -> Any:
    from PIL import Image

    im = Image.open(BytesIO(image_bytes))
    if im.mode in ("RGBA", "P"):
        im = im.convert("RGB")
    return im


class UnifiedTextModel:
    """Entry point: ``generate_content`` for text; optional ``image_bytes`` for vision (meals, etc.)."""

    def __init__(
        self,
        *,
        google_model: Any | None,
        openai_client: Any | None,
        model_name: str,
    ) -> None:
        self._google = google_model
        self._openai = openai_client
        self._model_name = model_name

    def generate_content(
        self,
        prompt: str,
        *,
        image_bytes: bytes | None = None,
        image_mime: str = "image/jpeg",
    ) -> Any:
        if self._openai is not None:
            if image_bytes:
                b64 = base64.standard_b64encode(image_bytes).decode("ascii")
                uri = f"data:{image_mime};base64,{b64}"
                content: Any = [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": uri}},
                ]
            else:
                content = prompt
            r = self._openai.chat.completions.create(
                model=self._model_name,
                messages=[{"role": "user", "content": content}],
            )
            chunk = (r.choices[0].message.content or "") if r.choices else ""
            return _TextResponse(chunk)
        assert self._google is not None
        if image_bytes:
            return self._google.generate_content([prompt, _pil_from_bytes(image_bytes)])
        return self._google.generate_content(prompt)


def build_text_model() -> UnifiedTextModel:
    """EURI (**EURI_API_KEY** + **BASE_URL**) uses OpenAI-compatible chat; else Google SDK."""
    import gemini_env

    key, base = gemini_env.resolve_gemini_credentials()
    model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    if base:
        from openai import OpenAI

        client = OpenAI(api_key=key, base_url=base.rstrip("/"))
        return UnifiedTextModel(
            google_model=None, openai_client=client, model_name=model_name
        )
    import google.generativeai as genai

    genai.configure(api_key=key)
    gm = genai.GenerativeModel(model_name)
    return UnifiedTextModel(google_model=gm, openai_client=None, model_name=model_name)
