const METADATA = {
  head: { label: '고개', group: 'head', homeLabel: '정면' },
  crown: { label: '정수리 카메라', group: 'head', homeLabel: '정면' },
  right_shoulder_x: { label: '오른팔 X', group: 'right', homeLabel: '팔 내림' },
  right_shoulder_y: { label: '오른팔 Y', group: 'right', homeLabel: '팔 내림' },
  left_shoulder_x: { label: '왼팔 X', group: 'left', homeLabel: '팔 내림' },
  left_shoulder_y: { label: '왼팔 Y', group: 'left', homeLabel: '팔 내림' },
};

export function createAxes(profile) {
  return Object.entries(METADATA).map(([id, metadata]) => {
    const source = profile.axes[id];
    if (!source || ![source.minimum, source.maximum, source.neutral].every(Number.isFinite)) {
      throw new Error(`Invalid robot profile: ${id}`);
    }
    const zero = source.joint?.servo_zero ?? source.neutral;
    const direction = source.joint?.direction ?? 1;
    if (![1, -1].includes(direction) || zero < source.minimum || zero > source.maximum) {
      throw new Error(`Invalid joint calibration: ${id}`);
    }
    const endpoints = [(source.minimum - zero) / direction, (source.maximum - zero) / direction].map(value => value === 0 ? 0 : value);
    return Object.freeze({
      id, ...metadata,
      channel: source.channel,
      min: source.minimum,
      max: source.maximum,
      neutral: source.neutral,
      zero, direction,
      relativeMin: Math.min(...endpoints),
      relativeMax: Math.max(...endpoints),
    });
  });
}

export function clampServo(axis, value) {
  if (!Number.isFinite(value)) throw new TypeError('Angle must be finite.');
  return Math.min(axis.max, Math.max(axis.min, Math.round(value)));
}

export function toRelative(axis, servo) {
  const value = (servo - axis.zero) / axis.direction;
  return value === 0 ? 0 : value;
}

export function toServo(axis, relative) {
  if (!Number.isFinite(relative)) throw new TypeError('Angle must be finite.');
  return clampServo(axis, axis.zero + axis.direction * relative);
}

export function homePose(axes) {
  return Object.fromEntries(axes.map(axis => [axis.id, axis.neutral]));
}

export function normalizePose(axes, patch, previous = homePose(axes)) {
  const result = { ...previous };
  for (const [id, value] of Object.entries(patch)) {
    const axis = axes.find(item => item.id === id);
    if (!axis) throw new TypeError(`Unknown axis: ${id}`);
    result[id] = clampServo(axis, value);
  }
  return result;
}

export function jointRotations(axes, pose) {
  const relative = Object.fromEntries(axes.map(axis => [axis.id, toRelative(axis, pose[axis.id])]));
  const radians = value => value * Math.PI / 180;
  // Front is +Z; the robot's right is -X. Positive arm X moves forward.
  return {
    headY: -radians(relative.head),
    crownY: -radians(relative.crown),
    rightX: -radians(relative.right_shoulder_x),
    rightZ: -radians(relative.right_shoulder_y),
    leftX: -radians(relative.left_shoulder_x),
    leftZ: radians(relative.left_shoulder_y),
  };
}

export const ELBOW_LIMITS = Object.freeze({ min: 120, max: 180, preset: 150 });

export function normalizeElbows(patch, previous = { right: ELBOW_LIMITS.preset, left: ELBOW_LIMITS.preset }) {
  const result = { ...previous };
  for (const [side, value] of Object.entries(patch)) {
    if (!['right', 'left'].includes(side) || !Number.isFinite(value)) throw new TypeError('Invalid passive elbow angle.');
    result[side] = Math.max(ELBOW_LIMITS.min, Math.min(ELBOW_LIMITS.max, Math.round(value)));
  }
  return result;
}

export function elbowRotation(angle) {
  return -(180 - angle) * Math.PI / 180;
}

export function validateRecording(axes, recording) {
  if (recording.terminal_state !== 'completed' || !Array.isArray(recording.samples) || recording.samples.length < 2) throw new Error('Incomplete recording.');
  let previousTime = -1;
  for (const sample of recording.samples) {
    if (!Array.isArray(sample) || !Number.isInteger(sample[0]) || sample[0] <= previousTime) throw new Error('Invalid recording clock.');
    previousTime = sample[0];
    if (!Array.isArray(sample[1]) || sample[1].length !== 6) throw new Error('Recording must contain six motor channels only.');
    for (const axis of axes) {
      const value = sample[1][axis.channel];
      if (!Number.isInteger(value) || value < axis.min || value > axis.max) throw new Error('Recorded command is outside the robot profile.');
    }
    if (!Number.isInteger(sample[2]) || sample[2] < 0 || sample[2] >= recording.eye_atlas.count) throw new Error('Missing eye frame.');
    if (!Number.isInteger(sample[3]) || !recording.stages[sample[3]]) throw new Error('Missing recording stage.');
  }
  if (recording.samples[0][0] !== 0 || previousTime !== recording.duration_ms) throw new Error('Recording duration mismatch.');
  return recording;
}

export function sampleRecording(axes, recording, timeMs) {
  if (!Number.isFinite(timeMs)) throw new TypeError('Playback time must be finite.');
  const time = Math.max(0, Math.min(recording.duration_ms, timeMs));
  let low = 0, high = recording.samples.length - 1;
  while (low < high) {
    const mid = Math.ceil((low + high) / 2);
    if (recording.samples[mid][0] <= time) low = mid;
    else high = mid - 1;
  }
  const sample = recording.samples[low];
  return {
    timeMs: time, sampledMs: sample[0],
    pose: Object.fromEntries(axes.map(axis => [axis.id, sample[1][axis.channel]])),
    eyeFrame: sample[2], eyePose: [...sample[4]], stage: recording.stages[sample[3]],
  };
}
