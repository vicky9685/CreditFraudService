"""
LLM provider supporting Ollama (Qwen3) as primary backend.
Falls back to a lightweight HuggingFace pipeline if Ollama is unavailable.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from config.settings import get_settings

logger = logging.getLogger(__name__)


class LLMProvider:
    """
    Unified LLM interface.

    Priority:
      1. Ollama (qwen3:latest or configured model) — zero cost, local inference.
      2. HuggingFace pipeline (Qwen/Qwen2.5-0.5B-Instruct) — tiny model, CPU-safe.
    """

    def __init__(self) -> None:
        self._cfg = get_settings()
        self._backend: str = "none"
        self._client: Any = None
        self._init_backend()

    def _init_backend(self) -> None:
        if self._try_ollama():
            return
        logger.warning(
            "Ollama not available at %s — falling back to HuggingFace pipeline.",
            self._cfg.ollama_base_url,
        )
        self._try_huggingface()

    def _try_ollama(self) -> bool:
        try:
            import ollama

            client = ollama.Client(host=self._cfg.ollama_base_url)
            # Lightweight ping — list local models
            models = client.list()
            available = [m.model for m in models.models]
            logger.info("Ollama available. Models: %s", available)

            target = self._cfg.ollama_model
            if not any(target in m for m in available):
                logger.warning(
                    "Model '%s' not pulled yet. Run: ollama pull %s", target, target
                )
            self._client = client
            self._backend = "ollama"
            return True
        except Exception as exc:
            logger.debug("Ollama init failed: %s", exc)
            return False

    def _try_huggingface(self) -> bool:
        try:
            from transformers import pipeline as hf_pipeline

            model_id = "Qwen/Qwen2.5-0.5B-Instruct"
            logger.info("Loading HuggingFace model '%s' (CPU)…", model_id)
            self._client = hf_pipeline(
                "text-generation",
                model=model_id,
                max_new_tokens=512,
                do_sample=False,
                device_map="cpu",
            )
            self._backend = "huggingface"
            logger.info("HuggingFace backend ready (%s)", model_id)
            return True
        except Exception as exc:
            logger.error("HuggingFace init failed: %s", exc)
            self._backend = "mock"
            return False

    # ── public generate ───────────────────────────────────────────────────────

    def generate(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.1,
        max_tokens: int = 1024,
    ) -> tuple[str, int]:
        """
        Returns (answer_text, estimated_token_count).
        """
        if self._backend == "ollama":
            return self._generate_ollama(system_prompt, user_message, temperature, max_tokens)
        if self._backend == "huggingface":
            return self._generate_hf(system_prompt, user_message, max_tokens)
        # Mock fallback — returns deterministic analysis for testing without LLM
        return self._generate_mock(system_prompt, user_message)

    def _generate_ollama(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float,
        max_tokens: int,
    ) -> tuple[str, int]:
        import ollama

        try:
            response = self._client.chat(
                model=self._cfg.ollama_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                options={
                    "temperature": temperature,
                    "num_predict": max_tokens,
                },
            )
            text = response.message.content or ""
            tokens = getattr(response, "eval_count", len(text.split()) * 2)
            return text, tokens
        except Exception as exc:
            logger.error("Ollama generate error: %s", exc)
            return f"[LLM Error: {exc}]", 0

    def _generate_hf(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int,
    ) -> tuple[str, int]:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        try:
            output = self._client(messages, max_new_tokens=max_tokens)
            text = output[0]["generated_text"][-1]["content"]
            return text, len(text.split()) * 2
        except Exception as exc:
            logger.error("HuggingFace generate error: %s", exc)
            return f"[LLM Error: {exc}]", 0

    @staticmethod
    def _generate_mock(system_prompt: str, user_message: str) -> tuple[str, int]:
        """Used in tests / when no LLM backend is available."""
        answer = (
            "[Mock LLM Response]\n\n"
            "Risk Assessment: Based on the transaction features provided, "
            "this transaction exhibits several fraud indicators. "
            "A human investigator review is recommended.\n\n"
            "Note: Configure Ollama with 'ollama pull qwen3' for real LLM inference."
        )
        return answer, 50

    @property
    def backend(self) -> str:
        return self._backend

    def health(self) -> dict[str, Any]:
        return {
            "backend": self._backend,
            "model": self._cfg.ollama_model if self._backend == "ollama" else "hf-fallback",
            "available": self._backend != "none",
        }


@lru_cache(maxsize=1)
def get_llm_client() -> LLMProvider:
    return LLMProvider()
