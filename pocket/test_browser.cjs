/* Optional browser integration test: node pocket/test_browser.cjs (Playwright). */
const {chromium} = require('playwright');
const {spawn} = require('node:child_process');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const assert = require('node:assert/strict');
const net = require('node:net');
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));

(async () => {
  const temp = await fs.mkdtemp(path.join(os.tmpdir(), 'xi-pocket-browser-'));
  const data = path.join(temp, 'data'); await fs.mkdir(data);
  if (process.env.XI_TEST_EXPORTS) {
    await fs.mkdir(path.join(data, 'exports'));
    for (const name of ['Capsules','CanonicalTruths','XiJournals','GuardianRuntimes','ObserverProfiles'])
      await fs.copyFile(path.join(process.env.XI_TEST_EXPORTS, name + '.xi'), path.join(data, 'exports', name + '.xi'));
  }
  const probe = net.createServer(); await new Promise(resolve => probe.listen(0, '127.0.0.1', resolve));
  const port = probe.address().port; await new Promise(resolve => probe.close(resolve));
  const server = spawn('python3', [path.join(__dirname, 'server.py'), '--data', data, '--port', String(port)], {stdio:'ignore'});
  let browser;
  try {
    const base = 'http://127.0.0.1:' + port;
    for (let i=0;i<50;i++) { try { if ((await fetch(base+'/api/status')).ok) break; } catch {} await pause(100); }
    const token = (await fs.readFile(path.join(data, 'owner-token'), 'utf8')).trim();
    browser = await chromium.launch({headless:true,args:['--no-sandbox'],...(process.env.CHROME_PATH ? {executablePath:process.env.CHROME_PATH} : {})});
    const context = await browser.newContext({viewport:{width:390,height:844}});
    const page = await context.newPage(); const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(base); await page.fill('#secret', token); await page.click('#login-form button');
    await page.waitForSelector('#room:not([hidden])');
    await page.waitForFunction(() => !!navigator.serviceWorker.controller);
    await page.fill('#draft', '<img src=x onerror="window.PWNED=true"> Ω');
    await page.click('#compose button'); await page.waitForFunction(() => document.querySelector('#pending').textContent === 'Queue clear');
    assert.equal(await page.locator('#feed img').count(), 0);
    assert.equal(await page.evaluate(() => !!window.PWNED), false);
    if (process.env.XI_TEST_EXPORTS) {
      await page.click('#cache-library'); await page.waitForFunction(() => document.querySelector('#library-state').textContent.startsWith('1004'));
    }
    await page.fill('#draft', 'draft survives offline reload ⟁');
    await page.waitForFunction(async () => {
      const db = await new Promise(resolve => { const r=indexedDB.open('xi-pocket-v1');r.onsuccess=()=>resolve(r.result); });
      const result = await new Promise(resolve => { const r=db.transaction('state').objectStore('state').get('draft');r.onsuccess=()=>resolve(r.result); });
      db.close(); return result === 'draft survives offline reload ⟁';
    });
    await context.setOffline(true); await page.reload({waitUntil:'domcontentloaded'});
    await page.waitForSelector('#room:not([hidden])');
    assert.equal(await page.inputValue('#draft'), 'draft survives offline reload ⟁');
    if (process.env.XI_TEST_EXPORTS) assert.match(await page.textContent('#library-state'), /^1004/);
    await page.fill('#draft', 'offline event · one durable receipt'); await page.click('#compose button');
    await page.waitForFunction(() => document.querySelector('#pending').textContent.startsWith('1 kept'));
    let lostResponse = false;
    await page.route('**/api/room', async route => {
      if (route.request().method() === 'POST' && !lostResponse) {
        await route.fetch(); lostResponse = true; await route.abort('failed');
      } else await route.continue();
    });
    await context.setOffline(false); await page.click('#refresh');
    await page.waitForFunction(() => document.querySelector('#notice').textContent.length > 0);
    for (let i=0;i<30 && !lostResponse;i++) await pause(100);
    assert.equal(lostResponse, true);
    await page.click('#refresh'); await page.waitForFunction(() => document.querySelector('#pending').textContent === 'Queue clear');
    const events = await (await fetch(base+'/api/room', {headers:{Authorization:'Bearer '+token}})).json();
    assert.equal(events.events.filter(e=>e.text === 'offline event · one durable receipt').length, 1);
    assert.equal(errors.length, 0, errors.join('\n'));
    if (process.env.XI_TEST_SCREENSHOT) await page.screenshot({path:process.env.XI_TEST_SCREENSHOT,fullPage:true});
    console.log(JSON.stringify({status:'PASS',viewport:'390x844',offline_reload:true,draft_preserved:true,
      offline_queue:true,lost_post_response_reconciled:true,duplicate_events:0,script_injection_executed:false,
      private_archive_records:process.env.XI_TEST_EXPORTS?1004:'not supplied',javascript_errors:errors.length}));
    await context.close();
  } finally {
    if (browser) await browser.close(); server.kill('SIGTERM');
    await new Promise(resolve => server.once('exit', resolve)); await fs.rm(temp,{recursive:true,force:true});
  }
})().catch(error=>{console.error(error.message);process.exitCode=1;});
