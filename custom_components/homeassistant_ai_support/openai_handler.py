"""Obsługa API OpenAI dla integracji Home Assistant AI Support."""

from __future__ import annotations

import logging
from typing import Any

from httpx import AsyncClient as HttpxAsyncClient
from openai import AsyncOpenAI, APIError, AuthenticationError, RateLimitError

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

class OpenAIAnalyzer:
    """Klasa do zarządzania interakcjami z API OpenAI."""

    def __init__(
        self,
        hass: HomeAssistant,
        api_key: str,
        model: str = "gpt-4o",
        max_tokens: int = 2000
    ):
        """Inicjalizacja klienta OpenAI."""
        self.hass = hass
        self.http_client = HttpxAsyncClient()  # Niestandardowy klient HTTP
        self.client = AsyncOpenAI(
            api_key=api_key,
            http_client=self.http_client,
            max_retries=3  # Dodana wartość retries dla lepszej odporności
        )
        self.model = model
        self.max_tokens = max_tokens

    async def analyze_logs(self, logs: str) -> str:
        """Analiza logów przez OpenAI."""
        if not logs or logs.strip() == "":
            return "Brak logów do analizy."
            
        system_prompt = (
            "Jesteś ekspertem od analizy logów systemowych Home Assistant. "
            "Przeanalizuj poniższe logi i przygotuj zwięzły raport w języku polskim, "
            "wskazując potencjalne problemy i sugerując rozwiązania. "
            "Skup się na błędach, ostrzeżeniach i nieprawidłowym działaniu systemu."
        )
        
        # Szacowanie tokenów w logach (w przybliżeniu 1 token na 4 znaki)
        estimated_tokens = len(logs) // 4
        max_log_tokens = 14000  # Zarezerwuj tokeny na prompt systemowy i odpowiedź
        
        # Przytnij logi jeśli przekraczają limit tokenów
        if estimated_tokens > max_log_tokens:
            _LOGGER.warning(
                "Logi przekraczają szacowany limit tokenów (%s > %s). Przycinanie do ostatnich %s tokenów.", 
                estimated_tokens, max_log_tokens, max_log_tokens
            )
            # Zachowaj najnowsze logi (ostatnią część stringa)
            logs = logs[-max_log_tokens * 4:]
            logs = "...[logi zostały przycięte ze względu na rozmiar]...\n" + logs
        
        try:
            _LOGGER.debug("Wysyłanie %s znaków logów do API OpenAI", len(logs))
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": logs}
                ],
                max_tokens=self.max_tokens
            )
            
            analysis = response.choices[0].message.content
            _LOGGER.debug("Otrzymano analizę z API OpenAI (%s znaków)", len(analysis))
            return analysis
            
        except APIError as api_err:
            error_message = f"Błąd API OpenAI: {api_err}"
            _LOGGER.error(error_message)
            return error_message
            
        except AuthenticationError as auth_err:
            error_message = f"Błąd uwierzytelniania OpenAI: {auth_err}"
            _LOGGER.error(error_message)
            return error_message
            
        except RateLimitError as rate_err:
            error_message = f"Przekroczono limit zapytań OpenAI: {rate_err}"
            _LOGGER.error(error_message)
            return error_message
            
        except Exception as err:
            error_message = f"Błąd analizy logów: {err}"
            _LOGGER.error(error_message)
            return error_message

    async def close(self):
        """Zamknij połączenia."""
        await self.http_client.aclose()
