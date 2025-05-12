"""Obsługa API OpenAI dla integracji Home Assistant AI Support."""

from __future__ import annotations

import logging
import asyncio
import json

_LOGGER = logging.getLogger(__name__)

class OpenAIAnalyzer:
    def __init__(
        self,
        hass,
        api_key: str,
        model: str = "gpt-4.1-mini",
        system_prompt: str = "",
        max_tokens: int = 2000
    ):
        self.hass = hass
        self.api_key = api_key
        self.model = model
        self.system_prompt = system_prompt
        self.max_tokens = max_tokens

        self._openai = None
        self.client = None

    async def update_model(self, new_model: str):
        """Aktualizuje model bez tworzenia nowego klienta."""
        _LOGGER.info("Aktualizacja modelu OpenAI z %s na %s", self.model, new_model)
        self.model = new_model
        return True

    async def update_system_prompt(self, new_prompt: str):
        """Aktualizuje prompt systemowy bez tworzenia nowego klienta."""
        _LOGGER.info("Aktualizacja promptu systemowego")
        self.system_prompt = new_prompt
        return True

    async def _load_openai_module(self):
        """Leniwe zaimportowanie modułu openai w executorze."""
        if self._openai is None:
            def _import():
                import openai
                return openai
            self._openai = await self.hass.async_add_executor_job(_import)
        return self._openai

    async def async_init_client(self):
        """Zainicjalizuj AsyncOpenAI klienta poza pętlą zdarzeń."""
        openai = await self._load_openai_module()
        try:
            def _create_client():
                return openai.AsyncOpenAI(
                    api_key=self.api_key,
                    max_retries=3
                )
            self.client = await self.hass.async_add_executor_job(_create_client)
        except Exception as err:
            _LOGGER.error("Błąd podczas inicjalizacji klienta OpenAI: %s", err)
            raise

    async def analyze_logs(
        self,
        logs: str,
        cost_optimization: bool,
        max_retries: int = 3
    ) -> str:
        if not logs.strip():
            return "Brak logów do analizy"

        # Upewnij się, że klient jest zainicjalizowany
        if self.client is None:
            await self.async_init_client()

        if cost_optimization:
            logs = self._optimize_logs(logs)

        # Ograniczenie rozmiaru
        logs_to_send = logs[-20000:] if len(logs) > 20000 else logs

        # Fallback modeli
        fallback_models = {
            "gpt-4o-mini": "gpt-4.1-mini",
            "gpt-4o":      "gpt-4.1",
            "gpt-4.1-nano": "gpt-3.5-turbo"
        }
        current_model = self.model
        model_attempt = 0
        max_model_attempts = 2

        # Załaduj referencje wyjątków
        openai = await self._load_openai_module()
        APIError = getattr(openai, "APIError", Exception)
        AuthenticationError = getattr(openai, "AuthenticationError", Exception)
        BadRequestError = getattr(openai, "BadRequestError", Exception)
        RateLimitError = getattr(openai, "RateLimitError", Exception)

        for attempt in range(max_retries):
            try:
                _LOGGER.debug("Próba %d analizy za pomocą modelu %s", attempt + 1, current_model)

                response = await self.client.chat.completions.create(
                    model=current_model,
                    messages=[
                        {"role": "system", "content": self.system_prompt},
                        {"role": "user",   "content": logs_to_send or "Brak logów do analizy"}
                    ],
                    max_tokens=self.max_tokens,
                    timeout=50.0
                )
                return response.choices[0].message.content

            except asyncio.CancelledError as err:
                # Jeśli to ostatnia próba, propaguj
                if attempt == max_retries - 1:
                    _LOGGER.error("Anulowano operację po %d próbach: %s", attempt + 1, err)
                    raise
                _LOGGER.warning("Próba %d analizy anulowana, ponawiam...", attempt + 1)
                await asyncio.sleep(2)

            except BadRequestError as err:
                msg = str(err)
                code = getattr(err, "code", None)
                _LOGGER.error("Błąd żądania OpenAI: %s (kod: %s)", msg, code)

                if (code == "model_not_found"
                        or "does not exist or you do not have access" in msg):
                    _LOGGER.warning("Brak dostępu do modelu %s", current_model)
                    if current_model in fallback_models and model_attempt < max_model_attempts:
                        new_model = fallback_models[current_model]
                        _LOGGER.info("Przełączanie modelu: %s -> %s", current_model, new_model)
                        current_model = new_model
                        model_attempt += 1
                        continue
                    return (
                        f"Błąd dostępu do modelu: Nie masz dostępu do {current_model}."
                        " Sprawdź ustawienia API.")
                return f"Błąd żądania: {msg}"

            except AuthenticationError as err:
                _LOGGER.error("Błąd autoryzacji: %s", err)
                return "Nieprawidłowy klucz API. Sprawdź konfigurację."

            except RateLimitError as err:
                _LOGGER.error("Limit zapytań przekroczony: %s", err)
                if attempt == max_retries - 1:
                    return "Przekroczono limit zapytań do OpenAI. Spróbuj później."
                wait = (attempt + 1) * 5
                _LOGGER.info("Czekam %d s przed ponowną próbą limitu...", wait)
                await asyncio.sleep(wait)

            except APIError as err:
                _LOGGER.error("Błąd API OpenAI: %s", err)
                return f"Błąd API OpenAI: {err}"

            except Exception as err:
                _LOGGER.error("Nieoczekiwany błąd: %s", err, exc_info=True)
                return f"Nieoczekiwany błąd: {err}"

        return "Nie udało się przeanalizować logów po wielokrotnych próbach."

    async def analyze_anomalies(self, anomalies, context=None):
        """Analizuje wykryte anomalie."""
        if not anomalies:
            return "Nie wykryto anomalii."

        prompt = (
            "Analizuję następujące anomalie w Home Assistant:\n\n"
        )
        if context:
            prompt += f"Kontekst:\n{json.dumps(context, indent=2, ensure_ascii=False)}\n\n"
        prompt += json.dumps(anomalies, indent=2, ensure_ascii=False)

        return await self.analyze_logs(prompt, cost_optimization=False)

    def _optimize_logs(self, logs: str) -> str:
        lines = logs.split("\n")
        filtered = [
            l for l in lines
            if any(k in l for k in ("ERROR", "WARNING", "CRITICAL", "Exception", "Traceback"))
        ][-1500:]
        return "\n".join(filtered)

    async def close(self):
        """Zamknij klienta OpenAI."""
        if self.client:
            try:
                await self.client.close()
            except Exception as err:
                _LOGGER.warning("Błąd przy zamykaniu klienta OpenAI: %s", err)
