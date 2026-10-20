import { readFile } from 'node:fs/promises';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createAxes, clampServo, toServo, toRelative, homePose, normalizePose, jointRotations, validateRecording, sampleRecording, normalizeElbows, elbowRotation } from './model.js';

const profile = JSON.parse(await readFile(new URL('../../raspberry_pi/robot_demo/robot_motion_profile.json', import.meta.url)));
const simulation = JSON.parse(await readFile(new URL('simulation-data.json', import.meta.url)));
const axes = createAxes(profile);
const axis = id => axes.find(item => item.id === id);

test('the six channel mappings match the robot profile', () => {
  assert.deepEqual(Object.fromEntries(axes.map(item => [item.id, item.channel])), {
    head: 0, crown: 2, right_shoulder_x: 1, right_shoulder_y: 3, left_shoulder_x: 4, left_shoulder_y: 5,
  });
});

test('the user-defined neutral commands all correspond to relative zero', () => {
  assert.deepEqual(homePose(axes), {
    head: 90, crown: 90, right_shoulder_x: 45, right_shoulder_y: 0, left_shoulder_x: 135, left_shoulder_y: 180,
  });
  for (const item of axes) assert.equal(toRelative(item, item.neutral), 0);
});

test('the safety limits and relative limits are preserved', () => {
  assert.deepEqual(axes.map(item => [item.id, item.min, item.max, item.relativeMin, item.relativeMax]), [
    ['head', 45, 135, -45, 45], ['crown', 45, 135, -45, 45],
    ['right_shoulder_x', 0, 180, -45, 135], ['right_shoulder_y', 0, 45, 0, 45],
    ['left_shoulder_x', 0, 180, -45, 135], ['left_shoulder_y', 135, 180, 0, 45],
  ]);
});

test('left arm commands decrease as its relative position increases', () => {
  assert.equal(toServo(axis('left_shoulder_x'), 60), 75);
  assert.equal(toServo(axis('left_shoulder_y'), 30), 150);
  assert.equal(toServo(axis('right_shoulder_x'), 60), 105);
  assert.equal(toServo(axis('right_shoulder_y'), 30), 30);
});

test('head and crown 45 degrees mean robot-left', () => {
  for (const id of ['head', 'crown']) {
    assert.equal(toRelative(axis(id), 45), -45);
    assert.equal(toServo(axis(id), 45), 135);
  }
  const rotation = jointRotations(axes, normalizePose(axes, { head: 45, crown: 45 }));
  assert.ok(rotation.headY > 0 && rotation.crownY > 0);
});

test('out-of-range parameters are clamped on every axis', () => {
  for (const item of axes) {
    assert.equal(clampServo(item, -999), item.min);
    assert.equal(clampServo(item, 999), item.max);
    assert.ok(toServo(item, -999) >= item.min);
    assert.ok(toServo(item, 999) <= item.max);
  }
});

test('non-finite and unknown parameters are rejected', () => {
  for (const value of [NaN, Infinity, undefined, null, '90']) {
    assert.throws(() => clampServo(axis('head'), value), TypeError);
  }
  assert.throws(() => normalizePose(axes, { not_a_joint: 10 }), TypeError);
});

test('changing one parameter preserves the other five', () => {
  const previous = homePose(axes);
  const next = normalizePose(axes, { head: 60 }, previous);
  assert.equal(next.head, 60);
  assert.equal(previous.head, 90);
  assert.equal(next.left_shoulder_y, 180);
});

test('arm forward and outward rotations are mirrored correctly', () => {
  const pose = normalizePose(axes, { right_shoulder_x: 105, left_shoulder_x: 75, right_shoulder_y: 30, left_shoulder_y: 150 });
  const rotation = jointRotations(axes, pose);
  assert.equal(rotation.rightX, rotation.leftX);
  assert.equal(rotation.rightZ, -rotation.leftZ);
});

test('both recordings are complete runtime exports and finish at neutral', () => {
  assert.equal(simulation.mode, 'simulation_only');
  assert.equal(simulation.source_hash.length, 64);
  assert.deepEqual(simulation.profile, profile);
  for (const dance of simulation.dances) {
    validateRecording(axes, dance);
    assert.deepEqual(sampleRecording(axes, dance, dance.duration_ms).pose, homePose(axes));
  }
  const groove = simulation.dances.find(dance => dance.id === 'cuvo_groove');
  assert.ok(groove.duration_ms <= 15000);
  assert.equal(groove.stages.filter(stage => stage.beat).length, 16);
});

test('playback consumes all six channel values without recalculating the dance', () => {
  for (const dance of simulation.dances) for (const sample of dance.samples) {
    const snapshot = sampleRecording(axes, dance, sample[0]);
    for (const item of axes) assert.equal(snapshot.pose[item.id], sample[1][item.channel]);
    assert.deepEqual(snapshot.eyePose, sample[4]);
    assert.equal(snapshot.eyeFrame, sample[2]);
  }
});

test('scrubbing is deterministic and bounded, without browser easing', () => {
  const dance = simulation.dances[0];
  assert.equal(sampleRecording(axes, dance, -100).sampledMs, 0);
  assert.equal(sampleRecording(axes, dance, 999999).sampledMs, dance.duration_ms);
  const sample = sampleRecording(axes, dance, 1359);
  assert.equal(sample.sampledMs, 1340);
  assert.deepEqual(sampleRecording(axes, dance, 1359), sample);
  assert.throws(() => sampleRecording(axes, dance, NaN), TypeError);
});

test('elbows are static manual geometry and never additional motor axes', () => {
  assert.equal(axes.length, 6);
  assert.deepEqual(normalizeElbows({}), { right: 150, left: 150 });
  assert.deepEqual(normalizeElbows({ right: 0, left: 200 }), { right: 120, left: 180 });
  assert.equal(elbowRotation(180), -0);
  assert.ok(Math.abs(elbowRotation(120) + Math.PI / 3) < 1e-9);
  assert.throws(() => normalizeElbows({ head: 150 }), TypeError);
  assert.throws(() => normalizeElbows({ left: NaN }), TypeError);
});

test('invalid recordings are rejected instead of silently clamping motor commands', () => {
  const dance = structuredClone(simulation.dances[0]);
  dance.samples[2][1][3] = 46;
  assert.throws(() => validateRecording(axes, dance));
});
