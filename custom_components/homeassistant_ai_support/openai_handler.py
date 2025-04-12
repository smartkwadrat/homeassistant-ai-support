"""Obsługa API OpenAI dla integracji Home Assistant AI Support."""
from __future__ import annotations

import logging
from typing import Any

from openai import AsyncOpenAI, APIError, RateLimitError
from homeassistant.core import HomeAssistant
from homeassistant.helpers.httpx_client import get_async_client

_LOGGER = logging.getLogger(__name__)

class OpenAIAnalyzer:
    """Klasa do komunikacji z API OpenAI."""
    
    def __init__(
        self,
        hass: HomeAssistant,
        api_key: str,
        model: str = "gpt-4o",
        max_tokens: int = 2000,
        temperature: float = 0.3
    ):
        """Inicjalizacja klienta OpenAI."""
        self.hass = hass
        self.client = AsyncOpenAI(
            api_key=api_key,
            http_client=get_async_client(self.hass)
        )
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature

    async def analyze_logs(self, logs: str) -> str | None:
        """Analiza logów przez OpenAI."""
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
                temperature=self.temperature,
                max_tokens=self.max_tokens
            )
            return response.choices[0].message.content
        
        except RateLimitError as err:
            _LOGGER.error("Limit zapytań przekroczony: %s", err)
            return None
            
        except APIError as err:
            _LOGGER.error("Błąd API OpenAI: %s", err)
            return None
            
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.exception("Nieoczekiwany błąd: %s", err)
            return None
