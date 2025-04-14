"""Obsługa API OpenAI dla integracji Home Assistant AI Support."""

from __future__ import annotations

import logging
from typing import Any

from openai import AsyncOpenAI, APIError, AuthenticationError
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

class OpenAIAnalyzer:
    def __init__(
        self,
        hass: HomeAssistant,
        api_key: str,
        model: str = "gpt-4o",
        max_tokens: int = 2000
    ):
        self.hass = hass
        self.client = AsyncOpenAI(
            api_key=api_key,
            max_retries=2
        )
        self.model = model
        self.max_tokens = max_tokens

    async def analyze_logs(self, logs: str) -> str:
        if not logs.strip():
            return "Brak logów do analizy"
            
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
                    {"role": "user", "content": logs[-30000:]}
                ],
                max_tokens=self.max_tokens
            )
            return response.choices[0].message.content
            
        except APIError as err:
            _LOGGER.error("Błąd API OpenAI: %s", err)
            return f"Błąd API: {err}"
        except AuthenticationError as err:
            _LOGGER.error("Błąd autentykacji: %s", err)
            return "Nieprawidłowy klucz API"
        except Exception as err:
            _LOGGER.error("Błąd analizy: %s", err, exc_info=True)
            return f"Błąd analizy: {err}"

    async def close(self):
        await self.client.close()
