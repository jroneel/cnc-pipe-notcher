import test from 'node:test';
import assert from 'node:assert/strict';
import {parseMachineGcode,machinePose,sampleSegment} from '../static/gcode.mjs';

test('machine words, torch state and inverse feed define paths rather than planned points',()=>{
  const parsed=parseMachineGcode('(comment)\nG21 G90 G94\nM5\nG0 Z100\nG0 X10 A0 B0\nG1 Z25 F800\nM3\nG93\nG1 X12 Z25 A90 B0 F2\nM5\nG0 Z100\nM2\nG1 X999');
  assert.equal(parsed.segments.length,3);
  assert.equal(parsed.segments[0].cutting,false);
  assert.equal(parsed.segments[1].cutting,true);
  assert.equal(parsed.segments[1].duration,30);
  assert.equal(parsed.segments[2].rapid,true);
  assert.equal(parsed.segments[2].cutting,false);
  assert.deepEqual(machinePose(parsed.segments[1].to,0).tip.map(v=>Math.round(v)),[12,0,25]);
});

test('B pivot compensation and direction reconstruct the torch in part coordinates',()=>{
  const pose=machinePose({X:10,Z:100,A:0,B:30},100);
  assert.ok(Math.abs(pose.tip[0]-60)<1e-9);
  assert.ok(Math.abs(pose.tip[1]-(100-100*Math.cos(Math.PI/6)))<1e-9);
  assert.ok(Math.abs(pose.direction[0]-.5)<1e-9);
  assert.ok(Math.abs(pose.direction[1]+Math.cos(Math.PI/6))<1e-9);
});

test('interpolated rotary moves trace an arc, not a chord',()=>{
  const segment={from:{X:0,Z:25,A:0,B:0},to:{X:0,Z:25,A:90,B:0}};
  const samples=sampleSegment(segment,0,5);
  assert.equal(samples.length,19);
  for(const p of samples)assert.ok(Math.abs(Math.hypot(p[1],p[2])-25)<1e-9);
  assert.ok(Math.abs(samples[9][1]-25/Math.sqrt(2))<1e-9);
});

test('modal positioning, inches and incremental axes are interpreted',()=>{
  const parsed=parseMachineGcode('G20\nG90\nG0 X1 Z2 A0 B0\nG91\nG1 X1 A90 F10\nZ1\nM2');
  assert.equal(parsed.segments[0].to.X,50.8);
  assert.equal(parsed.segments[0].to.Z,50.8);
  assert.equal(parsed.segments[0].to.A,90);
  assert.ok(Math.abs(parsed.segments[1].to.Z-76.2)<1e-9);
});

test('unsupported programs cannot masquerade as machine previews',()=>{
  assert.throws(()=>parseMachineGcode('G2 X1'),/Unsupported G2/);
  assert.throws(()=>parseMachineGcode('G1 X1 Y1 E1'),/not Y motion/);
  assert.throws(()=>parseMachineGcode('G91\nG1 X1'),/no initial position/);
});
