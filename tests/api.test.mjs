import test from 'node:test';
import assert from 'node:assert/strict';
import {readPlanResponse, planURL} from '../static/api.mjs';

test('XML proxy errors have an actionable error rather than a JSON parser failure', async () => {
  for (const status of [200, 403, 502]) {
    const response = new Response('<?xml version="1.0"?><Error>Denied</Error>',
      {status, headers: {'Content-Type': 'application/xml'}});
    await assert.rejects(readPlanResponse(response), new RegExp(`HTTP ${status}.*proxy`));
  }
});
test('HTML cannot be downloaded as G-code', async () => {
  await assert.rejects(readPlanResponse(new Response('<html>Login</html>',
    {headers: {'Content-Type': 'text/html'}}), true), /instead of a G-code file/);
});
test('JSON application errors remain visible', async () => {
  await assert.rejects(readPlanResponse(new Response(JSON.stringify({error:'Stock mismatch'}),
    {status:400,headers:{'Content-Type':'application/json'}})), /Stock mismatch/);
});
test('malformed and unexpected JSON fail clearly', async () => {
  await assert.rejects(readPlanResponse(new Response('{', {headers:{'Content-Type':'application/json'}})), /malformed JSON/);
  await assert.rejects(readPlanResponse(new Response('{}', {headers:{'Content-Type':'application/json'}})), /invalid toolpath/);
});
test('valid toolpath and G-code responses are accepted', async () => {
  const data={points:[{x:1,y:2,z:3,a:0},{x:1,y:2,z:3,a:360}],width:50,height:50,bevel:0,bevel_offset:0,triangles:10,warnings:[]};
  assert.deepEqual(await readPlanResponse(new Response(JSON.stringify(data), {headers:{'Content-Type':'application/json'}})),data);
  const blob=await readPlanResponse(new Response('G21\nM2\n', {headers:{'Content-Type':'text/plain'}}),true);
  assert.equal(await blob.text(),'G21\nM2\n');
});
test('API address retains development proxy prefixes', () => {
  assert.equal(planURL('https://host/proxy/5000/?token=example#preview'),'https://host/proxy/5000/api/plan');
  assert.equal(planURL('https://host/proxy/5000'),'https://host/proxy/5000/api/plan');
  assert.equal(planURL('http://localhost:5000/'),'http://localhost:5000/api/plan');
});
