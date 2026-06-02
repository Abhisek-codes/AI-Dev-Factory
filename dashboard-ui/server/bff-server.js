import path from 'node:path'
import { fileURLToPath } from 'node:url'
import compression from 'compression'
import express from 'express'
import { createProxyMiddleware } from 'http-proxy-middleware'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const rootDir = path.resolve(__dirname, '..')
const distDir = path.resolve(rootDir, 'dist')

const app = express()
const port = Number(process.env.PORT || 8080)
const backendUrl = process.env.BACKEND_URL

if (!backendUrl) {
  // eslint-disable-next-line no-console
  console.error('[BFF] Missing required environment variable BACKEND_URL')
  process.exit(1)
}

app.get('/bff-health', (_req, res) => {
  res.json({
    status: 'ok',
    service: 'dashboard-ui-bff',
    backendUrl,
    timestamp: new Date().toISOString()
  })
})

const apiProxy = createProxyMiddleware({
  target: backendUrl,
  changeOrigin: true,
  xfwd: true,
  ws: true,
  pathRewrite: (path) => `/api${path}`,
  onProxyRes: (proxyRes, req) => {
    if (req.url?.startsWith('/pipeline/events/')) {
      proxyRes.headers['cache-control'] = 'no-cache, no-store, must-revalidate'
      proxyRes.headers['x-accel-buffering'] = 'no'
      proxyRes.headers.connection = 'keep-alive'
    }
  },
  proxyTimeout: 120000,
  timeout: 120000,
  logLevel: 'warn'
})

app.use('/api', apiProxy)

// Apply compression only to static assets/pages. Avoid compressing /api streams.
app.use(compression())

app.use(express.static(distDir, { index: false }))

app.get('*', (_req, res) => {
  res.sendFile(path.join(distDir, 'index.html'))
})

app.listen(port, () => {
  // eslint-disable-next-line no-console
  console.log(`[BFF] listening on port ${port}`)
  // eslint-disable-next-line no-console
  console.log(`[BFF] proxying /api to ${backendUrl}`)
})
