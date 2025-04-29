# homeassistant-ai-support

This is custom integration to home assistant which use ChatGPT for analyzing logs and system behaviour
 
Version 0.7.8


Dashboard card for displaying the newest report:

```yaml
type: markdown
title: Latest AI report
content: |-
  sensor.ai_support_status_analizy_logow

  type: markdown
  title: Latest AI report
  content: |
    **Data:** {{ state_attr('sensor.ai_support_status_analizy_logow', 'timestamp') }}

    {{ state_attr('sensor.ai_support_status_analizy_logow', 'report') }}

  ```


Dashboard cards for displaying selected report:

```yaml
type: entities
entities:
  - entity: input_select.ai_support_report_file
title: Select report
  ```

```yaml
type: markdown
title: Wybrany raport AI
content: |-
  **Data:** {{ state_attr('sensor.wybrany_raport_ai', 'timestamp') }}

  {{ state_attr('sensor.wybrany_raport_ai', 'report') }}
  ```


(Optional) To enable logging for this integration, add following lines to configuration.yaml:

```yaml
logger:
  default: info
  logs:
    custom_components.homeassistant_ai_support: debug
    openai: debug
```