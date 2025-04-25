# homeassistant-ai-support

This is custom integration to home assistant which use ChatGPT for analyzing logs and system behaviour
 
Version 0.7.0


Dashboard card for displaying the newest report:

```yaml
type: markdown
title: Ostatni raport AI
content: |-
  sensor.ai_support_status_analizy_logow

  type: markdown
  title: Ostatni raport AI
  content: |
    **Data:** {{ state_attr('sensor.ai_support_status_analizy_logow', 'timestamp') }}

    **Raport:** {{ state_attr('sensor.ai_support_status_analizy_logow', 'report') }}

  ```


(Optional) To enable logging for this integration, add following lines to configuration.yaml:

```yaml
logger:
  default: info
  logs:
    custom_components.homeassistant_ai_support: debug
    openai: debug
```