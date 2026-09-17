// Generate a 5s cinematic FinHub intro bumper via Agnes Video 2.5
// (async task: POST /v1/videos → poll /agnesapi?video_id= → download mp4).
import fs from 'node:fs';
import path from 'node:path';

const BASE = 'https://apihub.agnes-ai.com';
const KEY = process.env.AGNES_KEY;
const OUT = process.env.OUT || '/workspace/FinHub/screenshots/video';
if (!KEY) { console.error('AGNES_KEY not set'); process.exit(1); }

const PROMPT = 'Cinematic slow camera push through a dark financial command center, ' +
  'glowing amber and golden candlestick chart holograms rising and flowing, ' +
  'golden data streams and fine particles drifting through the air, ' +
  'premium fintech atmosphere, elegant smooth motion, no text, no logos';

const r = await fetch(`${BASE}/v1/videos`, {
  method: 'POST',
  headers: { Authorization: `Bearer ${KEY}`, 'Content-Type': 'application/json' },
  body: JSON.stringify({
    model: 'agnes-video-2.5',
    mode: 'text',
    prompt: PROMPT,
    seconds: '5',
    size: '1080P',
    aspect_ratio: '16:9',
  }),
});
const created = await r.json();
console.log('create http=', r.status, JSON.stringify(created).slice(0, 300));
if (!r.ok) process.exit(1);
const videoId = created.video_id || created.id;
if (!videoId) { console.error('no video_id'); process.exit(1); }

// Poll — video RPM on the free tier is 1/min, so poll at a civilized pace.
const deadline = Date.now() + 10 * 60 * 1000;
let last = '';
while (Date.now() < deadline) {
  await new Promise((res) => setTimeout(res, 15000));
  const q = await fetch(`${BASE}/agnesapi?video_id=${encodeURIComponent(videoId)}&model_name=agnes-video-2.5`,
    { headers: { Authorization: `Bearer ${KEY}` } });
  const j = await q.json().catch(() => ({}));
  const line = `status=${j.status} progress=${j.progress}`;
  if (line !== last) { console.log(new Date().toISOString().slice(11, 19), line); last = line; }
  if (j.status === 'completed') {
    const url = j.metadata?.url;
    if (!url) { console.error('completed but no url', JSON.stringify(j).slice(0, 300)); process.exit(1); }
    const buf = Buffer.from(await (await fetch(url)).arrayBuffer());
    const file = path.join(OUT, 'agnes-intro-bumper.mp4');
    fs.writeFileSync(file, buf);
    console.log('saved', file, `${(buf.length / 1048576).toFixed(1)}MB`);
    process.exit(0);
  }
  if (j.status === 'failed') {
    console.error('FAILED', JSON.stringify(j.error || j).slice(0, 400));
    process.exit(1);
  }
}
console.error('poll timeout after 10min');
process.exit(1);
