"""Obsługa API OpenAI dla integracji Home Assistant AI Support."""
from __future__ import annotations

import logging
from typing import Any
from httpx import AsyncClient as HttpxAsyncClient

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
        self.http_client = HttpxAsyncClient()  # Niestandardowy klient HTTP
        self.client = AsyncOpenAI(
            api_key=api_key,
            http_client=self.http_client,
            max_retries=0
        )
        self.model = model
        self.max_tokens = max_tokens

    async def analyze_logs(self, logs: str) -> str:
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
                max_tokens=self.max_tokens
            )
            return response.choices[0].message.content
            
        except Exception as err:
            _LOGGER.error("Błąd analizy logów: %s", err)
            return "Błąd analizy"

    async def close(self):
        """Zamknij połączenia."""
        await self.http_client.aclose()
