import axios from 'axios';
const api = axios.create({ baseURL: import.meta.env.VITE_API_URL || '/api', timeout: 120000 });
export const getSummary = () => api.get('/summary').then(r => r.data);
export const getHistory = (params = {}) => api.get('/history', { params }).then(r => r.data);
export const getRealBenchmarks = () => api.get('/real-benchmarks').then(r => r.data);
export const predictOperation = data => api.post('/predict', data).then(r => r.data);
export const optimizeOperation = data => api.post('/optimize', data).then(r => r.data);
export const getNeuralModel = () => api.get('/control/model').then(r => r.data);
export const runNeuralControl = data => api.post('/control/run', data).then(r => r.data);
export const stepNeuralControl = data => api.post('/control/step', data).then(r => r.data);
export function errorMessage(e) {
  const detail = e.response?.data?.detail;
  return typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map(d => `${d.loc.at(-1)}: ${d.msg}`).join('; ') : 'Cannot reach the service. Check that the API is running, then retry.';
}
