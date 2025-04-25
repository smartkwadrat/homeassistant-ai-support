"""OpenAI API handler for Home Assistant AI Support integration."""

from __future__ import annotations

import logging
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
        self.api_key = api_key
        self.model = model
        self.system_prompt = system_prompt
        self.max_tokens = max_tokens
        self.client: AsyncOpenAI | None = None

    async def async_init(self):
        """Initialize OpenAI client."""
        self.client = AsyncOpenAI(
            api_key=self.api_key,
            max_retries=2,
            timeout=30.0
        )

    async def analyze_logs(self, logs: str, cost_optimization: bool) -> str:
        """Analyze logs using OpenAI API."""
        if not self.client:
            await self.async_init()

        if not logs.strip():
            return "No logs to analyze"

        if cost_optimization:
            logs = self._optimize_logs(logs)

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": logs[-30000:] or "No logs to analyze"}
                ],
                max_tokens=self.max_tokens
            )
            return response.choices[0].message.content
        except APIError as err:
            _LOGGER.error("OpenAI API error: %s", err)
            return f"API Error: {err}"
        
        except AuthenticationError as err:
            _LOGGER.error("Authentication error: %s", err)
            return "invalid_api_key_auth" 
        
        except ConnectionError as err:
            return "connection_error"

    def _optimize_logs(self, logs: str) -> str:
        """Optimize logs for cost reduction."""
        if not logs:
            return ""
        return '\n'.join([
            line for line in logs.split('\n')
            if any(keyword in line for keyword in ['ERROR', 'WARNING'])
        ][-1000:])

    async def close(self):
        """Clean up resources."""
        if self.client:
            await self.client.close()
