import React, { useEffect, useState } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ReferenceLine, ResponsiveContainer } from 'recharts';
import { useWorkspaceState } from '../components/WorkspaceState';
import { getNeuralModel, runNeuralControl, stepNeuralControl, errorMessage } from '../services/industrial';
import '../neural-control.css';

const defaults = { target:22, target_after:28, steps:36, target_step:10, disturbance_step:20,
  disturbance_enabled:true, material_factor:.82, ambient:30, tariff:.8, max_energy_kwh:45,
  max_temperature:55, energy_weight:.5, horizon:5, samples:128, iterations:3, seed:42 };
const initialState = [.7,1200,.9,40,21,21];
const initialManual = { state:initialState, command:initialState.slice(0,3), rows:[] };
const format = (v,d=2) => Number(v).toLocaleString('en-US',{ minimumFractionDigits:d, maximumFractionDigits:d });
const names = ['Machine load','Machine speed','Power factor','Process temperature','Production rate','Interval energy'];
const units = ['ratio','rpm','ratio','°C','units/h','kWh'];

function Field({ label,value,min,max,step='any',onChange }) {
  return <label className="field"><span>{label}</span><input type="number" required min={min} max={max} step={step} value={value} onChange={e=>onChange(e.target.value===''?'':Number(e.target.value))}/></label>;
}

function saveReport(result) {
  const url=URL.createObjectURL(new Blob([JSON.stringify(result,null,2)],{type:'application/json'}));
  const link=document.createElement('a'); link.href=url; link.download='neural-control-run.json'; link.click();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
}

function ControlChart({ rows,series,limit,limitName='Limit',events=false,settings }) {
  return <div className="chart"><ResponsiveContainer width="100%" height="100%"><LineChart data={rows} margin={{top:20,right:20,bottom:5,left:0}}>
    <CartesianGrid stroke="#263746" strokeDasharray="3 5" vertical={false}/>
    <XAxis dataKey="step" tick={{fill:'#8397aa',fontSize:11}} name="Interval"/><YAxis tick={{fill:'#8397aa',fontSize:11}} width={45}/>
    <Tooltip contentStyle={{background:'#14212c',border:'1px solid #35495b'}} labelFormatter={v=>`Interval ${v}`} formatter={(v,n)=>[format(v),n]}/><Legend/>
    {series.map(([key,label,color,dash])=><Line key={key} dataKey={key} name={label} stroke={color} strokeWidth={2} strokeDasharray={dash} dot={false} isAnimationActive={false}/>)}
    {limit!==undefined&&<ReferenceLine y={limit} stroke="#edb064" strokeDasharray="4 4" label={{value:limitName,fill:'#edb064',position:'insideTopRight',fontSize:10}}/>}
    {events&&<ReferenceLine x={settings.target_step+1} stroke="#5d8297" strokeDasharray="3 3" label={{value:'Setpoint',fill:'#96acbe',fontSize:10,position:'insideTopLeft'}}/>}
    {events&&settings.disturbance_enabled&&<ReferenceLine x={settings.disturbance_step+1} stroke="#edb064" strokeDasharray="3 3" label={{value:'Disturbance',fill:'#edb064',fontSize:10,position:'insideTopRight'}}/>}
  </LineChart></ResponsiveContainer></div>;
}

export default function NeuralControl() {
  const [model,setModel]=useState(null), [modelError,setModelError]=useState('');
  const [form,setForm]=useWorkspaceState('control.form',defaults);
  const [result,setResult]=useWorkspaceState('control.result',null);
  const [busy,setBusy]=useWorkspaceState('control.busy',false);
  const [error,setError]=useWorkspaceState('control.error','');
  const [manual,setManual]=useWorkspaceState('control.manual',initialManual);
  const [manualTarget,setManualTarget]=useWorkspaceState('control.manualTarget',28);
  const [manualDisturbed,setManualDisturbed]=useWorkspaceState('control.manualDisturbed',false);
  const [mode,setMode]=useWorkspaceState('control.mode','experiment');
  const [cursor,setCursor]=useWorkspaceState('control.cursor',35);
  const [playing,setPlaying]=useState(false);

  useEffect(()=>{ let active=true; getNeuralModel().then(m=>{if(active)setModel(m);}).catch(e=>{if(active)setModelError(errorMessage(e));}); return()=>{active=false;}; },[]);
  useEffect(()=>{ if(!playing||!result)return; if(cursor>=result.rows.length-1){setPlaying(false);return;} const timer=setTimeout(()=>setCursor(cursor+1),350); return()=>clearTimeout(timer); },[playing,result,cursor]);
  function update(key,value) {setForm(f=>({...f,[key]:value}));setResult(null);setPlaying(false);setError('');}
  async function run(e) {
    e.preventDefault();setBusy(true);setError('');setResult(null);setPlaying(false);
    try{const run=await runNeuralControl(form);setResult(run);setCursor(run.rows.length-1);}catch(e){setError(errorMessage(e));}finally{setBusy(false);}
  }
  async function advance(e) {
    e.preventDefault();setBusy(true);setError('');
    try{const next=await stepNeuralControl({state:manual.state,previous_command:manual.command,target:Number(manualTarget),
      ambient:Number(form.ambient)+(manualDisturbed?3:0),material_factor:manualDisturbed?Number(form.material_factor):1,
      tariff:Number(form.tariff)*(manualDisturbed?1.35:1),max_energy_kwh:Number(form.max_energy_kwh),max_temperature:Number(form.max_temperature),
      energy_weight:Number(form.energy_weight),horizon:Number(form.horizon),samples:Number(form.samples),iterations:Number(form.iterations),seed:Number(form.seed)+manual.rows.length});
      setManual(previous=>({state:next.measured_next_state,command:next.action,rows:[...previous.rows,{...next.row,step:previous.rows.length+1,minutes:(previous.rows.length+1)*15}]}));
    }catch(e){setError(errorMessage(e));}finally{setBusy(false);}
  }

  const m=model?.metrics;
  const current=result?.rows[Math.min(cursor,result.rows.length-1)];
  const chartRows=result?.rows.slice(0,cursor+1).map((r,i)=>({...r,baseline_production:result.baseline_rows[i].production_rate,baseline_energy:result.baseline_rows[i].energy_kwh}));
  return <>
    <section className="panel"><div className="panel-heading"><div><h2>Deep artificial neural network + feedback control</h2><p>The ANN predicts next states. MPC plans bounded actuator moves. The plant executes one move and returns a new measurement.</p></div><span className="tag">ANN + MPC</span></div>
      <div className="control-flow"><span>Measured state</span><b>→</b><span>Deep ANN model</span><b>→</b><span>MPC action</span><b>→</b><span>Dynamic plant</span><b>↺</b></div>
      {modelError&&<div className="error" role="alert">{modelError}</div>}
      {m?<><div className="neural-architecture">{m.architecture.map((width,i)=><React.Fragment key={i}>{i>0&&<i>→</i>}<span><b>{width}</b><small>{i===0?'Inputs':i===m.architecture.length-1?'Outputs':`Hidden ${i}`}</small></span></React.Fragment>)}<p>ReLU · Adam · {format(m.parameter_count,0)} trained parameters</p></div>
        <div className="neural-metrics"><span>Held-out energy MAE <b>{format(m.mae.energy_kwh,3)} kWh</b></span><span>Held-out production MAE <b>{format(m.mae.production_rate,3)} units/h</b></span><span>Training / test transitions <b>{format(m.train_rows,0)} / {format(m.test_rows,0)}</b></span></div><small>Independent simulated trajectories held out for testing. These metrics describe the dynamic ANN; the steel-data benchmark remains a separate experiment.</small>
        <details className="control-details"><summary>ANN validation and model comparison</summary><div className="table-scroll"><table><thead><tr><th>Held-out MAE</th><th>Deep ANN</th><th>LightGBM</th><th>Persistence</th></tr></thead><tbody>{[['energy_kwh','Energy / kWh'],['production_rate','Production / units/h'],['process_temperature','Temperature / °C']].map(([key,label])=><tr key={key}><td>{label}</td><td>{format(m.mae[key],3)}</td><td>{format(m.lightgbm_comparison_mae?.[key],3)}</td><td>{format(m.persistence_mae[key],3)}</td></tr>)}</tbody></table></div><p>Five-step recursive prediction MAE: energy {format(m.recursive_test_rollout?.at(-1).energy_mae_kwh,3)} kWh; production {format(m.recursive_test_rollout?.at(-1).production_mae,3)} units/h. No measurement correction is injected inside those test windows.</p></details>
        </>:<p>Loading trained neural model…</p>}
    </section>
    <div className="control-mode" role="group" aria-label="Control mode"><button className={mode==='experiment'?'':'secondary'} onClick={()=>{setMode('experiment');setPlaying(false);}}>Closed-loop experiment</button><button className={mode==='interactive'?'':'secondary'} onClick={()=>{setMode('interactive');setPlaying(false);}}>Interactive control</button></div>
    {error&&<div className="error" role="alert">{error}</div>}
    {mode==='experiment'?<>
      <form className="panel" onSubmit={run}><fieldset disabled={busy}><div className="panel-heading"><div><h2>Setpoint tracking & disturbance rejection</h2><p>Run an accelerated feedback experiment and compare with fixed commands under the same disturbances.</p></div><span className="tag">15 MIN / INTERVAL</span></div>
        <div className="form-grid four"><Field label="Initial target / units/h" min={8} max={38} value={form.target} onChange={v=>update('target',v)}/><Field label="New target / units/h" min={8} max={38} value={form.target_after} onChange={v=>update('target_after',v)}/><Field label="Simulation intervals" min={12} max={72} step={1} value={form.steps} onChange={v=>update('steps',v)}/><Field label="Setpoint change after interval" min={1} max={Number(form.steps)-1} step={1} value={form.target_step} onChange={v=>update('target_step',v)}/><Field label="Disturbance after interval" min={1} max={Number(form.steps)-1} step={1} value={form.disturbance_step} onChange={v=>update('disturbance_step',v)}/><Field label="Disturbed material factor" min={.7} max={1.15} value={form.material_factor} onChange={v=>update('material_factor',v)}/><Field label="Energy limit / kWh per interval" min={5} max={65} value={form.max_energy_kwh} onChange={v=>update('max_energy_kwh',v)}/><Field label="Process temperature limit / °C" min={35} max={70} value={form.max_temperature} onChange={v=>update('max_temperature',v)}/></div>
        <div className="opt-controls"><label className="checkbox-control"><input type="checkbox" checked={form.disturbance_enabled} onChange={e=>update('disturbance_enabled',e.target.checked)}/> Apply material, ambient and tariff disturbance</label><button disabled={busy||!model}>{busy?'Running feedback loop…':'Run closed-loop experiment ↗'}</button></div>
        <details className="control-details"><summary>Advanced controller settings</summary><div className="form-grid four"><Field label="MPC horizon / intervals" min={2} max={8} step={1} value={form.horizon} onChange={v=>update('horizon',v)}/><Field label="Candidates per search round" min={32} max={256} step={1} value={form.samples} onChange={v=>update('samples',v)}/><Field label="Search rounds" min={2} max={5} step={1} value={form.iterations} onChange={v=>update('iterations',v)}/><Field label="Energy preference" min={0} max={5} value={form.energy_weight} onChange={v=>update('energy_weight',v)}/><Field label="Ambient temperature / °C" min={20} max={35} value={form.ambient} onChange={v=>update('ambient',v)}/><Field label="Base tariff / CU per kWh" min={.01} max={5} value={form.tariff} onChange={v=>update('tariff',v)}/><Field label="Random seed" min={0} max={2147483646} step={1} value={form.seed} onChange={v=>update('seed',v)}/></div></details>
        <p>The controller sees each new setpoint and disturbance when it occurs. Temperature and energy limits are checked on predictions; actual violations are reported.</p>
      </fieldset></form>
      {result&&<><div className="metrics"><div className="metric"><span>Production tracking MAE</span><div><strong>{format(result.summary.tracking_mae,3)}</strong><small> units/h</small></div><p>Fixed commands: {format(result.baseline_summary.tracking_mae,3)} units/h</p></div><div className="metric"><span>Total simulated energy</span><div><strong>{format(result.summary.total_energy_kwh)}</strong><small> kWh</small></div><p>Output: {format(result.summary.total_units)} units</p></div><div className="metric"><span>Within 10% of target</span><div><strong>{format(result.summary.within_10_percent_target*100,1)}</strong><small> %</small></div><p>All executed intervals included</p></div><div className="metric"><span>Observed limit violations</span><div><strong>{result.summary.energy_violations+result.summary.temperature_violations}</strong><small> checks</small></div><p>Energy: {result.summary.energy_violations} · Temperature: {result.summary.temperature_violations}</p></div></div>
        <section className="panel"><div className="panel-heading"><div><h2>Feedback experiment playback</h2><p>Actual measurements from the completed accelerated simulation. Each simulated interval is 15 minutes.</p></div><button className="secondary" onClick={()=>saveReport(result)}>Export control report ↗</button></div><div className="replay-controls"><button className="secondary" onClick={()=>{if(!playing&&cursor>=result.rows.length-1)setCursor(0);setPlaying(!playing);}}>{playing?'Pause playback':'Play measurements'}</button><label className="replay-slider">Interval {cursor+1} / {result.rows.length}<input aria-label="Playback interval" type="range" min={0} max={result.rows.length-1} value={cursor} onChange={e=>{setPlaying(false);setCursor(Number(e.target.value));}}/></label><span>Measured rate <b>{format(current.production_rate)} units/h</b></span></div></section>
        <section className="panel"><h2>Production tracking / units per hour</h2><ControlChart rows={chartRows} settings={result.settings} events series={[
          ['target','Setpoint','#ffbb66','4 4'],['production_rate','ANN MPC · measured','#4cd6b3'],['baseline_production','Fixed commands · measured','#8397aa','3 3']]}/></section>
        <div className="two-col"><section className="panel"><h2>Interval energy / kWh</h2><ControlChart rows={chartRows} limit={result.settings.max_energy_kwh} series={[
          ['energy_kwh','MPC · measured','#4cd6b3'],['predicted_energy_kwh','ANN prediction','#899bff','4 4'],['baseline_energy','Fixed commands','#8397aa','3 3']]}/></section><section className="panel"><h2>Process temperature / °C</h2><ControlChart rows={chartRows} limit={result.settings.max_temperature} series={[
          ['process_temperature','Process temperature','#4cd6b3'],['ambient_temperature','Ambient temperature','#8397aa','3 3']]}/></section></div>
        <section className="panel"><h2>Actuator commands and measured response</h2><div className="table-scroll"><table><thead><tr>{['Interval','Target u/h','Measured u/h','Load command','Speed command rpm','PF command','Energy kWh','Predicted feasible'].map(v=><th key={v}>{v}</th>)}</tr></thead><tbody>{chartRows.map(row=><tr key={row.step}><td>{row.step}</td><td>{format(row.target)}</td><td>{format(row.production_rate)}</td><td>{format(row.load_command,3)}</td><td>{format(row.speed_command,0)}</td><td>{format(row.power_factor_command,3)}</td><td>{format(row.energy_kwh)}</td><td><span className={row.predicted_horizon_feasible?'normal-badge':'anomaly-badge'}>{row.predicted_horizon_feasible?'Yes':'Least-violation action'}</span></td></tr>)}</tbody></table></div>
          <p>Fixed-command baseline output: {format(result.baseline_summary.total_units)} units; energy: {format(result.baseline_summary.total_energy_kwh)} kWh. Different output totals make this a tracking comparison, not an equal-output savings experiment.</p></section>
      </>}
    </>:<>
      <form className="panel" onSubmit={advance}><fieldset disabled={busy}><div className="panel-heading"><div><h2>Execute one feedback step</h2><p>Choose a setpoint, compute an ANN-based action, execute it in the simulator and use the new measured state for the next step.</p></div><span className="tag">STEP {manual.rows.length}</span></div>
        <div className="manual-controls"><Field label="Interactive production target / units/h" min={8} max={38} value={manualTarget} onChange={setManualTarget}/><label className="checkbox-control"><input type="checkbox" checked={manualDisturbed} onChange={e=>setManualDisturbed(e.target.checked)}/> Apply disturbance now</label><button disabled={busy||!model}>{busy?'Computing control action…':'Advance one control step →'}</button><button type="button" className="secondary" onClick={()=>{setManual(initialManual);setError('');}}>Reset simulated plant</button></div>
        <small>Uses the configured horizon, search budget and limits from the experiment settings. Reset starts from the same initial state.</small>
      </fieldset></form>
      <section className="panel"><h2>Current measured state</h2><div className="neural-metrics">{manual.state.map((value,i)=><span key={i}>{names[i]}<b>{format(value,i===1?0:i===2?3:2)} {units[i]}</b></span>)}</div>
        {manual.rows.length>0&&<p>Last action: load {format(manual.command[0],3)}, speed {format(manual.command[1],0)} rpm, PF {format(manual.command[2],3)}. {manual.rows.at(-1).predicted_horizon_feasible?'Predicted horizon satisfies configured limits.':'No candidate satisfied all predicted limits; the controller executed its lowest-penalty candidate.'}</p>}
        {manual.rows.length>0&&<p className={manual.state[5]>form.max_energy_kwh||manual.state[3]>form.max_temperature?'warning':'success'}>Observed energy limit: {manual.state[5]>form.max_energy_kwh?'Exceeded':'Within limit'} · Observed temperature limit: {manual.state[3]>form.max_temperature?'Exceeded':'Within limit'}</p>}
      </section>
      {manual.rows.length>0&&<section className="panel"><h2>Interactive feedback trace</h2><ControlChart rows={manual.rows} series={[
        ['target','Setpoint','#ffbb66','4 4'],['production_rate','Measured production','#4cd6b3'],['predicted_production_rate','ANN one-step prediction','#899bff','3 3']]}/></section>}
    </>}
    <section className="panel"><h2>Control scope</h2><p>This is closed-loop control of a dynamic simulated process using a trained deep ANN as the prediction model. The ANN does not directly output a policy; MPC searches for actions through its predictions. Hard actuator bounds and slew limits are enforced. Process limits can still be violated when targets are infeasible, disturbances occur or the model is inaccurate.</p></section>
  </>;
}
