# homeassistant-ai-support

This is custom integration to home assistant which use ChatGPT for analyzing logs and system behaviour
 
Version 0.9.0


Dashboard card for displaying the newest report (English) :

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

Karta do wyświetlania najnowszego raportu (Polski) :

```yaml
type: markdown
title: Ostatni raport AI
content: |-
  sensor.ai_support_status_analizy_logow

  type: markdown
  title: Latest AI report
  content: |
    **Data:** {{ state_attr('sensor.ai_support_status_analizy_logow', 'timestamp') }}

    {{ state_attr('sensor.ai_support_status_analizy_logow', 'report') }}
  ```


Dashboard cards for displaying selected report (English):

```yaml
type: entities
entities:
  - entity: input_select.ai_support_report_file
title: Select report
  ```

```yaml
type: markdown
title: Selected AI Report
content: |-
  **Data:** {{ state_attr('sensor.ai_support_selected_report', 'timestamp') }}

  {{ state_attr('sensor.ai_support_selected_report', 'report') }}
  ```

Karty do wyświetlania dowolnego raportu (Polski):

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
  **Data:** {{ state_attr('sensor.ai_support_wybrany_raport', 'timestamp') }}

  {{ state_attr('sensor.ai_support_wybrany_raport', 'report') }}
  ```

(Optional) To enable logging for this integration, add following lines to configuration.yaml:

```yaml
logger:
  default: info
  logs:
    custom_components.homeassistant_ai_support: debug
    openai: debug
```