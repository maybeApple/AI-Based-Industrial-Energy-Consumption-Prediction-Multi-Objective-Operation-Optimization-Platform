"""Produce a source + trained artifacts + frontend build handoff, no installed dependencies."""
from pathlib import Path
import argparse
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT.parent / 'industrial-energy-v1.2-neural-control.zip'
EXCLUDE = {'.git', '.venv', 'node_modules', '__pycache__', '.pytest_cache', 'runtime', 'playwright-browsers'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=DEST)
    output = parser.parse_args().output.resolve()
    files = sorted(p for p in ROOT.rglob('*') if p.is_file()
                   and not any(part in EXCLUDE for part in p.relative_to(ROOT).parts)
                   and p.name != '.env' and p.suffix not in {'.log', '.pyc'})
    manifest = ROOT / 'docs' / 'FILE-TREE.txt'
    manifest.write_text('\n'.join(str(p.relative_to(ROOT)).replace('\\', '/') for p in files) + '\n', encoding='utf-8')
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, 'industrial-energy/' + path.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
        assert 'industrial-energy/frontend/dist/index.html' in archive.namelist()
        assert 'industrial-energy/data/industrial/Steel_industry_data.csv' in archive.namelist()
    print(f'{output} ({output.stat().st_size / 1024 / 1024:.2f} MB; {len(files)} files)')


if __name__ == '__main__':
    main()
