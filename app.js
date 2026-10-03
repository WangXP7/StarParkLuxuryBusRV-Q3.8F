import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';

// The glTF was written with export_yup: three.y = blender.z (up), three.z = -blender.y.
// The nose points to +X; the entrance door sits on +Z.
// The exporter names nodes after the mesh data-block, so match by stripped suffix.
const base = (n) => n.replace(/_\d+$/, '');
// Everything is clipped in the cutaway views except the running gear and the cabin
// fittings, which is what makes them readable instead of hollowing the furniture too.
// The names are the first mesh joined into each module, not the collection names.
const KEEP = new Set(['Cylinder012', 'Cylinder021', 'Cylinder030', 'Cylinder039', 'Cylinder048',
  'Cylinder057', 'dash', 'block', 'gfloor', 'floor', 'kcab', 'bedplat', 'rec', 'rail',
  'sofa1', 'Downlights', 'InteriorLED']);

const VIEWS = {
  orbit: [
    { k: '前四分之三', pos: [15.4, 13.7, 12.6], tgt: [0.75, 1.90, 0.35], fov: 26 },
    { k: '正侧', pos: [0.5, 4.4, 21.0], tgt: [0, 1.95, 0], fov: 26 },
    { k: '车尾', pos: [-18.0, 8.6, 13.0], tgt: [-1.2, 1.95, 0], fov: 26 },
    { k: '车顶俯视', pos: [1.5, 27.0, 7.0], tgt: [0, 0.8, 0], fov: 29 },
    { k: '前脸特写', pos: [10.6, 2.7, 5.7], tgt: [5.7, 1.75, 0], fov: 26 },
    { k: '车轮特写', pos: [4.6, 1.3, 4.0], tgt: [2.9, 0.62, 1.1], fov: 26 },
    { k: '底盘后桥', pos: [-6.4, 1.15, 7.4], tgt: [-3.4, 0.6, 0.6], fov: 28 },
    { k: '后部车库', pos: [-9.2, 0.72, 3.4], tgt: [-4.6, 0.62, 0.2], fov: 40 },
    // the wet bath is a 0.5 m deep cell with no standing room, so it is shown by cutting the coach open
    { k: '卫浴模块', sec: true, pos: [-1.90, 2.75, 4.30], tgt: [-2.20, 1.66, -0.90], fov: 34, cut: -0.78 }
  ],
  interior: [
    // three.z = -blender.y, so the driver (left-hand drive, blender +Y) sits at -Z.
    // every eye point was ray-checked clear of the cabin geometry in all six directions
    { k: '驾驶席', pos: [3.80, 2.38, -0.55], yaw: -Math.PI / 2, pitch: -0.10, fov: 62 },
    { k: '全景过道', pos: [0.20, 1.75, 0.00], yaw: -Math.PI / 2, pitch: -0.04 },
    { k: '会客沙发', pos: [2.90, 2.05, 0.30], yaw: Math.PI / 2, pitch: -0.10 },
    { k: '厨房', pos: [1.40, 1.72, -0.30], yaw: 2.03, pitch: -0.10 },
    { k: '后舱回望', pos: [-1.70, 1.72, 0.10], yaw: Math.PI / 2, pitch: -0.12, fov: 68 },
    { k: '上层卧铺', pos: [-4.60, 2.30, 0.10], yaw: -Math.PI / 2, pitch: -0.15 }
  ],
  look: [
    { k: '看向·前', yaw: -Math.PI / 2 },
    { k: '看向·后', yaw: Math.PI / 2 },
    { k: '看向·左', yaw: 0 },
    { k: '看向·右', yaw: Math.PI }
  ]
};

// the aisle the walker is allowed to roam, in metres — keeps you out of the galley run
const WALK = { x: [-4.95, 4.60], z: [-0.80, 0.55] };

const canvas = document.getElementById('stage');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: 'high-performance' });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setSize(innerWidth, innerHeight, false);
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 0.96;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.localClippingEnabled = true;

const scene = new THREE.Scene();
scene.fog = new THREE.Fog(0x574d43, 34, 118);

const camera = new THREE.PerspectiveCamera(26, innerWidth / innerHeight, 0.05, 400);
camera.position.set(19.0, 16.7, 15.6);

const pmrem = new THREE.PMREMGenerator(renderer);
scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;

function gradientTexture() {
  const c = document.createElement('canvas');
  c.width = c.height = 512;
  const g = c.getContext('2d');
  const r = g.createRadialGradient(256, 256, 20, 256, 256, 256);
  r.addColorStop(0, '#4a453f');
  r.addColorStop(0.40, '#2a2724');
  r.addColorStop(1, '#0a0a0b');
  g.fillStyle = r;
  g.fillRect(0, 0, 512, 512);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

// a painted horizon: without it the driver's-eye view looks out onto a void
function skyTexture() {
  const c = document.createElement('canvas');
  c.width = 8;
  c.height = 256;
  const g = c.getContext('2d');
  const lg = g.createLinearGradient(0, 0, 0, 256);
  lg.addColorStop(0.00, '#0e1013');
  lg.addColorStop(0.36, '#282c33');
  lg.addColorStop(0.49, '#7d7166');
  lg.addColorStop(0.53, '#4b443d');
  lg.addColorStop(1.00, '#121214');
  g.fillStyle = lg;
  g.fillRect(0, 0, 8, 256);
  const t = new THREE.CanvasTexture(c);
  t.mapping = THREE.EquirectangularReflectionMapping;
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}
scene.background = skyTexture();

const ground = new THREE.Mesh(
  new THREE.CircleGeometry(90, 96),
  new THREE.MeshStandardMaterial({ map: gradientTexture(), roughness: 0.94, metalness: 0.0, envMapIntensity: 0.25 })
);
ground.rotation.x = -Math.PI / 2;
ground.receiveShadow = true;
scene.add(ground);

const sun = new THREE.DirectionalLight(0xfff2e0, 2.1);
sun.position.set(16, 22, -14);
sun.castShadow = true;
sun.shadow.mapSize.set(2048, 2048);
sun.shadow.camera.near = 1;
sun.shadow.camera.far = 70;
sun.shadow.camera.left = -14;
sun.shadow.camera.right = 14;
sun.shadow.camera.top = 12;
sun.shadow.camera.bottom = -6;
sun.shadow.bias = -0.0006;
sun.shadow.normalBias = 0.02;
scene.add(sun);
scene.add(new THREE.HemisphereLight(0xbcd0e8, 0x3b352e, 0.38));

for (const x of [-4.4, -1.6, 1.2, 3.6, 4.9]) {
  const p = new THREE.PointLight(0xffb46a, 6, 9, 2);
  p.position.set(x, 3.0, 0);
  scene.add(p);
}

const clipPlane = new THREE.Plane(new THREE.Vector3(0, 0, -1), 0.35);
const clipMats = [];
// glass reads dark and mirrored from outside, but has to clear up once you are inside
const GLASS = { WindGlass: 1, TintGlass: 1, BlackGlass: 1 };
const glass = [];
let model = null;

const controls = new OrbitControls(camera, canvas);
controls.enableDamping = true;
controls.dampingFactor = 0.06;
controls.minDistance = 2.2;
controls.maxDistance = 70;
controls.maxPolarAngle = Math.PI * 0.497;
controls.target.set(0.75, 1.80, 0.35);
controls.autoRotate = true;
controls.autoRotateSpeed = 0.55;
controls.addEventListener('start', () => { controls.autoRotate = false; });

const fp = {
  on: false, yaw: -Math.PI / 2, pitch: -0.05,
  keys: new Set(), drag: null, pos: new THREE.Vector3(2.5, 1.55, -0.1)
};

new GLTFLoader().load(
  './assets/starpark_rv.glb',
  (gltf) => {
    model = gltf.scene;
    model.traverse((o) => {
      if (!o.isMesh) return;
      o.castShadow = true;
      o.receiveShadow = true;
      if (!KEEP.has(base(o.name))) {
        o.material = o.material.clone();
        o.material.clippingPlanes = [];
        clipMats.push(o.material);
      }
      const mat = o.material;
      if (GLASS[mat.name] !== undefined) {
        mat.transparent = true;
        mat.depthWrite = false;
        mat.roughness = 0.06;
        mat.metalness = 0.0;
        glass.push(mat);
      }
    });
    scene.add(model);
    setGlass(false);
    document.getElementById('loader').classList.add('done');
    applyQuery();
  },
  (e) => {
    if (!e.total) return;
    document.getElementById('pbar').style.width = Math.round(e.loaded / e.total * 100) + '%';
  },
  (err) => { document.getElementById('ptext').textContent = '模型载入失败：' + err.message; }
);

const chipsEl = document.getElementById('chips');
const hintEl = document.getElementById('hint');
const cutWrap = document.getElementById('cutWrap');
const cutSlider = document.getElementById('cut');
let mode = 'orbit';

function addChip(label, fn) {
  const b = document.createElement('button');
  b.textContent = label;
  b.onclick = () => {
    fn();
    [...chipsEl.children].forEach((c) => c.classList.remove('on'));
    b.classList.add('on');
  };
  chipsEl.appendChild(b);
  return b;
}

function markChip(i) {
  [...chipsEl.children].forEach((c, n) => c.classList.toggle('on', n === i));
}

function buildChips() {
  chipsEl.innerHTML = '';
  if (mode === 'interior') {
    VIEWS.interior.forEach((v) => addChip(v.k, () => applyStation(v)));
    chipsEl.appendChild(document.createTextNode(' '));
    VIEWS.look.forEach((v) => addChip(v.k, () => { fp.yaw = v.yaw; }));
  } else {
    VIEWS.orbit.forEach((v) => {
      if (!v.sec || mode === 'section') addChip(v.k, () => applyView(mode, v));
    });
  }
  if (chipsEl.firstChild) chipsEl.firstChild.classList.add('on');
}

function applyView(kind, v) {
  fp.on = false;
  controls.enabled = true;
  camera.up.set(0, 1, 0);
  camera.fov = v.fov || 40;
  camera.updateProjectionMatrix();
  camera.position.set(...v.pos);
  controls.target.set(...v.tgt);
  controls.autoRotate = false;
  controls.update();
  if (Number.isFinite(v.cut)) clipPlane.constant = v.cut;
  const on = Number.isFinite(v.cut) || mode === 'section';
  clipMats.forEach((m) => { m.clippingPlanes = on ? [clipPlane] : []; });
  // dark mirrored glazing over a cut-open body turns the near windows into opaque sheets
  setGlass(on || mode !== 'orbit');
  cutSlider.value = clipPlane.constant;
}

function applyStation(v) {
  fp.on = true;
  controls.enabled = false;
  fp.pos.set(...v.pos);
  fp.yaw = v.yaw;
  fp.pitch = v.pitch || 0;
  camera.fov = v.fov || 55;
  camera.updateProjectionMatrix();
}

function setGlass(clear) {
  // mirrored and dark from the street, near-invisible once you are standing inside
  glass.forEach((m) => {
    if (clear) { m.opacity = m.name === 'BlackGlass' ? 0.45 : 0.16; m.color.setRGB(0.30, 0.36, 0.41); }
    else { m.opacity = m.name === 'BlackGlass' ? 0.92 : 0.80; m.color.setRGB(0.045, 0.055, 0.065); }
  });
}

function setMode(next) {
  mode = next;
  document.getElementById('modes').querySelectorAll('button')
    .forEach((b) => b.classList.toggle('on', b.dataset.mode === next));
  cutWrap.hidden = next !== 'section';
  clipMats.forEach((m) => { m.clippingPlanes = next === 'section' ? [clipPlane] : []; });
  setGlass(next !== 'orbit');
  hintEl.textContent = next === 'interior'
    ? '拖拽环视四周 · W/A/S/D 或方向键在车内走动 · 滚轮改变视野'
    : next === 'section'
      ? '拖动滑块沿车身纵向剖开 · 按住拖拽旋转视角'
      : '按住拖拽旋转视角 · 滚轮缩放 · 右键平移';
  if (next === 'interior') applyStation(VIEWS.interior[0]);
  else applyView(next, VIEWS.orbit[0]);
  buildChips();
}

document.getElementById('modes').addEventListener('click', (e) => {
  const b = e.target.closest('button');
  if (b) setMode(b.dataset.mode);
});

// ?mode=orbit|interior|section & view=N / station=N / cut=-1.35..1.35  — shareable deep links
function applyQuery() {
  const q = new URLSearchParams(location.search);
  const want = q.get('mode');
  if (want === 'orbit' || want === 'interior' || want === 'section') setMode(want);
  const i = parseInt(q.get('station'), 10);
  if (mode === 'interior' && VIEWS.interior[i]) { applyStation(VIEWS.interior[i]); markChip(i); }
  const v = parseInt(q.get('view'), 10);
  const preset = VIEWS.orbit[v];
  if (mode !== 'interior' && preset && (!preset.sec || mode === 'section')) {
    applyView(mode, preset);
    markChip(v);
  }
  const cut = parseFloat(q.get('cut'));
  if (Number.isFinite(cut)) {
    clipPlane.constant = Math.max(-1.35, Math.min(1.35, cut));
    document.getElementById('cut').value = clipPlane.constant;
  }
}

document.getElementById('cut').addEventListener('input', (e) => {
  clipPlane.constant = parseFloat(e.target.value);
});

canvas.addEventListener('pointerdown', (e) => {
  if (!fp.on) return;
  fp.drag = { x: e.clientX, y: e.clientY };
  canvas.setPointerCapture(e.pointerId);
});
canvas.addEventListener('pointermove', (e) => {
  if (!fp.on || !fp.drag) return;
  fp.yaw -= (e.clientX - fp.drag.x) * 0.0038;
  fp.pitch = Math.max(-1.35, Math.min(1.35, fp.pitch - (e.clientY - fp.drag.y) * 0.0032));
  fp.drag = { x: e.clientX, y: e.clientY };
});
canvas.addEventListener('pointerup', () => { fp.drag = null; });
canvas.addEventListener('wheel', (e) => {
  if (!fp.on) return;
  e.preventDefault();
  camera.fov = Math.max(28, Math.min(95, camera.fov + Math.sign(e.deltaY) * 3));
  camera.updateProjectionMatrix();
}, { passive: false });

addEventListener('keydown', (e) => { fp.keys.add(e.key.toLowerCase()); });
addEventListener('keyup', (e) => { fp.keys.delete(e.key.toLowerCase()); });

function stepFp(dt) {
  const k = fp.keys;
  const fwd = new THREE.Vector3(-Math.sin(fp.yaw), 0, -Math.cos(fp.yaw));
  const right = new THREE.Vector3(-fwd.z, 0, fwd.x);
  const move = new THREE.Vector3();
  if (k.has('w') || k.has('arrowup')) move.add(fwd);
  if (k.has('s') || k.has('arrowdown')) move.sub(fwd);
  if (k.has('a') || k.has('arrowleft')) move.sub(right);
  if (k.has('d') || k.has('arrowright')) move.add(right);
  if (move.lengthSq() > 0) {
    move.normalize().multiplyScalar(2.1 * dt);
    fp.pos.x = Math.max(WALK.x[0], Math.min(WALK.x[1], fp.pos.x + move.x));
    fp.pos.z = Math.max(WALK.z[0], Math.min(WALK.z[1], fp.pos.z + move.z));
  }
  camera.position.copy(fp.pos);
  camera.rotation.order = 'YXZ';
  camera.rotation.set(fp.pitch, fp.yaw, 0);
}

const clock = new THREE.Clock();
renderer.setAnimationLoop(() => {
  const dt = Math.min(clock.getDelta(), 0.05);
  if (fp.on) stepFp(dt);
  else controls.update();
  renderer.render(scene, camera);
});

addEventListener('resize', () => {
  camera.aspect = innerWidth / innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight, false);
});

buildChips();
