import { build } from 'esbuild';
import { readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';

const profileUrl = new URL('../../raspberry_pi/robot_demo/robot_motion_profile.json', import.meta.url);
const profile = JSON.parse(await readFile(profileUrl, 'utf8'));
const python = process.env.CUVO_PYTHON || 'python3';
execFileSync(python, [fileURLToPath(new URL('../../scripts/generate_groove_audio.py', import.meta.url))]);
const simulation = JSON.parse(execFileSync(python, [fileURLToPath(new URL('../../raspberry_pi/robot_demo/export_simulation.py', import.meta.url))], { encoding: 'utf8', maxBuffer: 32 * 1024 * 1024 }));
await writeFile(new URL('simulation-data.json', import.meta.url), JSON.stringify(simulation));

await build({
  entryPoints: [fileURLToPath(new URL('app.js', import.meta.url))],
  outfile: fileURLToPath(new URL('browser.bundle.js', import.meta.url)),
  bundle: true,
  format: 'iife',
  platform: 'browser',
  target: ['safari16', 'chrome110'],
  minify: true,
  legalComments: 'eof',
  define: {
    __CUVO_PROFILE__: JSON.stringify(profile),
    __CUVO_SIMULATION__: JSON.stringify(simulation),
  },
});
const licenses = [];
for (const dependency of ['three', 'lucide']) {
  licenses.push(`${dependency}\n\n${await readFile(new URL(`node_modules/${dependency}/LICENSE`, import.meta.url), 'utf8')}`);
}
await writeFile(new URL('THIRD_PARTY_LICENSES.txt', import.meta.url), licenses.join('\n\n'));
console.log(JSON.stringify({ mode: simulation.mode, source: simulation.source_hash.slice(0, 12), dances: simulation.dances.map(dance => ({ title: dance.title, duration_ms: dance.duration_ms })) }));
