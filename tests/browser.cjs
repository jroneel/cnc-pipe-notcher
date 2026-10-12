// Start app.py first. Requires Playwright and a Chromium executable.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
  const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium'});
  try{
    const page=await browser.newPage(),errors=[];
    page.on('pageerror',e=>errors.push(e.message));
    const base=process.env.NOTCHER_URL||'http://127.0.0.1:5000/';
    for(const [shape,height] of [['round',50],['square',50],['rectangle',40]]){
      await page.goto(base);
      await page.locator('#model').setInputFiles(`examples/${shape}-oblique-tube.stl`);
      await page.waitForFunction(()=>document.querySelector('input[name=width]').value!=='');
      assert.equal(await page.locator('#shape').inputValue(),shape);
      for(const [name,value] of [['width',50],['height',height],['wall',3]]){
        const field=page.locator(`input[name=${name}]`);
        assert.ok(Math.abs(Number(await field.inputValue())-value)<.001);
        assert.equal(await field.evaluate(el=>el.required),false);
        assert.equal(await field.isDisabled(),true);
      }
      await page.getByRole('button',{name:'Generate toolpath preview'}).click();
      await page.waitForFunction(()=>document.querySelector('#count').textContent!=='—');
    }
    await page.goto(base);
    await page.route('**/api/detect',async route=>{await new Promise(resolve=>setTimeout(resolve,250));await route.continue();});
    await page.locator('#model').setInputFiles('examples/rectangle-oblique-tube.stl');
    await page.getByRole('button',{name:'Generate toolpath preview'}).click();
    await page.waitForFunction(()=>document.querySelector('#count').textContent!=='—');
    await page.unroute('**/api/detect');
    await page.getByRole('button',{name:'Switch input and display units to inches'}).click();
    assert.ok(Math.abs(Number(await page.locator('input[name=width]').inputValue())-50/25.4)<1e-10);
    await page.goto(base);
    await page.route('**/api/detect',route=>route.fulfill({status:400,contentType:'application/json',body:JSON.stringify({error:'Unsupported section: use manual stock settings'})}));
    await page.locator('#model').setInputFiles('examples/round-oblique-tube.stl');
    await page.waitForFunction(()=>document.querySelector('#stock-status').className==='error');
    await page.locator('#stock-mode').selectOption('manual');
    assert.equal(await page.locator('input[name=width]').isDisabled(),false);
    assert.equal(await page.locator('input[name=width]').evaluate(el=>el.required),true);
    await page.locator('#shape').selectOption('rectangle');
    assert.equal(await page.locator('input[name=height]').evaluate(el=>el.required),true);
    assert.deepEqual(errors,[]);
    console.log('Chromium checks passed: autofill for all shapes, preview, pending detection, inches and manual fallback');
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
