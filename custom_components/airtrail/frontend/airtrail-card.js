/**
 * AirTrail card for Home Assistant, styled after Mushroom.
 *
 * Finds the entities of an AirTrail device through the entity registry, so the
 * minimal configuration is just `type: custom:airtrail-card`.
 */

const DOMAIN = "airtrail";
const DEFAULT_COLOR = "#3c83f6";

const STATS = {
  upcoming_flights: { short: "upcoming", label: "Upcoming flights", icon: "mdi:airplane-clock" },
  past_flights: { short: "past", label: "Past flights", icon: "mdi:history" },
  total_flights: { short: "flights", label: "Total flights", icon: "mdi:airplane" },
  total_distance: { label: "Total distance", icon: "mdi:map-marker-distance" },
  total_flight_time: { label: "Total flight time", icon: "mdi:timer-outline" },
  airports_visited: { short: "airports", label: "Airports visited", icon: "mdi:airport" },
  top_airline: { label: "Top airline", icon: "mdi:airplane-marker" },
  top_airport: { label: "Top airport", icon: "mdi:airport" },
  top_aircraft: { label: "Top aircraft", icon: "mdi:airplane-cog" },
  top_route: { label: "Top route", icon: "mdi:routes" },
};

const DEFAULT_CONFIG = {
  show_header: true,
  stats: ["upcoming_flights", "total_flights", "total_distance", "total_flight_time"],
  list: "upcoming",
  max_flights: 5,
};

const escape = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c],
  );

/** Resolve a UI colour name (e.g. "blue") or any CSS colour. */
const resolveColor = (color) => {
  if (!color) return DEFAULT_COLOR;
  if (/^[a-z-]+$/.test(color)) return `var(--${color}-color, ${DEFAULT_COLOR})`;
  return color;
};

/** Parse "YYYY-MM-DD HH:MM" (airport local time) without shifting timezones. */
const parseLocal = (value) => {
  const match = /^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}))?/.exec(value || "");
  if (!match) return null;
  const [, y, m, d, hh = "0", mm = "0"] = match;
  return new Date(Date.UTC(+y, +m - 1, +d, +hh, +mm));
};

class AirTrailCard extends HTMLElement {
  static getConfigElement() {
    return document.createElement("airtrail-card-editor");
  }

  static getStubConfig() {
    return {};
  }

  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._signature = null;
  }

  setConfig(config) {
    if (config.list && !["upcoming", "past", "none"].includes(config.list)) {
      throw new Error("list must be one of: upcoming, past, none");
    }
    this._config = { ...DEFAULT_CONFIG, ...config };
    this._signature = null;
    if (this._hass) this._render();
  }

  set hass(hass) {
    this._hass = hass;
    const entities = this._entities();
    const signature = JSON.stringify([
      hass.locale,
      hass.themes?.darkMode,
      Object.values(entities).map((id) => hass.states[id]?.last_updated),
    ]);
    // Only re-render when a relevant entity (or the locale) has changed
    if (signature !== this._signature) {
      this._signature = signature;
      this._render();
    }
  }

  connectedCallback() {
    // Keep relative times ("in 3 hours", "lands in 20m") current
    this._timer = setInterval(() => this._render(), 60000);
    this._render();
  }

  disconnectedCallback() {
    clearInterval(this._timer);
  }

  getCardSize() {
    const list = this._config?.list === "none" ? 0 : this._config?.max_flights ?? 5;
    return 2 + Math.ceil(list / 1.5);
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6, rows: "auto" };
  }

  /** Map translation keys to entity IDs for the configured (or first) AirTrail device. */
  _entities() {
    const registry = Object.values(this._hass?.entities || {}).filter(
      (entry) => entry.platform === DOMAIN,
    );
    const deviceId = this._config?.device || registry.find((e) => e.device_id)?.device_id;
    const entities = {};
    for (const entry of registry) {
      if (entry.device_id === deviceId && entry.translation_key) {
        entities[entry.translation_key] = entry.entity_id;
      }
    }
    return entities;
  }

  _state(key) {
    const entityId = this._entities()[key];
    return entityId ? this._hass.states[entityId] : undefined;
  }

  _relative(flight) {
    const rtf = new Intl.RelativeTimeFormat(this._hass.locale?.language, {
      numeric: "auto",
    });
    let seconds;
    if (flight.departure) {
      seconds = (new Date(flight.departure) - Date.now()) / 1000;
    } else {
      const today = new Date();
      today.setHours(0, 0, 0, 0);
      const date = parseLocal(flight.date);
      const local = new Date(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate());
      return rtf.format(Math.round((local - today) / 86400000), "day");
    }
    const abs = Math.abs(seconds);
    if (abs < 3600) return rtf.format(Math.round(seconds / 60), "minute");
    if (abs < 86400) return rtf.format(Math.round(seconds / 3600), "hour");
    return rtf.format(Math.round(seconds / 86400), "day");
  }

  _formatLocal(value, options) {
    const date = parseLocal(value);
    if (!date) return "";
    return new Intl.DateTimeFormat(this._hass.locale?.language, {
      ...options,
      timeZone: "UTC",
    }).format(date);
  }

  _formatDuration(ms) {
    const minutes = Math.max(0, Math.round(ms / 60000));
    const h = Math.floor(minutes / 60);
    const m = minutes % 60;
    return h ? `${h}h ${m}m` : `${m}m`;
  }

  _moreInfo(entityId) {
    if (!entityId) return;
    this.dispatchEvent(
      new CustomEvent("hass-more-info", {
        detail: { entityId },
        bubbles: true,
        composed: true,
      }),
    );
  }

  _renderHeader() {
    const inFlight = this._state("in_flight");
    const next = this._state("next_flight");
    const last = this._state("last_flight");

    if (inFlight?.state === "on") {
      const f = inFlight.attributes;
      const start = new Date(f.departure).getTime();
      const end = f.arrival ? new Date(f.arrival).getTime() : null;
      const now = Date.now();
      const progress = end ? Math.min(100, Math.max(0, ((now - start) / (end - start)) * 100)) : null;
      const secondary = end
        ? `In flight · lands in ${this._formatDuration(end - now)}`
        : "In flight";
      return `
        <div class="header" data-entity="${escape(inFlight.entity_id)}">
          ${this._shape("mdi:airplane", true)}
          <div class="info">
            <span class="primary">${escape(f.title)}</span>
            <span class="secondary">${escape(secondary)}</span>
          </div>
        </div>
        ${progress !== null ? `<div class="progress"><div style="width:${progress.toFixed(1)}%"></div></div>` : ""}`;
    }

    if (next && next.state !== "unknown" && next.state !== "unavailable") {
      const f = next.attributes;
      const when = f.departure_local
        ? this._formatLocal(f.departure_local, {
            weekday: "short",
            day: "numeric",
            month: "short",
            hour: "2-digit",
            minute: "2-digit",
          })
        : this._formatLocal(f.date, { weekday: "short", day: "numeric", month: "short" });
      const secondary = [
        this._relative(f),
        when,
        f.departure_gate && `Gate ${f.departure_gate}`,
        f.seat_number && `Seat ${f.seat_number}`,
      ].filter(Boolean);
      return `
        <div class="header" data-entity="${escape(next.entity_id)}">
          ${this._shape("mdi:airplane-takeoff")}
          <div class="info">
            <span class="primary">${escape(f.title)}</span>
            <span class="secondary">${escape(secondary.join(" · "))}</span>
          </div>
        </div>`;
    }

    const lastTitle = last?.attributes?.title;
    return `
      <div class="header" data-entity="${escape(last?.entity_id ?? "")}">
        ${this._shape("mdi:airplane-off", false, true)}
        <div class="info">
          <span class="primary">No upcoming flights</span>
          ${lastTitle ? `<span class="secondary">Last: ${escape(lastTitle)} · ${escape(this._relative(last.attributes))}</span>` : ""}
        </div>
      </div>`;
  }

  _shape(icon, active = false, muted = false) {
    return `
      <div class="shape ${active ? "active" : ""} ${muted ? "muted" : ""}">
        <ha-icon icon="${icon}"></ha-icon>
      </div>`;
  }

  _renderChips() {
    const chips = (this._config.stats || [])
      .map((key) => [key, this._state(key)])
      .filter(([, state]) => state && state.state !== "unavailable");
    if (!chips.length) return "";
    return `
      <div class="chips">
        ${chips
          .map(([key, state]) => {
            // Counts share a unit ("flights"), so label them by what they count
            const short = STATS[key]?.short;
            const value = short
              ? `${Number(state.state).toLocaleString(this._hass.locale?.language)} ${short}`
              : this._hass.formatEntityState
                ? this._hass.formatEntityState(state)
                : `${state.state} ${state.attributes.unit_of_measurement ?? ""}`;
            const label = STATS[key]?.label ?? key;
            return `
              <div class="chip" data-entity="${escape(state.entity_id)}" title="${escape(label)}">
                <ha-icon icon="${escape(STATS[key]?.icon ?? "mdi:airplane")}"></ha-icon>
                <span>${escape(value)}</span>
              </div>`;
          })
          .join("")}
      </div>`;
  }

  _renderList() {
    if (this._config.list === "none") return "";
    const source = this._state(this._config.list === "past" ? "past_flights" : "upcoming_flights");
    // Don't repeat the flight that's already shown in the header
    const headerId =
      this._config.show_header !== false && this._state("in_flight")?.state !== "on"
        ? this._state("next_flight")?.attributes?.id
        : undefined;
    const flights = (source?.attributes?.flights || [])
      .filter((f) => this._config.list === "past" || f.id !== headerId)
      .slice(0, this._config.max_flights);
    if (!flights.length) {
      const past = this._config.list === "past";
      const days = source?.attributes?.days;
      const range = days ? ` in the ${past ? "last" : "next"} ${days} days` : "";
      return `<div class="empty">No ${past ? "past" : "upcoming"} flights${escape(range)}</div>`;
    }
    return `
      <div class="list" data-entity="${escape(source.entity_id)}">
        ${flights
          .map((f) => {
            const date = parseLocal(f.departure_local || f.date);
            const time = f.departure_local
              ? this._formatLocal(f.departure_local, { hour: "2-digit", minute: "2-digit" })
              : null;
            const cities =
              f.origin_city && f.destination_city
                ? `${f.origin_city} → ${f.destination_city}`
                : null;
            const secondary = [f.flight_number, f.airline, time].filter(Boolean).join(" · ");
            return `
              <div class="row">
                <div class="date">
                  <span class="day">${date ? date.getUTCDate() : "?"}</span>
                  <span class="month">${date ? escape(this._formatLocal(f.departure_local || f.date, { month: "short" })) : ""}</span>
                </div>
                <div class="info">
                  <span class="primary">${escape(f.route)}${cities ? ` <span class="muted">${escape(cities)}</span>` : ""}</span>
                  <span class="secondary">${escape(secondary)}</span>
                </div>
                <span class="badge">${escape(this._relative(f))}</span>
              </div>`;
          })
          .join("")}
      </div>`;
  }

  _render() {
    if (!this._config || !this._hass) return;
    const hasDevice = Object.keys(this._entities()).length > 0;
    const { title } = this._config;

    this.shadowRoot.innerHTML = `
      <style>${STYLES}</style>
      <ha-card style="--airtrail-color: ${escape(resolveColor(this._config.color))}">
        ${title ? `<div class="title">${escape(title)}</div>` : ""}
        <div class="content">
          ${
            hasDevice
              ? [
                  this._config.show_header !== false ? this._renderHeader() : "",
                  this._renderChips(),
                  this._renderList(),
                ].join("")
              : `<div class="empty">No AirTrail device found. Add the AirTrail integration first.</div>`
          }
        </div>
      </ha-card>`;

    this.shadowRoot.querySelectorAll("[data-entity]").forEach((el) => {
      el.addEventListener("click", (ev) => {
        ev.stopPropagation();
        this._moreInfo(el.dataset.entity);
      });
    });
  }
}

const STYLES = `
  :host {
    --spacing: var(--mush-spacing, 12px);
    --icon-size: var(--mush-icon-size, 36px);
    --icon-border-radius: var(--mush-icon-border-radius, 50%);
    --chip-height: var(--mush-chip-height, 36px);
    --chip-border-radius: var(--mush-chip-border-radius, 19px);
    --primary-size: var(--mush-card-primary-font-size, 14px);
    --primary-weight: var(--mush-card-primary-font-weight, bold);
    --secondary-size: var(--mush-card-secondary-font-size, 12px);
    --secondary-weight: var(--mush-card-secondary-font-weight, bolder);
  }
  ha-card {
    overflow: hidden;
    height: 100%;
    box-sizing: border-box;
  }
  .title {
    padding: var(--spacing) var(--spacing) 0;
    font-size: var(--mush-title-font-size, 18px);
    font-weight: var(--mush-title-font-weight, normal);
    color: var(--primary-text-color);
  }
  .content {
    display: flex;
    flex-direction: column;
    gap: var(--spacing);
    padding: var(--spacing);
  }
  .header,
  .row {
    display: flex;
    align-items: center;
    gap: var(--spacing);
    min-width: 0;
  }
  .header,
  .chip,
  .list {
    cursor: pointer;
  }
  .shape {
    flex: none;
    display: flex;
    align-items: center;
    justify-content: center;
    width: var(--icon-size);
    height: var(--icon-size);
    border-radius: var(--icon-border-radius);
    background: color-mix(in srgb, var(--airtrail-color) 20%, transparent);
    color: var(--airtrail-color);
    --mdc-icon-size: 20px;
  }
  .shape.active ha-icon {
    animation: fly 2s ease-in-out infinite;
  }
  .shape.muted {
    background: color-mix(in srgb, var(--disabled-text-color, #bdbdbd) 20%, transparent);
    color: var(--disabled-text-color, #bdbdbd);
  }
  @keyframes fly {
    0%, 100% { transform: translateY(1px) rotate(-3deg); }
    50% { transform: translateY(-1px) rotate(3deg); }
  }
  .info {
    display: flex;
    flex-direction: column;
    min-width: 0;
    flex: 1;
  }
  .primary,
  .secondary {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .primary {
    font-size: var(--primary-size);
    font-weight: var(--primary-weight);
    line-height: 20px;
    color: var(--primary-text-color);
  }
  .secondary {
    font-size: var(--secondary-size);
    font-weight: var(--secondary-weight);
    line-height: 16px;
    color: var(--secondary-text-color);
  }
  .muted {
    font-weight: normal;
    color: var(--secondary-text-color);
  }
  .progress {
    height: 6px;
    border-radius: 3px;
    background: color-mix(in srgb, var(--airtrail-color) 20%, transparent);
    overflow: hidden;
  }
  .progress div {
    height: 100%;
    border-radius: 3px;
    background: var(--airtrail-color);
  }
  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: var(--mush-chip-spacing, 8px);
  }
  .chip {
    display: flex;
    align-items: center;
    gap: 6px;
    height: var(--chip-height);
    padding: 0 12px 0 10px;
    box-sizing: border-box;
    border-radius: var(--chip-border-radius);
    background: var(--mush-chip-background, var(--secondary-background-color));
    font-size: 0.85em;
    font-weight: bold;
    color: var(--primary-text-color);
    --mdc-icon-size: 16px;
  }
  .chip ha-icon {
    color: var(--airtrail-color);
  }
  .list {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .date {
    flex: none;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    width: var(--icon-size);
    height: var(--icon-size);
    border-radius: var(--mush-control-border-radius, 12px);
    background: var(--secondary-background-color);
    line-height: 1;
  }
  .date .day {
    font-size: 14px;
    font-weight: bold;
    color: var(--primary-text-color);
  }
  .date .month {
    font-size: 9px;
    text-transform: uppercase;
    color: var(--secondary-text-color);
  }
  .badge {
    flex: none;
    font-size: var(--secondary-size);
    color: var(--secondary-text-color);
  }
  .empty {
    font-size: var(--secondary-size);
    color: var(--secondary-text-color);
  }
`;

const EDITOR_SCHEMA = [
  { name: "device", selector: { device: { integration: DOMAIN } } },
  {
    type: "grid",
    name: "",
    schema: [
      { name: "title", selector: { text: {} } },
      { name: "color", selector: { ui_color: {} } },
    ],
  },
  { name: "show_header", selector: { boolean: {} } },
  {
    name: "stats",
    selector: {
      select: {
        multiple: true,
        reorder: true,
        options: Object.entries(STATS).map(([value, { label }]) => ({ value, label })),
      },
    },
  },
  {
    type: "grid",
    name: "",
    schema: [
      {
        name: "list",
        selector: {
          select: {
            mode: "dropdown",
            options: [
              { value: "upcoming", label: "Upcoming flights" },
              { value: "past", label: "Past flights" },
              { value: "none", label: "Hidden" },
            ],
          },
        },
      },
      { name: "max_flights", selector: { number: { min: 1, max: 20, mode: "box" } } },
    ],
  },
];

const EDITOR_LABELS = {
  device: "AirTrail device (defaults to the first one)",
  title: "Title",
  color: "Accent colour",
  show_header: "Show next / current flight",
  stats: "Statistics",
  list: "Flight list",
  max_flights: "Flights to show",
};

class AirTrailCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = config;
    this._update();
  }

  set hass(hass) {
    this._hass = hass;
    this._update();
  }

  _update() {
    if (!this._config || !this._hass) return;
    if (!this._form) {
      this._form = document.createElement("ha-form");
      this._form.schema = EDITOR_SCHEMA;
      this._form.computeLabel = (schema) => EDITOR_LABELS[schema.name] ?? schema.name;
      this._form.addEventListener("value-changed", (ev) => {
        ev.stopPropagation();
        this.dispatchEvent(
          new CustomEvent("config-changed", {
            detail: { config: ev.detail.value },
            bubbles: true,
            composed: true,
          }),
        );
      });
      this.appendChild(this._form);
    }
    this._form.hass = this._hass;
    this._form.data = { ...DEFAULT_CONFIG, ...this._config };
  }
}

if (!customElements.get("airtrail-card")) {
  customElements.define("airtrail-card", AirTrailCard);
  customElements.define("airtrail-card-editor", AirTrailCardEditor);

  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "airtrail-card",
    name: "AirTrail",
    description: "Your next flight, flight statistics and upcoming or past flights.",
    preview: true,
    documentationURL: "https://github.com/owenvoke/hass-airtrail",
  });
}
