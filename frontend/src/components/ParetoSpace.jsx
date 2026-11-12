import React, { useMemo, useRef, useState } from 'react';
import './pareto-space.css';

const initialView = { azimuth: .34, elevation: .40, zoom: 1 };
const axes = [
  { key: 'energy_kwh', label: 'Energy', unit: 'kWh / 15 min', color: '#7bdbc8', goal: 'minimize' },
  { key: 'cost', label: 'Total cost', unit: 'CU / 15 min', color: '#ffbe78', goal: 'minimize' },
  { key: 'production_rate', label: 'Production rate', unit: 'units/h', color: '#bdaaff', goal: 'maximize' },
];
const steps = [0, .25, .5, .75, 1];
const origin = [0, 0, 0];
const limit = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const axisPoint = (axis, value) => origin.map((_, i) => i === axis ? value : 0);
const fixed = (value) => value.toFixed(2);
const tick = (value) => Number(value.toFixed(2)).toString();

function project(coords, camera) {
  const [x, y, z] = coords.map(value => value - .5);
  const { azimuth, elevation, zoom } = camera;
  const side = Math.cos(azimuth)*x - Math.sin(azimuth)*y;
  const front = Math.sin(azimuth)*x + Math.cos(azimuth)*y;
  const scale = 197*zoom;
  return [320 + scale*side, 178 + scale*(Math.sin(elevation)*front - Math.cos(elevation)*z),
    Math.cos(elevation)*front + Math.sin(elevation)*z];
}

function line(a, b, camera, props = {}) {
  const [x1, y1] = project(a, camera);
  const [x2, y2] = project(b, camera);
  return <line x1={x1} y1={y1} x2={x2} y2={y2} {...props}/>;
}

function PlaneGrid({ camera }) {
  return <g className="pareto-grid" aria-hidden="true">
    <polygon points={[[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]]
      .map(point => project(point, camera).slice(0, 2).join(',')).join(' ')}/>
    {steps.map(value => <g key={value}>
      {line([value, 0, 0], [value, 1, 0], camera)}
      {line([0, value, 0], [1, value, 0], camera)}
      {line([0, 0, value], [1, 0, value], camera)}
      {line([0, 0, value], [0, 1, value], camera)}
    </g>)}
    {[[1, 0], [0, 1], [1, 1]].map(([x, y]) =>
      line([x, y, 0], [x, y, 1], camera, { key: x + ':' + y, className: 'pareto-grid-edge' }))}
  </g>;
}

export default function ParetoSpace({ points, recommended, selected, onSelect }) {
  const [camera, setCamera] = useState(initialView);
  const [hovered, setHovered] = useState(null);
  const drag = useRef(null);
  const moved = useRef(false);
  const pointElements = useRef(new Map());
  const ranges = useMemo(() => axes.map(({ key }) => {
    const values = points.map(point => point[key]);
    const low = Math.min(...values);
    const high = Math.max(...values);
    const margin = Math.max((high - low)*.07, .05);
    return [Math.max(0, low - margin), high + margin];
  }), [points]);
  const normalize = point => axes.map(({ key }, i) =>
    (point[key] - ranges[i][0]) / (ranges[i][1] - ranges[i][0]));
  const markerPriority = point => point.id === selected.id ? 2 : point.id === recommended.id ? 1 : 0;
  const plotted = points.map(point => ({ point, position: project(normalize(point), camera) }))
    .sort((a, b) => markerPriority(a.point) - markerPriority(b.point) || a.position[2] - b.position[2]);
  const active = hovered ?? selected;
  const selectedPosition = normalize(selected);
  const [originX, originY] = project(origin, camera);
  const rotate = radians => setCamera(current => ({ ...current, azimuth: current.azimuth + radians }));
  const zoom = factor => setCamera(current => ({ ...current, zoom: limit(current.zoom*factor, .72, 1.24) }));

  function startDrag(event) {
    if (event.button !== 0 || !event.isPrimary) return;
    moved.current = false;
    drag.current = { id: event.pointerId, x: event.clientX, y: event.clientY, camera };
  }
  function orbit(event) {
    const start = drag.current;
    if (!start || start.id !== event.pointerId) return;
    const dx = event.clientX - start.x, dy = event.clientY - start.y;
    if (!moved.current && Math.hypot(dx, dy) < 4) return;
    if (!moved.current) {
      event.currentTarget.setPointerCapture(event.pointerId);
      moved.current = true;
      setHovered(null);
    }
    setCamera({ ...start.camera, azimuth: start.camera.azimuth + dx*.012,
      elevation: limit(start.camera.elevation + dy*.008, .18, 1.12) });
  }
  function pointKey(event, point) {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      onSelect(point);
    } else if (['ArrowLeft', 'ArrowRight'].includes(event.key)) {
      event.preventDefault();
      const index = points.indexOf(point);
      const next = points[(index + (event.key === 'ArrowRight' ? 1 : -1) + points.length) % points.length];
      onSelect(next);
      pointElements.current.get(next.id)?.focus();
    }
  }

  return <div className="pareto-space">
    <div className="pareto-camera" aria-label="Chart view controls" role="group">
      <button className="secondary" type="button" onClick={() => rotate(-.35)}>Rotate left</button>
      <button className="secondary" type="button" onClick={() => rotate(.35)}>Rotate right</button>
      <button className="secondary" type="button" aria-label="Zoom out" onClick={() => zoom(1/1.15)}>−</button>
      <button className="secondary" type="button" aria-label="Zoom in" onClick={() => zoom(1.15)}>+</button>
      <button className="secondary" type="button" onClick={() => setCamera(initialView)}>Reset view</button>
    </div>
    <svg className="pareto-scene" viewBox="30 0 580 355" role="group" aria-label="Three-dimensional Pareto front: energy, total cost, and production rate"
      onPointerDown={startDrag} onPointerMove={orbit} onPointerUp={() => { drag.current = null; }}
      onPointerLeave={() => { if (!moved.current) drag.current = null; }}
      onLostPointerCapture={() => { drag.current = null; }} onPointerCancel={() => { drag.current = null; }}>
      <PlaneGrid camera={camera}/>
      {axes.map(({ label, color }, i) => {
        const end = axisPoint(i, 1);
        const [endX, endY] = project(end, camera);
        const side = endX - originX;
        return <g className="pareto-axis" key={label} fill={color} aria-hidden="true">
          {line(origin, end, camera, { stroke: color })}
          {steps.map((value, j) => {
            const [x, y] = project(axisPoint(i, value), camera);
            const [low, high] = ranges[i];
            return <g key={value}><circle cx={x} cy={y} r="2"/>
              {j > 0 && j < steps.length - 1 && <text x={x + (i === 2 ? -7 : 0)} y={y + (i === 2 ? 4 : 15)}
                textAnchor={i === 2 ? 'end' : 'middle'}>{tick(low + (high - low)*value)}</text>}
            </g>;
          })}
          <text className="pareto-axis-name" x={limit(endX + (side < -20 ? -10 : side > 20 ? 10 : 0), 105, 535)}
            y={limit(endY + (i === 2 ? -12 : 22), 21, 342)} textAnchor={side < -20 ? 'end' : side > 20 ? 'start' : 'middle'}>
            {label}
          </text>
        </g>;
      })}
      {line([selectedPosition[0], selectedPosition[1], 0], selectedPosition, camera, { className: 'pareto-drop', 'aria-hidden': true })}
      {plotted.map(({ point, position: [x, y] }) => {
        const isRecommended = point.id === recommended.id;
        const isSelected = point.id === selected.id;
        return <g key={point.id} ref={node => {
          if (node) pointElements.current.set(point.id, node);
          else pointElements.current.delete(point.id);
        }} transform={'translate(' + x + ' ' + y + ')'} className="pareto-marker" role="button"
          tabIndex={isSelected ? 0 : -1} aria-pressed={isSelected}
          aria-label={(isRecommended ? 'Recommended point. ' : 'Candidate ' + point.id + '. ') +
            fixed(point.energy_kwh) + ' kWh, ' + fixed(point.cost) + ' CU, ' + fixed(point.production_rate) + ' units per hour'}
          data-point-id={point.id} onClick={() => { if (!moved.current) onSelect(point); }} onKeyDown={event => pointKey(event, point)}
          onPointerEnter={() => { if (!drag.current) setHovered(point); }} onPointerLeave={() => setHovered(null)}>
          <circle className="pareto-hit" r={isRecommended || isSelected ? 13 : 7}/>
          {isSelected && <circle className="pareto-selection" r="10"/>}
          {isRecommended ? <path className="pareto-recommended" d="M0 -8 L2.4 -2.5 L8 -2.5 L3.6 1.1 L5 7 L0 3.5 L-5 7 L-3.6 1.1 L-8 -2.5 L-2.4 -2.5 Z"/>
            : <circle className="pareto-candidate" r={isSelected ? 5.5 : 4}/>}
        </g>;
      })}
    </svg>
    <div className="pareto-axis-legend">
      {axes.map(({ label, unit, goal, color }) => <span key={label} style={{ '--axis-color': color }}>
        <strong>{label}</strong> · {unit} · {goal}
      </span>)}
    </div>
    <div className="pareto-readout">
      <strong>{active.id === recommended.id ? '★ Recommended point' : 'Candidate #' + active.id}</strong>
      <span>{fixed(active.energy_kwh)} kWh · {fixed(active.cost)} CU · {fixed(active.production_rate)} units/h</span>
    </div>
    <small>Drag to rotate. Select a marker, or focus it and use the arrow keys to step through solutions. The gold star marks the recommendation; the ring marks your selection.</small>
  </div>;
}
