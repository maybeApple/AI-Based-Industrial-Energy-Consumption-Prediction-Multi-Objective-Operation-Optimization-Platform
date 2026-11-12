"""End-to-end acceptance for ANN control. API must be running on :8000."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
from browser_acceptance import english_only, navigate, capture

ROOT=Path(__file__).resolve().parents[1]


def main():
    errors=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='msedge',headless=True)
        page=browser.new_page(viewport={'width':1440,'height':1100})
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto('http://127.0.0.1:8000/#control',wait_until='networkidle')
        page.get_by_text('9,638 trained parameters',exact=False).wait_for()
        english_only(page)
        page.get_by_text('ANN validation and model comparison',exact=True).click()
        expect(page.get_by_text('0.283',exact=True)).to_be_visible()
        page.get_by_text('ANN validation and model comparison',exact=True).click()
        page.get_by_role('button',name='Run closed-loop experiment',exact=False).click()
        page.get_by_role('heading',name='Feedback experiment playback').wait_for(timeout=120000)
        capture(page,'07-neural-control.png')
        with page.expect_download() as download:
            page.get_by_role('button',name='Export control report',exact=False).click()
        report=json.loads(Path(download.value.path()).read_text(encoding='utf-8'))
        assert report['controller']=='ANN-based receding-horizon MPC'
        assert len(report['rows'])==36 and report['architecture']==[11,96,64,32,6]
        page.get_by_role('button',name='Play measurements',exact=True).click()
        page.get_by_role('button',name='Pause playback',exact=True).click()
        navigate(page,'Overview');navigate(page,'Neural Control')
        expect(page.get_by_role('heading',name='Feedback experiment playback')).to_be_visible()
        page.get_by_role('button',name='Interactive control',exact=True).click()
        page.get_by_role('button',name='Advance one control step',exact=False).click()
        page.get_by_text('STEP 1',exact=True).wait_for()
        page.get_by_label('Interactive production target / units/h').fill('32')
        page.get_by_label('Apply disturbance now').check()
        page.get_by_role('button',name='Advance one control step',exact=False).click()
        page.get_by_text('STEP 2',exact=True).wait_for()
        expect(page.get_by_role('heading',name='Interactive feedback trace')).to_be_visible()
        english_only(page)
        capture(page,'08-interactive-control.png')
        page.set_viewport_size({'width':390,'height':844})
        page.wait_for_function('document.documentElement.scrollWidth <= window.innerWidth',timeout=5000)
        page.get_by_role('button',name='Closed-loop experiment',exact=True).click()
        page.wait_for_function('document.documentElement.scrollWidth <= window.innerWidth',timeout=5000)
        capture(page,'09-mobile-neural-control.png')
        english_only(page)
        page.set_viewport_size({'width':1440,'height':1100})
        page.get_by_label('Energy limit / kWh per interval').fill('5')
        page.get_by_role('button',name='Run closed-loop experiment',exact=False).click()
        page.get_by_role('heading',name='Feedback experiment playback').wait_for(timeout=120000)
        expect(page.get_by_text('Least-violation action',exact=True).first).to_be_visible()
        page.get_by_role('button',name='Interactive control',exact=True).click()
        page.get_by_role('button',name='Reset simulated plant',exact=True).click()
        expect(page.get_by_text('STEP 0',exact=True)).to_be_visible()
        assert not errors,errors
        browser.close()
    print(json.dumps({'status':'passed','browser_errors':errors,'control_screenshots':str(ROOT/'docs'/'screenshots')}))


if __name__=='__main__':
    main()
