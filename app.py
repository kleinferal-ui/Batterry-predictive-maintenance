import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import analytics as an
import db

st.set_page_config(page_title="Battery Predictive Maintenance", page_icon="🔋",
                   layout="wide", initial_sidebar_state="expanded")
db.initialize()

OKC, WARNC, CRITC, ACC = "#34d399", "#fbbf24", "#f87171", "#38bdf8"
COLORS = {an.OK: OKC, an.WARN: WARNC, an.CRIT: CRITC}
UNITS = {"voltage": ("Voltage", "V"), "current": ("Current", "A"), "temperature": ("Temperature", "°C")}

st.markdown("""
<style>
:root{--bg:#0b1220;--panel:#111b2e;--line:#22324a;--muted:#8da2bb;--text:#e8eef7;--acc:#38bdf8}
.stApp{background:var(--bg);color:var(--text);font-family:"Segoe UI",system-ui,sans-serif}
[data-testid="stSidebar"]{background:#0d1626;border-right:1px solid var(--line)}
[data-testid="stMainBlockContainer"]{max-width:1400px;padding-top:1.5rem}
h1,h2,h3,h4{color:#f4f8fd!important;letter-spacing:-.02em}
.page-title{font-size:1.7rem;font-weight:700;margin:0}
.page-sub{color:var(--muted);font-size:.9rem;margin:.2rem 0 1.2rem}
.card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px 18px;height:100%}
.k-label{color:var(--muted);font-size:.72rem;font-weight:700;letter-spacing:.09em;text-transform:uppercase}
.k-value{font-family:Consolas,monospace;font-size:2rem;font-weight:700;margin-top:6px;line-height:1.1}
.k-unit{font-size:.95rem;color:var(--acc);margin-left:4px}
.k-delta{font-size:.78rem;color:var(--muted);margin-top:6px}
.banner{border-radius:14px;padding:16px 20px;border:1px solid;margin-bottom:1rem}
.banner b{font-size:1.1rem}
.pill{display:inline-block;padding:3px 12px;border-radius:999px;font-size:.75rem;font-weight:700;border:1px solid}
div[data-testid="stPlotlyChart"]{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:6px}
div[data-testid="stForm"]{background:var(--panel);border:1px solid var(--line);border-radius:14px}
div.stButton>button,div[data-testid="stDownloadButton"] button{border-radius:9px;font-weight:650}
</style>""", unsafe_allow_html=True)


# ----------------------------------------------------------------- helpers
def show(obj, kind="chart"):
    """Render a plotly figure or dataframe full-width on any Streamlit version."""
    fn = st.plotly_chart if kind == "chart" else st.dataframe
    kw = {"hide_index": True} if kind == "table" else {}
    try:
        fn(obj, width="stretch", **kw)
    except TypeError:
        fn(obj, use_container_width=True, **kw)


def style(fig, height=360, title=None):
    fig.update_layout(template="plotly_dark", height=height, title=title,
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      margin=dict(t=50 if title else 20, b=30, l=50, r=20),
                      legend=dict(orientation="h", y=1.12, x=0), font=dict(family="Segoe UI"))
    fig.update_xaxes(gridcolor="#1b2a41")
    fig.update_yaxes(gridcolor="#1b2a41")
    return fig


def header(title, sub):
    st.markdown(f"<div class='page-title'>{title}</div><div class='page-sub'>{sub}</div>", unsafe_allow_html=True)


def kpi(col, label, value, unit, delta=None):
    d = f"<div class='k-delta'>{delta}</div>" if delta else ""
    col.markdown(f"<div class='card'><div class='k-label'>{label}</div><div class='k-value'>{value}"
                 f"<span class='k-unit'>{unit}</span></div>{d}</div>", unsafe_allow_html=True)


def banner(status, headline, lines):
    c = COLORS[status]
    body = "".join(f"<div style='color:#c9d6e6;font-size:.88rem;margin-top:4px'>• {x}</div>" for x in lines)
    st.markdown(f"<div class='banner' style='border-color:{c};background:{c}14'>"
                f"<span class='pill' style='color:{c};border-color:{c}'>{status.upper()}</span> "
                f"<b style='margin-left:8px'>{headline}</b>{body}</div>", unsafe_allow_html=True)


def gauge(value, title, unit, lo, hi, steps, fmt=".2f"):
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=value, number=dict(suffix=f" {unit}", valueformat=fmt),
        title=dict(text=title, font=dict(size=14, color="#8da2bb")),
        gauge=dict(axis=dict(range=[lo, hi]), bar=dict(color="#e8eef7", thickness=0.22),
                   bgcolor="rgba(0,0,0,0)", borderwidth=0,
                   steps=[dict(range=[a, b], color=c) for a, b, c in steps])))
    return style(fig, 210).update_layout(margin=dict(t=50, b=10, l=25, r=25))


def gauges(latest, t):
    v, tmp, cur = latest["voltage"], latest["temperature"], latest["current"]
    vlo, vhi = min(t.voltage_crit * 0.9, v * 0.97), max(t.nominal_voltage * 1.1, v * 1.02)
    thi, chi = max(t.temp_crit * 1.4, tmp * 1.1), max(t.current_crit * 1.4, cur * 1.1)
    r, a, g = "#7f2f2f", "#7d6420", "#1f6b52"
    return (gauge(v, "Voltage", "V", vlo, vhi, [(vlo, t.voltage_crit, r), (t.voltage_crit, t.voltage_warn, a), (t.voltage_warn, vhi, g)]),
            gauge(cur, "Current", "A", 0, chi, [(0, t.current_warn, g), (t.current_warn, t.current_crit, a), (t.current_crit, chi, r)]),
            gauge(tmp, "Temperature", "°C", 0, thi, [(0, t.temp_warn, g), (t.temp_warn, t.temp_crit, a), (t.temp_crit, thi, r)], ".1f"))


ACTIONS = {an.OK: "Continue routine monitoring and follow the manufacturer's maintenance schedule.",
           an.WARN: "Collect more readings under comparable conditions and review the trend. Plan an inspection.",
           an.CRIT: "Verify the measurement, then inspect the battery, connections and BMS per approved procedures."}

# ----------------------------------------------------------------- data + sidebar
history = db.load_history()
t = db.load_thresholds()

st.sidebar.markdown("## 🔋 Battery Console")
st.sidebar.caption("Predictive maintenance · condition monitoring")
page = st.sidebar.radio("Navigate", ["Overview", "Trend Analysis", "Alerts & Assessment", "Anomaly Detection",
                                      "Data & Maintenance Log", "Settings"], label_visibility="collapsed")
window = st.sidebar.selectbox("Analysis window", ["All data", "Last 24 hours", "Last 7 days", "Last 30 days"])
data = history
if not history.empty and window != "All data":
    hours = {"Last 24 hours": 24, "Last 7 days": 168, "Last 30 days": 720}[window]
    data = history[history["timestamp"] >= history["timestamp"].max() - pd.Timedelta(hours=hours)]
if not data.empty:
    status, reasons = an.overall_status(data, t)
    st.sidebar.markdown(f"<div class='card' style='margin-top:10px'><div class='k-label'>System status</div>"
                        f"<div style='color:{COLORS[status]};font-weight:700;font-size:1.2rem;margin-top:4px'>● {status}</div>"
                        f"<div class='k-delta'>{len(data)} readings · latest {data['timestamp'].iloc[-1]:%d %b %H:%M}</div></div>",
                        unsafe_allow_html=True)
st.sidebar.caption("Prototype. Thresholds are demonstration values; use manufacturer limits for real systems.")

if page not in ("Settings", "Data & Maintenance Log") and data.empty:
    header(page, "No readings available yet")
    st.info("No saved readings in this window. Open **Data & Maintenance Log**, upload a CSV and save it.")
    st.stop()

# ----------------------------------------------------------------- OVERVIEW
if page == "Overview":
    header("Battery Bank Overview", "Lithium-ion battery bank · live condition summary from saved readings")
    d = an.add_derived(data)
    latest, prev = d.iloc[-1], (d.iloc[-2] if len(d) > 1 else d.iloc[-1])
    score = an.health_score(data, t)
    banner(status, {an.OK: "All monitored values are within limits", an.WARN: "Attention recommended",
                    an.CRIT: "Immediate review recommended"}[status],
           reasons or ["No threshold breach or adverse short-term trend detected"])
    cols = st.columns(5)
    dv, dc, dt = (latest[k] - prev[k] for k in ("voltage", "current", "temperature"))
    kpi(cols[0], "Voltage", f"{latest['voltage']:.2f}", "V", f"{dv:+.2f} V vs previous")
    kpi(cols[1], "Current", f"{latest['current']:.2f}", "A", f"{dc:+.2f} A vs previous")
    kpi(cols[2], "Temperature", f"{latest['temperature']:.1f}", "°C", f"{dt:+.1f} °C vs previous")
    kpi(cols[3], "Power", f"{latest['power_w']:.0f}", "W", "voltage × current")
    kpi(cols[4], "Health indicator", f"{score:.0f}", "/100", "rule-based screening score")
    st.write("")
    for col, fig in zip(st.columns(3), gauges(latest, t)):
        with col:
            show(fig)
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_scatter(x=d["timestamp"], y=d["voltage"], name="Voltage (V)", line=dict(color=ACC, width=2.5), secondary_y=False)
    fig.add_scatter(x=d["timestamp"], y=d["temperature"], name="Temperature (°C)", line=dict(color=WARNC, width=2.5), secondary_y=True)
    fig.add_hline(y=t.voltage_crit, line_dash="dot", line_color=CRITC, annotation_text="Low-voltage limit")
    fig.update_yaxes(title_text="Voltage (V)", secondary_y=False)
    fig.update_yaxes(title_text="Temperature (°C)", secondary_y=True, showgrid=False)
    show(style(fig, 380, "Voltage and temperature"))

# ----------------------------------------------------------------- TRENDS
elif page == "Trend Analysis":
    header("Trend Analysis", "Measurements over time, smoothing, rates of change and simple projections")
    c1, c2 = st.columns([3, 1])
    metrics = c1.multiselect("Measurements", list(UNITS), default=["voltage", "temperature"],
                             format_func=lambda m: UNITS[m][0])
    smooth = c2.slider("Smoothing (readings)", 1, 12, 3)
    d = an.add_derived(data, smooth)
    limits = {"voltage": [(t.voltage_warn, WARNC), (t.voltage_crit, CRITC)],
              "temperature": [(t.temp_warn, WARNC), (t.temp_crit, CRITC)],
              "current": [(t.current_warn, WARNC), (t.current_crit, CRITC)]}
    if metrics:
        fig = make_subplots(rows=len(metrics), cols=1, shared_xaxes=True, vertical_spacing=0.07,
                            subplot_titles=[f"{UNITS[m][0]} ({UNITS[m][1]})" for m in metrics])
        for i, m in enumerate(metrics, 1):
            fig.add_scatter(x=d["timestamp"], y=d[m], mode="lines+markers", name=UNITS[m][0],
                            line=dict(color=ACC, width=1.5), opacity=0.55, row=i, col=1)
            fig.add_scatter(x=d["timestamp"], y=d[f"{m}_avg"], name=f"{UNITS[m][0]} (smoothed)",
                            line=dict(color=WARNC, width=3), row=i, col=1)
            for val, col in limits[m]:
                fig.add_hline(y=val, line_dash="dot", line_color=col, row=i, col=1)
        show(style(fig, 260 * len(metrics) + 60).update_layout(showlegend=False))
    st.markdown("#### Rate of change and projection")
    st.caption("Straight-line extrapolation through the recorded points. A rough indication only, not a remaining-useful-life estimate.")
    rows = [("voltage", t.voltage_warn, False, "Voltage → warning"), ("voltage", t.voltage_crit, False, "Voltage → critical"),
            ("temperature", t.temp_warn, True, "Temperature → warning"), ("temperature", t.temp_crit, True, "Temperature → critical")]
    for col, (m, lim, rising, label) in zip(st.columns(4), rows):
        p = an.project_crossing(data, m, lim, rising)
        val = {"reached": "Reached", "stable": "Not trending", "insufficient": "Need more data"}.get(p["status"], an.fmt_hours(p["hours"]))
        kpi(col, label, val, "", "" if p["slope"] is None else f"{p['slope']:+.3f} {UNITS[m][1]}/h")
    st.markdown("#### Summary statistics")
    stats = data[list(UNITS)].describe().T[["mean", "min", "max", "std"]].round(2)
    stats.index = [f"{UNITS[i][0]} ({UNITS[i][1]})" for i in stats.index]
    show(stats.reset_index().rename(columns={"index": "Measurement"}), "table")

# ----------------------------------------------------------------- ALERTS
elif page == "Alerts & Assessment":
    header("Alerts & Maintenance Assessment", "Readings checked against warning and critical limits (edit limits in Settings)")
    banner(status, f"Current assessment: {status}", reasons or ["No threshold breach or adverse short-term trend detected"])
    st.markdown(f"**Recommended action:** {ACTIONS[status]}")
    flagged = an.add_status_column(data, t)
    counts = flagged["status"].value_counts()
    for col, s in zip(st.columns(3), [an.OK, an.WARN, an.CRIT]):
        kpi(col, f"{s} readings", int(counts.get(s, 0)), "", f"{counts.get(s, 0) / len(flagged):.0%} of window")
    fig = go.Figure()
    for s in [an.OK, an.WARN, an.CRIT]:
        sub = flagged[flagged["status"] == s]
        fig.add_scatter(x=sub["timestamp"], y=sub["voltage"], mode="markers", name=s,
                        marker=dict(color=COLORS[s], size=11, line=dict(width=1, color="#0b1220")),
                        customdata=sub[["temperature", "current"]],
                        hovertemplate="%{x}<br>%{y:.2f} V · %{customdata[0]:.1f} °C · %{customdata[1]:.2f} A<extra></extra>")
    show(style(fig, 340, "Reading status timeline (voltage)").update_yaxes(title_text="Voltage (V)"))
    issues = flagged[flagged["status"] != an.OK]
    st.markdown("#### Flagged readings")
    if issues.empty:
        st.success("No readings crossed a configured limit.")
    else:
        show(issues.sort_values("timestamp", ascending=False), "table")
    st.caption("Rule-based screening only. A flag is not proof of battery failure.")

# ----------------------------------------------------------------- ANOMALY
elif page == "Anomaly Detection":
    header("Machine-Learning Anomaly Screening", "Isolation Forest highlights readings that differ from the rest of the dataset")
    if len(data) < 8:
        st.info(f"At least 8 readings are needed. Current count: {len(data)}.")
        st.stop()
    sens = st.slider("Sensitivity (expected share of unusual readings)", 0.01, 0.30, 0.10, 0.01)
    res = an.run_isolation_forest(data, sens)
    odd = res[res["model_result"] == -1]
    for col, (lab, val) in zip(st.columns(3), [("Readings analysed", len(res)), ("Flagged unusual", len(odd)),
                                               ("Method", "Isolation Forest")]):
        kpi(col, lab, val, "")
    st.write("")
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1,
                        subplot_titles=["Voltage (V)", "Temperature (°C)"])
    for i, m in enumerate(["voltage", "temperature"], 1):
        fig.add_scatter(x=res["timestamp"], y=res[m], mode="lines+markers", line=dict(color=ACC), name="Reading", row=i, col=1, showlegend=i == 1)
        fig.add_scatter(x=odd["timestamp"], y=odd[m], mode="markers", marker=dict(color=CRITC, size=13, symbol="diamond"),
                        name="Flagged", row=i, col=1, showlegend=i == 1)
    show(style(fig, 520))
    if odd.empty:
        st.success("No unusual readings flagged at this sensitivity.")
    else:
        st.warning(f"{len(odd)} reading(s) flagged for review. A flag is not proof of damage or failure.")
        show(odd.drop(columns="model_result").round(3), "table")
    st.download_button("Download screening results (CSV)", res.drop(columns="model_result").to_csv(index=False).encode(),
                       "battery_anomaly_screening.csv", "text/csv")
    st.caption("Unsupervised and experimental. It does not predict failure or remaining useful life.")

# ----------------------------------------------------------------- DATA + LOG
elif page == "Data & Maintenance Log":
    header("Data & Maintenance Log", "Import readings, review saved history and record maintenance actions")
    tab_up, tab_hist, tab_log = st.tabs(["Import readings", "Saved history", "Maintenance log"])

    with tab_up:
        up = st.file_uploader("Upload battery readings (CSV)", type=["csv"])
        st.caption("Required columns: timestamp, voltage, current, temperature")
        if up is not None:
            res = None
            try:
                res = an.clean_readings(pd.read_csv(up))
            except Exception as e:
                st.error(f"Could not read the CSV: {e}")
            if res is not None and res.error:
                st.error(res.error)
            elif res is not None:
                st.success(f"{len(res.data)} valid readings found.")
                for n in res.notes:
                    st.info(n)
                show(res.data.head(50), "table")
                if st.button("Save readings to database", type="primary"):
                    ins, skip = db.save_readings(res.data)
                    st.success(f"Saved {ins} new reading(s). {skip} already existed and were skipped.")
                    st.rerun()

    with tab_hist:
        if history.empty:
            st.info("Nothing saved yet.")
        else:
            st.write(f"**{len(history)}** saved readings · {history['timestamp'].min():%d %b %Y %H:%M} → {history['timestamp'].max():%d %b %Y %H:%M}")
            show(history.sort_values("timestamp", ascending=False), "table")
            st.download_button("Download history (CSV)", history.to_csv(index=False).encode(), "battery_history_export.csv", "text/csv")

    with tab_log:
        with st.form("log_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            action_date = c1.date_input("Date of inspection / action")
            status_in = c2.selectbox("Assessment status", ["Routine check", "Monitoring", "Inspection required", "Maintenance completed"])
            action = st.text_input("Action taken", placeholder="e.g. Checked readings and inspected terminals")
            notes = st.text_area("Notes (optional)", placeholder="Observations or follow-up needed")
            if st.form_submit_button("Save log entry", type="primary"):
                if action.strip():
                    db.add_log_entry(action_date.isoformat(), status_in, action.strip(), notes.strip())
                    st.success("Log entry saved.")
                else:
                    st.warning("Enter the action taken before saving.")
        log = db.load_log()
        if log.empty:
            st.info("No maintenance actions logged yet.")
        else:
            show(log.drop(columns="id").rename(columns={"action_date": "Date", "status": "Status", "action_taken": "Action",
                                                         "notes": "Notes", "logged_at": "Saved at"}), "table")
            labels = {int(r.id): f"{r.action_date} · {r.action_taken}" for r in log.itertuples()}
            c1, c2 = st.columns([3, 1])
            pick = c1.selectbox("Remove an entry", list(labels), format_func=labels.get)
            if c2.button("Delete entry"):
                db.delete_log_entry(pick)
                st.rerun()
            st.download_button("Download log (CSV)", log.drop(columns="id").to_csv(index=False).encode(), "battery_maintenance_log.csv", "text/csv")

# ----------------------------------------------------------------- SETTINGS
elif page == "Settings":
    header("Settings", "Operating limits used for alerts, assessment and the health indicator. Saved to the database.")
    with st.form("thresholds"):
        c1, c2, c3 = st.columns(3)
        c1.markdown("**Voltage (V)**")
        vw = c1.number_input("Warning below", value=float(t.voltage_warn), step=0.1)
        vc = c1.number_input("Critical below", value=float(t.voltage_crit), step=0.1)
        nv = c1.number_input("Nominal voltage", value=float(t.nominal_voltage), step=0.5)
        c2.markdown("**Temperature (°C)**")
        tw = c2.number_input("Warning above", value=float(t.temp_warn), step=0.5)
        tc = c2.number_input("Critical above", value=float(t.temp_crit), step=0.5)
        c3.markdown("**Current (A)**")
        cw = c3.number_input("Warning above", value=float(t.current_warn), step=0.1)
        cc = c3.number_input("Critical above", value=float(t.current_crit), step=0.1)
        ok = st.form_submit_button("Save limits", type="primary")
    if ok:
        if vc >= vw or tc <= tw or cc <= cw:
            st.error("Critical limits must be beyond warning limits (voltage: lower; temperature and current: higher).")
        else:
            db.save_thresholds(an.Thresholds(vw, vc, tw, tc, cw, cc, nv))
            st.success("Limits saved.")
            st.rerun()
    if st.button("Reset to defaults"):
        db.save_thresholds(an.Thresholds())
        st.rerun()
    st.caption("Defaults are demonstration values only. Use the battery manufacturer's and BMS specifications for a real installation.")
