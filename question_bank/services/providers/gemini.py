"""Google Gemini provider for question-bank generation."""

from __future__ import annotations

import json
import logging
from typing import Any

import requests
from django.conf import settings

from question_bank.services.prompts import (
    SYSTEM_INSTRUCTION,
    build_generation_prompt,
    build_repair_prompt,
    build_retry_correction_prompt,
)
from question_bank.services.providers.base import AIQuestionProvider
from question_bank.services.schemas import GENERATION_RESPONSE_SCHEMA, REPAIR_RESPONSE_SCHEMA

logger = logging.getLogger(__name__)

# Prefer lighter models first for large JSON banks; fall back when overloaded.
DEFAULT_MODEL = "gemini-3.5-flash-lite"
DEFAULT_FALLBACKS = (
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.6-flash",
    "gemini-flash-lite-latest",
)


class GeminiProviderError(Exception):
    """Safe, admin-facing Gemini failure."""

    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


class GeminiQuestionProvider(AIQuestionProvider):
    """
    Calls Gemini via the Generative Language REST API using the `requests`
    package already installed in this project.

    Web/search grounding is NOT enabled.
    """

    API_BASE = "https://generativelanguage.googleapis.com/v1beta"

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout: int | None = None,
        max_attempts: int | None = None,
        fallback_models: list[str] | None = None,
    ):
        self.api_key = api_key or getattr(settings, "GEMINI_API_KEY", "") or ""
        self.model = model or getattr(settings, "GEMINI_MODEL", DEFAULT_MODEL) or DEFAULT_MODEL
        self.timeout = timeout or int(getattr(settings, "AI_GENERATION_TIMEOUT", 180))
        self.max_attempts = max_attempts or int(getattr(settings, "AI_GENERATION_MAX_ATTEMPTS", 2))
        if fallback_models is not None:
            self.fallback_models = fallback_models
        else:
            raw = getattr(settings, "GEMINI_MODEL_FALLBACKS", "") or ""
            if isinstance(raw, str) and raw.strip():
                self.fallback_models = [m.strip() for m in raw.split(",") if m.strip()]
            else:
                self.fallback_models = list(DEFAULT_FALLBACKS)

    def _model_candidates(self) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for name in [self.model, *self.fallback_models]:
            if name and name not in seen:
                seen.add(name)
                ordered.append(name)
        return ordered

    def generate_question_bank(
        self,
        *,
        source_content: str,
        domain: str,
        language: str,
        difficulty: str,
        total_sets: int,
        normal_sets: int,
        simulation_sets: int,
        questions_per_set: int,
        set_plans: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if not self.api_key:
            raise GeminiProviderError(
                "Question generation failed: GEMINI_API_KEY is not configured."
            )

        def _prompt(extra: str = "") -> str:
            base = build_generation_prompt(
                source_content=source_content,
                domain=domain,
                language=language,
                difficulty=difficulty,
                total_sets=total_sets,
                normal_sets=normal_sets,
                simulation_sets=simulation_sets,
                questions_per_set=questions_per_set,
                set_plans=set_plans,
            )
            return f"{base}\n\n{extra}" if extra else base

        return self._generate_with_retries(
            prompt_builder=_prompt,
            response_schema=GENERATION_RESPONSE_SCHEMA,
        )

    def generate_replacements(
        self,
        *,
        source_content: str,
        domain: str,
        language: str,
        missing_slots: list[dict[str, Any]],
        existing_questions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if not self.api_key:
            raise GeminiProviderError(
                "Question generation failed: GEMINI_API_KEY is not configured."
            )
        if not missing_slots:
            return {"insufficient_source_content": False, "message": "", "replacements": []}

        def _prompt(extra: str = "") -> str:
            base = build_repair_prompt(
                source_content=source_content,
                domain=domain,
                language=language,
                missing_slots=missing_slots,
                existing_questions=existing_questions,
            )
            return f"{base}\n\n{extra}" if extra else base

        return self._generate_with_retries(
            prompt_builder=_prompt,
            response_schema=REPAIR_RESPONSE_SCHEMA,
        )

    def _generate_with_retries(
        self,
        *,
        prompt_builder,
        response_schema: dict[str, Any],
    ) -> dict[str, Any]:
        prompt = prompt_builder()
        last_error = "Unknown Gemini error"
        capacity_errors = 0
        models = self._model_candidates()

        for model in models:
            for attempt in range(1, self.max_attempts + 1):
                try:
                    raw_text = self._call_gemini(
                        prompt, model=model, response_schema=response_schema,
                    )
                    payload = self._parse_json(raw_text)
                    if not isinstance(payload, dict):
                        raise GeminiProviderError("Gemini returned non-object JSON.")
                    if model != self.model:
                        logger.info("Gemini succeeded with fallback model=%s", model)
                    self.model = model
                    return payload
                except GeminiProviderError as exc:
                    last_error = str(exc)
                    logger.warning(
                        "Gemini generation model=%s attempt %s/%s failed: %s",
                        model,
                        attempt,
                        self.max_attempts,
                        last_error,
                    )
                    if exc.retryable:
                        capacity_errors += 1
                        break
                    if attempt >= self.max_attempts:
                        break
                    prompt = prompt_builder(build_retry_correction_prompt(last_error))

        if capacity_errors:
            raise GeminiProviderError(
                "Question generation failed: Gemini is temporarily overloaded "
                f"across tried models ({', '.join(models)}). "
                "Please wait a minute and retry. "
                f"Last error: {last_error}"
            )
        raise GeminiProviderError(
            f"Question generation failed: Gemini returned invalid structured output. ({last_error})"
        )

    def _call_gemini(
        self,
        user_prompt: str,
        *,
        model: str,
        response_schema: dict[str, Any] | None = None,
    ) -> str:
        url = f"{self.API_BASE}/models/{model}:generateContent"
        headers = {"Content-Type": "application/json"}
        params = {"key": self.api_key}
        schema = response_schema or GENERATION_RESPONSE_SCHEMA
        body = {
            "systemInstruction": {
                "parts": [{"text": SYSTEM_INSTRUCTION}],
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": user_prompt}],
                }
            ],
            "generationConfig": {
                "temperature": float(getattr(settings, "AI_GENERATION_TEMPERATURE", 0.4)),
                "responseMimeType": "application/json",
                "responseSchema": schema,
            },
        }

        try:
            response = requests.post(
                url,
                headers=headers,
                params=params,
                json=body,
                timeout=self.timeout,
            )
        except requests.Timeout as exc:
            raise GeminiProviderError(
                "Question generation failed: Gemini API timeout.",
                retryable=True,
            ) from exc
        except requests.RequestException as exc:
            logger.exception("Gemini network failure")
            raise GeminiProviderError(
                "Question generation failed: could not reach Gemini API.",
                retryable=True,
            ) from exc

        # Some models reject complex responseSchema — retry once with JSON mime only.
        if response.status_code == 400 and "responseSchema" in body.get("generationConfig", {}):
            logger.warning(
                "Gemini rejected responseSchema on model=%s; retrying with JSON mime type only",
                model,
            )
            body = {
                **body,
                "generationConfig": {
                    "temperature": body["generationConfig"]["temperature"],
                    "responseMimeType": "application/json",
                },
            }
            try:
                response = requests.post(
                    url,
                    headers=headers,
                    params=params,
                    json=body,
                    timeout=self.timeout,
                )
            except requests.Timeout as exc:
                raise GeminiProviderError(
                    "Question generation failed: Gemini API timeout.",
                    retryable=True,
                ) from exc
            except requests.RequestException as exc:
                logger.exception("Gemini network failure on schema fallback")
                raise GeminiProviderError(
                    "Question generation failed: could not reach Gemini API.",
                    retryable=True,
                ) from exc

        if response.status_code != 200:
            api_message = _safe_api_error_message(response)
            detail = (api_message or "").lower()
            overloaded = response.status_code in (429, 503) or "high demand" in detail or "unavailable" in detail

            if response.status_code == 400:
                raise GeminiProviderError(
                    "Question generation failed: Gemini rejected the request "
                    f"(invalid request).{api_message}"
                )
            if response.status_code in (401, 403):
                raise GeminiProviderError(
                    "Question generation failed: invalid or unauthorized Gemini API key."
                    f"{api_message}"
                )
            if response.status_code == 404:
                raise GeminiProviderError(
                    "Question generation failed: Gemini model not found "
                    f"('{model}'). Update GEMINI_MODEL in .env."
                    f"{api_message}",
                    retryable=True,  # try next fallback model
                )
            if overloaded:
                raise GeminiProviderError(
                    "Question generation failed: Gemini is temporarily overloaded "
                    f"on model '{model}'.{api_message}",
                    retryable=True,
                )
            if response.status_code >= 500:
                raise GeminiProviderError(
                    f"Question generation failed: Gemini service error.{api_message}",
                    retryable=True,
                )
            raise GeminiProviderError(
                f"Question generation failed: Gemini HTTP {response.status_code}."
                f"{api_message}"
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise GeminiProviderError(
                "Question generation failed: Gemini returned non-JSON HTTP body."
            ) from exc

        try:
            parts = data["candidates"][0]["content"]["parts"]
            # Ignore thought-only parts if present; keep text parts.
            texts = [
                p.get("text", "")
                for p in parts
                if isinstance(p, dict) and p.get("text") and not p.get("thought")
            ]
            if not texts:
                texts = [p.get("text", "") for p in parts if isinstance(p, dict)]
            text = "\n".join(t for t in texts if t).strip()
        except (KeyError, IndexError, TypeError) as exc:
            block = data.get("promptFeedback") or data.get("error") or {}
            logger.warning("Gemini empty/blocked response: %s", block)
            raise GeminiProviderError(
                "Question generation failed: Gemini returned no usable content."
            ) from exc

        if not text:
            raise GeminiProviderError(
                "Question generation failed: Gemini returned empty content."
            )
        return text

    @staticmethod
    def _parse_json(raw_text: str) -> Any:
        text = raw_text.strip()
        # Defensive: strip accidental markdown fences if the model ignores mime type.
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise GeminiProviderError(
                "Question generation failed: Gemini returned invalid JSON."
            ) from exc


def _safe_api_error_message(response: requests.Response) -> str:
    """Extract a short, non-sensitive API error message for admins/logs."""
    try:
        payload = response.json()
        message = (payload.get("error") or {}).get("message") or ""
    except ValueError:
        message = ""
    message = " ".join(str(message).split())
    if not message:
        return ""
    return f" Details: {message[:240]}"


def get_ai_provider() -> AIQuestionProvider:
    provider_name = (getattr(settings, "AI_PROVIDER", "gemini") or "gemini").lower()
    if provider_name == "gemini":
        return GeminiQuestionProvider()
    raise GeminiProviderError(
        f"Question generation failed: unsupported AI_PROVIDER '{provider_name}'."
    )
