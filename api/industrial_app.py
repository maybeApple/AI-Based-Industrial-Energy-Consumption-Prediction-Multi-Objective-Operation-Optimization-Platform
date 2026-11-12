"""V1 entry point. Original api.main remains available for upstream comparison."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from .industrial.data import ROOT
from .industrial.service import IndustrialService
from .industrial.routes import router


@asynccontextmanager
async def lifespan(app):
    app.state.industrial = IndustrialService()
    yield


app = FastAPI(title='Industrial Energy · Prediction, Optimization & Neural Control', version='1.2.0', lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=['http://localhost:5173', 'http://127.0.0.1:5173'],
                   allow_methods=['GET', 'POST'], allow_headers=['Content-Type'])
app.include_router(router)
dist = ROOT / 'frontend' / 'dist'
if dist.exists():
    app.mount('/', StaticFiles(directory=dist, html=True), name='dashboard')
