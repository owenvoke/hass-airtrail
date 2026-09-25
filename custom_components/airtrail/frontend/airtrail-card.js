/**
 * AirTrail card for Home Assistant, styled after Mushroom.
 *
 * Finds the entities of an AirTrail device through the entity registry, so the
 * minimal configuration is just `type: custom:airtrail-card`.
 */

const DOMAIN = "airtrail";
const DEFAULT_COLOR = "#3c83f6";

// `name` is the short label shown on the badge, `label` is used in the editor
const STATS = {
  upcoming_flights: { name: "Upcoming", label: "Upcoming flights", icon: "mdi:airplane-clock" },
  past_flights: { name: "Past", label: "Past flights", icon: "mdi:history" },
  total_flights: { name: "Total", label: "Total flights", icon: "mdi:airplane" },
  total_distance: { name: "Distance", label: "Total distance", icon: "mdi:map-marker-distance" },
  total_flight_time: { name: "Flight time", label: "Total flight time", icon: "mdi:timer-outline" },
  airports_visited: { name: "Airports", label: "Airports visited", icon: "mdi:airport" },
  top_airline: { name: "Airline", label: "Top airline", icon: "mdi:airplane-marker" },
  top_airport: { name: "Airport", label: "Top airport", icon: "mdi:airport" },
  top_aircraft: { name: "Aircraft", label: "Top aircraft", icon: "mdi:airplane-cog" },
  top_route: { name: "Route", label: "Top route", icon: "mdi:routes" },
};

// What each flight list entry can show beneath its route. `relative` is shown on
// the right of the entry rather than in the details line.
const ENTRY_DETAILS = {
  flight_number: "Flight number",
  airline: "Airline",
  departure_time: "Departure time",
  arrival_time: "Arrival time",
  duration: "Duration",
  distance: "Distance",
  aircraft: "Aircraft",
  seat: "Seat",
  seat_class: "Class",
  relative: "Time until / since",
};

let cardHelpers;
const loadCardHelpers = () => (cardHelpers ??= window.loadCardHelpers?.());

const DEFAULT_CONFIG = {
  show_header: true,
  stats: ["upcoming_flights", "total_flights", "total_distance", "total_flight_time"],
  lists: ["upcoming"],
  max_flights: 5,
  entry_details: ["flight_number", "airline", "departure_time", "relative"],
  route: "both",
};

const ROUTES = ["codes", "locations", "both"];

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

const LISTS = ["upcoming", "past"];

/** Convert the old single `list` option into `lists`, and validate. */
const normalizeConfig = (config) => {
  const { list, ...rest } = config;
  if (rest.route !== undefined && !ROUTES.includes(rest.route)) {
    throw new Error(`route must be one of: ${ROUTES.join(", ")}`);
  }
  if (list !== undefined && rest.lists === undefined) {
    rest.lists = { both: ["upcoming", "past"], none: [] }[list] ?? [list];
  }
  if (rest.lists !== undefined) {
    if (!Array.isArray(rest.lists) || rest.lists.some((l) => !LISTS.includes(l))) {
      throw new Error(`lists must only contain: ${LISTS.join(", ")}`);
    }
  }
  return rest;
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
    // Keys of the header / list entries whose details are expanded
    this._expanded = new Set();
  }

  setConfig(config) {
    this._config = { ...DEFAULT_CONFIG, ...normalizeConfig(config) };
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
    const list = (this._config?.lists?.length ?? 1) * (this._config?.max_flights ?? 5);
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

  /** Time until departure, or for a flight that has happened, time since it landed. */
  _relative(flight, { landed = false } = {}) {
    const rtf = new Intl.RelativeTimeFormat(this._hass.locale?.language, {
      numeric: "auto",
    });
    let seconds;
    if (flight.departure) {
      let instant = new Date(flight.departure).getTime();
      if (landed) {
        if (flight.arrival) {
          instant = new Date(flight.arrival).getTime();
        } else if (flight.duration_minutes) {
          instant += flight.duration_minutes * 60000;
        }
      }
      seconds = (instant - Date.now()) / 1000;
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

  /** The route as airport codes, locations or both, honouring the card options. */
  _route(f, { html = false } = {}) {
    const codes = f.origin && f.destination ? `${f.origin} → ${f.destination}` : f.route;
    const cities =
      f.origin_city && f.destination_city ? `${f.origin_city} → ${f.destination_city}` : null;
    const route = this._config.route || "both";
    // Fall back to codes when a flight has no locations recorded
    const showCities = route !== "codes" && cities;
    const showCodes = route !== "locations" || !showCities;

    if (!html) return [showCodes && codes, showCities && cities].filter(Boolean).join(" · ");
    if (showCodes && showCities) {
      return `${escape(codes)}<span class="separator">·</span><span class="muted">${escape(cities)}</span>`;
    }
    return escape(showCodes ? codes : cities);
  }

  _title(f, options) {
    const route = this._route(f, options);
    if (!f.flight_number) return route;
    return `${options?.html ? escape(f.flight_number) : f.flight_number} ${route}`;
  }

  _detail(f, key) {
    const lang = this._hass.locale?.language;
    const time = (value) =>
      value ? this._formatLocal(value, { hour: "2-digit", minute: "2-digit" }) : null;
    switch (key) {
      case "flight_number":
        return f.flight_number;
      case "airline":
        return f.airline;
      case "departure_time":
        return time(f.departure_local);
      case "arrival_time":
        return f.arrival_local ? `Arr. ${time(f.arrival_local)}` : null;
      case "duration":
        return f.duration_minutes ? this._formatDuration(f.duration_minutes * 60000) : null;
      case "distance":
        return f.distance_km ? `${Math.round(f.distance_km).toLocaleString(lang)} km` : null;
      case "aircraft":
        return f.aircraft;
      case "seat":
        return f.seat_number ? `Seat ${f.seat_number}` : null;
      case "seat_class":
        return f.seat_class ? f.seat_class[0].toUpperCase() + f.seat_class.slice(1) : null;
      default:
        return null;
    }
  }

  _renderDetails(f) {
    const lang = this._hass.locale?.language;
    const when = (value) =>
      value
        ? this._formatLocal(value, {
            weekday: "short",
            day: "numeric",
            month: "short",
            hour: "2-digit",
            minute: "2-digit",
          })
        : null;
    const airport = (name, code) => (name ? `${name}${code ? ` (${code})` : ""}` : code);
    const terminalGate = (terminal, gate) =>
      [terminal && `Terminal ${terminal}`, gate && `Gate ${gate}`].filter(Boolean).join(" · ");
    const capitalise = (value) => (value ? value[0].toUpperCase() + value.slice(1) : null);
    const others = f.other_passengers || [];

    const rows = [
      ["From", airport(f.origin_name, f.origin)],
      ["To", airport(f.destination_name, f.destination)],
      ["Departs", when(f.departure_local) && `${when(f.departure_local)} local`],
      ["Arrives", when(f.arrival_local) && `${when(f.arrival_local)} local`],
      ["Departure", terminalGate(f.departure_terminal, f.departure_gate)],
      ["Arrival", terminalGate(f.arrival_terminal, f.arrival_gate)],
      ["Airline", [f.airline, f.flight_number].filter(Boolean).join(" · ")],
      ["Aircraft", [f.aircraft, f.aircraft_registration].filter(Boolean).join(" · ")],
      ["Seat", [f.seat_number, capitalise(f.seat)].filter(Boolean).join(" · ")],
      ["Class", capitalise(f.seat_class)],
      ["Reason", capitalise(f.flight_reason)],
      ["Duration", f.duration_minutes ? this._formatDuration(f.duration_minutes * 60000) : null],
      ["Distance", f.distance_km ? `${Math.round(f.distance_km).toLocaleString(lang)} km` : null],
      ["With", others.length ? others.join(", ") : null],
      ["Note", f.note],
    ].filter(([, value]) => value);

    return `
      <dl class="details">
        ${rows.map(([label, value]) => `<dt>${label}</dt><dd>${escape(value)}</dd>`).join("")}
      </dl>`;
  }

  /** A header or list entry that expands to show the flight's details when tapped. */
  _expandable(key, f, content) {
    const expanded = this._expanded.has(key);
    return `
      <div class="entry ${expanded ? "expanded" : ""}">
        <div class="toggle" data-toggle="${escape(key)}" role="button" tabindex="0"
          aria-expanded="${expanded}">${content}</div>
        ${expanded ? this._renderDetails(f) : ""}
      </div>`;
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
      const arrivalTime = f.arrival_local
        ? this._formatLocal(f.arrival_local, { hour: "2-digit", minute: "2-digit" })
        : null;
      const secondary = [
        end ? `In flight · lands in ${this._formatDuration(end - now)}` : "In flight",
        arrivalTime && `${arrivalTime} local`,
        f.arrival_terminal && `Terminal ${f.arrival_terminal}`,
        f.arrival_gate && `Gate ${f.arrival_gate}`,
      ]
        .filter(Boolean)
        .join(" · ");
      return `
        ${this._expandable(
          "header",
          f,
          `<div class="header">
            ${this._shape("mdi:airplane", true)}
            <div class="info">
              <span class="primary">${this._title(f, { html: true })}</span>
              <span class="secondary">${escape(secondary)}</span>
            </div>
          </div>`,
        )}
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
      // On the day of departure, lead with a countdown and where to go
      const untilDeparture = f.departure ? new Date(f.departure).getTime() - Date.now() : null;
      const today = !f.departure && f.date === new Date().toLocaleDateString("sv");
      const soon = today || (untilDeparture !== null && untilDeparture < 86400000);
      const secondary = soon
        ? [
            untilDeparture !== null
              ? `Departs in ${this._formatDuration(untilDeparture)}`
              : "Departs today",
            f.departure_local &&
              this._formatLocal(f.departure_local, { hour: "2-digit", minute: "2-digit" }),
            f.departure_terminal && `Terminal ${f.departure_terminal}`,
            f.departure_gate && `Gate ${f.departure_gate}`,
            f.seat_number && `Seat ${f.seat_number}`,
          ].filter(Boolean)
        : [
            this._relative(f),
            when,
            f.departure_gate && `Gate ${f.departure_gate}`,
            f.seat_number && `Seat ${f.seat_number}`,
          ].filter(Boolean);
      return this._expandable(
        "header",
        f,
        `<div class="header ${soon ? "soon" : ""}">
          ${this._shape("mdi:airplane-takeoff")}
          <div class="info">
            <span class="primary">${this._title(f, { html: true })}</span>
            <span class="secondary">${escape(secondary.join(" · "))}</span>
          </div>
        </div>`,
      );
    }

    const lastTitle = last?.attributes?.id !== undefined ? this._title(last.attributes) : null;
    const content = `
      <div class="header">
        ${this._shape("mdi:airplane-off", false, true)}
        <div class="info">
          <span class="primary">No upcoming flights</span>
          ${lastTitle ? `<span class="secondary">Last: ${escape(lastTitle)} · ${escape(this._relative(last.attributes, { landed: true }))}</span>` : ""}
        </div>
      </div>`;
    // Tapping shows the last flight's details, if there is one
    return lastTitle ? this._expandable("header", last.attributes, content) : content;
  }

  _shape(icon, active = false, muted = false) {
    return `
      <div class="shape ${active ? "active" : ""} ${muted ? "muted" : ""}">
        <ha-icon icon="${icon}"></ha-icon>
      </div>`;
  }

  _badgeConfigs() {
    return (this._config.stats || [])
      .map((key) => [key, this._state(key)])
      .filter(([, state]) => state && state.state !== "unavailable")
      .map(([key, state]) => ({
        type: "entity",
        entity: state.entity_id,
        name: STATS[key]?.name ?? key,
        icon: STATS[key]?.icon,
        color: this._config.color || DEFAULT_COLOR,
        show_name: true,
        show_icon: true,
        show_state: true,
      }));
  }

  _renderChips() {
    return this._badgeConfigs().length ? `<div class="chips"></div>` : "";
  }

  /** Fill the chips row with Home Assistant's own entity badges. */
  async _mountBadges() {
    const container = this.shadowRoot.querySelector(".chips");
    if (!container) return;
    const helpers = await loadCardHelpers();
    // Skip if a newer render has replaced this container in the meantime
    if (!helpers || !container.isConnected) return;

    const badges = new Map();
    for (const config of this._badgeConfigs()) {
      const key = JSON.stringify(config);
      const badge = this._badges?.get(key) ?? helpers.createBadgeElement(config);
      badge.hass = this._hass;
      badges.set(key, badge);
      container.appendChild(badge);
    }
    // Reuse badge elements across renders rather than recreating them
    this._badges = badges;
  }

  _renderList() {
    const lists = this._config.lists || [];
    if (lists.length === 1) return this._renderSection(lists[0]);
    // Label each section when more than one list is shown
    return lists
      .map(
        (kind) => `
          <div class="section">
            <span class="heading">${kind === "past" ? "Past" : "Upcoming"}</span>
            ${this._renderSection(kind)}
          </div>`,
      )
      .join("");
  }

  _renderSection(kind) {
    const past = kind === "past";
    const source = this._state(past ? "past_flights" : "upcoming_flights");
    // Don't repeat the flight that's already shown in the header
    const headerId =
      this._config.show_header !== false && this._state("in_flight")?.state !== "on"
        ? this._state("next_flight")?.attributes?.id
        : undefined;
    const flights = (source?.attributes?.flights || [])
      .filter((f) => past || f.id !== headerId)
      .slice(0, this._config.max_flights);
    if (!flights.length) {
      const days = source?.attributes?.days;
      const range = days ? ` in the ${past ? "last" : "next"} ${days} days` : "";
      const other = !past && headerId !== undefined ? "other " : "";
      return `<div class="empty">No ${other}${past ? "past" : "upcoming"} flights${escape(range)}</div>`;
    }
    return `
      <div class="list">
        ${flights
          .map((f) => {
            const date = parseLocal(f.departure_local || f.date);
            const details = this._config.entry_details || [];
            const secondary = details
              .filter((key) => key !== "relative")
              .map((key) => this._detail(f, key))
              .filter(Boolean)
              .join(" · ");
            return this._expandable(
              `${kind}-${f.id}`,
              f,
              `
              <div class="row">
                <div class="date">
                  <span class="day">${date ? date.getUTCDate() : "?"}</span>
                  <span class="month">${date ? escape(this._formatLocal(f.departure_local || f.date, { month: "short" })) : ""}</span>
                </div>
                <div class="info">
                  <span class="primary">${this._route(f, { html: true })}</span>
                  ${secondary ? `<span class="secondary">${escape(secondary)}</span>` : ""}
                </div>
                ${details.includes("relative") ? `<span class="badge">${escape(this._relative(f, { landed: past }))}</span>` : ""}
              </div>`,
            );
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

    this.shadowRoot.querySelectorAll("[data-toggle]").forEach((el) => {
      const toggle = (ev) => {
        ev.stopPropagation();
        const key = el.dataset.toggle;
        if (!this._expanded.delete(key)) this._expanded.add(key);
        this._render();
      };
      el.addEventListener("click", toggle);
      el.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter" || ev.key === " ") {
          ev.preventDefault();
          toggle(ev);
        }
      });
    });

    this._mountBadges();
  }
}

const STYLES = `
  :host {
    --spacing: var(--mush-spacing, 12px);
    --icon-size: var(--mush-icon-size, 36px);
    --icon-border-radius: var(--mush-icon-border-radius, 50%);
    --chip-height: var(--mush-chip-height, 28px);
    --chip-border-radius: var(--mush-chip-border-radius, 14px);
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
  .toggle {
    cursor: pointer;
    border-radius: var(--mush-control-border-radius, 12px);
    outline: none;
  }
  .toggle:focus-visible {
    box-shadow: 0 0 0 2px var(--airtrail-color);
  }
  .details {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 4px 12px;
    margin: 8px 0 2px calc(var(--icon-size) + var(--spacing));
    padding: 10px 12px;
    border-radius: var(--mush-control-border-radius, 12px);
    background: var(--secondary-background-color);
    font-size: var(--secondary-size);
    line-height: 16px;
  }
  .details dt {
    color: var(--secondary-text-color);
  }
  .details dd {
    margin: 0;
    color: var(--primary-text-color);
    overflow-wrap: anywhere;
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
  .header.soon {
    margin: -6px;
    padding: 6px;
    border-radius: var(--mush-control-border-radius, 12px);
    background: color-mix(in srgb, var(--airtrail-color) 12%, transparent);
  }
  .header.soon .shape {
    background: var(--airtrail-color);
    color: var(--text-primary-color, #fff);
  }
  .header.soon .secondary {
    color: var(--primary-text-color);
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
  .separator {
    margin: 0 6px;
    font-weight: normal;
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
    gap: var(--mush-chip-spacing, 6px);
    --ha-badge-size: var(--chip-height);
    --ha-badge-border-radius: var(--chip-border-radius);
  }
  .section {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .heading {
    font-size: var(--secondary-size);
    font-weight: bold;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--secondary-text-color);
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
    name: "lists",
    selector: {
      select: {
        multiple: true,
        reorder: true,
        mode: "dropdown",
        options: [
          { value: "upcoming", label: "Upcoming" },
          { value: "past", label: "Past" },
        ],
      },
    },
  },
  { name: "max_flights", selector: { number: { min: 1, max: 20, mode: "box" } } },
  {
    name: "entry_details",
    selector: {
      select: {
        multiple: true,
        reorder: true,
        mode: "dropdown",
        options: Object.entries(ENTRY_DETAILS).map(([value, label]) => ({ value, label })),
      },
    },
  },
  {
    name: "route",
    selector: {
      select: {
        mode: "box",
        options: [
          { value: "codes", label: "Airport codes", description: "LHR → JFK" },
          { value: "locations", label: "Locations", description: "London → New York" },
          { value: "both", label: "Both", description: "LHR → JFK · London → New York" },
        ],
      },
    },
  },
];

const EDITOR_HELPERS = {
  stats: "Badges shown below the next flight, in this order",
  lists: "Flight lists shown at the bottom of the card, in this order",
  entry_details: "What each flight in the lists shows beneath its route, in this order",
};

const EDITOR_LABELS = {
  device: "AirTrail device (defaults to the first one)",
  title: "Title",
  color: "Accent colour",
  show_header: "Show next / current flight",
  stats: "Statistics",
  lists: "Flight lists",
  max_flights: "Flights to show",
  entry_details: "Entry details",
  route: "Route",
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
      this._form.computeHelper = (schema) => EDITOR_HELPERS[schema.name];
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
    this._form.data = { ...DEFAULT_CONFIG, ...normalizeConfig(this._config) };
  }
}

const defineElements = () => {
  if (customElements.get("airtrail-card")) return;
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
};

// This script can load before Home Assistant has installed its own custom element
// registry, and anything defined before then is invisible to dashboards. The app
// element is defined once that registry is in place, so wait for it.
const whenReady = () => {
  if (window.customElements.get("home-assistant")) {
    defineElements();
  } else {
    setTimeout(whenReady, 50);
  }
};
whenReady();
