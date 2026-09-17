// Use Agnes AI (https://apihub.agnes-ai.com/v1) to generate branded FinHub
// background art for the showcase title/end cards. The AI image is used only
// as a 16:9-cropped background — crisp brand text is overlaid later with PIL
// (AI models render CJK text unreliably). API key comes from $AGNES_KEY.
import fs from 'node:fs';
import path from 'node:path';

const BASE = 'https://apihub.agnes-ai.com/v1';
const KEY = process.env.AGNES_KEY;
const OUT = process.env.OUT || '/workspace/FinHub/screenshots/video';
if (!KEY) { console.error('AGNES_KEY not set'); process.exit(1); }

const JOBS = [
  {
    name: 'title-bg',
    prompt: 'Ultra-detailed cinematic dark financial command center, deep charcoal and near-black background, ' +
            'glowing amber and gold data streams, holographic candlestick charts and flowing network lines, ' +
            'subtle bokeh, premium fintech aesthetic, no text, no logos, 16:9 composition, photorealistic 3D render',
  },
  {
    name: 'end-bg',
    prompt: 'Abstract dark finance background, amber and gold particles forming a shield and an upward arrow, ' +
            'deep black radial gradient, minimal, premium, cinematic, no text, no logo, 16:9 composition',
  },
];

async function genImage(prompt, name) {
  const r = await fetch(`${BASE}/images/generations`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${KEY}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ model: 'agnes-image-2.1-flash', prompt, n: 1, size: '1024x1024' }),
  });
  const j = await r.json();
  console.log(`[${name}] http=${r.status}`);
  if (!r.ok) { console.error(JSON.stringify(j).slice(0, 400)); throw new Error(`gen failed ${name}`); }
  const url = j.data?.[0]?.url || j.data?.url || j.url;
  if (!url) { console.error('no url in', JSON.stringify(j).slice(0, 400)); throw new Error('no url'); }
  const buf = Buffer.from(await (await fetch(url)).arrayBuffer());
  const file = path.join(OUT, `agnes-${name}.png`);
  fs.writeFileSync(file, buf);
  console.log(`[${name}] saved ${file} (${buf.length} bytes) url=${url.slice(0, 80)}`);
  return file;
}

for (const job of JOBS) {
  try { await genImage(job.prompt, job.name); }
  catch (e) { console.error(`[${job.name}] ERROR ${e.message}`); process.exitCode = 1; }
}
