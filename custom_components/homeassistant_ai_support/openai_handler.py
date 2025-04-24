"""Obsługa API OpenAI dla integracji Home Assistant AI Support."""

from __future__ import annotations

import logging
from typing import Any

from openai import AsyncOpenAI, APIError, AuthenticationError
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)

class OpenAIAnalyzer:
    def __init__(
        self,
        hass: HomeAssistant,
        api_key: str,
        model: str = "gpt-4.1-mini",
        system_prompt: str = "",
        max_tokens: int = 2000
    ):
        self.hass = hass
        # Używamy HTTP klienta Home Assistant, który jest async-safe
        session = async_get_clientsession(hass)
        self.client = AsyncOpenAI(
            api_key=api_key,
            max_retries=2,
            timeout=30.0,
            http_client=session
        )
        self.model = model
        self.system_prompt = system_prompt
        self.max_tokens = max_tokens

    async def analyze_logs(self, logs: str, cost_optimization: bool) -> str:
        if not logs.strip():
            return "Brak logów do analizy"

        if cost_optimization:
            logs = self._optimize_logs(logs)

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": logs[-30000:] if logs else "Brak logów do analizy"}
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

    def _optimize_logs(self, logs: str) -> str:
        if not logs:
            return ""
        lines = logs.split('\n')
        return '\n'.join([
            line for line in lines
            if any(keyword in line for keyword in ['ERROR', 'WARNING'])
        ][-1000:])

    async def close(self):
        # OpenAI client może nie mieć metody close w najnowszych wersjach
        if hasattr(self.client, 'close'):
            await self.client.close()
        # Jeśli używamy sesji aiohttp, to ona zajmie się zamknięciem