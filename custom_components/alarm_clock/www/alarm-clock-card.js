// Dashboard card for the Alarm Clock integration.
//
// Reads everything from one entity - the "next alarm" sensor of a single
// virtual alarm clock device (sensor.<device>_next_trigger) - since that's
// the only place the full schedule is exposed (its `alarms` attribute).
// There's no per-alarm entity to bind to (see README's Phase 5 section),
// so every mutation here goes through the alarm_clock.* services instead
// of entity state writes.
//
// Deliberately vanilla (no build step, no framework) - this repo ships it
// as a static file served straight from custom_components/alarm_clock/www/.

const WEEKDAY_ORDER = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];

const I18N = {
  de: {
    recurring: "Wiederkehrend",
    onetime: "Einmalig",
    add: "Hinzufügen",
    noAlarms: "Keine Weckzeiten gestellt.",
    weekdayShort: { mon: "Mo", tue: "Di", wed: "Mi", thu: "Do", fri: "Fr", sat: "Sa", sun: "So" },
    weekdayLong: {
      mon: "Montag", tue: "Dienstag", wed: "Mittwoch", thu: "Donnerstag",
      fri: "Freitag", sat: "Samstag", sun: "Sonntag",
    },
    months: ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"],
    selectWeekday: "Bitte mindestens einen Wochentag auswählen.",
    fillTime: "Bitte eine Uhrzeit angeben.",
    fillDate: "Bitte ein Datum angeben.",
    entityNotFound: "Wecker-Entität nicht gefunden.",
    noEntity: "Bitte in den Karteneinstellungen einen Wecker auswählen.",
    error: "Fehler",
    delete: "Löschen",
    addAlarm: "Wecker hinzufügen",
    close: "Schließen",
    stop: "Beenden",
    snooze: "Schlummern",
  },
  en: {
    recurring: "Recurring",
    onetime: "One-time",
    add: "Add",
    noAlarms: "No alarms set.",
    weekdayShort: { mon: "Mo", tue: "Tu", wed: "We", thu: "Th", fri: "Fr", sat: "Sa", sun: "Su" },
    weekdayLong: {
      mon: "Monday", tue: "Tuesday", wed: "Wednesday", thu: "Thursday",
      fri: "Friday", sat: "Saturday", sun: "Sunday",
    },
    months: ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
    selectWeekday: "Please select at least one weekday.",
    fillTime: "Please enter a time.",
    fillDate: "Please enter a date.",
    entityNotFound: "Alarm clock entity not found.",
    noEntity: "Please select an alarm clock in the card settings.",
    error: "Error",
    delete: "Delete",
    addAlarm: "Add alarm",
    close: "Close",
    stop: "Stop",
    snooze: "Snooze",
  },
};

function textsFor(hass) {
  return (hass && hass.language || "de").startsWith("en") ? I18N.en : I18N.de;
}

function formatAlarmLabel(alarm, t) {
  if (alarm.kind === "recurring") {
    return `${t.weekdayLong[alarm.weekday] || alarm.weekday} – ${alarm.time}`;
  }
  const [year, month, day] = (alarm.date || "").split("-").map((part) => parseInt(part, 10));
  const monthName = t.months[(month || 1) - 1] || month;
  return `${day}. ${monthName} ${year} – ${alarm.time}`;
}

function deviceNameFromFriendly(friendlyName) {
  // Strips the translated entity name ("Nächster Alarm" / "Next alarm") that
  // has_entity_name appends after the device name - covers both languages
  // regardless of which one is currently active, since this repo only ships
  // German + English translations (others fall back to the English string).
  return (friendlyName || "").replace(/\s*(Nächster Alarm|Next alarm)\s*$/i, "").trim();
}

function nextOccurrenceFor(alarm, now) {
  const [hour, minute] = alarm.time.split(":").map(Number);
  if (alarm.kind === "recurring") {
    const targetIdx = WEEKDAY_ORDER.indexOf(alarm.weekday);
    const mondayIndexedToday = (now.getDay() + 6) % 7; // JS Sunday=0 -> Monday=0..Sunday=6
    const daysAhead = (targetIdx - mondayIndexedToday + 7) % 7;
    const candidate = new Date(now.getFullYear(), now.getMonth(), now.getDate() + daysAhead, hour, minute, 0, 0);
    if (candidate <= now) candidate.setDate(candidate.getDate() + 7);
    return candidate;
  }
  const [year, month, day] = (alarm.date || "").split("-").map(Number);
  return new Date(year, (month || 1) - 1, day || 1, hour, minute, 0, 0);
}

function sortAlarms(alarms) {
  const now = new Date();
  return [...alarms]
    .map((alarm) => ({ alarm, next: nextOccurrenceFor(alarm, now) }))
    .sort((a, b) => a.next - b.next)
    .map((entry) => entry.alarm);
}

const CARD_STYLE = `
  :host { display: block; }
  ha-card { padding: 16px; }
  .card-header-row {
    display: flex; align-items: center; justify-content: space-between;
    margin-bottom: 12px;
  }
  .device-name {
    font-size: 1.2em; font-weight: 500;
    color: var(--ha-card-header-color, var(--primary-text-color));
  }
  .ringing-actions { display: flex; gap: 8px; margin-bottom: 12px; }
  .ringing-actions button {
    flex: 1; padding: 10px; border-radius: 8px; border: none;
    font: inherit; cursor: pointer;
  }
  .ringing-actions .stop-btn { background: var(--error-color, #db4437); color: #fff; }
  .ringing-actions .snooze-btn {
    background: var(--primary-color); color: var(--text-primary-color, #fff);
  }
  .alarm-list { display: flex; flex-direction: column; gap: 4px; margin-bottom: 16px; }
  .alarm-row {
    display: flex; align-items: center; gap: 8px;
    padding: 6px 8px; border-radius: 8px;
    background: var(--secondary-background-color);
  }
  .alarm-row ha-icon { color: var(--secondary-text-color); flex-shrink: 0; }
  .alarm-row .alarm-label { flex: 1; color: var(--primary-text-color); }
  .alarm-row button.delete-btn {
    background: none; border: none; cursor: pointer; padding: 4px;
    color: var(--secondary-text-color); display: flex; align-items: center;
  }
  .alarm-row button.delete-btn:hover { color: var(--error-color, #db4437); }
  .no-alarms { color: var(--secondary-text-color); font-style: italic; margin-bottom: 16px; }
  .open-add-btn {
    background: none; border: none; cursor: pointer; padding: 6px;
    border-radius: 50%; color: var(--primary-color); flex-shrink: 0;
    display: flex; align-items: center; justify-content: center;
  }
  .open-add-btn:hover { background: var(--secondary-background-color); }
  .modal-overlay {
    position: fixed; inset: 0; background: rgba(0, 0, 0, 0.5);
    display: flex; align-items: center; justify-content: center;
    z-index: 10; padding: 16px; box-sizing: border-box;
  }
  .modal-content {
    background: var(--card-background-color, white); color: var(--primary-text-color);
    border-radius: 12px; padding: 16px; width: 100%; max-width: 340px;
    box-shadow: var(--dialog-box-shadow, 0 4px 24px rgba(0, 0, 0, 0.3));
  }
  .modal-header {
    display: flex; align-items: center; justify-content: space-between;
    margin-bottom: 12px; font-size: 1.1em;
  }
  .modal-header button {
    background: none; border: none; cursor: pointer; padding: 4px;
    color: var(--secondary-text-color); display: flex; align-items: center;
  }
  .mode-toggle { display: flex; gap: 8px; margin-bottom: 10px; }
  .mode-toggle button {
    flex: 1; padding: 6px; border-radius: 8px; border: 1px solid var(--divider-color);
    background: var(--card-background-color); color: var(--primary-text-color);
    cursor: pointer; font: inherit;
  }
  .mode-toggle button.active {
    background: var(--primary-color); color: var(--text-primary-color, #fff);
    border-color: var(--primary-color);
  }
  .weekday-chips { display: flex; gap: 4px; margin-bottom: 10px; flex-wrap: wrap; }
  .weekday-chips button {
    width: 36px; height: 36px; border-radius: 50%; border: 1px solid var(--divider-color);
    background: var(--card-background-color); color: var(--primary-text-color);
    cursor: pointer; font: inherit;
  }
  .weekday-chips button.selected {
    background: var(--primary-color); color: var(--text-primary-color, #fff);
    border-color: var(--primary-color);
  }
  .form-row { display: flex; gap: 8px; margin-bottom: 10px; align-items: center; }
  .form-row input {
    flex: 1; padding: 6px 8px; border-radius: 8px; border: 1px solid var(--divider-color);
    background: var(--card-background-color); color: var(--primary-text-color); font: inherit;
  }
  .add-btn {
    width: 100%; padding: 8px; border-radius: 8px; border: none;
    background: var(--primary-color); color: var(--text-primary-color, #fff);
    cursor: pointer; font: inherit;
  }
  .card-error-message, .modal-error-message {
    color: var(--error-color, #db4437); margin-top: 8px; font-size: 0.9em;
  }
  [hidden] { display: none !important; }
`;

class AlarmClockCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._built = false;
    this._selectedDays = new Set();
    this._lastAlarmsJson = null;
  }

  setConfig(config) {
    if (!config || !config.entity) {
      throw new Error("Please select an alarm clock (next alarm sensor) in the card settings.");
    }
    this._config = config;
    if (this._hass) this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() {
    return 4;
  }

  static getConfigElement() {
    return document.createElement("alarm-clock-card-editor");
  }

  static getStubConfig(hass) {
    const entities = hass ? Object.keys(hass.states) : [];
    const match = entities.find((id) => id.startsWith("sensor.") && id.endsWith("_next_trigger"));
    return { entity: match || "" };
  }

  _render() {
    if (!this._hass || !this._config) return;
    const t = textsFor(this._hass);

    if (!this._config.entity) {
      this._renderMessage(t.noEntity);
      return;
    }

    const stateObj = this._hass.states[this._config.entity];
    if (!stateObj) {
      this._renderMessage(`${t.entityNotFound} (${this._config.entity})`);
      return;
    }

    if (!this._built) {
      this._buildStaticStructure(t);
    }
    this._updateDynamic(stateObj, t);
  }

  _renderMessage(message) {
    this._built = false;
    this.shadowRoot.innerHTML = `
      <style>${CARD_STYLE}</style>
      <ha-card><div style="padding: 16px; color: var(--secondary-text-color);">${message}</div></ha-card>
    `;
  }

  _buildStaticStructure(t) {
    this.shadowRoot.innerHTML = `
      <style>${CARD_STYLE}</style>
      <ha-card>
        <div class="card-content">
          <div class="card-header-row">
            <span class="device-name"></span>
            <button type="button" class="open-add-btn" aria-label="${t.addAlarm}" title="${t.addAlarm}">
              <ha-icon icon="mdi:plus"></ha-icon>
            </button>
          </div>
          <div class="ringing-actions" hidden>
            <button type="button" class="stop-btn">${t.stop}</button>
            <button type="button" class="snooze-btn">${t.snooze}</button>
          </div>
          <div class="alarm-list"></div>
          <div class="no-alarms" hidden>${t.noAlarms}</div>
          <div class="card-error-message" hidden></div>
        </div>
      </ha-card>
      <div class="modal-overlay" hidden>
        <div class="modal-content">
          <div class="modal-header">
            <span>${t.addAlarm}</span>
            <button type="button" class="modal-close" aria-label="${t.close}" title="${t.close}">
              <ha-icon icon="mdi:close"></ha-icon>
            </button>
          </div>
          <div class="mode-toggle">
            <button type="button" class="mode-btn active" data-mode="recurring">${t.recurring}</button>
            <button type="button" class="mode-btn" data-mode="onetime">${t.onetime}</button>
          </div>
          <div class="recurring-form">
            <div class="weekday-chips">
              ${WEEKDAY_ORDER.map((day) => `<button type="button" data-day="${day}">${t.weekdayShort[day]}</button>`).join("")}
            </div>
            <div class="form-row">
              <input type="time" class="recurring-time" />
            </div>
            <button type="button" class="add-btn recurring-add">${t.add}</button>
          </div>
          <div class="onetime-form" hidden>
            <div class="form-row">
              <input type="date" class="onetime-date" />
              <input type="time" class="onetime-time" />
            </div>
            <button type="button" class="add-btn onetime-add">${t.add}</button>
          </div>
          <div class="modal-error-message" hidden></div>
        </div>
      </div>
    `;

    const root = this.shadowRoot;
    const recurringForm = root.querySelector(".recurring-form");
    const onetimeForm = root.querySelector(".onetime-form");
    const modalOverlay = root.querySelector(".modal-overlay");

    root.querySelector(".open-add-btn").addEventListener("click", () => this._openModal());
    root.querySelector(".modal-close").addEventListener("click", () => this._closeModal());
    modalOverlay.addEventListener("click", (ev) => {
      if (ev.target === modalOverlay) this._closeModal();
    });

    root.querySelectorAll(".mode-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        root.querySelectorAll(".mode-btn").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        const isRecurring = btn.dataset.mode === "recurring";
        recurringForm.hidden = !isRecurring;
        onetimeForm.hidden = isRecurring;
        this._clearError("modal");
      });
    });

    root.querySelectorAll(".weekday-chips button").forEach((chip) => {
      chip.addEventListener("click", () => {
        const day = chip.dataset.day;
        if (this._selectedDays.has(day)) {
          this._selectedDays.delete(day);
          chip.classList.remove("selected");
        } else {
          this._selectedDays.add(day);
          chip.classList.add("selected");
        }
      });
    });

    root.querySelector(".recurring-add").addEventListener("click", () => this._addRecurring());
    root.querySelector(".onetime-add").addEventListener("click", () => this._addOnetime());
    root.querySelector(".alarm-list").addEventListener("click", (ev) => {
      const btn = ev.target.closest(".delete-btn");
      if (btn) this._deleteAlarm(parseInt(btn.dataset.id, 10));
    });
    root.querySelector(".stop-btn").addEventListener("click", () => {
      this._callService("stop", {}, "card").catch(() => {});
    });
    root.querySelector(".snooze-btn").addEventListener("click", () => {
      this._callService("snooze", {}, "card").catch(() => {});
    });

    this._built = true;
  }

  _siblingEntityId(domain, suffix) {
    // Deterministic - entity.py always names entities
    // "<domain>.<slugified device name>_<key>", and this._config.entity is
    // always the "..._next_trigger" sensor, so stripping/replacing that
    // suffix gives every other entity of the same device without needing
    // the frontend's device/entity registry helpers.
    const deviceSlug = (this._config.entity || "").replace(/^sensor\./, "").replace(/_next_trigger$/, "");
    return `${domain}.${deviceSlug}_${suffix}`;
  }

  _updateDynamic(stateObj, t) {
    const root = this.shadowRoot;

    root.querySelector(".device-name").textContent = deviceNameFromFriendly(stateObj.attributes.friendly_name);

    const ringingState = this._hass.states[this._siblingEntityId("binary_sensor", "ringing")];
    root.querySelector(".ringing-actions").hidden = !(ringingState && ringingState.state === "on");

    const alarms = stateObj.attributes.alarms || [];
    const alarmsJson = JSON.stringify(alarms);
    if (alarmsJson === this._lastAlarmsJson) return;
    this._lastAlarmsJson = alarmsJson;

    const listEl = root.querySelector(".alarm-list");
    const noAlarmsEl = root.querySelector(".no-alarms");
    if (alarms.length === 0) {
      listEl.innerHTML = "";
      noAlarmsEl.hidden = false;
      return;
    }
    noAlarmsEl.hidden = true;
    listEl.innerHTML = sortAlarms(alarms)
      .map((alarm) => `
        <div class="alarm-row">
          <ha-icon icon="${alarm.kind === "recurring" ? "mdi:calendar-sync" : "mdi:calendar-clock"}"></ha-icon>
          <span class="alarm-label">${formatAlarmLabel(alarm, t)}</span>
          <button type="button" class="delete-btn" data-id="${alarm.id}" title="${t.delete}" aria-label="${t.delete}">
            <ha-icon icon="mdi:delete-outline"></ha-icon>
          </button>
        </div>
      `)
      .join("");
  }

  _openModal() {
    this._clearError("modal");
    const modalOverlay = this.shadowRoot.querySelector(".modal-overlay");
    modalOverlay.hidden = false;
    this._escapeHandler = (ev) => {
      if (ev.key === "Escape") this._closeModal();
    };
    document.addEventListener("keydown", this._escapeHandler);
    const firstField = modalOverlay.querySelector(".weekday-chips button");
    if (firstField) firstField.focus();
  }

  _closeModal() {
    const modalOverlay = this.shadowRoot.querySelector(".modal-overlay");
    modalOverlay.hidden = true;
    if (this._escapeHandler) {
      document.removeEventListener("keydown", this._escapeHandler);
      this._escapeHandler = null;
    }
  }

  disconnectedCallback() {
    if (this._escapeHandler) {
      document.removeEventListener("keydown", this._escapeHandler);
      this._escapeHandler = null;
    }
  }

  _errorElement(scope) {
    return this.shadowRoot.querySelector(scope === "modal" ? ".modal-error-message" : ".card-error-message");
  }

  _clearError(scope = "card") {
    const el = this._errorElement(scope);
    el.hidden = true;
    el.textContent = "";
  }

  _showError(message, scope = "card") {
    const el = this._errorElement(scope);
    el.hidden = false;
    el.textContent = message;
  }

  async _callService(service, data, scope = "card") {
    this._clearError(scope);
    const t = textsFor(this._hass);
    try {
      await this._hass.callService("alarm_clock", service, {
        entity_id: this._config.entity,
        ...data,
      });
    } catch (err) {
      this._showError(`${t.error}: ${(err && err.message) || err}`, scope);
      throw err;
    }
  }

  async _addRecurring() {
    const t = textsFor(this._hass);
    if (this._selectedDays.size === 0) {
      this._showError(t.selectWeekday, "modal");
      return;
    }
    const timeInput = this.shadowRoot.querySelector(".recurring-time");
    if (!timeInput.value) {
      this._showError(t.fillTime, "modal");
      return;
    }
    try {
      await this._callService(
        "set_recurring",
        { weekday: Array.from(this._selectedDays), time: timeInput.value },
        "modal"
      );
    } catch {
      return;
    }
    this._selectedDays.clear();
    this.shadowRoot.querySelectorAll(".weekday-chips button.selected").forEach((b) => b.classList.remove("selected"));
    timeInput.value = "";
    this._closeModal();
  }

  async _addOnetime() {
    const t = textsFor(this._hass);
    const dateInput = this.shadowRoot.querySelector(".onetime-date");
    const timeInput = this.shadowRoot.querySelector(".onetime-time");
    if (!dateInput.value) {
      this._showError(t.fillDate, "modal");
      return;
    }
    if (!timeInput.value) {
      this._showError(t.fillTime, "modal");
      return;
    }
    try {
      await this._callService("set_onetime", { date: dateInput.value, time: timeInput.value }, "modal");
    } catch {
      return;
    }
    dateInput.value = "";
    timeInput.value = "";
    this._closeModal();
  }

  async _deleteAlarm(alarmId) {
    try {
      await this._callService("delete_alarm", { alarm_id: alarmId });
    } catch {
      // error already shown by _callService
    }
  }
}

class AlarmClockCardEditor extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {};
  }

  setConfig(config) {
    this._config = config || {};
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  _render() {
    if (!this._hass || !this._config) return;
    if (!this._picker) {
      this.shadowRoot.innerHTML = `<div style="padding: 4px 0;"></div>`;
      this._picker = document.createElement("ha-entity-picker");
      this._picker.includeDomains = ["sensor"];
      this._picker.entityFilter = (stateObj) => stateObj.entity_id.endsWith("_next_trigger");
      this._picker.addEventListener("value-changed", (ev) => {
        ev.stopPropagation();
        this._config = { ...this._config, entity: ev.detail.value };
        this.dispatchEvent(
          new CustomEvent("config-changed", { detail: { config: this._config }, bubbles: true, composed: true })
        );
      });
      this.shadowRoot.firstElementChild.appendChild(this._picker);
    }
    this._picker.hass = this._hass;
    this._picker.label = textsFor(this._hass) === I18N.en ? "Alarm clock" : "Wecker";
    this._picker.value = this._config.entity || "";
  }
}

customElements.define("alarm-clock-card", AlarmClockCard);
customElements.define("alarm-clock-card-editor", AlarmClockCardEditor);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "alarm-clock-card",
  name: "Alarm Clock",
  description: "Shows and manages the schedule of one virtual alarm clock (Alarm Clock integration).",
  preview: false,
});
