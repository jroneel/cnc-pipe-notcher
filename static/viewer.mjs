import * as THREE from './vendor/three.module.js';
import {OrbitControls} from './vendor/OrbitControls.js';
import {parseMachineGcode,machinePose,interpolateState,sampleSegment} from './gcode.mjs';

function dispose(group){
  for(const child of [...group.children]){
    group.remove(child);child.traverse(object=>{object.geometry?.dispose();if(object.material){for(const material of [].concat(object.material))material.dispose();}});
  }
}

export function createViewer(canvas,controls){
  const renderer=new THREE.WebGLRenderer({canvas,antialias:true,preserveDrawingBuffer:true});
  renderer.setClearColor(0x101923);renderer.setPixelRatio(Math.min(devicePixelRatio||1,2));
  const scene=new THREE.Scene(),camera=new THREE.PerspectiveCamera(40,1,.01,100000);
  camera.up.set(0,0,1);camera.position.set(100,-150,100);
  const orbit=new OrbitControls(camera,canvas);orbit.enableDamping=true;
  const part=new THREE.Group(),cuts=new THREE.Group(),rapids=new THREE.Group(),head=new THREE.Group();
  scene.add(part,cuts,rapids,head,new THREE.AmbientLight(0xffffff,2));
  const light=new THREE.DirectionalLight(0xffffff,3);light.position.set(1,-2,3);scene.add(light);
  const marker=new THREE.Mesh(new THREE.SphereGeometry(1,16,8),new THREE.MeshBasicMaterial({color:0xff7185,depthTest:false}));
  const beam=new THREE.Line(new THREE.BufferGeometry(),new THREE.LineBasicMaterial({color:0xff7185,depthTest:false}));
  head.add(marker,beam);head.visible=false;
  let parsed=null,pivot=0,bounds=null,playing=false,lastTime=0,progress=1,modelReady=false;
  function fit(box){
    if(!box||box.isEmpty())return;
    const centre=box.getCenter(new THREE.Vector3()),size=box.getSize(new THREE.Vector3());
    const distance=Math.max(size.length(),1)/(2*Math.tan(camera.fov*Math.PI/360))*1.25;
    orbit.target.copy(centre);camera.position.copy(centre).add(new THREE.Vector3(.25,-1,.6).normalize().multiplyScalar(distance));
    camera.near=Math.max(distance/10000,.001);camera.far=Math.max(distance*100,1000);camera.updateProjectionMatrix();orbit.update();
  }
  function updatePose(value){
    progress=Math.max(0,Math.min(value,1));controls.slider.value=String(progress*1000);
    if(!parsed?.segments.length){head.visible=false;controls.motion.textContent=modelReady?'Original model loaded. Generate machine G-code to see motion.':'Upload a model.';return;}
    const position=progress*parsed.segments.length;
    const index=Math.min(Math.floor(position),parsed.segments.length-1),segment=parsed.segments[index];
    const state=interpolateState(segment.from,segment.to,progress===1?1:position-index),pose=machinePose(state,pivot);
    marker.position.fromArray(pose.tip);
    const beamEnd=pose.tip.map((v,i)=>v+pose.direction[i]*Math.max(8,pivot*.15));
    beam.geometry.dispose();beam.geometry=new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(...pose.pivot),new THREE.Vector3(...pose.tip),new THREE.Vector3(...beamEnd)]);
    const colour=segment.cutting?0xff7185:0x86bfff;marker.material.color.set(colour);beam.material.color.set(colour);
    head.visible=controls.head.checked;
    controls.motion.textContent=`Block ${index+1}/${parsed.segments.length} · ${segment.contour} · line ${segment.line} · ${segment.cutting?'TORCH ON':segment.rapid?'RAPID · torch off':'torch off'} · X ${state.X.toFixed(3)} mm Z ${state.Z.toFixed(3)} mm A ${state.A.toFixed(2)}° B ${state.B.toFixed(2)}°`;
    controls.program.dataset.line=String(segment.line);
  }
  function show(){part.visible=controls.model.checked;cuts.visible=controls.cuts.checked;rapids.visible=controls.rapid.checked;head.visible=!!parsed&&controls.head.checked;}
  for(const control of [controls.model,controls.cuts,controls.rapid,controls.head])control.addEventListener('change',show);
  controls.fit.addEventListener('click',()=>fit(bounds));
  function focusContour(){
    if(!parsed)return;
    const selected=controls.contour.value;
    const box=new THREE.Box3();for(const segment of parsed.segments.filter(s=>s.cutting&&(!selected||s.contour===selected)))for(const point of sampleSegment(segment,pivot,3))box.expandByPoint(new THREE.Vector3(...point));
    if(!box.isEmpty())fit(box.expandByScalar(Math.max(5,pivot*.1)));
  }
  controls.focus.addEventListener('click',focusContour);
  controls.contour.addEventListener('change',()=>{
    playing=false;controls.play.textContent='Play';focusContour();
    const index=parsed?.segments.findIndex(segment=>segment.cutting&&segment.contour===controls.contour.value);
    if(index>=0)updatePose((index+.5)/parsed.segments.length);
  });
  controls.slider.addEventListener('input',()=>{playing=false;controls.play.textContent='Play';updatePose(Number(controls.slider.value)/1000);});
  controls.play.addEventListener('click',()=>{if(!parsed)return;if(progress>=1)updatePose(0);playing=!playing;controls.play.textContent=playing?'Pause':'Play';});
  controls.reset.addEventListener('click',()=>{playing=false;controls.play.textContent='Play';updatePose(0);});
  const resize=()=>{const width=canvas.clientWidth,height=canvas.clientHeight;renderer.setSize(width,height,false);camera.aspect=width/height;camera.updateProjectionMatrix();};
  const observer=new ResizeObserver(resize);observer.observe(canvas);resize();
  renderer.setAnimationLoop(time=>{
    if(playing){updatePose(progress+Math.min(time-lastTime,100)*.00004);if(progress>=1){playing=false;controls.play.textContent='Play';}}
    lastTime=time;orbit.update();renderer.render(scene,camera);
  });
  return {
    clearProgram(){playing=false;parsed=null;dispose(cuts);dispose(rapids);canvas.dataset.gcodeSegments='0';canvas.dataset.contourCount='0';controls.program.value='';controls.contour.replaceChildren(new Option('All contours',''));controls.play.textContent='Play';controls.slider.disabled=true;controls.play.disabled=true;updatePose(0);},
    clearModel(){dispose(part);modelReady=false;bounds=null;this.clearProgram();canvas.dataset.modelFaces='0';},
    setModel(model){
      dispose(part);
      const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.Float32BufferAttribute(model.vertices.flat(),3));geometry.setIndex(model.faces.flat());geometry.computeVertexNormals();
      const mesh=new THREE.Mesh(geometry,new THREE.MeshStandardMaterial({color:0x6685a0,side:THREE.DoubleSide,transparent:true,opacity:.65,roughness:.7,depthWrite:false}));part.add(mesh);
      const edges=new THREE.LineSegments(new THREE.EdgesGeometry(geometry,30),new THREE.LineBasicMaterial({color:0x8aa6bc,transparent:true,opacity:.35}));part.add(edges);
      bounds=new THREE.Box3().setFromObject(mesh);modelReady=true;canvas.dataset.modelFaces=String(model.faces.length);fit(bounds);show();updatePose(progress);
    },
    setProgram(program,length){
      this.clearProgram();pivot=length;parsed=parseMachineGcode(program);controls.program.value=program;
      const names=[...new Set(parsed.segments.filter(s=>s.cutting).map(s=>s.contour))];
      controls.contour.replaceChildren(new Option('All contours',''),...names.map(name=>new Option(name,name)));
      canvas.dataset.contourCount=String(names.length);
      const cutVertices=[],rapidVertices=[];
      for(const segment of parsed.segments){
        const points=sampleSegment(segment,pivot),vertices=segment.cutting?cutVertices:rapidVertices;
        for(let i=1;i<points.length;i++)vertices.push(...points[i-1],...points[i]);
      }
      for(const [vertices,group,colour,opacity] of [[cutVertices,cuts,0x68d8b9,1],[rapidVertices,rapids,0xedbd68,.55]]){
        const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.Float32BufferAttribute(vertices,3));
        group.add(new THREE.LineSegments(geometry,new THREE.LineBasicMaterial({color:colour,transparent:true,opacity,depthTest:false})));
      }
      const scale=bounds?Math.max(bounds.getSize(new THREE.Vector3()).length()*.002,.7):1;marker.scale.setScalar(scale);
      controls.slider.disabled=false;controls.play.disabled=false;canvas.dataset.gcodeSegments=String(parsed.segments.length);show();updatePose(1);
    }
  };
}
