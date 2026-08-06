/* zendarq-dashboard frontend — Alpine.js app */

const LOCAL_TZ = "America/New_York";

const DEFAULT_CITIES = [
  { id: "nyc", name: "New York City" },
  { id: "tokyo", name: "Tokyo" },
  { id: "chicago", name: "Chicago" },
];

const WMO = {
  0: ["Clear sky", "☀️"], 1: ["Mainly clear", "🌤️"], 2: ["Partly cloudy", "⛅"],
  3: ["Overcast", "☁️"], 45: ["Fog", "🌫️"], 48: ["Rime fog", "🌫️"],
  51: ["Light drizzle", "🌦️"], 53: ["Moderate drizzle", "🌦️"], 55: ["Dense drizzle", "🌧️"],
  56: ["Freezing drizzle", "🌧️"], 57: ["Freezing drizzle", "🌧️"],
  61: ["Light rain", "🌦️"], 63: ["Moderate rain", "🌧️"], 65: ["Heavy rain", "🌧️"],
  66: ["Freezing rain", "🌧️"], 67: ["Freezing rain", "🌧️"],
  71: ["Light snow", "🌨️"], 73: ["Moderate snow", "🌨️"], 75: ["Heavy snow", "❄️"],
  77: ["Snow grains", "❄️"],
  80: ["Light showers", "🌦️"], 81: ["Moderate showers", "🌧️"], 82: ["Violent showers", "⛈️"],
  85: ["Snow showers", "🌨️"], 86: ["Heavy snow showers", "🌨️"],
  95: ["Thunderstorm", "⛈️"], 96: ["Thunderstorm, hail", "⛈️"], 99: ["Thunderstorm, hail", "⛈️"],
};

function toF(c) { return Math.round((c * 9) / 5 + 32); }
function kmhToMph(k) { return Math.round(k * 0.621371); }
function mmToIn(mm) { return (mm / 25.4).toFixed(2); }

function fmtTime(iso) {
  const m = iso && iso.match(/T(\d{2}):(\d{2})/);
  if (!m) return iso || "—";
  let h = +m[1];
  const ap = h >= 12 ? "PM" : "AM";
  h = h % 12 || 12;
  return `${h}:${m[2]} ${ap}`;
}

document.addEventListener("alpine:init", () => {
  Alpine.data("dashboard", () => ({
    units: "f",
    selected: ["nyc", "tokyo", "chicago"],
    current: [],
    hourly: {},
    daily: {},
    lastUpdated: null,
    refreshing: false,
    headerTime: "",
    tick: 0,
    charts: {},
    timers: [],

    /* ---------- lifecycle ---------- */

    init() {
      this.loadAll();
      this.timers.push(setInterval(() => { this.tick++; }, 30000));                    // per-city clocks
      this.timers.push(setInterval(() => this.updateHeaderClock(), 1000));            // header clock
      this.timers.push(setInterval(() => this.loadAll(true), 5 * 60 * 1000));         // silent auto-refresh
    },

    /* ---------- data loading ---------- */

    async loadAll(silent = false) {
      if (!silent) this.refreshing = true;
      try {
        const [cur, ...rest] = await Promise.all([
          fetch("/api/current").then(r => r.json()),
          ...this.selected.map(cid => fetch(`/api/hourly?city=${cid}`).then(r => r.json())),
          ...this.selected.map(cid => fetch(`/api/daily?city=${cid}`).then(r => r.json())),
        ]);
        const n = this.selected.length;
        const hourly = rest.slice(0, n);
        const daily = rest.slice(n);
        this.current = cur.cities;
        this.hourly = Object.fromEntries(hourly.map(x => [x.city, x.points]));
        this.daily = Object.fromEntries(daily.map(x => [x.city, x.days]));
        this.lastUpdated = new Date().toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
        this.$nextTick(() => this.buildCharts());
      } catch (e) {
        console.error("loadAll failed:", e);
      } finally {
        if (!silent) this.refreshing = false;
      }
    },

    async refreshNow() {
      this.refreshing = true;
      try {
        await fetch("/api/refresh", { method: "POST" });
      } catch (e) { console.error("refresh failed:", e); }
      await this.loadAll(false);
    },

    async toggleCity(id) {
      if (this.isSelected(id)) {
        this.selected = this.selected.filter(x => x !== id);
        this.$nextTick(() => this.buildCharts());
      } else {
        this.selected = [...this.selected, id];
        const [h, d] = await Promise.all([
          fetch(`/api/hourly?city=${id}`).then(r => r.json()),
          fetch(`/api/daily?city=${id}`).then(r => r.json()),
        ]);
        this.hourly[id] = h.points;
        this.daily[id] = d.days;
        this.$nextTick(() => this.buildCharts());
      }
    },

    toggleUnits(u) {
      if (this.units === u) return;
      this.units = u;
      this.$nextTick(() => this.buildCharts());
    },

    /* ---------- charts ---------- */

    buildCharts() {
      Object.keys(this.charts).forEach(k => { this.charts[k].destroy(); delete this.charts[k]; });
      this.selected.forEach(cid => {
        const pts = this.hourly[cid] || [];
        const el = document.getElementById("chart-" + cid);
        if (!pts.length || !el) return;
        const labels = pts.map(p => { const m = p.ts.match(/T(\d{2}):(\d{2})/); return m ? m[1] + ":" + m[2] : p.ts; });
        const temps = pts.map(p => this.units === "f" ? (p.temp_c * 9) / 5 + 32 : p.temp_c);
        const probs = pts.map(p => p.precip_prob ?? null);
        this.charts[cid] = new Chart(el.getContext("2d"), {
          type: "line",
          data: {
            labels,
            datasets: [
              {
                label: "Temp", data: temps,
                borderColor: "#4f8cff", backgroundColor: "rgba(79,140,255,.14)",
                fill: true, tension: 0.35, pointRadius: 0, borderWidth: 2,
              },
              {
                label: "Precip %", data: probs,
                borderColor: "#8b9bb4", backgroundColor: "rgba(139,155,180,.10)",
                borderDash: [4, 4], tension: 0.3, pointRadius: 0, borderWidth: 1.5,
                yAxisID: "yPrecip",
              },
            ],
          },
          options: {
            responsive: true, maintainAspectRatio: false, animation: false,
            interaction: { mode: "index", intersect: false },
            plugins: {
              legend: { display: false },
              tooltip: {
                backgroundColor: "#0e1626", borderColor: "rgba(255,255,255,.12)", borderWidth: 1,
                titleColor: "#e6ecf5", bodyColor: "#8b9bb4", padding: 10, cornerRadius: 10,
                callbacks: { label: ctx => ctx.dataset.label === "Temp" ? `${Math.round(ctx.parsed.y)}°` : `${ctx.parsed.y ?? "—"}%` },
              },
            },
            scales: {
              x: { grid: { display: false }, ticks: { color: "#8b9bb4", maxTicksLimit: 6, font: { size: 10 } } },
              y: { position: "left", grid: { color: "rgba(255,255,255,.06)" }, ticks: { color: "#8b9bb4", font: { size: 10 } } },
              yPrecip: { position: "right", min: 0, max: 100, grid: { display: false }, ticks: { color: "#8b9bb4", font: { size: 10 }, callback: v => v + "%" } },
            },
          },
        });
      });
    },

    /* ---------- display helpers ---------- */

    citiesMeta() {
      return DEFAULT_CITIES.map(d => {
        const hit = this.current.find(c => c.id === d.id);
        return { id: d.id, name: hit ? hit.name : d.name };
      });
    },

    isSelected(id) { return this.selected.includes(id); },
    cityName(id) {
      const hit = this.current.find(c => c.id === id);
      if (hit) return hit.name;
      const d = DEFAULT_CITIES.find(x => x.id === id);
      return d ? d.name : id;
    },
    cur(id) { return this.current.find(c => c.id === id); },

    tempText(c) { return c == null ? "—" : this.units === "f" ? `${toF(c)}°` : `${Math.round(c)}°`; },
    tempDisplay(id) { const c = this.cur(id); return c ? this.tempText(c.temp_c) : "—"; },
    feelsDisplay(id) { const c = this.cur(id); return c ? `${this.tempText(c.feels_like_c)}` : "—"; },
    humidityDisplay(id) { const c = this.cur(id); return c && c.humidity != null ? `${Math.round(c.humidity)}%` : "—"; },
    windDisplay(id) {
      const c = this.cur(id);
      if (!c || c.wind_kmh == null) return "—";
      return this.units === "f" ? `${kmhToMph(c.wind_kmh)} mph` : `${Math.round(c.wind_kmh)} km/h`;
    },
    precipDisplay(id) {
      const c = this.cur(id);
      if (!c || c.precip_mm == null) return "—";
      return this.units === "f" ? `${mmToIn(c.precip_mm)} in` : `${c.precip_mm.toFixed(1)} mm`;
    },

    emojiFor(id) {
      const c = this.cur(id);
      if (!c || c.code == null) return "❓";
      const [label, emoji] = WMO[c.code] || ["Unknown", "❓"];
      if (c.code === 0 && !c.is_day) return "🌙";
      if (c.code === 1 && !c.is_day) return "🌙";
      return emoji;
    },
    labelFor(id) {
      const c = this.cur(id);
      if (!c || c.code == null) return "…";
      return WMO[c.code] ? WMO[c.code][0] : "Unknown";
    },
    emojiCode(code) { return WMO[code] ? WMO[code][1] : "❓"; },

    clockFor(id) {
      const c = this.cur(id);
      if (!c || !c.tz) return "—";
      this.tick; // force reactivity
      return new Intl.DateTimeFormat("en-US", { hour: "numeric", minute: "2-digit", timeZone: c.tz }).format(new Date());
    },

    updateHeaderClock() {
      this.headerTime = new Intl.DateTimeFormat("en-US", { hour: "numeric", minute: "2-digit", timeZone: LOCAL_TZ }).format(new Date());
    },

    weekdayOf(date) {
      const d = new Date(date + "T00:00:00");
      return d.toLocaleDateString("en-US", { weekday: "short" });
    },
    isToday(date) {
      const today = new Date().toLocaleDateString("en-CA", { timeZone: LOCAL_TZ });
      return date === today;
    },
    sunTime(iso) { return fmtTime(iso); },
  }));
});
