# Home Assistant AI Support

**Version 0.9.7**

This custom integration for Home Assistant leverages AI models, such as OpenAI's ChatGPT, to analyze system logs, detect anomalies in entity behavior, and provide actionable insights. It automates log analysis, suggests potential issues, and helps maintain a smart home environment by identifying unusual patterns in your devices and sensors.

## Features

- **AI-Powered Log Analysis**: Automatically analyzes Home Assistant logs using OpenAI's API to identify potential issues and suggest solutions.
- **Anomaly Detection**: Monitors selected entities for unusual behavior based on historical data, with customizable sensitivity and priority levels.
- **Entity Discovery**: Uses AI to identify key entities for monitoring, categorizing them into standard and priority groups.
- **Baseline Building**: Creates behavioral models for entities to detect deviations over time.
- **Customizable Scheduling**: Configurable intervals for log analysis, anomaly checks, and baseline updates.
- **User-Friendly Dashboard**: Sensors and buttons to interact with the integration directly from the Home Assistant UI.
- **Multilingual Support**: Available in English and Polish with translated UI elements and reports.

## Prerequisites

- **Home Assistant**: Version 2023.5 or later.
- **OpenAI API Key**: Required for AI log analysis and entity discovery. Generate your key at the OpenAI portal and ensure billing is enabled.

## Installation

### Via HACS (NOT IMPLEMENTED YET)

1. Install HACS (Home Assistant Community Store) if you haven't already.
2. In HACS, go to **Integrations** and click the `+` button.
3. Search for `Home Assistant AI Support`.
4. Select the integration and click **Download**.
5. Restart Home Assistant.
6. Go to **Settings** → **Devices & Services** → **+ Add Integration** and search for `Home Assistant AI Support`.

### Manual Installation (Recommended)

1. Download the contents of this repository.
2. Copy the `custom_components/homeassistant_ai_support` folder to your Home Assistant's `custom_components` directory:
```yaml
<homeassistant_config_dir>/
└── custom_components/
└── homeassistant_ai_support/
├── init.py
└── ... (other files)
```
3. Restart Home Assistant.
4. Go to **Settings** → **Devices & Services** → **+ Add Integration** and search for `Home Assistant AI Support`.

## Configuration

1. Add the integration via the Home Assistant UI: **Settings** → **Devices & Services** → **+ Add Integration** → `Home Assistant AI Support`.
2. Follow the setup wizard:
- **API Key**: Enter your OpenAI API key.
- **Model**: Select the AI model (e.g., GPT-4.1 mini).
- **System Prompt**: Customize the AI prompt for log analysis (optional).
- **Scan Interval**: Set the frequency for log analysis (daily, every 2 days, weekly, monthly).
- **Additional Options**: Configure anomaly detection intervals, sensitivity, learning mode, and more.
3. Adjust settings later via **Integration Options** in **Settings** → **Devices & Services**.

## Usage

### Dashboard Cards for Reports

**Displaying the Latest Report (English):**
```yaml
type: markdown
title: Latest AI Report
content: |
Date: {{ state_attr('sensor.ai_support_status_analizy_logow', 'timestamp') }}
{{ state_attr('sensor.ai_support_status_analizy_logow', 'report') }}
```

**Displaying the Latest Report (Polish):**
```yaml
type: markdown
title: Ostatni raport AI
content: |
Data: {{ state_attr('sensor.ai_support_status_analizy_logow', 'timestamp') }}
{{ state_attr('sensor.ai_support_status_analizy_logow', 'report') }}
```

**Selecting and Displaying a Specific Report (English):**
```yaml
type: entities
entities:

entity: input_select.ai_support_report_file
title: Select Report
```

```yaml
type: markdown
title: Selected AI Report
content: |
Date: {{ state_attr('sensor.ai_support_selected_report', 'timestamp') }}
{{ state_attr('sensor.ai_support_selected_report', 'report') }}
```

**Selecting and Displaying a Specific Report (Polish):**
```yaml
type: entities
entities:

entity: input_select.ai_support_report_file
title: Wybierz raport
```

```yaml
type: markdown
title: Wybrany raport AI
content: |
Data: {{ state_attr('sensor.ai_support_wybrany_raport', 'timestamp') }}
{{ state_attr('sensor.ai_support_wybrany_raport', 'report') }}
```

### Buttons and Sensors

- **Generate Report Button**: Triggers immediate log analysis and report generation.
- **Discover Entities Button**: Uses AI to identify key entities for anomaly monitoring.
- **Build Baseline Button**: Builds or updates behavioral models for monitored entities.
- **Sensors**: Display status of log analysis, anomaly detection, entity discovery, and baseline building.

### Services

- **Analyze Now**: Trigger immediate log analysis via the service `homeassistant_ai_support.analyze_now`.
- **Report False Alarm**: Mark an anomaly as a false positive with `homeassistant_ai_support.report_false_alarm`.
- **Toggle Monitoring**: Enable or disable anomaly monitoring with `homeassistant_ai_support.toggle_monitoring`.

### Logging (Optional)

To enable detailed logging for debugging, add the following to your `configuration.yaml`:
```yaml
logger:
default: info
logs:
custom_components.homeassistant_ai_support: debug
openai: debug
```

## Anomaly Detection

This integration monitors entities for anomalies based on historical data:
- **Numeric Entities**: Detects values outside expected ranges using statistical models.
- **Binary Entities**: Flags unexpected state changes based on historical flip rates.
- **Categorical Entities**: Identifies rare or new states in entity behavior.

Configure sensitivity, check intervals, and priority levels in the integration options to fine-tune detection.

## Troubleshooting

- **API Key Issues**: Ensure your OpenAI API key is valid and billing is enabled. Check logs for authentication errors.
- **No Reports Generated**: Verify that log files exist and contain relevant data. Adjust log level filters in options if needed.
- **Anomaly Detection Not Working**: Ensure a baseline model is built by pressing the "Build Baseline" button. Check if entities are selected for monitoring.

## Support and Contributions

- **Documentation**: Full details and updates at [GitHub Repository](https://github.com/smartkwadrat/homeassistant-ai-support).
- **Issues**: Report bugs or request features at [Issue Tracker](https://github.com/smartkwadrat/homeassistant-ai-support/issues).
- **Contributions**: Pull requests are welcome! Fork the repository and submit your changes.

## License

This integration is released under the MIT License.