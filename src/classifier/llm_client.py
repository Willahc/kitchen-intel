"""Cliente HTTP direto para chamadas de API de LLM (Gate 5).

Não utiliza LangChain nem bibliotecas intermediárias.
Opera diretamente sobre REST APIs via HTTP (httpx).
Suporta OpenAI, Anthropic e Google Gemini.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Callable

import httpx

try:
    from dotenv import load_dotenv

    # Carregar .env se existir na raiz do projeto
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)
    else:
        load_dotenv()
except ImportError:
    pass

# Preços oficiais por milhão de tokens (USD)
MODEL_PRICING: dict[tuple[str, str], dict[str, float]] = {
    ("openai", "gpt-4o-mini"): {"input": 0.150, "output": 0.600},
    ("openai", "gpt-4o"): {"input": 2.500, "output": 10.000},
    # Fonte: https://developers.openai.com/api/docs/models/gpt-5.6-luna (consultada em 2026-09-13).
    ("openai", "gpt-5.6-luna"): {"input": 0.200, "output": 1.200},
    ("anthropic", "claude-3-5-haiku-20241022"): {"input": 0.800, "output": 4.000},
    ("anthropic", "claude-3-haiku-20240307"): {"input": 0.250, "output": 1.250},
    ("gemini", "gemini-2.5-flash"): {"input": 0.075, "output": 0.300},
    ("gemini", "gemini-1.5-flash"): {"input": 0.075, "output": 0.300},
    ("gemini", "gemini-flash-latest"): {"input": 0.075, "output": 0.300},
    ("google", "gemini-2.5-flash"): {"input": 0.075, "output": 0.300},
    ("google", "gemini-flash-latest"): {"input": 0.075, "output": 0.300},
    # Fonte: https://console.groq.com/docs/models (consultada em 2026-09-13).
    ("groq", "openai/gpt-oss-120b"): {"input": 0.150, "output": 0.600},
    ("openrouter", "nvidia/nemotron-3-super-120b-a12b:free"): {"input": 0.0, "output": 0.0},
    ("cerebras", "qwen-3.8-27b"): {"input": 0.0, "output": 0.0},
    ("nvidia", "openai/gpt-oss-20b"): {"input": 0.0, "output": 0.0},
    ("nvidia", "nvidia/nemotron-3-super-120b-a12b"): {"input": 0.0, "output": 0.0},
}


class MissingCredentialsError(RuntimeError):
    """Exceção levantada quando nenhuma chave de API está disponível no ambiente."""

    def __init__(self, provider: str, env_var: str) -> None:
        super().__init__(
            f"Credencial ausente para o provedor '{provider}'. "
            f"Defina a variável de ambiente '{env_var}' para executar inferências reais."
        )
        self.provider = provider
        self.env_var = env_var


class DailyQuotaExhaustedError(RuntimeError):
    """Exceção levantada quando a cota diária do modelo for esgotada (HTTP 429 RESOURCE_EXHAUSTED)."""

    def __init__(self, message: str, retry_delay: str | None = None) -> None:
        super().__init__(message)
        self.retry_delay = retry_delay


class LLMClient:
    """Cliente HTTP direto para inferência de LLM com medição de tokens, latência e custo."""

    def __init__(
        self,
        provider: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        timeout_seconds: float = 45.0,
        mock_handler: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        reasoning_effort: str | None = None,
    ) -> None:
        # Detecção automática de provedor se não especificado
        if not provider:
            if os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"):
                provider = "gemini"
            elif os.getenv("OPENAI_API_KEY"):
                provider = "openai"
            elif os.getenv("OPENROUTER_API_KEY"):
                provider = "openrouter"
            elif os.getenv("CEREBRAS_API_KEY"):
                provider = "cerebras"
            elif os.getenv("NVIDIA_API_KEY"):
                provider = "nvidia"
            elif os.getenv("ANTHROPIC_API_KEY"):
                provider = "anthropic"
            else:
                provider = "gemini"

        self.provider = provider.lower()

        default_models = {
            "gemini": "gemini-2.5-flash",
            "google": "gemini-2.5-flash",
            "openai": "gpt-4o-mini",
            "anthropic": "claude-3-5-haiku-20241022",
            "groq": "openai/gpt-oss-120b",
            "openrouter": "nvidia/nemotron-3-super-120b-a12b:free",
            "cerebras": "qwen-3.8-27b",
            "nvidia": "openai/gpt-oss-20b",
        }
        self.model = model or default_models.get(self.provider, "gemini-2.5-flash")
        self.timeout_seconds = timeout_seconds
        self.mock_handler = mock_handler

        env_var_map = {
            "gemini": "GEMINI_API_KEY",
            "google": "GEMINI_API_KEY",
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "groq": "GROQ_API_KEY",
            "openrouter": "OPENROUTER_API_KEY",
            "cerebras": "CEREBRAS_API_KEY",
            "nvidia": "NVIDIA_API_KEY",
        }

        self.env_var_name = env_var_map.get(self.provider, f"{self.provider.upper()}_API_KEY")
        google_fallback = os.getenv("GOOGLE_API_KEY") if self.provider in {"gemini", "google"} else None
        self.api_key = api_key or os.getenv(self.env_var_name) or google_fallback
        self.reasoning_effort = reasoning_effort
        if self.provider == "groq" and self.reasoning_effort is None:
            self.reasoning_effort = "low"
        if self.provider == "openai" and self.model == "gpt-5.6-luna" and self.reasoning_effort is None:
            self.reasoning_effort = "none"

    def is_configured(self) -> bool:
        return bool(self.api_key) or self.mock_handler is not None

    def calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        pricing = MODEL_PRICING.get((self.provider, self.model))
        if not pricing:
            # Fallback para gemini/openai
            if "flash" in self.model:
                pricing = {"input": 0.075, "output": 0.300}
            elif "mini" in self.model:
                pricing = {"input": 0.150, "output": 0.600}
            else:
                return 0.0
        in_cost = (input_tokens / 1_000_000) * pricing["input"]
        out_cost = (output_tokens / 1_000_000) * pricing["output"]
        return round(in_cost + out_cost, 8)

    def estimate_max_cost(self, num_records: int, avg_input_tokens: int = 800, avg_output_tokens: int = 150) -> float:
        """Estima o custo máximo teórico para um número de registros."""
        return self.calculate_cost(num_records * avg_input_tokens, num_records * avg_output_tokens)

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        """Executa chamada direta de inferência HTTP e devolve raw_text, tokens, latência e custo."""
        if self.mock_handler:
            start = time.perf_counter()
            mock_payload = {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "temperature": temperature,
                "provider": self.provider,
                "model": self.model,
            }
            res = self.mock_handler(mock_payload)
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            in_tok = res.get("input_tokens", 0)
            out_tok = res.get("output_tokens", 0)
            return {
                "content": res["content"],
                "input_tokens": in_tok,
                "output_tokens": out_tok,
                "total_tokens": in_tok + out_tok,
                "latency_ms": latency_ms,
                "cost": self.calculate_cost(in_tok, out_tok),
            }

        if not self.api_key:
            raise MissingCredentialsError(self.provider, self.env_var_name)

        if self.provider in {"gemini", "google"}:
            return self._call_gemini(system_prompt, user_prompt, temperature)
        elif self.provider == "openai":
            return self._call_openai(system_prompt, user_prompt, temperature)
        elif self.provider == "anthropic":
            return self._call_anthropic(system_prompt, user_prompt, temperature)
        elif self.provider == "groq":
            return self._call_groq(system_prompt, user_prompt, temperature)
        elif self.provider == "openrouter":
            return self._call_openrouter(system_prompt, user_prompt, temperature)
        elif self.provider == "cerebras":
            return self._call_cerebras(system_prompt, user_prompt, temperature)
        elif self.provider == "nvidia":
            return self._call_nvidia(system_prompt, user_prompt, temperature)
        else:
            raise ValueError(f"Provedor '{self.provider}' não suportado.")


    def _call_gemini(self, system_prompt: str, user_prompt: str, temperature: float) -> dict[str, Any]:
        url = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }

        max_http_retries = 4
        response = None
        latency_ms = 0.0
        for attempt in range(1, max_http_retries + 1):
            try:
                start = time.perf_counter()
                with httpx.Client(timeout=self.timeout_seconds) as client:
                    response = client.post(url, headers=headers, json=payload)
                latency_ms = round((time.perf_counter() - start) * 1000, 2)

                if response.status_code == 429:
                    resp_text = response.text
                    if "GenerateRequestsPerDay" in resp_text or "exceeded your current quota" in resp_text:
                        raise DailyQuotaExhaustedError(
                            f"Cota diária de requisições esgotada para o modelo '{self.model}'. Detalhe: {resp_text[:200]}"
                        )
                    if attempt < max_http_retries:
                        sleep_time = attempt * 5.0
                        try:
                            err_details = response.json().get("error", {}).get("details", [])
                            for d in err_details:
                                if d.get("@type", "").endswith("RetryInfo"):
                                    delay_str = str(d.get("retryDelay", "")).rstrip("s")
                                    if delay_str:
                                        sleep_time = max(sleep_time, float(delay_str) + 1.0)
                        except Exception:
                            pass
                        time.sleep(sleep_time)
                        continue
                    raise RuntimeError(f"Erro HTTP 429 da Gemini API: {resp_text}")
                elif response.status_code in {500, 502, 503, 504}:
                    if attempt < max_http_retries:
                        time.sleep(attempt * 3.0)
                        continue
                    raise RuntimeError(f"Erro HTTP {response.status_code} da Gemini API: {response.text}")
                elif response.status_code != 200:
                    raise RuntimeError(f"Erro HTTP {response.status_code} da Gemini API: {response.text}")
                break
            except (httpx.TimeoutException, httpx.ConnectError) as err:
                if attempt < max_http_retries:
                    time.sleep(attempt * 3.0)
                    continue
                raise err

        data = response.json()
        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        in_tokens = usage.get("prompt_tokens", 0)
        out_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", in_tokens + out_tokens)

        return {
            "content": content,
            "input_tokens": in_tokens,
            "output_tokens": out_tokens,
            "total_tokens": total_tokens,
            "latency_ms": latency_ms,
            "cost": self.calculate_cost(in_tokens, out_tokens),
        }

    def _call_openai(self, system_prompt: str, user_prompt: str, temperature: float) -> dict[str, Any]:
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        response_schema = {
            "type": "object",
            "properties": {
                "relevant": {"type": "boolean"},
                "relevance": {"type": "string", "enum": ["ALTA", "MEDIA", "BAIXA", "IRRELEVANTE"]},
                "categories": {"type": "array", "items": {"type": "string"}},
                "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
                "reason": {"type": "string", "minLength": 3, "maxLength": 2000},
            },
            "required": ["relevant", "relevance", "categories", "confidence", "reason"],
            "additionalProperties": False,
        }
        payload = {
            "model": self.model,
            "temperature": temperature,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "kitchen_intel_classification",
                    "strict": True,
                    "schema": response_schema,
                },
            },
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if self.reasoning_effort is not None:
            payload["reasoning_effort"] = self.reasoning_effort

        start = time.perf_counter()
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(url, headers=headers, json=payload)

        latency_ms = round((time.perf_counter() - start) * 1000, 2)

        if response.status_code != 200:
            raise RuntimeError(f"Erro HTTP {response.status_code} da OpenAI: {response.text}")

        data = response.json()
        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        in_tokens = usage.get("prompt_tokens", 0)
        out_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", in_tokens + out_tokens)

        return {
            "content": content,
            "input_tokens": in_tokens,
            "output_tokens": out_tokens,
            "total_tokens": total_tokens,
            "latency_ms": latency_ms,
            "cost": self.calculate_cost(in_tokens, out_tokens),
            "rate_limit_headers": {
                key: value
                for key, value in response.headers.items()
                if key.lower().startswith("x-ratelimit-") or key.lower() == "retry-after"
            },
        }

    def _call_groq(self, system_prompt: str, user_prompt: str, temperature: float) -> dict[str, Any]:
        """Chamada OpenAI-compatível da Groq, com limites obtidos dos headers reais."""
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        response_schema = {
            "type": "object",
            "properties": {
                "relevant": {"type": "boolean"},
                "relevance": {"type": "string", "enum": ["ALTA", "MEDIA", "BAIXA", "IRRELEVANTE"]},
                "categories": {"type": "array", "items": {"type": "string"}},
                "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
                "reason": {"type": "string", "minLength": 3, "maxLength": 2000},
            },
            "required": ["relevant", "relevance", "categories", "confidence", "reason"],
            "additionalProperties": False,
        }
        payload = {
            "model": self.model,
            "temperature": temperature,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "kitchen_intel_classification",
                    "strict": True,
                    "schema": response_schema,
                },
            },
            "reasoning_effort": self.reasoning_effort,
            "include_reasoning": False,
            "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
        }
        start = time.perf_counter()
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(url, headers=headers, json=payload)
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        if response.status_code == 429:
            retry_after = response.headers.get("retry-after")
            raise DailyQuotaExhaustedError("HTTP 429 da Groq API", retry_delay=retry_after)
        if response.status_code != 200:
            raise RuntimeError(f"Erro HTTP {response.status_code} da Groq API: {response.text}")
        data = response.json()
        usage = data.get("usage", {})
        in_tokens = usage.get("prompt_tokens", 0)
        out_tokens = usage.get("completion_tokens", 0)
        return {
            "content": data["choices"][0]["message"]["content"],
            "input_tokens": in_tokens,
            "output_tokens": out_tokens,
            "total_tokens": usage.get("total_tokens", in_tokens + out_tokens),
            "latency_ms": latency_ms,
            "cost": self.calculate_cost(in_tokens, out_tokens),
            "rate_limit_headers": {key: value for key, value in response.headers.items() if key.lower() in {"retry-after", "x-ratelimit-limit-requests", "x-ratelimit-remaining-requests", "x-ratelimit-limit-tokens", "x-ratelimit-remaining-tokens", "x-ratelimit-reset-requests", "x-ratelimit-reset-tokens"}},
        }

    def _call_openrouter(self, system_prompt: str, user_prompt: str, temperature: float) -> dict[str, Any]:
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        schema = {
            "type": "object",
            "properties": {
                "relevant": {"type": "boolean"},
                "relevance": {"type": "string", "enum": ["ALTA", "MEDIA", "BAIXA", "IRRELEVANTE"]},
                "categories": {"type": "array", "items": {"type": "string"}},
                "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
                "reason": {"type": "string", "minLength": 3, "maxLength": 2000},
            },
            "required": ["relevant", "relevance", "categories", "confidence", "reason"],
            "additionalProperties": False,
        }
        payload = {
            "model": self.model,
            "temperature": temperature,
            "response_format": {"type": "json_schema", "json_schema": {"name": "kitchen_intel_classification", "strict": True, "schema": schema}},
            "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
        }
        start = time.perf_counter()
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(url, headers=headers, json=payload)
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        if response.status_code == 429:
            raise DailyQuotaExhaustedError("HTTP 429 do OpenRouter", retry_delay=response.headers.get("retry-after"))
        if response.status_code != 200:
            raise RuntimeError(f"Erro HTTP {response.status_code} do OpenRouter: {response.text}")
        data = response.json()
        usage = data.get("usage", {})
        in_tokens = usage.get("prompt_tokens", usage.get("input_tokens", 0))
        out_tokens = usage.get("completion_tokens", usage.get("output_tokens", 0))
        headers_out = {k: v for k, v in response.headers.items() if k.lower().startswith("x-ratelimit-") or k.lower() == "retry-after"}
        return {"content": data["choices"][0]["message"]["content"], "input_tokens": in_tokens, "output_tokens": out_tokens, "total_tokens": usage.get("total_tokens", in_tokens + out_tokens), "latency_ms": latency_ms, "cost": self.calculate_cost(in_tokens, out_tokens), "rate_limit_headers": headers_out}

    def _call_anthropic(self, system_prompt: str, user_prompt: str, temperature: float) -> dict[str, Any]:
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": self.api_key or "",
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "temperature": temperature,
            "max_tokens": 1024,
            "system": system_prompt,
            "messages": [
                {"role": "user", "content": user_prompt},
            ],
        }

        start = time.perf_counter()
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(url, headers=headers, json=payload)

        latency_ms = round((time.perf_counter() - start) * 1000, 2)

        if response.status_code != 200:
            raise RuntimeError(f"Erro HTTP {response.status_code} da Anthropic: {response.text}")

        data = response.json()
        content = data["content"][0]["text"]
        usage = data.get("usage", {})
        in_tokens = usage.get("input_tokens", 0)
        out_tokens = usage.get("output_tokens", 0)
        total_tokens = in_tokens + out_tokens

        return {
            "content": content,
            "input_tokens": in_tokens,
            "output_tokens": out_tokens,
            "total_tokens": total_tokens,
            "latency_ms": latency_ms,
            "cost": self.calculate_cost(in_tokens, out_tokens),
        }

    def _call_cerebras(self, system_prompt: str, user_prompt: str, temperature: float) -> dict[str, Any]:
        """Inferência via API OpenAI-compatível da Cerebras."""
        url = "https://api.cerebras.ai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {
            "model": self.model,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        start = time.perf_counter()
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(url, headers=headers, json=payload)
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        if response.status_code == 429:
            raise DailyQuotaExhaustedError("HTTP 429 da Cerebras API", retry_delay=response.headers.get("retry-after"))
        if response.status_code != 200:
            raise RuntimeError(f"Erro HTTP {response.status_code} da Cerebras API: {response.text}")
        data = response.json()
        usage = data.get("usage", {})
        in_tokens = usage.get("prompt_tokens", 0)
        out_tokens = usage.get("completion_tokens", 0)
        return {
            "content": data["choices"][0]["message"]["content"],
            "input_tokens": in_tokens,
            "output_tokens": out_tokens,
            "total_tokens": usage.get("total_tokens", in_tokens + out_tokens),
            "latency_ms": latency_ms,
            "cost": self.calculate_cost(in_tokens, out_tokens),
            "rate_limit_headers": {k: v for k, v in response.headers.items() if "ratelimit" in k.lower()},
        }

    def _call_nvidia(self, system_prompt: str, user_prompt: str, temperature: float) -> dict[str, Any]:
        """Inferência via API Catalog / NIM hospedada da NVIDIA."""
        url = "https://integrate.api.nvidia.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {
            "model": self.model,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        start = time.perf_counter()
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(url, headers=headers, json=payload)
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        if response.status_code == 429:
            raise DailyQuotaExhaustedError("HTTP 429 da NVIDIA API", retry_delay=response.headers.get("retry-after"))
        if response.status_code != 200:
            raise RuntimeError(f"Erro HTTP {response.status_code} da NVIDIA API: {response.text}")
        data = response.json()
        usage = data.get("usage", {})
        in_tokens = usage.get("prompt_tokens", 0)
        out_tokens = usage.get("completion_tokens", 0)
        rate_headers = {k: v for k, v in response.headers.items() if "ratelimit" in k.lower() or k.lower().startswith("nvcf-")}
        return {
            "content": data["choices"][0]["message"]["content"],
            "input_tokens": in_tokens,
            "output_tokens": out_tokens,
            "total_tokens": usage.get("total_tokens", in_tokens + out_tokens),
            "latency_ms": latency_ms,
            "cost": self.calculate_cost(in_tokens, out_tokens),
            "rate_limit_headers": rate_headers,
        }

