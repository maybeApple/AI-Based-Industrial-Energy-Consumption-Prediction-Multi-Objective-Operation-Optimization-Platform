"""Serve offline forecast evaluations. Neither training nor downloads run in the API."""
import json

from .data import ARTIFACTS

BENCHMARK_IDS = ('steel', 'scada-compressor')


def real_benchmarks():
    folder = ARTIFACTS / 'real_benchmarks'
    paths = [folder / (key + '.json') for key in BENCHMARK_IDS]
    return {'benchmarks': [json.loads(path.read_text(encoding='utf-8')) for path in paths if path.is_file()]}
