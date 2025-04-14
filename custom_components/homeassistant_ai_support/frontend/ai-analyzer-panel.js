class AIAnalyzerPanel extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: 'open' });
      this._hass = null;
      this._history = [];
    }
  
    set hass(hass) {
      this._hass = hass;
      this._getHistory();
      this._render();
    }
  
    _getHistory() {
      if (!this._hass) return;
      
      this._hass.callWS({
        type: 'homeassistant_ai_support/get_history',
      }).then(result => {
        this._history = result.history || [];
        this._render();
      }).catch(err => {
        console.error('Error fetching AI analyzer history:', err);
      });
    }
  
    async _runAnalysis() {
      try {
        await this._hass.callService('homeassistant_ai_support', 'analyze_now');
        setTimeout(() => this._getHistory(), 1000);
      } catch (err) {
        console.error('Error running analysis:', err);
      }
    }
  
    _render() {
      if (!this._hass) return;
  
      // Tworzenie styli CSS
      const style = document.createElement('style');
      style.textContent = `
        :host {
          display: block;
          padding: 16px;
          font-family: var(--paper-font-body1_-_font-family);
        }
        .header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 16px;
        }
        .card {
          background-color: var(--card-background-color);
          border-radius: 8px;
          box-shadow: var(--ha-card-box-shadow, 0 2px 2px 0 rgba(0, 0, 0, 0.14), 0 1px 5px 0 rgba(0, 0, 0, 0.12), 0 3px 1px -2px rgba(0, 0, 0, 0.2));
          padding: 16px;
          margin-bottom: 16px;
        }
        .card-header {
          display: flex;
          justify-content: space-between;
          color: var(--primary-text-color);
          font-weight: 500;
          font-size: 16px;
          margin-bottom: 8px;
        }
        .timestamp {
          color: var(--secondary-text-color);
          font-size: 14px;
        }
        .report {
          white-space: pre-wrap;
          color: var(--primary-text-color);
          margin-top: 8px;
        }
        .logs {
          font-family: monospace;
          white-space: pre-wrap;
          background-color: var(--code-background-color, #f0f0f0);
          padding: 8px;
          border-radius: 4px;
          margin-top: 8px;
          max-height: 200px;
          overflow-y: auto;
          font-size: 12px;
        }
        .no-items {
          text-align: center;
          color: var(--secondary-text-color);
          margin: 32px 0;
          font-style: italic;
        }
        mwc-button {
          --mdc-theme-primary: var(--primary-color);
        }
        .collapsible {
          cursor: pointer;
          user-select: none;
        }
      `;
  
      // Stworzenie głównego kontenera
      const content = document.createElement('div');
      
      // Nagłówek
      const header = document.createElement('div');
      header.className = 'header';
      
      const title = document.createElement('h2');
      title.textContent = 'Analiza logów AI';
      header.appendChild(title);
      
      const runButton = document.createElement('mwc-button');
      runButton.setAttribute('raised', '');
      runButton.textContent = 'Uruchom analizę';
      runButton.addEventListener('click', () => this._runAnalysis());
      header.appendChild(runButton);
      
      content.appendChild(header);
      
      // Lista analiz
      if (this._history && this._history.length > 0) {
        this._history.forEach(item => {
          const card = document.createElement('div');
          card.className = 'card';
          
          const cardHeader = document.createElement('div');
          cardHeader.className = 'card-header';
          
          const idSpan = document.createElement('span');
          idSpan.textContent = `Analiza #${item.id}`;
          cardHeader.appendChild(idSpan);
          
          const timestamp = document.createElement('span');
          timestamp.className = 'timestamp';
          const date = new Date(item.timestamp);
          timestamp.textContent = date.toLocaleString();
          cardHeader.appendChild(timestamp);
          
          card.appendChild(cardHeader);
          
          const report = document.createElement('div');
          report.className = 'report';
          report.textContent = item.report || 'Brak danych analizy';
          card.appendChild(report);
          
          // Logs preview (collapsible)
          const logsHeader = document.createElement('div');
          logsHeader.className = 'collapsible';
          logsHeader.textContent = '🔍 Pokaż fragment logów';
          logsHeader.onclick = function() {
            const logs = this.nextElementSibling;
            if (logs.style.display === 'none' || !logs.style.display) {
              logs.style.display = 'block';
              this.textContent = '🔍 Ukryj fragment logów';
            } else {
              logs.style.display = 'none';
              this.textContent = '🔍 Pokaż fragment logów';
            }
          };
          card.appendChild(logsHeader);
          
          const logs = document.createElement('div');
          logs.className = 'logs';
          logs.style.display = 'none';
          logs.textContent = item.logs_preview || 'Brak podglądu logów';
          card.appendChild(logs);
          
          content.appendChild(card);
        });
      } else {
        const noItems = document.createElement('div');
        noItems.className = 'no-items';
        noItems.textContent = 'Brak historii analiz. Uruchom analizę, aby zobaczyć wyniki.';
        content.appendChild(noItems);
      }
  
      // Aktualizacja DOM
      const shadow = this.shadowRoot;
      shadow.innerHTML = '';
      shadow.appendChild(style);
      shadow.appendChild(content);
    }
  }
  
  customElements.define('ai-analyzer-panel', AIAnalyzerPanel);
  