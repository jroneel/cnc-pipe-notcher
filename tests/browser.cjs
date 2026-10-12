// Start app.py first. Requires Playwright and a Chromium executable.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const {readFileSync}=require('node:fs');
(async()=>{
  const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium'});
  try{
    const page=await browser.newPage(),errors=[],modules=[];
    page.on('pageerror',e=>errors.push(e.message));
    page.on('response',response=>{if(response.url().includes('.mjs'))modules.push(response);});
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
    for(const [model,shape,height,radius] of [['round','round',50,0],['square','square',50,0],['rectangle','rectangle',40,0],['rounded-square','square',50,8],['rounded-rectangle','rectangle',40,8],['coarse-rounded-rectangle','rectangle',40,8]]){
      await page.goto(base);
      await page.locator('#model').setInputFiles(`examples/${model}-oblique-tube.stl`);
      await page.waitForFunction(()=>document.querySelector('input[name=width]').value!=='');
      assert.equal(await page.locator('#shape').inputValue(),shape);
      assert.ok(Math.abs(Number(await page.locator('input[name=corner_radius]').inputValue())-radius)<.01);
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
      const downloadPromise=page.waitForEvent('download');
      await page.locator('#viewer-export').click();
      const download=await downloadPromise;
      assert.equal(download.suggestedFilename(),'notcher-viewer-only.nc');
      const text=readFileSync(await download.path(),'utf8');
      assert.match(text,/VIEWER ONLY/);
      assert.equal(text.split('\n').filter(line=>line.startsWith('G1 X')).length,Number(await page.locator('#count').textContent())-1);
      assert.match(text,/G1 X-?\d+\.\d+ Y-?\d+\.\d+ Z-?\d+\.\d+/);
      const prusaPromise=page.waitForEvent('download');
      await page.locator('#prusa-export').click();
      const prusaDownload=await prusaPromise;
      assert.equal(prusaDownload.suggestedFilename(),'notcher-prusa-viewer-only.gcode');
      const prusa=readFileSync(await prusaDownload.path(),'utf8');
      assert.match(prusa,/DO NOT RUN ON A CNC MACHINE OR 3D PRINTER/);
      assert.match(prusa,/G1 X.* Y.* Z0\.2000 E/);
    }
    if(process.env.NOTCHER_TEST_MODEL){
      await page.goto(base);
      await page.locator('#model').setInputFiles(process.env.NOTCHER_TEST_MODEL);
      await page.waitForFunction(()=>document.querySelector('input[name=width]').value!=='');
      assert.ok(Math.abs(Number(await page.locator('input[name=width]').inputValue())-76.2)<.001);
      assert.ok(Math.abs(Number(await page.locator('input[name=height]').inputValue())-25.4)<.001);
      await page.getByRole('button',{name:'Generate toolpath preview'}).click();
      await page.waitForFunction(()=>document.querySelector('#count').textContent!=='—');
      assert.match(await page.locator('#warnings').textContent(),/does not cut interior holes/);
      assert.match(await page.locator('#stock-status').textContent(),/4.83 \/ 4.83/);
    }
    await page.goto(base);
    await page.route('**/api/detect',async route=>{await new Promise(resolve=>setTimeout(resolve,250));await route.continue();});
    await page.locator('#model').setInputFiles('examples/rectangle-oblique-tube.stl');
    await page.getByRole('button',{name:'Generate toolpath preview'}).click();
    await page.waitForFunction(()=>document.querySelector('#count').textContent!=='—');
    await page.unroute('**/api/detect');
    assert.ok(modules.length>0);
    for(const response of modules){
      assert.equal(response.status(),200);
      assert.match(response.headers()['content-type'],/^text\/javascript/);
      assert.equal(response.headers()['cache-control'],'no-store');
    }
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
    assert.match(await page.locator('#status').textContent(),/Could not load units.mjs/);
    assert.equal(await page.locator('#generate').isDisabled(),true);
    console.log('Chromium checks passed: autofill for all shapes, preview, pending detection, inches and manual fallback');
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
