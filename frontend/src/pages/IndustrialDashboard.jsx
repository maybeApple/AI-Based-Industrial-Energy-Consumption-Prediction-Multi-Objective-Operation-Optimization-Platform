import React, { useEffect, useState } from 'react';
import IndustrialChart from '../components/IndustrialChart';
import { getSummary, getHistory, getRealBenchmarks, predictOperation, errorMessage } from '../services/industrial';
import '../industrial.css';
import Optimization from './Optimization';
import NeuralControl from './NeuralControl';
import { useWorkspaceState } from '../components/WorkspaceState';

const tabs = [['overview', '◫', 'Overview'], ['predict', '⌁', 'Energy Prediction'], ['optimize', '⤴', 'Optimization'], ['control', '⟳', 'Neural Control'], ['history', '▤', 'History & Equipment'], ['steel', '◇', 'Real-data Validation']];
const defaults = { machine_load: .7, machine_speed: 1200, temperature: 32, power_factor: .9 };
const tabFromHash = () => tabs.some(t => t[0] === window.location.hash.slice(1)) ? window.location.hash.slice(1) : 'overview';
const number = (v, d = 2) => Number(v).toLocaleString('en-US', { maximumFractionDigits: d, minimumFractionDigits: d });
function Metric({ label, value, unit, detail }) { return <div className="metric"><span>{label}</span><div><strong>{value}</strong> <small>{unit}</small></div><p>{detail}</p></div>; }
function Field({ label, value, onChange, min, max, step = 'any' }) { return <label className="field"><span>{label}</span><input type="number" required min={min} max={max} step={step} value={value} onChange={e => onChange(e.target.value === '' ? '' : Number(e.target.value))}/></label>; }
function Download({ data, name, label = 'Export CSV' }) {
  function download() {
    if (!data?.length) return;
    const keys = Object.keys(data[0]);
    const csv = '\uFEFF' + [keys.join(','), ...data.map(r => keys.map(k => '"' + String(r[k] ?? '').replaceAll('"', '""') + '"').join(','))].join('\n');
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8;' }));
    const a = document.createElement('a'); a.href = url; a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return <button className="secondary" disabled={!data?.length} onClick={download}>{label} ↗</button>;
}

export default function IndustrialDashboard() {
  const [tab, setActiveTab] = useState(tabFromHash);
  function setTab(key) { window.location.hash = key; setActiveTab(key); }
  useEffect(() => {
    const onHashChange = () => setActiveTab(tabFromHash());
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, []);
  const [summary, setSummary] = useState(null), [history, setHistory] = useState([]), [benchmarks, setBenchmarks] = useState([]);
  const [error, setError] = useState(''), [loading, setLoading] = useState(false);
  async function load() {
    setLoading(true); setError('');
    try { const [s, h, real] = await Promise.all([getSummary(), getHistory(), getRealBenchmarks()]); setSummary(s); setHistory(h.rows); setBenchmarks(real.benchmarks); }
    catch (e) { setError(errorMessage(e)); } finally { setLoading(false); }
  }
  useEffect(() => { load(); }, []);
  return <div className="industrial-app">
    <aside className="sidebar"><div className="brand"><b className="brand-symbol">E</b><div>ENERGY<span>INDUSTRIAL INTELLIGENCE</span></div></div>
      <p className="nav-caption">WORKSPACE / V1.2</p><nav>{tabs.map(([key, icon, title]) => <button key={key} className={tab === key ? 'active' : ''} onClick={() => setTab(key)}><i>{icon}</i>{title}{tab === key && <b>›</b>}</button>)}</nav>
      <div className="sidebar-bottom"><span className="status-dot"/> Offline demo workspace<p>No hardware · Local inference</p><small>Based on EnergyOpt</small></div>
    </aside>
    <main className="workspace"><header className="topbar"><span>Industrial AI <em>/</em> {tabs.find(t => t[0] === tab)[2]}</span><span className="version">V1.2 <span className="status-dot"/> {summary ? 'Models ready' : 'Awaiting service'}</span></header>
      <div className="page"><div className="page-heading"><div><div className="eyebrow">ENERGY & OPERATIONS</div><h1>{tabs.find(t => t[0] === tab)[2]}</h1><p>AI-Based Industrial Energy Consumption Prediction and Multi-Objective Operation Optimization</p></div><button className="secondary" onClick={load} disabled={loading}>{loading ? 'Loading…' : 'Refresh data ↻'}</button></div>
        <div className="source-note"><span>DATA SOURCE</span>{tab === 'steel' ? 'Measured industrial electricity · Independent chronological evaluations · 15-minute one-step forecasts' : tab === 'control' ? 'Dynamic simulated plant · Trained ANN dynamics · Simulated feedback at every control step · No hardware' : 'Simulated operations · SIM-ROLL-01 · 15-minute intervals · Offline decision support'}</div>
        {error && <div className="error" role="alert">{error}</div>}
        {!summary && <section className="panel"><h2>{loading ? 'Connecting to models and data…' : 'Waiting for the API'}</h2><p>Start the API, then select Refresh data.</p></section>}
        {summary && tab === 'overview' && <>
          <div className="metrics"><Metric label="Energy · last 24 hours" value={number(summary.last_24h_energy_kwh)} unit="kWh" detail="Historical total · Simulated operations"/><Metric label="Output · last 24 hours" value={number(summary.last_24h_units)} unit="units" detail="Production rate × 0.25 hours per interval"/><Metric label="Test prediction error" value={number(summary.metrics.mae_kwh)} unit="kWh MAE" detail="Chronological holdout · LightGBM"/><Metric label="Anomaly candidates" value={summary.last_24h_anomalies} unit="/ 96 readings" detail="Isolation Forest + residual rule · Review needed"/></div>
          <section className="panel"><div className="panel-heading"><div><h2>Energy consumption & predictions</h2><p>Last 24 hours · Test-set replay · kWh / 15 min</p></div><span className="tag">LIGHTGBM</span></div><IndustrialChart rows={history}/></section>
          <div className="two-col"><section className="panel"><h2>Test an operating decision before changing settings</h2><div className="steps">Forecast energy <b>→</b> Compare operating points <b>→</b> Simulate control</div><p>Explore three objectives together, benchmark costs at the same output, and export the settings and assumptions behind each result.</p><button onClick={() => setTab('optimize')}>Explore optimization <span>↗</span></button></section><section className="panel"><h2>Equipment snapshot · {summary.machine.id}</h2><p>Historical simulation / {summary.latest_timestamp}</p><div className="device-stats"><span>Load <b>{number(summary.machine.machine_load*100, 1)}%</b></span><span>Speed <b>{number(summary.machine.machine_speed, 0)} rpm</b></span><span>Temperature <b>{number(summary.machine.temperature, 1)} °C</b></span></div><small>This is a historical simulation, not live telemetry.</small></section></div>
        </>}
        {summary && tab === 'predict' && <Prediction metrics={summary.metrics}/>}
        {summary && tab === 'optimize' && <Optimization/>}
        {summary && tab === 'control' && <NeuralControl/>}
        {summary && tab === 'history' && <History summary={summary}/>}
        {summary && tab === 'steel' && <RealDataValidation benchmarks={benchmarks}/>}
        <footer>INDUSTRIAL ENERGY LAB <span>Predict consumption · Compare operating choices · Keep data provenance visible</span></footer>
      </div>
    </main>
  </div>;
}

function Prediction({ metrics }) {
  const [point, setPoint] = useWorkspaceState('prediction.point', defaults);
  const [observed, setObserved] = useWorkspaceState('prediction.observed', '');
  const [result, setResult] = useWorkspaceState('prediction.result', null);
  const [busy, setBusy] = useWorkspaceState('prediction.busy', false);
  const [error, setError] = useWorkspaceState('prediction.error', '');
  function update(k, v) { setPoint(p => ({ ...p, [k]: v })); setResult(null); }
  async function submit(e) { e.preventDefault(); setBusy(true); setError(''); setResult(null); try { setResult(await predictOperation({ ...point, energy_kwh: observed === '' ? null : Number(observed) })); } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); } }
  return <><div className="two-col"><form className="panel" onSubmit={submit}><fieldset disabled={busy}><h2>Plan an operating point</h2><p>Estimate energy for one 15-minute interval. Production rate is derived from the demonstration capacity model.</p><div className="form-grid">
    <Field label="Machine load / 0–1" value={point.machine_load} min={.25} max={1} onChange={v => update('machine_load', v)}/><Field label="Machine speed / rpm" value={point.machine_speed} min={600} max={1800} onChange={v => update('machine_speed', v)}/><Field label="Ambient temperature / °C" value={point.temperature} min={20} max={45} onChange={v => update('temperature', v)}/><Field label="Power factor / 0–1" value={point.power_factor} min={.8} max={.99} onChange={v => update('power_factor', v)}/>
    <label className="field"><span>Observed energy / kWh (optional anomaly check)</span><input type="number" min="0" max="500" step="any" value={observed} placeholder="Not used as a prediction feature" onChange={e => { setObserved(e.target.value); setResult(null); }}/></label></div><button disabled={busy}>{busy ? 'Predicting…' : 'Predict energy →'}</button>{error && <div className="error" role="alert">{error}</div>}</fieldset></form>
    <section className="panel prediction-result"><span className="tag">OPERATING POINT PREDICTION</span>{result ? <><p>Predicted energy / 15 minutes</p><div className="hero-number">{number(result.predicted_energy_kwh)}<small> kWh</small></div><div className="interval">90% nominal prediction interval <b>{number(result.lower_kwh)} – {number(result.upper_kwh)} kWh</b></div><p>Derived production rate <strong>{number(result.operating_point.production_rate)} units/h</strong></p><div className={result.anomaly ? 'warning' : 'success'}>{result.anomaly === null ? 'No observed energy provided; anomaly check not run.' : result.anomaly ? 'Anomaly candidate detected. Review this operating point.' : 'No anomaly candidate detected.'}</div></> : <div className="empty"><div>⌁</div><h2>Explore energy at different operating points</h2><p>Enter operating parameters to see a prediction and optional anomaly check.</p></div>}</section></div>
    <div className="metrics"><Metric label="MAE" value={number(metrics.mae_kwh, 3)} unit="kWh" detail="Synthetic test set"/><Metric label="RMSE" value={number(metrics.rmse_kwh, 3)} unit="kWh" detail="Synthetic test set"/><Metric label="R²" value={number(metrics.r2, 4)} detail="Coefficient of determination on the test set"/><Metric label="Observed interval coverage" value={number(metrics.interval_coverage*100, 1)} unit="%" detail="Calibrated separately; evaluated on the test set"/></div></>;
}

function History({ summary }) {
  const [data, setData] = useState(null), [error, setError] = useState('');
  const [offset, setOffset] = useWorkspaceState('history.offset', 0);
  const [only, setOnly] = useWorkspaceState('history.only', false);
  useEffect(() => { let active = true; setError(''); setData(null); getHistory({ limit: 48, offset, anomalies_only: only }).then(d => { if (active) setData(d); }).catch(e => { if (active) setError(errorMessage(e)); }); return () => { active = false; }; }, [offset, only]);
  return <><section className="panel"><div className="panel-heading"><div><h2>{summary.machine.id} / Simulated rolling machine</h2><p>Historical replay · Latest reading {summary.latest_timestamp} · No hardware connection</p></div><span className="tag">SIMULATED</span></div><div className="device-stats"><span>Load <b>{number(summary.machine.machine_load*100)}%</b></span><span>Speed <b>{number(summary.machine.machine_speed, 0)} rpm</b></span><span>Power factor <b>{number(summary.machine.power_factor, 3)}</b></span></div></section><section className="panel"><div className="panel-heading"><h2>Operating history</h2><div className="inline-controls"><label><input type="checkbox" checked={only} onChange={e => { setOnly(e.target.checked); setOffset(0); }}/> Anomaly candidates only</label><Download data={data?.rows} name="industrial-history-page.csv" label="Export this page"/></div></div>{error && <div className="error">{error}</div>}<div className="table-scroll"><table><thead><tr>{['Timestamp', 'Load %', 'Speed rpm', 'Output u/h', 'Temperature °C', 'Power factor', 'Energy kWh', 'Status', 'Data split'].map(v => <th key={v}>{v}</th>)}</tr></thead><tbody>{data?.rows.slice().reverse().map(r => <tr key={r.timestamp}><td>{r.timestamp}</td><td>{number(r.machine_load*100, 1)}</td><td>{number(r.machine_speed, 0)}</td><td>{number(r.production_rate)}</td><td>{number(r.temperature, 1)}</td><td>{number(r.power_factor, 3)}</td><td>{number(r.energy_kwh)}</td><td><span className={r.anomaly ? 'anomaly-badge' : 'normal-badge'}>{r.anomaly ? 'Review' : 'Normal'}</span></td><td>{r.evaluation_split}</td></tr>)}</tbody></table></div>{!data && !error && <p>Loading readings…</p>}{data?.rows.length === 0 && <p>No readings match this filter.</p>}<div className="pagination"><span>{data ? `${data.total} readings / Page ${Math.floor(offset/48)+1}` : 'Loading'}</span><button className="secondary" disabled={offset === 0 || !data} onClick={() => setOffset(offset-48)}>Previous</button><button className="secondary" disabled={!data || offset+48 >= data.total} onClick={() => setOffset(offset+48)}>Next</button></div></section></>;
}

const benchmarkStyles = {
  actual: { name: 'Measured energy', color: '#4cd6b3' },
  forecast: { color: '#a2b0ff' },
  persistence: { color: '#a0adbc', dash: '3 4' },
  legacy: { color: '#f6ac72', dash: '5 4' },
  daily: { color: '#f6ac72', dash: '5 4' },
};

function RealDataValidation({ benchmarks }) {
  const [selected, setSelected] = useWorkspaceState('benchmarks.selected', 'steel');
  const [extras, setExtras] = useWorkspaceState('benchmarks.extraSeries', {});
  const [windows, setWindows] = useWorkspaceState('benchmarks.windows', {});
  const benchmark = benchmarks.find(item => item.id === selected) ?? benchmarks[0];
  if (!benchmark) return <section className="panel"><h2>Real-data benchmarks not prepared</h2><p>Follow the measured-data training guide in the README, then refresh this page.</p></section>;
  const { id, models, test_rows, source_rows } = benchmark;
  const shown = benchmark.windows.find(window => window.key === (windows[id] ?? benchmark.default_window)) ?? benchmark.windows[0];
  const chartError = value => value == null ? '—' : value > 0 && value < .001 ? '<0.001' : number(value, 3);
  const forecastModel = models.find(model => model.key === 'forecast');
  const persistence = models.find(model => model.key === 'persistence');
  const showExtra = Boolean(extras[id]);
  const extra = models.find(model => !['forecast', 'persistence'].includes(model.key));
  const lines = [{ key: 'actual', ...benchmarkStyles.actual }, ...models
    .filter(model => model.key !== extra?.key || showExtra)
    .map(model => ({ key: model.key, name: model.label, ...benchmarkStyles[model.key] }))];
  return <>
    <section className="panel"><div className="panel-heading">
      <div><h2>Measured energy benchmarks</h2><p>Each source is trained and tested separately. Compare models within the same site and asset.</p></div>
      <label className="field"><span>Measured dataset</span><select value={id} onChange={event => setSelected(event.target.value)}>
        {benchmarks.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}
      </select></label>
    </div></section>
    <div className="metrics">
      <Metric label="Source readings" value={number(source_rows, 0)} detail={benchmark.asset_scope}/>
      <Metric label="Scored test intervals" value={number(test_rows, 0)} detail="Chronological holdout"/>
      <Metric label={forecastModel.label + ' MAE'} value={number(forecastModel.test.mae_kwh, 3)} unit="kWh" detail="Full test period"/>
      <Metric label="Last-reading baseline MAE" value={number(persistence.test.mae_kwh, 3)} unit="kWh" detail="Same test intervals"/>
    </div>
    <section className="panel">
      <div className="panel-heading"><div><h2>{benchmark.chart_title}</h2><p>{shown.scored_rows} scored intervals · {benchmark.time_zone}</p></div>
        <label className="field"><span>Chart window</span><select value={shown.key} onChange={event => {
          const key = event.target.value; setWindows(previous => ({ ...previous, [id]: key }));
        }}>{benchmark.windows.map(window => <option key={window.key} value={window.key}>{window.label}</option>)}</select></label>
      </div>
      {extra && <div className="inline-controls"><label><input type="checkbox" checked={showExtra}
        onChange={event => { const checked = event.target.checked; setExtras(previous => ({ ...previous, [id]: checked })); }}/> Show {extra.label.toLowerCase()}</label></div>}
      <IndustrialChart key={id + '-' + shown.key} rows={shown.history} series={lines} timeZone={benchmark.time_zone}/>
      <Download data={shown.history} name={id + '-' + shown.key + '-48h-comparison.csv'} label="Export forecast comparison"/>
    </section>
    <section className="panel"><h2>Forecast accuracy</h2><p>Lower is better. The 48-hour chart is a diagnostic slice; it is separate from full-test performance.</p>
      <div className="table-scroll"><table><thead><tr><th>Method</th><th>Test MAE (kWh)</th><th>Test RMSE (kWh)</th><th>Largest test error (kWh)</th><th>Chart MAE (kWh)</th></tr></thead>
        <tbody>{models.map(model => <tr key={model.key}><td>{model.label}</td><td>{number(model.test.mae_kwh, 3)}</td>
          <td>{number(model.test.rmse_kwh, 3)}</td><td>{number(model.test.max_absolute_error_kwh, 3)}</td>
          <td>{chartError(shown.mae[model.key])}</td></tr>)}</tbody>
      </table></div>
    </section>
    <section className="panel"><h2>Evaluation scope & provenance</h2>
      <p>Training ends: {benchmark.training_end}; testing starts: {benchmark.test_start} ({benchmark.time_zone}). Forecasts use previously observed readings to predict the next 15 minutes.</p>
      {benchmark.notes.map(note => <p key={note}>{note}</p>)}
      <p><a href={benchmark.source_url} target="_blank" rel="noreferrer">{benchmark.source_label} ↗</a> · {benchmark.attribution}</p>
      <p>Measured-data results validate forecasting only. The Pareto optimizer and ANN control still use simulation.</p>
    </section>
  </>;
}
