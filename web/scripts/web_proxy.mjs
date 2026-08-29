#!/usr/bin/env node
/**
 * web_proxy.mjs — FinHub single-origin web server.
 *
 * Serves the built frontend (web/dist) and reverse-proxies the API + live
 * WebSocket stream to the backend, so the whole app is reachable from ONE
 * origin/port (ideal behind a sandbox preview URL). No extra deps: static
 * serving and the HTTP/SSE proxy use Node built-ins; the WebSocket hop uses
 * the `ws` package already present in web/node_modules.
 *
 *   node deploy/web_proxy.mjs [--port 5173] [--dist ../web/dist] [--backend http://localhost:8000]
 */
import http from 'node:http'
import path from 'node:path'
import fs from 'node:fs'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'

// `ws` lives in the pnpm store (not hoisted to node_modules/ws) — resolve it
// from any of the known store layouts before falling back to plain `require`.
const require = createRequire(import.meta.url)
function resolveWs() {
  try {
    return require('ws')
  } catch {
    // Fall through to the pnpm store layouts below.
  }
  const here = path.dirname(fileURLToPath(import.meta.url))
  for (const rel of [
    '../node_modules/.pnpm/ws@8.19.0/node_modules/ws',
    '../node_modules/ws',
    '../../../node_modules/.pnpm/ws@8.19.0/node_modules/ws',
  ]) {
    const p = path.resolve(here, rel)
    if (fs.existsSync(path.join(p, 'package.json'))) {
      return require(p)
    }
  }
  throw new Error('Cannot resolve "ws" package for the WebSocket proxy')
}
const { WebSocketServer, WebSocket } = resolveWs()

const __dirname = path.dirname(fileURLToPath(import.meta.url))

function arg(name, fallback) {
  const i = process.argv.indexOf(name)
  return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : fallback
}

const PORT = Number(arg('--port', process.env.WEB_PORT || 5173))
const DIST = path.resolve(__dirname, arg('--dist', '../web/dist'))
const BACKEND = arg('--backend', process.env.WEB_PROXY_BACKEND || 'http://localhost:8000')

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif': 'image/gif',
  '.webp': 'image/webp',
  '.ico': 'image/x-icon',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.ttf': 'font/ttf',
  '.otf': 'font/otf',
  '.map': 'application/json',
  '.txt': 'text/plain; charset=utf-8',
}

// ---- Static file serving ------------------------------------------------
function serveStatic(req, res) {
  const urlPath = decodeURIComponent(new URL(req.url, 'http://x').pathname)
  let filePath = path.normalize(path.join(DIST, urlPath))
  if (!filePath.startsWith(DIST)) {
    res.writeHead(403).end('Forbidden')
    return true
  }
  if (urlPath.endsWith('/')) filePath = path.join(filePath, 'index.html')
  if (!path.extname(filePath)) filePath = path.join(filePath, 'index.html')

  fs.stat(filePath, (err, stat) => {
    if (!err && stat.isFile()) {
      const type = MIME[path.extname(filePath).toLowerCase()] || 'application/octet-stream'
      res.writeHead(200, {
        'Content-Type': type,
        'Cache-Control': filePath.includes('/assets/') ? 'public, max-age=31536000, immutable' : 'no-cache',
      })
      fs.createReadStream(filePath).pipe(res)
      return
    }
    // SPA fallback: any unknown path serves the app shell.
    fs.readFile(path.join(DIST, 'index.html'), (e2, html) => {
      if (e2) {
        res.writeHead(404, { 'Content-Type': 'text/plain' }).end('Not found')
        return
      }
      res.writeHead(200, { 'Content-Type': MIME['.html'], 'Cache-Control': 'no-cache' })
      res.end(html)
    })
  })
  return true
}

// ---- HTTP / SSE reverse proxy -------------------------------------------
import https from 'node:https'

function proxyHttp(req, res, targetPath) {
  const backend = new URL(BACKEND)
  const headers = { ...req.headers }
  delete headers.host
  delete headers.connection
  const options = {
    method: req.method,
    headers,
    hostname: backend.hostname,
    port: backend.port || 80,
    path: targetPath,
  }
  const mod = backend.protocol === 'https:' ? https : http
  const upstream = mod.request(options, (upRes) => {
    res.writeHead(upRes.statusCode, upRes.headers)
    upRes.pipe(res)
  })
  upstream.on('error', () => {
    if (!res.headersSent) res.writeHead(502).end('Bad Gateway')
    else res.destroy()
  })
  req.pipe(upstream)
}

// ---- Main HTTP server ----------------------------------------------------
const server = http.createServer((req, res) => {
  const url = new URL(req.url, 'http://x')
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/ws/v1')) {
    proxyHttp(req, res, url.pathname + url.search)
    return
  }
  serveStatic(req, res)
})

// ---- WebSocket reverse proxy ---------------------------------------------
const wss = new WebSocketServer({ server })

wss.on('connection', (client, req) => {
  const url = new URL(req.url, 'http://x')
  if (!url.pathname.startsWith('/ws/v1')) {
    client.close(1008, 'forbidden')
    return
  }
  const backendUrl = BACKEND.replace(/^http/, 'ws') + url.pathname + url.search
  const upstream = new WebSocket(backendUrl, { headers: { ...req.headers } })

  upstream.on('open', () => {
    // No handshake work needed; messages flow once the tunnel is live.
  })
  upstream.on('message', (data, isBinary) => {
    if (client.readyState === WebSocket.OPEN) client.send(data, { binary: isBinary })
  })
  upstream.on('close', () => client.close())
  upstream.on('error', () => client.close())

  client.on('message', (data, isBinary) => {
    if (upstream.readyState === WebSocket.OPEN) upstream.send(data, { binary: isBinary })
  })
  client.on('close', () => upstream.close())
  client.on('error', () => upstream.close())
})

server.listen(PORT, '0.0.0.0', () => {
  console.log(`[web_proxy] serving ${DIST}`)
  console.log(`[web_proxy] proxying /api/v1, /ws/v1 -> ${BACKEND}`)
  console.log(`[web_proxy] listening on http://0.0.0.0:${PORT}`)
})
