import React from 'react';
import Dashboard from './pages/IndustrialDashboard';
import './index.css';
import { WorkspaceProvider } from './components/WorkspaceState';

export default function App() {
  return <WorkspaceProvider><Dashboard /></WorkspaceProvider>;
}
