"""Cloud LLM backend — OpenAI-compatible client for Groq, Gemini, Cerebras.

All three providers expose an OpenAI-compatible /chat/completions endpoint.
A single httpx client handles all of them. Provider differences are limited
to base URL, model name, and API key.

This module handles one provider at a time. Multi-provider failover is
implemented by ProviderPool (added in a subsequent commit).
"""

import base64
import json
from collections.abc import Iterator
from dataclasses import dataclass

import httpx

from .base import (
    TASK_CAPTION,
    TASK_DETAILED_CAPTION,
    TASK_OCR,
    TASK_QUERY,
    VALID_TASKS,
    InferenceBackend,
)

DEFAULT_SYSTEM_PROMPT = (
    "You are SHADOW, a private on-device life context agent. "
    "You are calm, concise, and helpful. "
    "Never mention that you are a language model."
)


# ---------- error taxonomy ----------


class CloudError(Exception):
    """Base class for cloud backend failures."""

    def __init__(self, message: str, provider: str = "", status_code: int = 0):
        super().__init__(message)
        self.provider = provider
        self.status_code = status_code


class RateLimitError(CloudError):
    """HTTP 429 — provider rate limit hit."""


class AuthError(CloudError):
    """HTTP 401/403 — invalid or missing API key."""


class ServerError(CloudError):
    """HTTP 5xx — provider-side failure."""


class NetworkError(CloudError):
    """Timeout, DNS, connection refused."""


# ---------- provider config ----------


@dataclass
class ProviderConfig:
    name: str
    base_url: str
    model: str
    api_key: str

    @property
    def masked_key(self) -> str:
        if not self.api_key:
            return ""
        if len(self.api_key) <= 8:
            return "*" * len(self.api_key)
        return self.api_key[:4] + "…" + self.api_key[-4:]


# ---------- backend ----------


class CloudBackend(InferenceBackend):
    """OpenAI-compatible cloud LLM client for a single provider."""

    def __init__(
        self,
        provider: ProviderConfig,
        timeout_sec: int = 30,
        max_retries: int = 2,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    ):
        self.provider = provider
        self.timeout_sec = timeout_sec
        self.max_retries = max_retries
        self.system_prompt = system_prompt
        self._client = self._make_client()
        self.last_prompt: str = ""
        self.last_prompt_at: float = 0.0

    # ---------- public API ----------

    def generate(self, prompt: str, **kwargs) -> str:
        return "".join(self.generate_stream(prompt, **kwargs)).strip()

    def generate_stream(self, prompt: str, **kwargs) -> Iterator[str]:
        max_tokens = kwargs.get("max_tokens", 512)
        temperature = kwargs.get("temperature", 0.7)

        import time as _time

        self.last_prompt = prompt
        self.last_prompt_at = _time.time()

        payload = {
            "model": self.provider.model,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }

        yielded_any = False
        attempt = 0
        while attempt <= self.max_retries:
            try:
                with self._client.stream(
                    "POST", "chat/completions", json=payload
                ) as response:
                    self._raise_for_status(response)
                    for chunk in self._iter_sse(response):
                        yielded_any = True
                        yield chunk
                return
            except NetworkError:
                # Retry network errors
                if yielded_any:
                    raise
                attempt += 1
                if attempt > self.max_retries:
                    raise
            except ServerError:
                # Retry server errors, but not mid-stream
                if yielded_any:
                    raise
                attempt += 1
                if attempt > self.max_retries:
                    raise
            except (RateLimitError, AuthError):
                # Caller (ProviderPool) handles failover
                raise

        # ---------- vision API ----------

    def supports_vision(self) -> bool:
        """Return whether this configured provider/model supports image input.

        Keep this conservative: a provider having a vision API does not mean
        every model available through that provider accepts image input.
        """
        provider_name = self.provider.name.strip().lower()
        model_name = self.provider.model.strip().lower()

        if provider_name == "gemini":
            return model_name.startswith("gemini-2.5-flash")

        return False

    def understand_image(
        self,
        image_bytes: bytes,
        task: str = TASK_CAPTION,
        prompt: str = "",
    ) -> str:
        """Describe, inspect, or extract text from an image using cloud vision.

        Images are encoded in memory and sent to the provider. This method
        does not write image bytes to disk.
        """
        if task not in VALID_TASKS:
            raise ValueError(
                f"Invalid vision task: {task!r}. "
                f"Expected one of {sorted(VALID_TASKS)}."
            )

        if not self.supports_vision():
            raise NotImplementedError(
                f"Vision is not supported by provider "
                f"{self.provider.name!r} with model "
                f"{self.provider.model!r}."
            )

        if not isinstance(image_bytes, bytes) or not image_bytes:
            raise ValueError("image_bytes must be non-empty bytes.")

        task_prompts = {
            TASK_CAPTION: "Describe this image briefly.",
            TASK_DETAILED_CAPTION: (
                "Describe this image in detail. Include visible objects, "
                "text, layout, and relevant relationships."
            ),
            TASK_OCR: (
                "Extract all readable text from this image. "
                "Preserve the original wording and line order where possible."
            ),
            TASK_QUERY: prompt.strip(),
        }

        effective_prompt = task_prompts[task]
        if not effective_prompt:
            raise ValueError("A non-empty prompt is required for the query task.")

        # Identify the image type from its signature instead of trusting
        # a filename or caller-supplied extension.
        if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            mime_type = "image/png"
        elif image_bytes.startswith(b"\xff\xd8\xff"):
            mime_type = "image/jpeg"
        elif image_bytes.startswith((b"GIF87a", b"GIF89a")):
            mime_type = "image/gif"
        elif image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WEBP":
            mime_type = "image/webp"
        else:
            raise ValueError(
                "Unsupported image format. Expected PNG, JPEG, GIF, or WebP."
            )

        encoded_image = base64.b64encode(image_bytes).decode("ascii")
        image_url = f"data:{mime_type};base64,{encoded_image}"

        payload = {
            "model": self.provider.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": effective_prompt,
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": image_url},
                        },
                    ],
                }
            ],
            "max_tokens": 1024,
            "stream": False,
        }

        try:
            response = self._client.post(
                "chat/completions",
                json=payload,
            )
        except httpx.TimeoutException as exc:
            raise NetworkError(
                f"Vision request timed out: {exc}",
                self.provider.name,
            ) from exc
        except httpx.RequestError as exc:
            raise NetworkError(
                f"Vision request failed: {exc}",
                self.provider.name,
            ) from exc

        self._raise_for_status(response)

        try:
            result = response.json()
            content = result["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise CloudError(
                "Vision endpoint returned an invalid response.",
                self.provider.name,
                response.status_code,
            ) from exc

        # Accommodate APIs that return content as a list of text parts.
        if isinstance(content, list):
            content = "\n".join(
                part["text"]
                for part in content
                if isinstance(part, dict) and isinstance(part.get("text"), str)
            )

        if not isinstance(content, str):
            raise CloudError(
                "Vision endpoint returned no usable text content.",
                self.provider.name,
                response.status_code,
            )

        return content.strip()

    def embed(self, text: str) -> list[float]:
        raise NotImplementedError(
            "CloudBackend does not embed. Use the local ONNX embedder."
        )

    @property
    def info(self) -> dict:
        return {
            "backend": "cloud",
            "provider": self.provider.name,
            "model": self.provider.model,
            "key_masked": self.provider.masked_key,
        }

    def test_connection(self) -> tuple[bool, str]:
        """Probe the provider. Returns (ok, message)."""
        payload = {
            "model": self.provider.model,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 5,
            "stream": False,
        }
        try:
            response = self._client.post("chat/completions", json=payload)
            self._raise_for_status(response)
            return True, "ok"
        except CloudError as exc:
            return False, str(exc)
        except httpx.HTTPError as exc:
            return False, f"network error: {exc}"

    def close(self) -> None:
        try:
            self._client.close()
        except Exception:
            pass

    # ---------- internals ----------

    def _make_client(self) -> httpx.Client:
        # httpx uses RFC 3986 URL joining. If base_url doesn't end with
        # a slash, the last path segment is replaced when joining a
        # relative path. Normalize to guarantee `/v1/chat/completions`
        # rather than `/chat/completions`.
        base = self.provider.base_url.rstrip("/") + "/"
        return httpx.Client(
            base_url=base,
            headers={
                "Authorization": f"Bearer {self.provider.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "SHADOW/0.3.7",
            },
            timeout=self.timeout_sec,
        )

    def _raise_for_status(self, response: httpx.Response) -> None:
        status = response.status_code
        if status < 400:
            return
        provider = self.provider.name
        if status == 429:
            raise RateLimitError("rate limit exceeded", provider, status)
        if status in (401, 403):
            raise AuthError("invalid or missing API key", provider, status)
        if 500 <= status < 600:
            raise ServerError(f"server error {status}", provider, status)
        # Try to include response body for debugging other errors
        snippet = ""
        try:
            snippet = response.text[:200]
        except Exception:
            pass
        raise CloudError(f"unexpected status {status}: {snippet}", provider, status)

    @staticmethod
    def _iter_sse(response: httpx.Response) -> Iterator[str]:
        """Parse Server-Sent Events from an OpenAI-compatible stream."""
        try:
            lines = response.iter_lines()
        except httpx.HTTPError as exc:
            raise NetworkError(f"stream failed: {exc}") from exc

        for line in lines:
            if not line:
                continue
            if not line.startswith("data: "):
                continue
            data = line[6:].strip()
            if data == "[DONE]":
                return
            try:
                chunk = json.loads(data)
            except json.JSONDecodeError:
                continue
            choices = chunk.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            content = delta.get("content")
            if content:
                yield content
