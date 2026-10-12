/* Optional UI verification and screenshot capture. Requires Playwright.
 * node scripts/verify_ui.cjs [report.html]
 */
const {chromium}=require('playwright');
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
const {pathToFileURL}=require('node:url');

(async()=>{
 const root=path.resolve(__dirname,'..');
 const report=path.resolve(process.argv[2]||path.join(root,'artifacts/report.html'));
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 try {
  const page=await browser.newPage({viewport:{width:1500,height:1100},deviceScaleFactor:1});
  const errors=[],remote=[];
  page.on('pageerror',e=>errors.push(String(e)));
  page.on('request',r=>{if(/^https?:/.test(r.url()))remote.push(r.url());});
  await page.goto(pathToFileURL(report).href);
  await page.waitForFunction(()=>document.getElementById('pnl').textContent.length>0);
  assert.equal(await page.locator('#chain tr').count(),12);
  assert.equal(await page.locator('#heatmap td').count(),49);
  assert.equal(await page.locator('.policy-tab').count(),4);
  assert.equal(await page.locator('#scenario option').count(),4);
  const verifyFrame=async()=>{
   const check=await page.evaluate(()=>({shown:document.getElementById('pnl').textContent,expected:money(frame().pnl),rows:document.querySelectorAll('#chain tr').length,heat:document.querySelectorAll('#heatmap td').length,overflow:document.documentElement.scrollWidth>innerWidth}));
   assert.equal(check.shown,check.expected);assert.equal(check.rows,12);assert.equal(check.heat,49);assert.equal(check.overflow,false);
  };
  for(let scenario=0;scenario<4;scenario++){
   await page.selectOption('#scenario',String(scenario));
   for(let policy=0;policy<4;policy++){
    await page.locator(`[data-policy="${policy}"]`).click();
    await verifyFrame();
   }
  }
  await page.selectOption('#scenario','2');
  await page.locator('[data-policy="0"]').click();
  await page.locator('[data-contract="SYN-30D-105P"]').click();
  assert.equal(await page.locator('#book-contract').textContent(),'SYN-30D-105P');
  await page.locator('[data-contract="SYN-7D-100C"]').click();
  await page.locator('[data-filter="risk"]').click();
  assert.ok((await page.locator('#audit').textContent()).includes('KILL_SWITCH'));
  await page.locator('[data-filter="all"]').click();
  await page.locator('#guide-button').click();
  assert.equal(await page.locator('#guide').evaluate(e=>e.open),true);
  await page.locator('#guide-close').click();
  const downloadPromise=page.waitForEvent('download');
  await page.locator('#export-button').click();
  const download=await downloadPromise;
  assert.equal(download.suggestedFilename(),'aegis-vol_shock-aegis-trades.csv');
  await page.locator('#scrubber').evaluate(e=>{e.value='0';e.dispatchEvent(new Event('input',{bubbles:true}));});
  await page.locator('#play').click();
  await page.waitForFunction(()=>Number(document.getElementById('scrubber').value)>0);
  await page.locator('#play').click();
  await page.locator('#jump').click();
  await verifyFrame();
  await page.screenshot({path:path.join(root,'artifacts/preview.png'),fullPage:true});
  fs.mkdirSync(path.join(root,'artifacts/.gif-frames'),{recursive:true});
  const box=await page.locator('.strip').boundingBox();
  const replayBox=await page.locator('.replay').boundingBox();
  const clip={x:box.x,y:box.y,width:box.width,height:replayBox.y+replayBox.height-box.y};
  const indices=await page.evaluate(()=>{const n=run().snapshots.length;return [0,Math.floor(n*.15),Math.floor(n*.3),Math.floor(n*.42),Math.floor(n*.47),Math.floor(n*.49),Math.floor(n*.50),Math.floor(n*.51),Math.floor(n*.52),Math.floor(n*.55),Math.floor(n*.65),Math.floor(n*.8),n-1];});
  for(let i=0;i<indices.length;i++){
   await page.locator('#scrubber').evaluate((e,v)=>{e.value=String(v);e.dispatchEvent(new Event('input',{bubbles:true}));},indices[i]);
   await page.screenshot({path:path.join(root,`artifacts/.gif-frames/${String(i).padStart(2,'0')}.png`),clip});
  }
  await page.setViewportSize({width:390,height:844});
  await page.locator('#jump').click();
  await verifyFrame();
  await page.screenshot({path:path.join(root,'artifacts/mobile-preview.png'),fullPage:true});
  assert.deepEqual(errors,[]);assert.deepEqual(remote,[]);
  console.log(JSON.stringify({desktop:'1500 × 1100',mobile:'390 × 844',scenarios:4,policies:4,heatmapCells:49,pageErrors:errors.length,remoteRequests:remote.length,checks:['correct displayed P&L','all scenario/policy switches','contract selection','risk filter','guide','CSV download','play/pause','scrubber','event jump','no page overflow']}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
