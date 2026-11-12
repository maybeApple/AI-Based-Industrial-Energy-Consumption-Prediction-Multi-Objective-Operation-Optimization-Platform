"""V1.1 browser acceptance checks. Start API on :8000 first; requires Edge."""
import json
import os
import re
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
BASE = os.environ.get('INDUSTRIAL_TEST_URL', 'http://127.0.0.1:8000')
OUT = Path(os.environ.get('INDUSTRIAL_TEST_SCREENSHOTS', ROOT / 'docs' / 'screenshots'))
OUT.mkdir(parents=True, exist_ok=True)


def english_only(page):
    assert not re.search(r'[\u3400-\u9fff]', page.locator('body').inner_text())
    assert page.locator('html').get_attribute('lang') == 'en'


def navigate(page, label):
    page.locator('nav').get_by_role('button', name=label, exact=False).click()


def capture(page, name):
    page.evaluate('window.scrollTo(0, 0)')
    page.screenshot(path=str(OUT / name), full_page=True)


def main():
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge', headless=True)
        page = browser.new_page(viewport={'width': 1440, 'height': 1100}, device_scale_factor=1)
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.goto(BASE, wait_until='networkidle')
        page.get_by_text('Models ready', exact=False).wait_for()
        english_only(page)
        capture(page, '01-overview.png')
        navigate(page, 'Energy Prediction')
        page.get_by_label('Observed energy / kWh').fill('499')
        page.get_by_role('button', name='Predict energy', exact=False).click()
        page.get_by_text('Anomaly candidate detected. Review this operating point.', exact=True).wait_for()
        english_only(page)
        capture(page, '02-prediction.png')
        navigate(page, 'Overview')
        navigate(page, 'Energy Prediction')
        expect(page.get_by_label('Observed energy / kWh')).to_have_value('499')
        expect(page.get_by_text('Anomaly candidate detected. Review this operating point.', exact=True)).to_be_visible()
        navigate(page, 'Optimization')
        page.get_by_label('Scenario preset').select_option('efficient')
        expect(page.get_by_label('Minimum production / units/h')).to_have_value('15')
        expect(page.get_by_label('Energy preference')).to_have_value('3')
        page.get_by_label('Scenario preset').select_option('balanced')
        page.get_by_role('button', name='Run optimization', exact=False).click()
        navigate(page, 'Overview')
        navigate(page, 'Optimization')
        page.get_by_role('heading', name='Recommended operating point', exact=True).wait_for(timeout=120000)
        page.get_by_role('heading', name='Compare with the reference operating point').wait_for()
        chart = page.get_by_role('group', name='Three-dimensional Pareto front:', exact=False)
        expect(chart).to_be_visible()
        expect(page.get_by_role('heading', name='Same-output benchmark')).to_be_visible()
        markers = chart.locator('.pareto-marker')
        assert markers.count() > 5
        initial_position = markers.first.get_attribute('transform')
        page.get_by_role('button', name='Rotate right').click()
        assert markers.first.get_attribute('transform') != initial_position
        page.get_by_role('button', name='Reset view').click()
        assert markers.first.get_attribute('transform') == initial_position
        page.get_by_role('button', name='Zoom in').click()
        assert markers.first.get_attribute('transform') != initial_position
        before_drag = markers.first.get_attribute('transform')
        chart.scroll_into_view_if_needed()
        box = chart.bounding_box()
        page.mouse.move(box['x'] + 20, box['y'] + 20)
        page.mouse.down()
        page.mouse.move(box['x'] + 125, box['y'] + 50, steps=6)
        page.mouse.up()
        assert markers.first.get_attribute('transform') != before_drag
        click_id = chart.locator('.pareto-marker[aria-pressed="false"]').last.get_attribute('data-point-id')
        candidate = chart.locator(f'[data-point-id="{click_id}"]')
        candidate.locator('.pareto-hit').click()
        expect(candidate).to_have_attribute('aria-pressed', 'true')
        page.get_by_role('button', name='Show recommendation', exact=True).click()
        selected = chart.locator('[aria-pressed="true"]')
        selected.focus()
        selected.press('ArrowRight')
        expect(page.get_by_role('heading', name='Candidate #', exact=False)).to_be_visible()
        page.get_by_role('button', name='Show recommendation', exact=True).click()
        page.get_by_role('button', name='Reset view').click()
        page.get_by_role('heading', name='Recommended operating point', exact=True).wait_for()
        english_only(page)
        page.locator('.pareto-layout').screenshot(path=str(OUT / 'pareto-3d-detail.png'))
        capture(page, '03-pareto.png')
        with page.expect_download() as download:
            page.get_by_role('button', name='Export CSV', exact=False).click()
        assert download.value.suggested_filename == 'pareto-synthetic.csv'
        with page.expect_download() as report:
            page.get_by_role('button', name='Download run report', exact=False).click()
        contents = json.loads(Path(report.value.path()).read_text(encoding='utf-8'))
        assert len(contents['pareto']) >= 5 and contents['request']['seed'] == 42
        assert contents['reference']['machine_load'] == .7
        benchmark = contents['same_output_benchmark']
        assert benchmark['status'] == 'ok'
        assert abs(benchmark['candidate']['production_rate'] - contents['reference']['production_rate']) < 1e-8
        navigate(page, 'Overview')
        navigate(page, 'Optimization')
        expect(page.get_by_role('heading', name='Recommended operating point', exact=True)).to_be_visible()
        page.get_by_label('Sort candidates').select_option('production_rate')
        rows = page.locator('tbody tr')
        assert float(rows.nth(0).locator('td').nth(3).inner_text()) >= float(rows.nth(1).locator('td').nth(3).inner_text())
        page.set_viewport_size({'width': 390, 'height': 844})
        for label in ['Overview', 'Energy Prediction', 'Optimization', 'History & Equipment', 'Real-data Validation']:
            navigate(page, label)
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), f'Mobile overflow: {label}'
            english_only(page)
            if label == 'Optimization':
                capture(page, '06-mobile-optimization.png')
        navigate(page, 'Overview')
        capture(page, '05-mobile.png')
        page.set_viewport_size({'width': 1440, 'height': 1100})
        navigate(page, 'Optimization')
        page.get_by_label('Minimum production / units/h').fill('45')
        expect(page.get_by_role('heading', name='Recommended operating point', exact=True)).to_have_count(0)
        page.get_by_label('Energy limit / kWh per 15 min').fill('1')
        page.get_by_role('button', name='Run optimization', exact=False).click()
        page.get_by_text('No feasible solution found in this search.', exact=False).wait_for(timeout=120000)
        english_only(page)
        page.get_by_label('Scenario preset').select_option('balanced')
        for weight in ['Energy preference', 'Cost preference', 'Output preference']:
            page.get_by_label(weight).fill('0')
        page.get_by_role('button', name='Run optimization', exact=False).click()
        expect(page.get_by_role('alert')).to_contain_text('At least one preference')
        navigate(page, 'History & Equipment')
        page.get_by_text('6000 readings', exact=False).wait_for()
        first = page.locator('tbody tr').first.inner_text()
        page.get_by_role('button', name='Next', exact=True).click()
        page.get_by_text('Page 2', exact=False).wait_for()
        assert page.locator('tbody tr').first.inner_text() != first
        navigate(page, 'Overview')
        navigate(page, 'History & Equipment')
        page.get_by_text('Page 2', exact=False).wait_for()
        page.get_by_label('Anomaly candidates only').check()
        page.locator('tbody tr').first.wait_for()
        assert page.locator('tbody .normal-badge').count() == 0
        english_only(page)
        navigate(page, 'Real-data Validation')
        page.get_by_role('heading', name='Measured steel energy / one-step forecast').wait_for()
        expect(page.get_by_label('Chart window')).to_have_value('final')
        page.get_by_label('Show previous lightgbm').check()
        expect(page.locator('.recharts-legend-wrapper').get_by_text('Previous LightGBM', exact=True)).to_be_visible()
        english_only(page)
        capture(page, '04-steel.png')
        page.get_by_label('Measured dataset').select_option('scada-compressor')
        expect(page.get_by_role('heading', name='Measured air compressor energy / one-step forecast')).to_be_visible()
        expect(page.get_by_label('Chart window')).to_have_value('first')
        page.get_by_label('Chart window').select_option('final')
        with page.expect_download() as real_export:
            page.get_by_role('button', name='Export forecast comparison', exact=False).click()
        assert real_export.value.suggested_filename == 'scada-compressor-final-48h-comparison.csv'
        assert len(Path(real_export.value.path()).read_text(encoding='utf-8-sig').splitlines()) == 193
        page.get_by_label('Chart window').select_option('first')
        english_only(page)
        capture(page, '10-scada-compressor.png')
        page.set_viewport_size({'width': 390, 'height': 844})
        page.wait_for_function('document.documentElement.scrollWidth <= window.innerWidth', timeout=4000)
        page.set_viewport_size({'width': 1440, 'height': 1100})
        page.route('**/api/predict', lambda route: route.abort())
        navigate(page, 'Energy Prediction')
        page.get_by_role('button', name='Predict energy', exact=False).click()
        expect(page.get_by_role('alert')).to_contain_text('Cannot reach the service')
        english_only(page)
        page.unroute('**/api/predict')
        page.goto(BASE + '/#optimize', wait_until='networkidle')
        expect(page.get_by_role('heading', name='Optimization', exact=True)).to_be_visible()
        assert not errors, errors
        browser.close()
    print(json.dumps({'status': 'passed', 'browser_errors': errors, 'screenshots': str(OUT)}))


if __name__ == '__main__':
    main()
