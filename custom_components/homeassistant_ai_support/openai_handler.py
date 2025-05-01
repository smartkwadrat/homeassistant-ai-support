"""Obsługa API OpenAI dla integracji Home Assistant AI Support."""

from __future__ import annotations

import logging
import asyncio
import json
from typing import Any

import httpx
from openai import AsyncOpenAI, APIError, AuthenticationError, BadRequestError, RateLimitError

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
    
        # Mechanizm ponownych prób z obsługą fallbacku modeli
        fallback_models = {
            "gpt-4o-mini": "gpt-4.1-mini",  # Jeśli gpt-4o-mini jest niedostępny, użyj gpt-4.1-mini
            "gpt-4o": "gpt-4.1",            # Jeśli gpt-4o jest niedostępny, użyj gpt-4.1
            "gpt-4.1-nano": "gpt-3.5-turbo" # Ostateczny fallback
        }
    
        current_model = self.model
        model_attempt = 0
        max_model_attempts = 2  # Maksymalna liczba modeli do wypróbowania
    
        for attempt in range(max_retries):
            try:
                _LOGGER.debug("Próba %d analizy za pomocą modelu %s", attempt + 1, current_model)
            
                response = await self.client.chat.completions.create(
                    model=current_model,
                    messages=[
                        {"role": "system", "content": self.system_prompt},
                        {"role": "user", "content": logs_to_send if logs_to_send else "Brak logów do analizy"}
                    ],
                    max_tokens=self.max_tokens,
                    timeout=50.0
                )
            
                return response.choices[0].message.content
            
            except asyncio.CancelledError as err:
                # Ostatnia próba, propaguj błąd
                if attempt == max_retries - 1:
                    _LOGGER.error("Anulowano operację po %d próbach: %s", attempt + 1, err)
                    raise
            
                _LOGGER.warning("Próba %d analizy anulowana, ponawiam...", attempt + 1)
                await asyncio.sleep(2)  # Krótka przerwa przed ponowną próbą
            
            except BadRequestError as err:
                error_message = str(err)
                error_code = getattr(err, "code", None)
                _LOGGER.error("Błąd żądania OpenAI: %s (kod: %s)", error_message, error_code)
            
                # Sprawdzamy, czy to błąd dostępu do modelu
                if error_code == "model_not_found" or "does not exist or you do not have access to it" or "does not have access to model" in error_message:
                    _LOGGER.warning("Brak dostępu do modelu %s", current_model)
                
                    # Próbujemy użyć modelu zastępczego, jeśli dostępny i nie przekroczyliśmy limitu prób
                    if current_model in fallback_models and model_attempt < max_model_attempts:
                        fallback_model = fallback_models[current_model]
                        _LOGGER.info("Przełączanie na model zastępczy: %s -> %s", current_model, fallback_model)
                        current_model = fallback_model
                        model_attempt += 1
                        # Resetujemy licznik prób dla nowego modelu
                        continue
                    else:
                        return (f"Błąd dostępu do modelu: Nie masz dostępu do modelu {current_model}. "
                            "Sprawdź swoje uprawnienia API lub zmień model w konfiguracji.")
            
                return f"Błąd żądania: {error_message}"
            
            except AuthenticationError as err:
                _LOGGER.error("Błąd autentykacji: %s", err)
                return "Nieprawidłowy klucz API OpenAI. Sprawdź swój klucz API w konfiguracji."
            
            except RateLimitError as err:
                _LOGGER.error("Przekroczono limit zapytań: %s", err)
            
                # Jeśli to ostatnia próba, zwróć komunikat
                if attempt == max_retries - 1:
                    return "Przekroczono limit zapytań do API OpenAI. Spróbuj ponownie później."
                
                # Czekaj dłużej przed ponowną próbą przy limicie rate
                wait_time = (attempt + 1) * 5  # Eksponencjalne wydłużanie czasu oczekiwania
                _LOGGER.info("Czekam %d sekund przed ponowną próbą...", wait_time)
                await asyncio.sleep(wait_time)
            
            except APIError as err:
                _LOGGER.error("Błąd API OpenAI: %s", err)
                return f"Błąd API OpenAI: {err}"
            
            except Exception as err:
                _LOGGER.error("Nieoczekiwany błąd: %s", err, exc_info=True)
                return f"Nieoczekiwany błąd: {err}"

    async def analyze_anomalies(self, anomalies, context=None):
        """Analizuje wykryte anomalie."""
        if not anomalies:
            return "Nie wykryto anomalii."
        
        prompt = (
            "Analizuję następujące anomalie wykryte w moim systemie Home Assistant. "
            "Każda anomalia zawiera identyfikator encji, aktualną wartość, oczekiwany zakres "
            "oraz kontekst. Wyjaśnij co mogą oznaczać te anomalie, jakie mogą być ich przyczyny "
            "i jakie działania powinienem podjąć:\n\n"
        )
        
        # Dodaj kontekst systemu
        if context:
            prompt += f"Kontekst systemu:\n{json.dumps(context, indent=2, ensure_ascii=False)}\n\n"
        
        # Dodaj dane anomalii
        prompt += json.dumps(anomalies, indent=2, ensure_ascii=False)
        
        response = await self.analyze_logs(prompt, False)
        return response

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