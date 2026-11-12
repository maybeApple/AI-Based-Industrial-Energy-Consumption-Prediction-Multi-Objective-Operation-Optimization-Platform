import React from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

const energyTick = value => value !== 0 && Math.abs(value) < .001 ? value.toExponential(1)
  : Number(value.toFixed(Math.abs(value) < 1 ? 3 : 2)).toString();

// Adapted from EnergyOpt ForecastChart: retained responsive Recharts composition.
// These are historical predictions; no fabricated forecast horizon or CI band.
export default function IndustrialChart({ rows, actual = 'energy_kwh', series, timeZone }) {
  const data = rows.map(r => ({ ...r, label: r.timestamp.slice(5, 16).replace('T', ' ') }));
  const lines = series ?? [
    { key: actual, name: 'Observed energy', color: '#4cd6b3' },
    { key: 'forecast', name: 'Model prediction', color: '#899bff', dash: '5 4' },
  ];
  return <div className="chart"><ResponsiveContainer width="100%" height="100%">
    <LineChart data={data} margin={{ top: 15, right: 20, bottom: 0, left: 0 }}>
      <CartesianGrid stroke="#263746" strokeDasharray="3 5" vertical={false}/>
      <XAxis dataKey="label" minTickGap={55} tick={{ fill: '#8397aa', fontSize: 11 }}/>
      <YAxis tick={{ fill: '#8397aa', fontSize: 11 }} tickFormatter={series ? energyTick : undefined} width={series ? 58 : 45}/>
      <Tooltip contentStyle={{ background: '#14212c', border: '1px solid #35495b', borderRadius: 8 }}
        labelFormatter={(label, values) => (values?.[0]?.payload?.timestamp?.slice(0, 16).replace('T', ' ') ?? label) + (timeZone ? ' ' + timeZone : '')}
        formatter={(v, n) => [(series ? energyTick(Number(v)) : Number(v).toFixed(2)) + ' kWh', n]}/>
      <Legend/>{lines.map(({ key, name, color, dash }) => <Line key={key} name={name} type={series ? 'linear' : 'monotone'}
        dataKey={key} stroke={color} dot={false} strokeDasharray={dash} strokeWidth={2} connectNulls={false} isAnimationActive={false}/>)}
    </LineChart>
  </ResponsiveContainer></div>;
}
