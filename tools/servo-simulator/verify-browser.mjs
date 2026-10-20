import { chromium } from 'playwright';
import { mkdir, writeFile, readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';

const output = new URL('test-output/', import.meta.url);
await mkdir(output, { recursive: true });
const browser = await chromium.launch({
  channel: 'chrome', headless: true,
  args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'],
});
const results = [];
const errors = [];
const remoteRequests = [];
const simulation = JSON.parse(await readFile(new URL('simulation-data.json', import.meta.url)));
const groove = simulation.dances[0];

async function seek(page, value) {
  await page.locator('#timeline').evaluate((element, next) => {
    element.value = String(next);
    element.dispatchEvent(new Event('input', { bubbles: true }));
  }, value);
  await page.waitForTimeout(100);
}

async function eyePixels(page) {
  return page.locator('#eye-viewer-left').evaluate(canvas => {
    const data = canvas.getContext('2d').getImageData(0, 0, 128, 128).data;
    let white = 0, checksum = 0;
    for (let index = 0; index < data.length; index += 4) {
      if (data[index] > 200) white += 1;
      checksum = (checksum + data[index] * (index + 1)) % 2147483647;
    }
    return { white, checksum };
  });
}

async function setRange(page, id, value) {
  await page.locator(`#range-${id}`).evaluate((element, next) => {
    element.value = String(next);
    element.dispatchEvent(new Event('input', { bubbles: true }));
  }, value);
  await page.waitForTimeout(100);
}

async function canvasPixels(page) {
  return page.locator('#viewport canvas').evaluate(canvas => {
    const copy = document.createElement('canvas');
    copy.width = canvas.width;
    copy.height = canvas.height;
    const context = copy.getContext('2d');
    context.drawImage(canvas, 0, 0);
    const bytes = context.getImageData(0, 0, copy.width, copy.height).data;
    let dark = 0;
    let chromatic = 0;
    let checksum = 0;
    for (let index = 0; index < bytes.length; index += 16) {
      const r = bytes[index], g = bytes[index + 1], b = bytes[index + 2];
      if (r + g + b < 390) dark += 1;
      if (Math.max(r, g, b) - Math.min(r, g, b) > 35) chromatic += 1;
      checksum = (checksum + r * 3 + g * 5 + b * 7) % 2147483647;
    }
    return { dark, chromatic, checksum, width: canvas.width, height: canvas.height };
  });
}

async function checkLayout(page) {
  return page.evaluate(() => {
    const bad = [...document.querySelectorAll('button, input, h1, .joint-heading, .joint-reference')].flatMap(element => {
      const r = element.getBoundingClientRect();
      return r.left < -1 || r.right > innerWidth + 1 || r.width <= 0 ? [element.outerHTML.slice(0, 150)] : [];
    });
    return { overflow: document.documentElement.scrollWidth > innerWidth + 1, bad };
  });
}

try {
  for (const [name, width, height] of [['desktop', 1440, 1000], ['tablet', 820, 1180], ['mobile', 390, 844], ['narrow', 320, 740]]) {
    const context = await browser.newContext({ viewport: { width, height }, isMobile: width < 500, hasTouch: width < 500 });
    await context.route('**/*', route => {
      if (/^https?:/.test(route.request().url())) {
        remoteRequests.push(route.request().url());
        return route.abort();
      }
      return route.continue();
    });
    const page = await context.newPage();
    page.on('pageerror', error => errors.push(`${name}: ${error.message}`));
    page.on('console', message => { if (message.type() === 'error') errors.push(`${name}: ${message.text()}`); });
    await page.goto(new URL('index.html', import.meta.url).href);
    await page.waitForFunction(() => window.cuvoSimulator?.getState().frames > 2 && window.cuvoSimulator.getState().ready, undefined, { timeout: 20000 });
    assert.equal(await page.evaluate(() => window.cuvoSimulator.getState().sourceHash), simulation.source_hash);
    await page.getByRole('button', { name: '기본 자세', exact: true }).click();
    await page.waitForTimeout(200);
    const pixels = await canvasPixels(page);
    assert.ok(pixels.dark > 150, `${name}: blank robot canvas`);
    assert.ok(pixels.chromatic > 100, `${name}: missing colored geometry`);
    const bounds = await page.evaluate(() => window.cuvoSimulator.getSceneSnapshot().projectedBounds);
    assert.ok(bounds.minX > -0.95 && bounds.maxX < 0.95 && bounds.minY > -0.95 && bounds.maxY < 0.95, `${name}: robot is cropped ${JSON.stringify(bounds)}`);
    const layout = await checkLayout(page);
    assert.equal(layout.overflow, false, `${name}: horizontal overflow`);
    assert.deepEqual(layout.bad, [], `${name}: clipped controls`);
    await page.screenshot({ path: fileURLToPath(new URL(`${name}.png`, output)), fullPage: true });
    const homeSnapshot = await page.evaluate(() => window.cuvoSimulator.getSceneSnapshot());
    await page.locator('#elbow-right').evaluate(element => { element.value = '120'; element.dispatchEvent(new Event('input', { bubbles: true })); });
    const bent = await page.evaluate(() => window.cuvoSimulator.getSceneSnapshot());
    assert.ok(Math.abs(bent.elbows.right.rotation + Math.PI / 3) < 1e-6);
    assert.ok(bent.hands.right[2] > homeSnapshot.hands.right[2]);
    await page.locator('#elbow-right').evaluate(element => { element.value = '150'; element.dispatchEvent(new Event('input', { bubbles: true })); });
    await setRange(page, 'head', -45);
    const lookingLeft = await page.evaluate(() => window.cuvoSimulator.getSceneSnapshot());
    assert.ok(lookingLeft.faceDirection[0] > 0.6, `${name}: head 45 is not robot-left`);
    const changedPixels = await canvasPixels(page);
    assert.notEqual(pixels.checksum, changedPixels.checksum, `${name}: canvas did not change with joint angle`);
    await setRange(page, 'right_shoulder_x', 60);
    await setRange(page, 'left_shoulder_x', 60);
    await setRange(page, 'right_shoulder_y', 30);
    await setRange(page, 'left_shoulder_y', 30);
    const posed = await page.evaluate(() => ({ state: window.cuvoSimulator.getState(), scene: window.cuvoSimulator.getSceneSnapshot() }));
    assert.equal(posed.state.pose.left_shoulder_x, 75);
    assert.equal(posed.state.pose.left_shoulder_y, 150);
    assert.ok(posed.scene.hands.right[2] > homeSnapshot.hands.right[2] + 0.5);
    assert.ok(posed.scene.hands.left[2] > homeSnapshot.hands.left[2] + 0.5);
    assert.ok(posed.scene.hands.right[0] < homeSnapshot.hands.right[0]);
    assert.ok(posed.scene.hands.left[0] > homeSnapshot.hands.left[0]);
    await page.getByRole('button', { name: '서보 명령값', exact: true }).click();
    assert.equal(await page.locator('#number-left_shoulder_x').inputValue(), '75');
    await page.locator('#number-head').fill('999');
    await page.locator('#number-head').press('Tab');
    assert.equal(await page.locator('#number-head').inputValue(), '135');
    await page.evaluate(() => window.cuvoSimulator.setPose({ head: 60, crown: 60 }));
    const crown = await page.evaluate(() => window.cuvoSimulator.getSceneSnapshot());
    assert.ok(crown.crownDirection[0] > crown.faceDirection[0], `${name}: crown does not inherit head yaw`);
    await page.getByRole('button', { name: '정면', exact: true }).click();
    await page.waitForTimeout(100);
    await page.screenshot({ path: fileURLToPath(new URL(`${name}-pose.png`, output)), fullPage: true });
    await page.getByRole('button', { name: '기본 자세', exact: true }).click();
    await page.getByRole('button', { name: '상대각도', exact: true }).click();
    const openEyes = await eyePixels(page);
    assert.ok(openEyes.white > 200, `${name}: eye atlas is blank`);
    const closedFrame = groove.samples.find(sample => sample[4][0] < 0.05);
    await seek(page, closedFrame[0]);
    assert.ok((await eyePixels(page)).white < openEyes.white, `${name}: recorded blink did not render`);
    const diagonal = groove.stages.find(stage => stage.name === 'groove_13').start_ms + 600;
    await seek(page, diagonal);
    const atDiagonal = await page.evaluate(() => window.cuvoSimulator.getState());
    assert.ok(atDiagonal.pose.crown < 90, `${name}: independent crown movement missing`);
    assert.notEqual((await eyePixels(page)).checksum, openEyes.checksum, `${name}: eye gaze did not change`);
    await page.screenshot({ path: fileURLToPath(new URL(`${name}-groove.png`, output)), fullPage: true });
    await page.getByRole('button', { name: '재생 정지', exact: true }).click();
    await page.getByRole('button', { name: '춤 재생', exact: true }).click();
    await page.waitForTimeout(1900);
    assert.equal(await page.evaluate(() => window.cuvoSimulator.getState().playing), true);
    const moving = await page.evaluate(() => window.cuvoSimulator.getState().relative.right_shoulder_y);
    assert.ok(moving > 0, `${name}: dance did not animate`);
    await page.getByRole('button', { name: '일시정지', exact: true }).click();
    const paused = await page.evaluate(() => window.cuvoSimulator.getState());
    await page.waitForTimeout(150);
    assert.equal(await page.evaluate(() => window.cuvoSimulator.getState().timeMs), paused.timeMs);
    await page.locator('#playback-speed').selectOption('0.5');
    await page.getByRole('button', { name: '춤 재개', exact: true }).click();
    await page.waitForTimeout(400);
    const slower = await page.evaluate(() => window.cuvoSimulator.getState());
    assert.ok(slower.timeMs - paused.timeMs > 100 && slower.timeMs - paused.timeMs < 350);
    assert.deepEqual(slower.elbows, { right: 150, left: 150 }, `${name}: choreography changed a passive elbow`);
    await page.getByRole('button', { name: '일시정지', exact: true }).click();
    await page.locator('#playback-speed').selectOption('1');
    if (name === 'desktop') {
      await page.locator('#play-sound').check();
      await page.waitForFunction(() => window.cuvoSimulator.getState().audioReady, undefined, { timeout: 5000 });
      await page.getByRole('button', { name: '처음부터 재생', exact: true }).click();
      await page.waitForTimeout(4500);
      await page.screenshot({ path: fileURLToPath(new URL('desktop-playing.png', output)), fullPage: true });
      await page.waitForFunction(() => !window.cuvoSimulator.getState().playing, undefined, { timeout: 15000 });
      const final = await page.evaluate(() => window.cuvoSimulator.getState());
      assert.equal(final.pose.head, 90);
      assert.equal(final.pose.left_shoulder_y, 180);
      assert.equal(final.timeMs, groove.duration_ms);
      await page.locator('#play-sound').uncheck();
    }
    await page.locator('#dance-select').selectOption('legacy_dance');
    const legacy = simulation.dances[1];
    const firstSwing = legacy.stages.find(stage => stage.name === 'dance_1_left');
    await seek(page, firstSwing.start_ms + 560);
    assert.equal(await page.evaluate(() => window.cuvoSimulator.getState().pose.right_shoulder_x), 125);
    assert.equal(await page.evaluate(() => window.cuvoSimulator.getState().pose.crown), 90);
    await page.locator('#dance-select').selectOption('cuvo_groove');
    const finalLayout = await checkLayout(page);
    assert.equal(finalLayout.overflow, false);
    assert.deepEqual(finalLayout.bad, []);
    results.push({ name, pixels, bounds, eyePixels: openEyes, interactionChecks: 24 });
    await context.close();
  }
  assert.deepEqual(errors, [], 'Browser errors');
  assert.deepEqual(remoteRequests, [], 'The simulator must work without internet requests');
  await writeFile(new URL('results.json', output), JSON.stringify({ results, errors, remoteRequests }, null, 2));
  console.log(JSON.stringify({ result: 'passed', viewports: results.length, checks: results.length * 24, errors, remoteRequests }, null, 2));
} finally {
  await browser.close();
}
