import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { api } from "./api";

const usd = (n) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(n ?? 0);

const RULES = {
  idle: "Idle",
  rightsize: "Underused",
  orphaned: "Unattached",
  spike: "Cost spike",
};

const COLORS = { spend: "#1d5b79", waste: "#c8432b", grid: "#d5dde3", muted: "#5d6d79" };

export default function App() {
  const [summary, setSummary] = useState(null);
  const [daily, setDaily] = useState([]);
  const [breakdown, setBreakdown] = useState([]);
  const [by, setBy] = useState("team");
  const [recs, setRecs] = useState([]);
  const [resources, setResources] = useState([]);
  const [rule, setRule] = useState("all");
  const [view, setView] = useState("findings");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      setError("");
      const [s, d, r, inv] = await Promise.all([
        api.summary(), api.daily(), api.recommendations(), api.resources(),
      ]);
      setSummary(s); setDaily(d); setRecs(r); setResources(inv);
    } catch (e) {
      setError(`${e.message}. Check that the API is running on port 8000.`);
    }
  }, []);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { api.breakdown(by).then(setBreakdown).catch(() => {}); }, [by]);

  const act = (fn) => async () => {
    setBusy(true);
    try { await fn(); await load(); api.breakdown(by).then(setBreakdown); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  };

  const shown = useMemo(() => recs.filter((r) => rule === "all" || r.rule === rule), [recs, rule]);
  const maxSave = Math.max(1, ...recs.map((r) => r.monthly_savings));

  return (
    <div className="page">
      <header className="top">
        <div>
          <h1>Cloud cost optimizer</h1>
          <p className="sub">Last 30 days of usage across your accounts</p>
        </div>
        <div className="actions">
          <button className="ghost" disabled={busy} onClick={act(api.reseed)}>Load sample data</button>
          <button disabled={busy} onClick={act(api.analyze)}>{busy ? "Working…" : "Run analysis"}</button>
        </div>
      </header>

      {error && <div className="error" role="alert">{error}</div>}

      <section className="ledger" aria-label="Key figures">
        <Figure label="Spend, last 30 days" value={usd(summary?.spend_30d)} />
        <Figure label="Recoverable per month" value={usd(summary?.potential_savings)} tone="waste"
                note={summary ? `${summary.savings_pct}% of spend` : ""} />
        <Figure label="Open findings" value={summary?.findings ?? "–"} />
        <Figure label="Resources tracked" value={summary?.resources ?? "–"} />
      </section>

      <section className="charts">
        <div className="panel wide">
          <h2>Daily spend</h2>
          <ResponsiveContainer width="100%" height={260}>
            <AreaChart data={daily} margin={{ left: 0, right: 8, top: 8 }}>
              <CartesianGrid stroke={COLORS.grid} vertical={false} />
              <XAxis dataKey="date" tickFormatter={(d) => d.slice(5, 10)} stroke={COLORS.muted} tickLine={false} />
              <YAxis tickFormatter={(v) => `$${v}`} stroke={COLORS.muted} tickLine={false} axisLine={false} width={56} />
              <Tooltip formatter={(v) => [usd(v), "Spend"]} labelFormatter={(d) => d.slice(0, 10)} />
              <Area dataKey="cost" stroke={COLORS.spend} fill={COLORS.spend} fillOpacity={0.14} strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        <div className="panel">
          <div className="panel-head">
            <h2>Spend by</h2>
            <div className="seg" role="tablist">
              {["team", "type", "region"].map((k) => (
                <button key={k} role="tab" aria-selected={by === k}
                        className={by === k ? "on" : ""} onClick={() => setBy(k)}>{k}</button>
              ))}
            </div>
          </div>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={breakdown} layout="vertical" margin={{ left: 8, right: 16 }}>
              <XAxis type="number" hide />
              <YAxis type="category" dataKey="name" width={92} stroke={COLORS.muted} tickLine={false} axisLine={false} />
              <Tooltip formatter={(v) => [usd(v), "Spend"]} cursor={{ fill: "#eef2f5" }} />
              <Bar dataKey="cost" fill={COLORS.spend} radius={[0, 4, 4, 0]} barSize={16} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>

      <section className="panel table-panel">
        <div className="panel-head">
          <div className="seg">
            <button className={view === "findings" ? "on" : ""} onClick={() => setView("findings")}>Findings</button>
            <button className={view === "inventory" ? "on" : ""} onClick={() => setView("inventory")}>Inventory</button>
          </div>
          {view === "findings" && (
            <div className="seg">
              {["all", ...Object.keys(RULES)].map((k) => (
                <button key={k} className={rule === k ? "on" : ""} onClick={() => setRule(k)}>
                  {k === "all" ? "All" : RULES[k]}
                </button>
              ))}
            </div>
          )}
        </div>

        {view === "findings" ? (
          shown.length === 0 ? (
            <p className="empty">No findings yet. Select “Run analysis” to scan your resources.</p>
          ) : (
            <div className="scroll">
              <table>
                <thead><tr><th>Resource</th><th>Finding</th><th>Why</th><th className="num">Saves / month</th></tr></thead>
                <tbody>
                  {shown.map((r) => (
                    <tr key={r.id}>
                      <td><strong>{r.name}</strong><span className="meta">{r.type} · {r.team} · {r.region}</span></td>
                      <td><span className={`chip ${r.rule}`}>{RULES[r.rule]}</span></td>
                      <td className="why">{r.reason}</td>
                      <td className="num">
                        {r.monthly_savings > 0 ? (
                          <>
                            <span>{usd(r.monthly_savings)}</span>
                            <span className="bar"><i style={{ width: `${(r.monthly_savings / maxSave) * 100}%` }} /></span>
                          </>
                        ) : "–"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        ) : (
          <div className="scroll">
            <table>
              <thead><tr><th>Resource</th><th>Type</th><th>Size</th><th>Team</th><th className="num">Avg CPU</th><th className="num">30-day cost</th></tr></thead>
              <tbody>
                {resources.map((r) => (
                  <tr key={r.id}>
                    <td><strong>{r.name}</strong><span className="meta">{r.id}</span></td>
                    <td>{r.type}</td><td>{r.size}</td><td>{r.team}</td>
                    <td className="num">{r.cpu_avg == null ? "–" : `${r.cpu_avg}%`}</td>
                    <td className="num">{usd(r.cost_30d)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

function Figure({ label, value, note, tone }) {
  return (
    <div className="figure">
      <span className="label">{label}</span>
      <span className={`value ${tone || ""}`}>{value}</span>
      {note && <span className="note">{note}</span>}
    </div>
  );
}
