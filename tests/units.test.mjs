import test from 'node:test';
import assert from 'node:assert/strict';
import {convertInputs, normalizeFormData, displayLength, fillStockInputs} from '../static/units.mjs';

function fixture() {
  const inputs = Object.fromEntries(Object.entries({width:'50',height:'40',wall:'3',corner_radius:'8',feed:'800',standoff:'1.5',clearance:'10',pivot:'100',bevel:'30',samples:'360'}).map(([name,value]) => {
    const attributes = {min: '0', max: '1000'};
    return [name, {value, hasAttribute: k => k in attributes,
      getAttribute: k => attributes[k], setAttribute: (k,v) => attributes[k]=v}];
  }));
  inputs.shape={value:'round'};
  return {inputs, form:{elements:{namedItem:name => inputs[name]}}};
}

test('conversion covers length and feed, preserving angles and sample counts', () => {
  const {form,inputs}=fixture();
  convertInputs(form,'mm','in');
  assert.ok(Math.abs(Number(inputs.width.value)-50/25.4)<1e-12);
  assert.ok(Math.abs(Number(inputs.feed.value)-800/25.4)<1e-12);
  assert.equal(inputs.bevel.value,'30');
  assert.equal(inputs.samples.value,'360');
  assert.equal(Number(inputs.pivot.getAttribute('max')),1000/25.4);
  assert.equal(inputs.feed.step,'any');
  convertInputs(form,'in','mm');
  assert.equal(inputs.width.value,'50');
  assert.equal(inputs.feed.value,'800');
  assert.equal(inputs.pivot.getAttribute('max'),'1000');
});

test('inch edits are submitted as millimetres and survive repeated toggles', () => {
  const {form,inputs}=fixture();
  convertInputs(form,'mm','in');
  inputs.width.value='2'; inputs.feed.value='40';
  const data=normalizeFormData(new FormData(),form,'in');
  assert.equal(data.get('width'),'50.8');
  assert.equal(data.get('feed'),'1016');
  assert.equal(data.get('wall'),'3');
  for(let i=0;i<100;i++){convertInputs(form,'in','mm');convertInputs(form,'mm','in');}
  assert.equal(inputs.width.value,'2');
  convertInputs(form,'in','mm');
  assert.equal(inputs.width.value,'50.8');
});

test('blank values remain blank; display values reflect selected units', () => {
  const {form,inputs}=fixture();inputs.wall.value='';
  convertInputs(form,'mm','in');
  assert.equal(inputs.wall.value,'');
  assert.equal(displayLength(25.4,'in'),'1.0000');
  assert.equal(displayLength(25.4,'mm'),'25.40');
});

test('detected stock is displayed in inches and submits exact millimetre dimensions', () => {
  const {form,inputs}=fixture();
  convertInputs(form,'mm','in');
  fillStockInputs(form,{shape:'rectangle',width:76.2,height:50.8,wall:3.175,corner_radius:6.35},'in');
  assert.equal(inputs.shape.value,'rectangle');
  assert.equal(inputs.width.value,'3');
  assert.equal(inputs.height.value,'2');
  assert.equal(inputs.wall.value,'0.125');
  assert.equal(inputs.corner_radius.value,'0.25');
  assert.equal(normalizeFormData(new FormData(),form,'in').get('corner_radius'),'6.35');
  assert.equal(normalizeFormData(new FormData(),form,'in').get('wall'),'3.175');
  convertInputs(form,'in','mm');
  assert.equal(inputs.width.value,'76.2');
});
