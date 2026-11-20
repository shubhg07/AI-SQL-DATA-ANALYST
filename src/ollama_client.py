"""Thin wrapper around a local Ollama server (http://localhost:11434)."""
from __future__ import annotations

import json
import os
import re

import requests
from dotenv import load_dotenv

load_dotenv()


class OllamaError(RuntimeError):
    """Raised when the LLM server is unreachable or returns unusable output."""


def _parse_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
    raise OllamaError(f"Model did not return valid JSON: {text[:200]!r}")


class OllamaClient:
    def __init__(self, model: str | None = None, base_url: str | None = None, timeout: int = 300):
        self.model = model or os.getenv("OLLAMA_MODEL", "llama3.1:8b")
        self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")).rstrip("/")
        self.timeout = timeout
        # Ollama sometimes doesn't use every CPU core by default. On a laptop with no
        # GPU, pointing it at (logical cores - 1) can measurably speed up generation.
        # Set OLLAMA_NUM_THREAD in .env to override; leave unset to let Ollama decide.
        num_thread = os.getenv("OLLAMA_NUM_THREAD")
        self.num_thread = int(num_thread) if num_thread else None

    # ---- health ----
    def list_models(self) -> list[str]:
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=5)
            r.raise_for_status()
            return [m["name"] for m in r.json().get("models", [])]
        except (requests.RequestException, ValueError):
            return []

    def is_available(self) -> bool:
        try:
            return requests.get(f"{self.base_url}/api/tags", timeout=3).ok
        except requests.RequestException:
            return False

    # ---- chat ----
    def chat(self, system: str, user: str, json_mode: bool = False, temperature: float = 0.1) -> str:
        options = {"temperature": temperature, "num_ctx": 8192}
        if self.num_thread:
            options["num_thread"] = self.num_thread
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "options": options,
        }
        if json_mode:
            payload["format"] = "json"
        try:
            r = requests.post(f"{self.base_url}/api/chat", json=payload, timeout=self.timeout)
        except requests.ConnectionError as e:
            raise OllamaError(
                f"Cannot reach Ollama at {self.base_url}. Start it with `ollama serve`."
            ) from e
        except requests.Timeout as e:
            raise OllamaError("Ollama took too long to answer (timeout).") from e

        if r.status_code == 404:
            raise OllamaError(f"Model '{self.model}' not found. Run: ollama pull {self.model}")
        try:
            r.raise_for_status()
            return r.json()["message"]["content"].strip()
        except (requests.HTTPError, KeyError, ValueError) as e:
            raise OllamaError(f"Unexpected response from Ollama: {e}") from e

    def chat_json(self, system: str, user: str, temperature: float = 0.1, retries: int = 1) -> dict:
        last_error: Exception | None = None
        for _ in range(retries + 1):
            text = self.chat(system, user, json_mode=True, temperature=temperature)
            try:
                return _parse_json(text)
            except OllamaError as e:
                last_error = e
        raise last_error  # type: ignore[misc]