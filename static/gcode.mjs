const axes = ['X','Z','A','B'];
const degrees = Math.PI/180;

export function parseMachineGcode(program) {
  const lines=program.split(/\r?\n/),segments=[];
  let position={X:null,Z:null,A:null,B:null},absolute=true,units=1,motion=null,torch=false,feed=null,inverse=false;
  let contour='Program';
  for(let index=0;index<lines.length;index++){
    const label=lines[index].match(/^\s*\(CONTOUR\s+\d+:\s*([^)]+)\)/i);
    if(label)contour=label[1].trim();
    const code=lines[index].replace(/\([^)]*\)/g,'').split(';')[0].toUpperCase();
    const words=[...code.matchAll(/([A-Z])\s*([-+]?(?:\d+\.?\d*|\.\d+))/g)].map(match=>[match[1],Number(match[2])]);
    for(const [letter,value] of words){
      if(letter==='G'){
        if(value===0||value===1)motion=value;
        else if(value===20)units=25.4;
        else if(value===21)units=1;
        else if(value===90)absolute=true;
        else if(value===91)absolute=false;
        else if(value===93)inverse=true;
        else if(value===94)inverse=false;
        else if(value!==4)throw new Error(`Unsupported G${value} on line ${index+1}`);
      }
      if(letter==='M'){
        if(value===3||value===4)torch=true;
        else if(value===5)torch=false;
        else if(value===2||value===30)return {segments,lines};
        else throw new Error(`Unsupported M${value} on line ${index+1}`);
      }
      if(letter==='F')feed=value;
      if(letter==='Y'||letter==='E')throw new Error(`This preview requires X/Z/A/B machine code, not ${letter} motion`);
    }
    const coordinates=words.filter(([letter])=>axes.includes(letter));
    if(!coordinates.length)continue;
    if(motion===null)throw new Error(`Axis movement has no G0/G1 mode on line ${index+1}`);
    const next={...position};
    for(const [letter,value] of coordinates){
      const amount=value*((letter==='X'||letter==='Z')?units:1);
      if(!absolute&&position[letter]===null)throw new Error(`Incremental ${letter} has no initial position on line ${index+1}`);
      next[letter]=absolute?amount:position[letter]+amount;
    }
    if(axes.every(axis=>position[axis]!==null)&&axes.every(axis=>next[axis]!==null)){
      segments.push({from:position,to:next,rapid:motion===0,cutting:torch&&motion===1,line:index+1,feed,inverse,contour,
        duration:motion===1&&inverse&&feed>0?60/feed:null});
    }
    position=next;
  }
  return {segments,lines};
}

export function machinePose(state,pivot){
  const a=state.A*degrees,b=state.B*degrees;
  const radius=state.Z-pivot*Math.cos(b);
  return {tip:[state.X+pivot*Math.sin(b),radius*Math.cos(a),radius*Math.sin(a)],
    pivot:[state.X,state.Z*Math.cos(a),state.Z*Math.sin(a)],
    direction:[Math.sin(b),-Math.cos(b)*Math.cos(a),-Math.cos(b)*Math.sin(a)]};
}

export function interpolateState(from,to,t){
  return Object.fromEntries(axes.map(axis=>[axis,from[axis]+(to[axis]-from[axis])*t]));
}

export function sampleSegment(segment,pivot,maxDegrees=1){
  const count=Math.max(1,Math.ceil(Math.max(Math.abs(segment.to.A-segment.from.A),Math.abs(segment.to.B-segment.from.B))/maxDegrees));
  return Array.from({length:count+1},(_,i)=>machinePose(interpolateState(segment.from,segment.to,i/count),pivot).tip);
}
