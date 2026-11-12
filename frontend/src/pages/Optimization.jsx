import React, { useState } from 'react';
import { useWorkspaceState } from '../components/WorkspaceState';
import ParetoSpace from '../components/ParetoSpace';
import { optimizeOperation, errorMessage } from '../services/industrial';

const format = (v, digits = 2) => Number(v).toLocaleString('en-US', { maximumFractionDigits: digits, minimumFractionDigits: digits });
const initial = { temperature: 32, tariff: .8, min_production_rate: 12, max_energy_kwh: 50 };
const defaultReference = { machine_load: .7, machine_speed: 1200, power_factor: .90 };
const presets = {
  balanced: { label: 'Balanced production', form: initial, weights: [1, 1, 1] },
  efficient: { label: 'Energy-conscious shift', form: { ...initial, min_production_rate: 15, max_energy_kwh: 30 }, weights: [3, 2, 1] },
  output: { label: 'High-output shift', form: { ...initial, min_production_rate: 30, max_energy_kwh: 45 }, weights: [1, 1, 3] },
};

function Field({ label, value, onChange, min, max }) {
  return <label className="field"><span>{label}</span><input type="number" required min={min} max={max} step="any" value={value} onChange={e => onChange(e.target.value === '' ? '' : Number(e.target.value))}/></label>;
}

function saveFile(text, name, type) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement('a');
  a.href = url; a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function exportCsv(points) {
  const keys = Object.keys(points[0]);
  const escape = value => `"${String(value ?? '').replaceAll('"', '""')}"`;
  saveFile('\uFEFF' + [keys.join(','), ...points.map(p => keys.map(k => escape(p[k])).join(','))].join('\n'), 'pareto-synthetic.csv', 'text/csv;charset=utf-8;');
}

function ChangeCards({ items, reference, point }) {
  return <div className="comparison-grid">{items.map(([label, key, unit]) => {
    const change = point[key] - reference[key];
    const percent = reference[key] !== 0 ? change/reference[key]*100 : null;
    const sign = change > 0 ? '+' : '';
    return <div className="comparison-card" key={key}><span>{label}</span><div><b>{format(reference[key])}</b><i>→</i><strong>{format(point[key])}</strong><small>{unit}</small></div><p>{sign}{format(change)} {unit}{percent !== null && ` (${sign}${format(percent, 1)}%)`}</p></div>;
  })}</div>;
}

function SameOutputBenchmark({ benchmark, reference }) {
  if (!benchmark) return null;
  const { status, candidate, target_production_rate, evaluated_points } = benchmark;
  return <section className="panel equal-output">
    <div className="panel-heading"><div><h2>Same-output benchmark</h2><p>Reference and alternative use the same output, tariff, temperature and interval.</p></div><span className="tag">MODELED COMPARISON</span></div>
    {status === 'ok' ? <>
      <ChangeCards reference={reference} point={{ ...candidate, cost_per_unit: candidate.cost/candidate.units_per_interval }}
        items={[[ 'Energy', 'energy_kwh', 'kWh' ], [ 'Total cost', 'cost', 'CU' ], [ 'Cost per unit', 'cost_per_unit', 'CU/unit' ]]}/>
      <p>Both settings deliver <strong>{format(target_production_rate)} units/h</strong>. The lowest-cost feasible alternative in the {evaluated_points.toLocaleString('en-US')}-point benchmark uses {format(candidate.machine_load*100, 1)}% load, {format(candidate.machine_speed, 0)} rpm and a power factor of {format(candidate.power_factor, 3)}.</p>
      <small>This fixed-output search is separate from the Pareto front. Results are simulation estimates, not measured factory savings.</small>
    </> : <p className="warning">{status === 'reference_below_minimum'
      ? `The reference produces ${format(target_production_rate)} units/h, below the scenario minimum.`
      : 'The reference exceeds the scenario energy limit.'} Edit the reference settings and run the scenario again to enable a like-for-like comparison.</p>}
  </section>;
}

function Comparison({ point, reference }) {
  return <section className="panel">
    <div className="panel-heading"><div><h2>Compare with the reference operating point</h2><p>Reference: {format(reference.machine_load*100, 1)}% load, {format(reference.machine_speed, 0)} rpm, power factor {format(reference.power_factor, 3)}.</p></div><span className="tag">{reference.feasible ? 'REFERENCE FEASIBLE' : 'REFERENCE OUTSIDE CONSTRAINTS'}</span></div>
    <ChangeCards point={point} reference={reference} items={[
      ['Energy', 'energy_kwh', 'kWh'], ['Total cost', 'cost', 'CU'], ['Production rate', 'production_rate', 'units/h'],
    ]}/>
    <p>Values are model estimates. If production differs, compare the same-output benchmark before drawing an efficiency conclusion.</p>
  </section>;
}

export default function Optimization() {
  const [form, setForm] = useWorkspaceState('optimization.form', initial);
  const [weights, setWeights] = useWorkspaceState('optimization.weights', [1, 1, 1]);
  const [result, setResult] = useWorkspaceState('optimization.result', null);
  const [selected, setSelected] = useWorkspaceState('optimization.selected', null);
  const [reference, setReference] = useWorkspaceState('optimization.reference', defaultReference);
  const [preset, setPreset] = useWorkspaceState('optimization.preset', 'balanced');
  const [busy, setBusy] = useWorkspaceState('optimization.busy', false);
  const [error, setError] = useWorkspaceState('optimization.error', '');
  const [sort, setSort] = useState('score');

  function invalidate() { setResult(null); setSelected(null); setError(''); }
  function update(key, value) { setForm(p => ({ ...p, [key]: value })); setPreset('custom'); invalidate(); }
  function applyPreset(key) {
    setPreset(key); setForm({ ...presets[key].form }); setWeights([...presets[key].weights]); invalidate();
  }
  async function submit(e) {
    e.preventDefault();
    if (weights.reduce((total, w) => total + Number(w), 0) <= 0) { setError('At least one preference weight must be greater than zero.'); return; }
    setBusy(true); invalidate();
    try { const response = await optimizeOperation({ ...form, weights, reference }); setResult(response); setSelected(response.recommended); }
    catch (e) { setError(errorMessage(e)); }
    finally { setBusy(false); }
  }

  return <>
    <form className="panel" onSubmit={submit}><fieldset disabled={busy}>
      <div className="panel-heading"><div><h2>Operating scenario & constraints</h2><p>Minimize energy and total cost; maximize production rate. Search load, speed and power factor.</p></div><span className="tag">NSGA-II</span></div>
      <label className="field preset-field"><span>Scenario preset</span><select value={preset} onChange={e => applyPreset(e.target.value)}>{preset === 'custom' && <option value="custom" disabled>Custom scenario</option>}{Object.entries(presets).map(([key, value]) => <option key={key} value={key}>{value.label}</option>)}</select></label>
      <div className="form-grid four">
        <Field label="Minimum production / units/h" min={1} max={45} value={form.min_production_rate} onChange={v => update('min_production_rate', v)}/>
        <Field label="Energy limit / kWh per 15 min" min={1} max={100} value={form.max_energy_kwh} onChange={v => update('max_energy_kwh', v)}/>
        <Field label="Tariff / CU per kWh" min={.01} max={10} value={form.tariff} onChange={v => update('tariff', v)}/>
        <Field label="Fixed ambient temperature / °C" min={20} max={45} value={form.temperature} onChange={v => update('temperature', v)}/>
      </div>
      <div className="opt-controls"><div className="weight-fields">{['Energy preference', 'Cost preference', 'Output preference'].map((label, i) => <Field key={label} label={label} min={0} max={10} value={weights[i]} onChange={v => { setWeights(weights.map((w, j) => i === j ? v : w)); setPreset('custom'); invalidate(); }}/>)}</div><button disabled={busy}>{busy ? 'Searching the Pareto front…' : 'Run optimization ↗'}</button></div>
      <p>Preferences rank the final solutions. Total cost includes electricity, simulated wear and power-factor compensation. CU is an illustrative currency unit.</p>
      <details className="reference-settings"><summary>Reference operating settings</summary>
        <p>Use the current settings to test a lower-cost alternative at the same production rate. This reference does not steer the Pareto search.</p>
        <div className="form-grid reference-fields">{[
          ['machine_load', 'Reference load / fraction', .25, 1], ['machine_speed', 'Reference speed / rpm', 600, 1800],
          ['power_factor', 'Reference power factor', .80, .99],
        ].map(([key, label, min, max]) => <Field key={key} label={label} min={min} max={max} value={reference[key]} onChange={v => { setReference(previous => ({ ...previous, [key]: v })); invalidate(); }}/>)}</div>
      </details>
      {error && <div className="error" role="alert">{error}</div>}
    </fieldset></form>
    {busy && <div className="progress-note" role="status"><span className="activity-dot"/> Evaluating operating points across three objectives. You can switch pages while this runs.</div>}
    {result?.status === 'no_feasible_solution' && <div className="warning" role="status">{result.message}</div>}
    {result?.pareto?.length > 0 && selected ? <>
      <div className="result-toolbar"><span>{result.pareto.length} solutions · {result.request.population} individuals × {result.request.generations} generations · Seed {result.request.seed} · {format(result.elapsed_seconds)} s</span><button className="secondary" onClick={() => saveFile(JSON.stringify({ ...result, selected_point: selected, disclaimer: 'Synthetic operating model. Not measured industrial savings.' }, null, 2), 'optimization-report.json', 'application/json')}>Download run report ↗</button></div>
      <div className="two-col pareto-layout"><section className="panel">
        <div className="panel-heading"><div><h2>3D Pareto Front</h2><p>Explore feasible trade-offs across energy, cost and production rate.</p></div><button className="secondary" onClick={() => exportCsv(result.pareto)}>Export CSV ↗</button></div>
        <ParetoSpace points={result.pareto} recommended={result.recommended} selected={selected} onSelect={setSelected}/>
      </section><section className="panel">
        <span className="tag">{selected.id === result.recommended.id ? 'RECOMMENDED' : 'SELECTED POINT'}</span>
        <h2 className="spaced">{selected.id === result.recommended.id ? 'Recommended operating point' : `Candidate #${selected.id}`}</h2>
        <div className="hero-number">{format(selected.energy_kwh)}<small> kWh / 15 min</small></div>
        <dl className="point-details">{[
          ['Total cost', `${format(selected.cost)} CU`], ['Production rate', `${format(selected.production_rate)} units/h`],
          ['Machine load', `${format(selected.machine_load*100, 1)}%`], ['Machine speed', `${format(selected.machine_speed, 0)} rpm`],
          ['Power factor', format(selected.power_factor, 3)], ['Electricity / wear / compensation', `${format(selected.electricity_cost)} / ${format(selected.wear_cost)} / ${format(selected.correction_cost)} CU`],
        ].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
        <p>Recommendation: closest to the normalized ideal point under your preference weights. It is not a guarantee of the best real-world operating setting.</p>
        <button className="secondary" onClick={() => setSelected(result.recommended)}>Show recommendation</button>
      </section></div>
      {result.reference && <SameOutputBenchmark benchmark={result.same_output_benchmark}
        reference={{ ...result.reference, cost_per_unit: result.reference.cost/result.reference.units_per_interval }}/>}
      {result.reference && <Comparison point={selected} reference={result.reference}/>}
      <section className="panel"><div className="panel-heading"><h2>Candidate operating points</h2><label className="field"><span>Sort candidates</span><select value={sort} onChange={e => setSort(e.target.value)}><option value="score">Recommendation score</option><option value="energy_kwh">Lowest energy</option><option value="cost">Lowest cost</option><option value="production_rate">Highest production</option></select></label></div>
        <div className="table-scroll"><table><thead><tr>{['Point', 'Energy kWh', 'Cost CU', 'Output u/h', 'Load %', 'Speed rpm', 'Power factor'].map(v => <th key={v}>{v}</th>)}</tr></thead><tbody>{result.pareto.slice().sort((a, b) => sort === 'production_rate' ? b[sort]-a[sort] : a[sort]-b[sort]).slice(0, 12).map(point => <tr key={point.id} className={point.id === selected.id ? 'selected-row' : ''}><td><button className="table-button" onClick={() => setSelected(point)}>{point.id === result.recommended.id ? '★ Recommended' : `#${point.id}`}</button></td><td>{format(point.energy_kwh)}</td><td>{format(point.cost)}</td><td>{format(point.production_rate)}</td><td>{format(point.machine_load*100, 1)}</td><td>{format(point.machine_speed, 0)}</td><td>{format(point.power_factor, 3)}</td></tr>)}</tbody></table></div><small>Showing the first 12 points in the selected order. The CSV and run report include every solution.</small>
      </section>
    </> : !busy && !result && <section className="panel empty"><div>⤴</div><h2>Balance energy and production</h2><p>Choose a scenario or enter your constraints, then run optimization.</p></section>}
  </>;
}
