"""Obsługa API OpenAI dla integracji Home Assistant AI Support."""

from __future__ import annotations

import logging
import asyncio
from typing import Any

import httpx
from openai import AsyncOpenAI, APIError, AuthenticationError

from homeassistant.core import HomeAssistant

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
        self.httpx_client = httpx.AsyncClient(timeout=60.0)  # Zwiększony timeout
        self.client = AsyncOpenAI(
            api_key=api_key,
            max_retries=3,  # Zwiększona liczba prób
            http_client=self.httpx_client
        )
        self.model = model
        self.system_prompt = system_prompt
        self.max_tokens = max_tokens

    async def analyze_logs(self, logs: str, cost_optimization: bool, max_retries: int = 3) -> str:
        if not logs.strip():
            return "Brak logów do analizy"
        
        if cost_optimization:
            logs = self._optimize_logs(logs)
        
        # Ograniczenie rozmiaru logów
        logs_to_send = logs[-20000:] if len(logs) > 20000 else logs
        
        # Mechanizm ponownych prób
        for attempt in range(max_retries):
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": self.system_prompt},
                        {"role": "user", "content": logs_to_send if logs_to_send else "Brak logów do analizy"}
                    ],
                    max_tokens=self.max_tokens,
                    timeout=50.0  # Explicit timeout dla tego żądania
                )
                return response.choices[0].message.content
            except asyncio.CancelledError as err:
                # Ostatnia próba, propaguj błąd
                if attempt == max_retries - 1:
                    _LOGGER.error("Anulowano operację po %d próbach: %s", attempt + 1, err)
                    raise
                _LOGGER.warning("Próba %d analizy anulowana, ponawiam...", attempt + 1)
                await asyncio.sleep(2)  # Krótka przerwa przed ponowną próbą
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
        # Filtruj ważne linie i ogranicz ich liczbę
        filtered_lines = [
            line for line in lines
            if any(keyword in line for keyword in ['ERROR', 'WARNING', 'CRITICAL', 'Exception', 'Traceback'])
        ][-1500:]  # Zwiększona liczba linii ale nadal z limitem
        return '\n'.join(filtered_lines)

    async def close(self):
        try:
            await self.httpx_client.aclose()
        except Exception as err:
            _LOGGER.warning("Błąd przy zamykaniu klienta HTTP: %s", err)
