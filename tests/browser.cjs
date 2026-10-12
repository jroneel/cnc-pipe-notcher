// Start app.py first. Requires Playwright and a Chromium executable.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
  const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium'});
  try{
    const page=await browser.newPage(),errors=[];
    page.on('pageerror',e=>errors.push(e.message));
    const base=process.env.NOTCHER_URL||'http://127.0.0.1:5000/';
    // A slow module must not leave a native-submit button that refreshes the page.
    await page.route('**/static/units.mjs*',async route=>{await new Promise(resolve=>setTimeout(resolve,500));await route.continue();});
    await page.goto(base,{waitUntil:'domcontentloaded'});
    assert.equal(await page.locator('#generate').isDisabled(),true);
    assert.equal(await page.locator('#generate').getAttribute('type'),'button');
    let navigations=0;
    const track=()=>navigations++;
    page.on('framenavigated',track);
    await page.locator('#settings').evaluate(form=>form.requestSubmit());
    await page.waitForFunction(()=>!document.querySelector('#generate').disabled);
    assert.equal(navigations,0);
    page.off('framenavigated',track);
    await page.unroute('**/static/units.mjs*');
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
      const drawn=await page.locator('#preview').evaluate(canvas=>{
        const pixels=canvas.getContext('2d').getImageData(0,0,canvas.width,canvas.height).data;
        let green=0;
        for(let i=0;i<pixels.length;i+=4)if(pixels[i+1]>150&&pixels[i]<140)green++;
        return green;
      });
      assert.ok(drawn>20,'The generated contour must actually be drawn on the canvas');
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
    await page.unroute('**/api/detect');
    // Module-loading failures must be visible and must never submit the form.
    await page.route('**/static/units.mjs*',route=>route.fulfill({status:503,contentType:'text/plain',body:'Unavailable'}));
    await page.goto(base);
    await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('Application could not start'));
    assert.equal(await page.locator('#generate').isDisabled(),true);
    console.log('Chromium checks passed: autofill for all shapes, preview, pending detection, inches and manual fallback');
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
