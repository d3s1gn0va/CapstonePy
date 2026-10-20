import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';
import { createIcons, Bot, Play, Pause, Square, RotateCcw, Scan } from 'lucide';
import { createAxes, toRelative, toServo, homePose, normalizePose, jointRotations, validateRecording, sampleRecording, normalizeElbows, elbowRotation } from './model.js';

const axes = createAxes(__CUVO_PROFILE__);
const simulation = __CUVO_SIMULATION__;
if (simulation.mode !== 'simulation_only' || simulation.schema_version !== 1) throw new Error('Unsupported simulation data.');
const dances = simulation.dances.map(dance => validateRecording(axes, dance));
let selectedDance = dances[0];
let elbows = normalizeElbows({});
const storageKey = 'cuvo-simulator-pose-20261018-freestop-v3';
let pose = homePose(axes);
let mode = 'relative';
let preview = null;
let playhead = 0;
let speed = 1;
let ready = false;
let lastEyeFrame = -1;
const atlasImages = new Map();
const eyeMasks = [];
const sounding = new Set();
const decodedSounds = new Map();
let audioContext;
let audioReady = false;
let renderedFrames = 0;

try {
  const stored = JSON.parse(localStorage.getItem(storageKey));
  if (stored?.version === 1) {
    pose = normalizePose(axes, stored.pose);
    if (stored.mode === 'servo') mode = 'servo';
    if (stored.elbows) elbows = normalizeElbows(stored.elbows);
  }
} catch { /* File-based browsing may disallow local storage. */ }

const jointControls = document.getElementById('joint-controls');
for (const [group, title] of [['head', '고개 · 정수리'], ['right', '오른팔'], ['left', '왼팔']]) {
  const section = document.createElement('section');
  section.className = 'joint-group';
  section.dataset.group = group;
  section.innerHTML = `<h3 class="group-title"><span class="group-dot" aria-hidden="true"></span>${title}</h3><div class="group-rows"></div>`;
  for (const axis of axes.filter(item => item.group === group)) {
    const row = document.createElement('div');
    row.className = 'joint-row';
    row.dataset.axis = axis.id;
    row.innerHTML = `
      <div class="joint-heading"><label for="range-${axis.id}">${axis.label}<span class="channel">CH${axis.channel}</span></label><output class="joint-readout" id="readout-${axis.id}"></output></div>
      <div class="joint-inputs"><input type="range" id="range-${axis.id}" step="1" aria-label="${axis.label} 각도"><div class="number-field"><input type="number" id="number-${axis.id}" step="1" aria-label="${axis.label} 각도 직접 입력" inputmode="numeric"></div></div>
      <div class="joint-reference"><span id="bounds-${axis.id}"></span><span>${axis.homeLabel} ${axis.zero}°</span></div>`;
    section.querySelector('.group-rows').append(row);
    row.querySelector('input[type="range"]').addEventListener('input', event => inputAngle(axis, event.target.valueAsNumber));
    const number = row.querySelector('input[type="number"]');
    number.addEventListener('input', () => {
      if (Number.isFinite(number.valueAsNumber)) inputAngle(axis, number.valueAsNumber, false);
    });
    number.addEventListener('change', () => {
      if (Number.isFinite(number.valueAsNumber)) inputAngle(axis, number.valueAsNumber);
      else syncControls();
    });
    number.addEventListener('blur', syncControls);
  }
  jointControls.append(section);
}

function save() {
  try { localStorage.setItem(storageKey, JSON.stringify({ version: 1, pose, mode, elbows })); } catch { /* Storage is optional. */ }
}

function syncControls(updateNumbers = true) {
  for (const axis of axes) {
    const relative = toRelative(axis, pose[axis.id]);
    const value = mode === 'relative' ? relative : pose[axis.id];
    const min = mode === 'relative' ? axis.relativeMin : axis.min;
    const max = mode === 'relative' ? axis.relativeMax : axis.max;
    for (const prefix of ['range', 'number']) {
      const element = document.getElementById(`${prefix}-${axis.id}`);
      element.min = min;
      element.max = max;
      if (prefix === 'range' || updateNumbers) element.value = value;
    }
    document.getElementById(`readout-${axis.id}`).textContent = mode === 'relative' ? `서보 ${pose[axis.id]}°` : `상대 ${relative}°`;
    document.getElementById(`bounds-${axis.id}`).textContent = `${mode === 'relative' ? '상대' : '서보'} ${min}–${max}°`;
  }
  for (const button of document.querySelectorAll('[data-mode]')) button.setAttribute('aria-pressed', String(button.dataset.mode === mode));
}

function inputAngle(axis, value, updateNumbers = true) {
  stopPreview();
  const servo = mode === 'relative' ? toServo(axis, value) : value;
  pose = normalizePose(axes, { [axis.id]: servo }, pose);
  syncControls(updateNumbers);
  applyPose();
  save();
  document.getElementById('angle-announcement').textContent = `${axis.label}, 서보 ${pose[axis.id]}도, 상대 ${toRelative(axis, pose[axis.id])}도`;
}

for (const button of document.querySelectorAll('[data-mode]')) button.addEventListener('click', () => {
  mode = button.dataset.mode;
  syncControls();
  save();
});
document.getElementById('reset-pose').addEventListener('click', () => {
  stopPreview();
  pose = homePose(axes);
  syncControls();
  applyPose();
  save();
});

for (const [side, label] of [['right', '오른팔'], ['left', '왼팔']]) {
  const row = document.createElement('div');
  row.className = 'joint-row';
  row.innerHTML = `<div class="joint-heading"><label for="elbow-${side}">${label}</label><output id="elbow-readout-${side}">${elbows[side]}°</output></div><input type="range" id="elbow-${side}" min="120" max="180" step="1" value="${elbows[side]}" aria-label="${label} 팔꿈치 고정각도"><div class="joint-reference"><span>120°</span><span>180°</span></div>`;
  row.querySelector('input').addEventListener('input', event => {
    elbows = normalizeElbows({ [side]: event.target.valueAsNumber }, elbows);
    document.getElementById(`elbow-readout-${side}`).textContent = `${elbows[side]}°`;
    applyPose();
    save();
  });
  document.getElementById('elbow-controls').append(row);
}

const viewport = document.getElementById('viewport');
const scene = new THREE.Scene();
scene.background = new THREE.Color('#edf2f3');
scene.fog = new THREE.Fog('#edf2f3', 17, 36);
const camera = new THREE.PerspectiveCamera(36, 1, 0.1, 70);
let renderer;
try {
  renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
} catch {
  const error = document.getElementById('render-error');
  error.hidden = false;
  error.textContent = '3D 화면을 열 수 없어요. 하드웨어 가속이 가능한 Safari 또는 Chrome에서 다시 열어주세요.';
  throw new Error('WebGL renderer unavailable.');
}
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.25;
viewport.append(renderer.domElement);

const orbit = new OrbitControls(camera, renderer.domElement);
orbit.target.set(0, 2.35, 0);
orbit.enableDamping = true;
orbit.dampingFactor = 0.09;
orbit.minDistance = 6;
orbit.maxDistance = 17;
orbit.maxPolarAngle = Math.PI * 0.49;
orbit.enablePan = false;

scene.add(new THREE.HemisphereLight('#ffffff', '#81988e', 2.5));
const keyLight = new THREE.DirectionalLight('#ffffff', 3.5);
keyLight.position.set(-4, 9, 7);
keyLight.castShadow = true;
keyLight.shadow.mapSize.set(1024, 1024);
keyLight.shadow.camera.left = -5;
keyLight.shadow.camera.right = 5;
keyLight.shadow.camera.top = 7;
keyLight.shadow.camera.bottom = -5;
keyLight.shadow.normalBias = 0.035;
scene.add(keyLight);
const rim = new THREE.DirectionalLight('#bcd7e4', 1.5);
rim.position.set(6, 5, -5);
scene.add(rim);

const materials = {
  shell: new THREE.MeshStandardMaterial({ color: '#f7faf9', roughness: 0.4, metalness: 0.08 }),
  dark: new THREE.MeshStandardMaterial({ color: '#283334', roughness: 0.6, metalness: 0.15 }),
  right: new THREE.MeshStandardMaterial({ color: '#4b99c6', roughness: 0.5 }),
  left: new THREE.MeshStandardMaterial({ color: '#cf7b80', roughness: 0.5 }),
  green: new THREE.MeshStandardMaterial({ color: '#60a08b', roughness: 0.5 }),
  lens: new THREE.MeshStandardMaterial({ color: '#173b48', roughness: 0.13, metalness: 0.35 }),
  screen: new THREE.MeshStandardMaterial({ color: '#172323', roughness: 0.28 }),
};

function mesh(geometry, material, parent, position = [0, 0, 0]) {
  const object = new THREE.Mesh(geometry, material);
  object.position.set(...position);
  object.castShadow = true;
  object.receiveShadow = true;
  parent.add(object);
  return object;
}
const box = (x, y, z, radius = 0.15) => new RoundedBoxGeometry(x, y, z, 5, radius);
const robot = new THREE.Group();
scene.add(robot);
mesh(box(2.12, 2.12, 1.35, 0.38), materials.shell, robot, [0, 1.56, 0]);
for (const x of [-0.5, 0.5]) mesh(box(0.82, 0.35, 1.13, 0.15), materials.dark, robot, [x, 0.18, 0.12]);
mesh(new THREE.CylinderGeometry(0.38, 0.43, 0.32, 48), materials.dark, robot, [0, 2.71, 0]);
mesh(box(0.6, 0.12, 0.05, 0.045), materials.green, robot, [0, 1.7, 0.693]);

const joints = {};
joints.head = new THREE.Group();
joints.head.position.y = 2.87;
robot.add(joints.head);
mesh(box(2.57, 1.75, 1.76, 0.48), materials.shell, joints.head, [0, 0.86, 0]);
const eyeSurfaces = [];
for (const [index, x] of [-0.59, 0.59].entries()) {
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = 128;
  const context = canvas.getContext('2d');
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.magFilter = THREE.NearestFilter;
  texture.minFilter = THREE.LinearFilter;
  const material = new THREE.MeshBasicMaterial({ map: texture, transparent: true, depthWrite: false, toneMapped: false });
  mesh(new THREE.PlaneGeometry(0.95, 0.95), material, joints.head, [x, 0.87, 0.943]);
  const monitor = document.getElementById(index === 0 ? 'eye-viewer-left' : 'eye-viewer-right').getContext('2d');
  eyeSurfaces.push({ context, texture, monitor });
}
joints.crown = new THREE.Group();
joints.crown.position.y = 1.8;
joints.head.add(joints.crown);
mesh(new THREE.CylinderGeometry(0.44, 0.48, 0.12, 48), materials.green, joints.crown);
mesh(box(0.83, 0.26, 0.65, 0.09), materials.dark, joints.crown, [0, 0.18, 0]);
const lens = mesh(new THREE.CylinderGeometry(0.12, 0.12, 0.075, 36), materials.lens, joints.crown, [0, 0.18, 0.36]);
lens.rotation.x = Math.PI / 2;
mesh(new THREE.TorusGeometry(0.13, 0.018, 8, 40), materials.green, joints.crown, [0, 0.18, 0.407]);

function labelSprite(text, color) {
  const canvas = document.createElement('canvas');
  canvas.width = 128;
  canvas.height = 64;
  const context = canvas.getContext('2d');
  context.fillStyle = color;
  context.font = '600 37px sans-serif';
  context.textAlign = 'center';
  context.textBaseline = 'middle';
  context.fillText(text, 64, 32);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: texture, depthTest: false, transparent: true }));
  sprite.scale.set(0.52, 0.26, 1);
  return sprite;
}

const handTips = {};
const elbowJoints = {};
for (const [side, sign] of [['right', -1], ['left', 1]]) {
  const material = materials[side];
  const bearing = mesh(new THREE.CylinderGeometry(0.26, 0.26, 0.28, 40), material, robot, [sign * 1.16, 2.39, 0]);
  bearing.rotation.z = Math.PI / 2;
  const pivotX = new THREE.Group();
  pivotX.position.set(sign * 1.39, 2.39, 0);
  robot.add(pivotX);
  const pivotY = new THREE.Group();
  pivotX.add(pivotY);
  joints[`${side}_shoulder_x`] = pivotX;
  joints[`${side}_shoulder_y`] = pivotY;
  mesh(new THREE.SphereGeometry(0.25, 24, 16), material, pivotY);
  mesh(new THREE.CapsuleGeometry(0.23, 0.35, 8, 24), materials.shell, pivotY, [0, -0.43, 0]);
  const elbow = new THREE.Group();
  elbow.position.y = -0.85;
  pivotY.add(elbow);
  elbowJoints[side] = elbow;
  mesh(new THREE.SphereGeometry(0.235, 24, 16), material, elbow);
  mesh(new THREE.CapsuleGeometry(0.22, 0.35, 8, 24), materials.shell, elbow, [0, -0.36, 0]);
  mesh(new THREE.SphereGeometry(0.235, 24, 16), material, elbow, [0, -0.63, 0]);
  const tip = new THREE.Object3D();
  tip.position.set(0, -0.85, 0);
  elbow.add(tip);
  handTips[side] = tip;
  const label = labelSprite(side === 'right' ? 'R' : 'L', side === 'right' ? '#2e79a7' : '#aa525a');
  label.position.set(sign * 1.62, 2.95, 0);
  robot.add(label);
}

const ground = mesh(new THREE.PlaneGeometry(100, 100), new THREE.MeshStandardMaterial({ color: '#edf2f3', roughness: 1 }), scene);
ground.rotation.x = -Math.PI / 2;
ground.position.y = -0.015;
ground.castShadow = false;
const grid = new THREE.GridHelper(16, 16, '#ccd9d9', '#d9e2e3');
grid.material.transparent = true;
grid.material.opacity = 0.55;
grid.position.y = -0.01;
scene.add(grid);
const axisHelpers = new THREE.Group();
const bodyAxes = new THREE.AxesHelper(2.0);
bodyAxes.position.set(0, 0.02, 0);
axisHelpers.add(bodyAxes);
for (const joint of Object.values(joints)) {
  const helper = new THREE.AxesHelper(0.55);
  helper.visible = false;
  joint.add(helper);
  joint.userData.axisHelper = helper;
}
axisHelpers.visible = false;
scene.add(axisHelpers);
document.getElementById('show-axes').addEventListener('change', event => {
  axisHelpers.visible = event.target.checked;
  for (const joint of Object.values(joints)) joint.userData.axisHelper.visible = event.target.checked;
});

function applyPose() {
  const rotation = jointRotations(axes, pose);
  joints.head.rotation.y = rotation.headY;
  joints.crown.rotation.y = rotation.crownY;
  joints.right_shoulder_x.rotation.x = rotation.rightX;
  joints.right_shoulder_y.rotation.z = rotation.rightZ;
  joints.left_shoulder_x.rotation.x = rotation.leftX;
  joints.left_shoulder_y.rotation.z = rotation.leftZ;
  for (const side of ['right', 'left']) elbowJoints[side].rotation.x = elbowRotation(elbows[side]);
  scene.updateMatrixWorld(true);
}

const views = {
  perspective: [6.3, 4.2, 9.5],
  front: [0, 3.1, 10.2],
  side: [10.2, 3.1, 0.5],
  top: [0, 11.8, 0.01],
};
function setView(view) {
  camera.position.set(...views[view]);
  orbit.target.set(0, 2.35, 0);
  orbit.update();
  for (const button of document.querySelectorAll('[data-view]')) button.setAttribute('aria-pressed', String(button.dataset.view === view));
}
for (const button of document.querySelectorAll('[data-view]')) button.addEventListener('click', () => setView(button.dataset.view));
document.getElementById('reset-view').addEventListener('click', () => setView('perspective'));

function resize() {
  const { width, height } = viewport.getBoundingClientRect();
  if (!width || !height) return;
  camera.aspect = width / height;
  // Preserve the complete robot when the scene is narrower than it is tall.
  camera.fov = width / height < 0.9 ? 48 : 36;
  camera.updateProjectionMatrix();
  renderer.setSize(width, height, false);
}
new ResizeObserver(resize).observe(viewport);
window.addEventListener('resize', resize);

const previewButton = document.getElementById('preview-dance');
const danceSelect = document.getElementById('dance-select');
const timeline = document.getElementById('timeline');
const soundSwitch = document.getElementById('play-sound');
for (const dance of dances) danceSelect.add(new Option(dance.title, dance.id));
document.getElementById('source-hash').textContent = simulation.source_hash.slice(0, 12);
document.getElementById('source-hash').title = simulation.source_hash;

function stopAudio() {
  for (const source of sounding) {
    try { source.stop(); } catch { /* An ended cue has nothing left to stop. */ }
  }
  sounding.clear();
}

async function prepareAudio() {
  if (!soundSwitch.checked) return;
  const dance = selectedDance;
  try {
    audioContext ||= new AudioContext();
    await audioContext.resume();
    await Promise.all(Object.entries(dance.audio_assets).map(async ([name, uri]) => {
      if (!decodedSounds.has(name)) {
        const bytes = Uint8Array.from(atob(uri.split(',')[1]), character => character.charCodeAt(0));
        decodedSounds.set(name, await audioContext.decodeAudioData(bytes.buffer));
      }
    }));
    if (dance !== selectedDance) return;
    audioReady = true;
    document.getElementById('audio-status').textContent = '소리 켜짐';
  } catch {
    soundSwitch.checked = false;
    document.getElementById('audio-status').textContent = '오디오 재생 불가';
  }
}

function playCue(event, offsetMs = 0) {
  if (!soundSwitch.checked || !audioReady || !decodedSounds.has(event.sound)) return;
  const source = audioContext.createBufferSource();
  const gain = audioContext.createGain();
  source.buffer = decodedSounds.get(event.sound);
  source.playbackRate.value = speed;
  gain.gain.value = 0.25;
  source.connect(gain).connect(audioContext.destination);
  source.onended = () => { sounding.delete(source); source.disconnect(); gain.disconnect(); };
  sounding.add(source);
  source.start(0, Math.max(0, offsetMs / 1000));
}

function resumeAudioAt(time) {
  stopAudio();
  for (const event of selectedDance.audio_events) {
    if (event.time_ms <= time && time < event.time_ms + event.duration_ms) playCue(event, time - event.time_ms);
  }
}

function drawEyes(index) {
  if (index === lastEyeFrame) return;
  const image = atlasImages.get(selectedDance.id);
  if (!image) return;
  lastEyeFrame = index;
  const columns = selectedDance.eye_atlas.columns;
  for (const [side, surface] of eyeSurfaces.entries()) {
    const x = (index % columns) * 256 + side * 128;
    const y = Math.floor(index / columns) * 128;
    surface.monitor.drawImage(image, x, y, 128, 128, 0, 0, 128, 128);
    surface.context.clearRect(0, 0, 128, 128);
    surface.context.drawImage(image, x, y, 128, 128, 0, 0, 128, 128);
    const pixels = surface.context.getImageData(0, 0, 128, 128);
    for (let p = 0; p < pixels.data.length; p += 4) pixels.data[p + 3] = eyeMasks[side][p];
    surface.context.putImageData(pixels, 0, 0);
    surface.texture.needsUpdate = true;
  }
}

function formatTime(ms) {
  return `${Math.floor(ms / 60000)}:${String(Math.floor(ms / 1000) % 60).padStart(2, '0')}.${Math.floor(ms % 1000 / 100)}`;
}

function showRecording(time) {
  const sample = sampleRecording(axes, selectedDance, time);
  playhead = sample.timeMs;
  pose = sample.pose;
  syncControls();
  applyPose();
  drawEyes(sample.eyeFrame);
  timeline.value = playhead;
  document.getElementById('playback-time').textContent = `${formatTime(playhead)} / ${formatTime(selectedDance.duration_ms)}`;
  document.getElementById('preview-state').textContent = playhead === selectedDance.duration_ms ? '완료 · 기본 자세' : sample.stage.label;
  document.getElementById('beat-state').textContent = sample.stage.beat ? `${sample.stage.beat} / 16박` : '';
}

function updatePreviewButton() {
  const label = preview ? '일시정지' : playhead > 0 && playhead < selectedDance.duration_ms ? '춤 재개' : '춤 재생';
  previewButton.setAttribute('aria-label', label);
  previewButton.dataset.tooltip = label;
  previewButton.innerHTML = `<i data-lucide="${preview ? 'pause' : 'play'}"></i>`;
  createIcons({ icons: { Play, Pause }, root: previewButton });
}
function stopPreview() {
  if (preview) updatePreview(performance.now());
  preview = null;
  stopAudio();
  updatePreviewButton();
  save();
}

function beginPreview() {
  if (!ready) return;
  if (playhead >= selectedDance.duration_ms) showRecording(0);
  preview = { start: performance.now(), from: playhead };
  const running = preview;
  resumeAudioAt(playhead);
  prepareAudio().then(() => { if (preview === running) resumeAudioAt(playhead); });
  updatePreviewButton();
}

previewButton.addEventListener('click', () => {
  if (preview) stopPreview();
  else beginPreview();
});
document.getElementById('restart-dance').addEventListener('click', () => {
  stopPreview();
  showRecording(0);
  beginPreview();
});
document.getElementById('stop-dance').addEventListener('click', () => {
  stopPreview();
  showRecording(0);
  updatePreviewButton();
});
timeline.addEventListener('input', () => {
  const playing = Boolean(preview);
  const time = timeline.valueAsNumber;
  stopPreview();
  showRecording(time);
  if (playing) beginPreview();
  else updatePreviewButton();
});
document.getElementById('playback-speed').addEventListener('change', event => {
  const playing = Boolean(preview);
  stopPreview();
  speed = Number(event.target.value);
  if (playing) beginPreview();
});
soundSwitch.addEventListener('change', async () => {
  stopAudio();
  if (soundSwitch.checked) {
    await prepareAudio();
    if (preview) resumeAudioAt(playhead);
  } else document.getElementById('audio-status').textContent = '소리 꺼짐';
});
danceSelect.addEventListener('change', () => {
  stopPreview();
  selectedDance = dances.find(dance => dance.id === danceSelect.value);
  lastEyeFrame = -1;
  audioReady = false;
  updateDance();
});
document.addEventListener('visibilitychange', () => {
  if (document.hidden) stopPreview();
});

function updatePreview(now) {
  if (!preview) return;
  const previous = playhead;
  const time = Math.min(selectedDance.duration_ms, preview.from + (now - preview.start) * speed);
  showRecording(time);
  for (const event of selectedDance.audio_events) {
    if (previous < event.time_ms && event.time_ms <= time && time < event.time_ms + event.duration_ms) playCue(event, time - event.time_ms);
  }
  if (time === selectedDance.duration_ms) {
    preview = null;
    stopAudio();
    updatePreviewButton();
  }
}

function updateDance() {
  timeline.max = selectedDance.duration_ms;
  document.getElementById('dance-meta').textContent = `${selectedDance.bpm ? `${selectedDance.bpm} BPM · ` : ''}${(selectedDance.duration_ms / 1000).toFixed(1)}초`;
  showRecording(0);
  updatePreviewButton();
}

async function loadRecordings() {
  try {
    const mask = new Image();
    mask.src = simulation.eye_mask_source;
    await mask.decode();
    for (const side of [0, 1]) {
      const canvas = document.createElement('canvas');
      canvas.width = canvas.height = 128;
      const context = canvas.getContext('2d');
      context.drawImage(mask, side * 128, 0, 128, 128, 0, 0, 128, 128);
      eyeMasks.push(context.getImageData(0, 0, 128, 128).data);
    }
    await Promise.all(dances.map(async dance => {
      const image = new Image();
      image.src = dance.eye_atlas.source;
      await image.decode();
      atlasImages.set(dance.id, image);
    }));
    ready = true;
    previewButton.disabled = false;
    updateDance();
  } catch {
    document.getElementById('preview-state').textContent = '눈 프레임을 불러오지 못했어요';
  }
}

syncControls();
applyPose();
setView('perspective');
resize();
createIcons({ icons: { Bot, Play, Pause, Square, RotateCcw, Scan } });
loadRecordings();
let previousFrame = 0;
renderer.setAnimationLoop(now => {
  if (now - previousFrame < 1000 / 40) return;
  previousFrame = now;
  updatePreview(now);
  orbit.update();
  renderer.render(scene, camera);
  renderedFrames += 1;
});

// Read-only scene snapshots make angle-direction and framing checks repeatable.
window.cuvoSimulator = Object.freeze({
  getState: () => ({ pose: { ...pose }, relative: Object.fromEntries(axes.map(axis => [axis.id, toRelative(axis, pose[axis.id])])), elbows: { ...elbows }, mode, playing: Boolean(preview), frames: renderedFrames, ready, timeMs: playhead, durationMs: selectedDance.duration_ms, danceId: selectedDance.id, speed, audioReady, sourceHash: simulation.source_hash, recorded: sampleRecording(axes, selectedDance, playhead) }),
  setPose: patch => { stopPreview(); pose = normalizePose(axes, patch, pose); syncControls(); applyPose(); save(); },
  getSceneSnapshot: () => {
    scene.updateMatrixWorld(true);
    const world = object => object.getWorldPosition(new THREE.Vector3()).toArray();
    const bounds = new THREE.Box3().setFromObject(robot);
    const projected = [];
    for (const x of [bounds.min.x, bounds.max.x]) for (const y of [bounds.min.y, bounds.max.y]) for (const z of [bounds.min.z, bounds.max.z]) {
      projected.push(new THREE.Vector3(x, y, z).project(camera));
    }
    return {
      joints: Object.fromEntries(Object.entries(joints).map(([id, joint]) => [id, { position: world(joint), rotation: joint.rotation.toArray().slice(0, 3) }])),
      hands: { right: world(handTips.right), left: world(handTips.left) },
      elbows: Object.fromEntries(Object.entries(elbowJoints).map(([side, joint]) => [side, { angle: elbows[side], rotation: joint.rotation.x, position: world(joint) }])),
      faceDirection: new THREE.Vector3(0, 0, 1).applyQuaternion(joints.head.getWorldQuaternion(new THREE.Quaternion())).toArray(),
      crownDirection: new THREE.Vector3(0, 0, 1).applyQuaternion(joints.crown.getWorldQuaternion(new THREE.Quaternion())).toArray(),
      worldBounds: [...bounds.min.toArray(), ...bounds.max.toArray()],
      projectedBounds: {
        minX: Math.min(...projected.map(point => point.x)), maxX: Math.max(...projected.map(point => point.x)),
        minY: Math.min(...projected.map(point => point.y)), maxY: Math.max(...projected.map(point => point.y)),
      },
    };
  },
});
