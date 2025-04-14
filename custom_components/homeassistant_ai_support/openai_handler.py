"""Obsługa API OpenAI dla integracji Home Assistant AI Support."""
from __future__ import annotations

import logging
from typing import Any

from openai import AsyncOpenAI, APIError, AuthenticationError
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
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens

    async def analyze_logs(self, logs: str) -> str:
        """Analiza logów przez OpenAI z pełnym debugowaniem."""
        _LOGGER.debug("Rozpoczęto analizę logów")
        
        system_prompt = (
            "Jesteś ekspertem od analizy logów systemowych Home Assistant. "
            "Przeanalizuj poniższe logi i przygotuj zwięzły raport w języku polskim, "
            "wskazując potencjalne problemy i sugerując rozwiązania."
        )

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": logs}
                ],
                max_tokens=self.max_tokens
            )
            
            _LOGGER.debug("Otrzymano odpowiedź od OpenAI: %s", response)
            return response.choices[0].message.content
            
        except AuthenticationError as err:
            _LOGGER.error("Błąd autoryzacji: %s", err)
            await self._show_error_notification("Nieprawidłowy klucz API")
            raise
            
        except APIError as err:
            _LOGGER.error("Błąd API: %s", err)
            await self._show_error_notification("Problem z połączeniem do OpenAI")
            raise
            
        except Exception as err:
            _LOGGER.exception("Nieoczekiwany błąd: %s", err)
            await self._show_error_notification("Wewnętrzny błąd systemu")
            raise

    async def _show_error_notification(self, message: str) -> None:
        """Wyświetl powiadomienie o błędzie w interfejsie HA."""
        await self.hass.services.async_call(
            "persistent_notification",
            "create",
            {
                "title": "Błąd analizy logów",
                "message": message,
                "notification_id": "ai_support_error"
            }
        )
