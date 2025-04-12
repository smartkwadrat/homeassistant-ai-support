import logging
_LOGGER = logging.getLogger(__name__)

# Przykład użycia w kodzie:
_LOGGER.debug("Rozpoczęto zbieranie logów systemowych")
_LOGGER.error("Błąd autoryzacji API OpenAI", exc_info=True)