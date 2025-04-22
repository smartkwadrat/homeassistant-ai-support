# homeassistant-ai-support

This is custom integration to home assistant which use ChatGPT for analyzing logs and system behaviour

To enable logging for this integration, add following lines to configuration.yaml:

```yaml
logger:
  default: info
  logs:
    custom_components.homeassistant_ai_support: debug
    openai: debug

Version 0.5.3