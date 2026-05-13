"""
LLM provider with automatic backend selection.

Priority order (first available wins):
  1. Groq       — free tier (14,400 tokens/day), fastest inference
  2. HuggingFace Inference API — free tier, serverless
  3. Ollama     — local Qwen3, zero-cost if running
  4. HuggingFace pipeline — tiny Qwen2.5-0.5B on CPU (works on any machine)
  5. Mock       — rule-based fallback, no LLM required

Set env vars to activate cloud backends:
  GROQ_API_KEY=gsk_...          → enables Groq (free at console.groq.com)
  HF_API_TOKEN=hf_...           → enables HuggingFace Inference API (free)
  OLLAMA_BASE_URL=http://...    → enables local Ollama/Qwen3
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Any

from config.settings import get_settings

logger = logging.getLogger(__name__)


class LLMProvider:
    """
    Unified LLM interface with automatic free-tier backend selection.
    """

    def __init__(self) -> None:
        self._cfg = get_settings()
        self._backend: str = "mock"
        self._client: Any = None
        self._model_name: str = "unknown"
        self._init_backend()

    def _init_backend(self) -> None:
        """Try each backend in priority order; use the first one that works."""
        if self._try_groq():
            return
        if self._try_hf_inference_api():
            return
        if self._try_ollama():
            return
        if self._try_hf_pipeline():
            return
        logger.warning("No LLM backend available — using mock responses.")
        self._backend = "mock"

    # ── 1. Groq (free tier, fastest) ─────────────────────────────────────────

    def _try_groq(self) -> bool:
        api_key = os.environ.get("GROQ_API_KEY", "")
        if not api_key:
            return False
        try:
            from groq import Groq
            client = Groq(api_key=api_key)
            # Prefer Qwen3 on Groq if available, otherwise use Llama3
            self._client = client
            self._backend = "groq"
            # qwen-qwen3-32b is available on Groq; fall back to llama3
            self._model_name = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")
            logger.info("Groq backend ready (model: %s)", self._model_name)
            return True
        except Exception as exc:
            logger.debug("Groq init failed: %s", exc)
            return False

    # ── 2. HuggingFace Inference API (free, serverless) ──────────────────────

    def _try_hf_inference_api(self) -> bool:
        token = os.environ.get("HF_API_TOKEN", "") or os.environ.get("HUGGINGFACE_API_TOKEN", "")
        if not token:
            return False
        try:
            from huggingface_hub import InferenceClient
            # Qwen3-0.6B is freely available via HF Inference API
            model = os.environ.get("HF_MODEL", "Qwen/Qwen2.5-0.5B-Instruct")
            client = InferenceClient(model=model, token=token)
            # Quick connectivity test
            client.text_generation("Hello", max_new_tokens=5)
            self._client = client
            self._backend = "hf_inference"
            self._model_name = model
            logger.info("HuggingFace Inference API ready (model: %s)", model)
            return True
        except Exception as exc:
            logger.debug("HF Inference API init failed: %s", exc)
            return False

    # ── 3. Ollama (local, Qwen3) ──────────────────────────────────────────────

    def _try_ollama(self) -> bool:
        try:
            import ollama
            client = ollama.Client(host=self._cfg.ollama_base_url)
            models = client.list()
            available = [m.model for m in models.models]
            target = self._cfg.ollama_model
            if not available:
                return False
            if not any(target in m for m in available):
                logger.warning("Ollama running but '%s' not pulled. Run: ollama pull %s", target, target)
            self._client = client
            self._backend = "ollama"
            self._model_name = target
            logger.info("Ollama backend ready (model: %s)", target)
            return True
        except Exception as exc:
            logger.debug("Ollama init failed: %s", exc)
            return False

    # ── 4. HuggingFace local pipeline (CPU, 0.5B model) ──────────────────────

    def _try_hf_pipeline(self) -> bool:
        try:
            from transformers import pipeline as hf_pipeline
            model_id = "Qwen/Qwen2.5-0.5B-Instruct"
            logger.info("Loading local HuggingFace model '%s' on CPU...", model_id)
            self._client = hf_pipeline(
                "text-generation",
                model=model_id,
                max_new_tokens=512,
                do_sample=False,
                device_map="cpu",
            )
            self._backend = "hf_pipeline"
            self._model_name = model_id
            logger.info("HuggingFace local pipeline ready (%s)", model_id)
            return True
        except Exception as exc:
            logger.debug("HF pipeline init failed: %s", exc)
            return False

    # ── generate dispatch ─────────────────────────────────────────────────────

    def generate(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.1,
        max_tokens: int = 1024,
    ) -> tuple[str, int]:
        """Returns (answer_text, estimated_token_count)."""
        if self._backend == "groq":
            return self._generate_groq(system_prompt, user_message, temperature, max_tokens)
        if self._backend == "hf_inference":
            return self._generate_hf_inference(system_prompt, user_message, max_tokens)
        if self._backend == "ollama":
            return self._generate_ollama(system_prompt, user_message, temperature, max_tokens)
        if self._backend == "hf_pipeline":
            return self._generate_hf_pipeline(system_prompt, user_message, max_tokens)
        return self._generate_mock(system_prompt, user_message)

    def _generate_groq(self, system: str, user: str, temp: float, max_tok: int) -> tuple[str, int]:
        try:
            resp = self._client.chat.completions.create(
                model=self._model_name,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=temp,
                max_tokens=max_tok,
            )
            text = resp.choices[0].message.content or ""
            tokens = resp.usage.total_tokens if resp.usage else len(text.split()) * 2
            return text, tokens
        except Exception as exc:
            logger.error("Groq generate error: %s", exc)
            return self._generate_mock(system, user)

    def _generate_hf_inference(self, system: str, user: str, max_tok: int) -> tuple[str, int]:
        try:
            prompt = f"<|system|>\n{system}\n<|user|>\n{user}\n<|assistant|>\n"
            text = self._client.text_generation(prompt, max_new_tokens=max_tok, temperature=0.1)
            return text, len(text.split()) * 2
        except Exception as exc:
            logger.error("HF Inference API error: %s", exc)
            return self._generate_mock(system, user)

    def _generate_ollama(self, system: str, user: str, temp: float, max_tok: int) -> tuple[str, int]:
        try:
            import ollama
            response = self._client.chat(
                model=self._model_name,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                options={"temperature": temp, "num_predict": max_tok},
            )
            text = response.message.content or ""
            tokens = getattr(response, "eval_count", len(text.split()) * 2)
            return text, tokens
        except Exception as exc:
            logger.error("Ollama generate error: %s", exc)
            return self._generate_mock(system, user)

    def _generate_hf_pipeline(self, system: str, user: str, max_tok: int) -> tuple[str, int]:
        try:
            messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
            output = self._client(messages, max_new_tokens=max_tok)
            text = output[0]["generated_text"][-1]["content"]
            return text, len(text.split()) * 2
        except Exception as exc:
            logger.error("HF pipeline error: %s", exc)
            return self._generate_mock(system, user)

    @staticmethod
    def _generate_mock(_system: str, _user: str) -> tuple[str, int]:
        """Rule-based fallback — works with no LLM at all."""
        return (
            "[Rule-based Analysis]\n\n"
            "Based on the transaction features, the risk scoring engine has evaluated "
            "this transaction using weighted heuristics covering amount, velocity, "
            "geographic factors, and merchant category.\n\n"
            "For LLM-powered analysis:\n"
            "  • Set GROQ_API_KEY (free at console.groq.com)\n"
            "  • Set HF_API_TOKEN (free at huggingface.co)\n"
            "  • Install Ollama: ollama pull qwen3"
        ), 60

    @property
    def backend(self) -> str:
        return self._backend

    @property
    def model_name(self) -> str:
        return self._model_name

    def health(self) -> dict[str, Any]:
        return {
            "backend": self._backend,
            "model": self._model_name,
            "available": self._backend != "mock",
            "free_backends": {
                "groq": bool(os.environ.get("GROQ_API_KEY")),
                "hf_inference": bool(os.environ.get("HF_API_TOKEN") or os.environ.get("HUGGINGFACE_API_TOKEN")),
                "ollama": self._backend == "ollama",
                "hf_pipeline": self._backend == "hf_pipeline",
            },
        }


@lru_cache(maxsize=1)
def get_llm_client() -> LLMProvider:
    return LLMProvider()
