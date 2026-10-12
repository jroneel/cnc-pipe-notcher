import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {readPlanResponse, planURL} from '../static/api.mjs';
import {convertInputs, normalizeFormData, displayLength, fillStockInputs} from '../static/units.mjs';

function ui(stock, failure=false) {
  const element=(value='')=>({value, textContent:'',className:'',disabled:false,events:{},
    addEventListener(name,fn){this.events[name]=fn;},setAttribute(k,v){this[k]=v;},
    hasAttribute(k){return k in this;},getAttribute(k){return this[k];}});
  const fields=Object.fromEntries(['width','height','wall','corner_radius','shape','feed','standoff','clearance','pivot','model'].map(name=>[name,element()]));
  fields.model.files=[];
  fields.feed.value='800';fields.standoff.value='1.5';fields.clearance.value='10';fields.pivot.value='0';
  const form=element();form.elements={namedItem:name=>fields[name]};
  const nodes=Object.fromEntries(['status','stock-status','stock-mode','units','export','count','range','offset'].map(id=>['#'+id,element()]));
  nodes['#stock-mode'].value='auto';
  const canvas=element();canvas.clientWidth=500;canvas.clientHeight=400;
  canvas.getContext=()=>new Proxy({}, {get:()=>()=>{}});
  nodes['#generate']=element();
  nodes['#viewer-export']=element();
  nodes['#prusa-export']=element();
  const document={querySelector:selector=>selector==='form'?form:selector==='canvas'?canvas:nodes[selector],querySelectorAll:()=>[]};
  let requests=0;
  const fetch=async url=>{requests++;assert.equal(url,'http://localhost:5000/api/detect');return new Response(JSON.stringify(failure?{error:'Cannot identify tubing'}:stock),{status:failure?400:200,headers:{'Content-Type':'application/json'}});};
  let script=readFileSync(new URL('../templates/index.html',import.meta.url),'utf8').split('<script type="module">')[1].split('</script>')[0];
  script=script.replace(/^const .*await import.*;$/gm,'');
  vm.runInNewContext(script,{document,location:{href:'http://localhost:5000/'},window:{addEventListener(){}},devicePixelRatio:1,
    URL,FormData,AbortController,fetch,readPlanResponse,planURL,convertInputs,normalizeFormData,displayLength,fillStockInputs});
  fields.model.files=[new Blob(['mesh'])];
  return {fields,nodes,requests:()=>requests};
}

test('file selection automatically fills read-only stock dimensions in selected units',async()=>{
  const {fields,nodes,requests}=ui({shape:'rectangle',width:76.2,height:50.8,wall:3.175,corner_radius:6.35});
  assert.equal(fields.width.readOnly,true);
  assert.equal(fields.width.required,false);
  assert.equal(fields.width.disabled,true);
  assert.equal(fields.shape.disabled,true);
  nodes['#units'].events.click();
  await fields.model.events.change();
  assert.equal(requests(),1);
  assert.equal(fields.shape.value,'rectangle');
  assert.equal(fields.width.value,'3');
  assert.equal(fields.height.value,'2');
  assert.equal(fields.wall.value,'0.125');
  assert.equal(fields.corner_radius.value,'0.25');
  assert.match(nodes['#stock-status'].textContent,/Detected rectangle/);
  nodes['#units'].events.click();
  assert.equal(fields.width.value,'76.2');
});

test('unsupported files leave no stale dimensions and manual mode unlocks inputs',async()=>{
  const {fields,nodes}=ui(null,true);
  fields.width.value='50';
  await fields.model.events.change();
  assert.equal(fields.width.value,'');
  assert.equal(nodes['#stock-status'].textContent,'Cannot identify tubing');
  assert.equal(nodes['#stock-status'].className,'error');
  nodes['#stock-mode'].value='manual';
  nodes['#stock-mode'].events.change();
  assert.equal(fields.width.readOnly,false);
  assert.equal(fields.width.required,true);
  assert.equal(fields.width.disabled,false);
  assert.equal(fields.shape.disabled,false);
});
