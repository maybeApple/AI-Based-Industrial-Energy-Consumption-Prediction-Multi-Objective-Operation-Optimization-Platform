from fastapi import APIRouter, Request, Query
from .schemas import OperatingPoint, OptimizeRequest, ControlSettings, ControlStepRequest
from .optimizer import optimize
from .control import run_control, advance_control
from .benchmarks import real_benchmarks

router = APIRouter(prefix='/api')


@router.get('/health')
def health():
    return {'status': 'ok', 'version': 'industrial-v1.2', 'mode': 'offline demonstration', 'language': 'en', 'neural_control': True}


@router.get('/summary')
def summary(request: Request):
    return request.app.state.industrial.summary()


@router.get('/history')
def history(request: Request, limit: int = Query(96, ge=1, le=500), offset: int = Query(0, ge=0), anomalies_only: bool = False):
    df = request.app.state.industrial.history
    if anomalies_only:
        df = df[df.anomaly]
    rows = df.iloc[::-1].iloc[offset:offset+limit].iloc[::-1]
    return {'total': len(df), 'offset': offset, 'limit': limit, 'rows': rows.to_dict(orient='records')}


@router.get('/steel')
def steel(request: Request):
    return request.app.state.industrial.steel()


@router.get('/real-benchmarks')
def measured_benchmarks():
    return real_benchmarks()


@router.post('/predict')
def predict(point: OperatingPoint, request: Request):
    return request.app.state.industrial.predict(point)


@router.post('/optimize')
def optimization(payload: OptimizeRequest, request: Request):
    return optimize(request.app.state.industrial.model, payload)


@router.get('/control/model')
def neural_model(request: Request):
    model = request.app.state.industrial.neural
    return {'ready':True, 'metrics':model.report, 'model_sha256':model.artifact_hash}


@router.post('/control/run')
def simulate_control(payload: ControlSettings, request: Request):
    return run_control(request.app.state.industrial.neural,payload)


@router.post('/control/step')
def single_control_step(payload: ControlStepRequest, request: Request):
    return advance_control(request.app.state.industrial.neural,payload)
