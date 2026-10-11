from __future__ import annotations

import json
from urllib import error as urllib_error
from urllib import request

from app.core.exceptions import GenerationError
from app.llm.base import LLM


class OllamaLLM(LLM):
    """Small HTTP client for a local Ollama chat server."""

    def __init__(self, base_url: str, model: str, timeout_seconds: float = 120.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

    def generate(self, prompt: str) -> str:
        # Qwen3 is a thinking-capable model. We disable thinking for this bounded
        # request/response path so the user-facing answer remains in message.content.
        payload = json.dumps(
            {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "think": False,
            }
        ).encode("utf-8")
        req = request.Request(
            f"{self.base_url}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib_error.HTTPError as exc:
            detail = "HTTP error from Ollama"
            try:
                body = exc.read().decode("utf-8", errors="replace")
                if body:
                    detail = f"Ollama rejected the request: {body[:300]}"
            except OSError:
                pass
            raise GenerationError(detail) from exc
        except (urllib_error.URLError, TimeoutError, OSError) as exc:
            raise GenerationError(
                "Cannot connect to Ollama. Make sure the Ollama service is running and the configured model is installed."
            ) from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GenerationError("Ollama returned an invalid response") from exc

        message = data.get("message") or {}
        answer = str(message.get("content", "")).strip()
        if not answer:
            # Keep compatibility with older/custom Ollama responses.
            answer = str(data.get("response", "")).strip()
        if not answer:
            raise GenerationError(
                f"Ollama returned an empty answer for model '{self.model}'. Verify the model is available and retry."
            )
        return answer
