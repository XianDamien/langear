import { createServer, type IncomingMessage } from 'node:http'
import { timingSafeEqual } from 'node:crypto'
import { pathToFileURL } from 'node:url'
import { createRunner, type AgentRun } from './planner.js'

async function body(request: IncomingMessage): Promise<unknown> {
  const chunks: Buffer[] = []
  let size = 0
  for await (const chunk of request) {
    size += chunk.length
    if (size > 512 * 1024) throw new Error('Request too large')
    chunks.push(chunk)
  }
  return JSON.parse(Buffer.concat(chunks).toString('utf8'))
}
export function server(run: AgentRun, token: string) {
  if (token.length < 32) throw new Error('AGENT_SERVICE_TOKEN must contain at least 32 characters')
  return createServer(async (request, response) => {
    response.setHeader('Content-Type', 'application/json')
    const provided = Buffer.from(request.headers.authorization || '')
    const expected = Buffer.from(`Bearer ${token}`)
    if (provided.length !== expected.length || !timingSafeEqual(provided, expected)) {
      response.writeHead(401).end('{"error":"Unauthorized"}'); return
    }
    const kind = request.url === '/scenario' ? 'scenario' : request.url === '/review' ? 'review' : request.url === '/translation' ? 'translation' : undefined
    if (request.method !== 'POST' || !kind) { response.writeHead(404).end('{}'); return }
    const abort = new AbortController()
    const timer = setTimeout(() => abort.abort(), 30000)
    response.on('close', () => { if (!response.writableEnded) abort.abort() })
    try {
      const context = await body(request)
      response.end(JSON.stringify(await run(kind, context, abort.signal)))
    } catch {
      // Provider errors may contain credentials, signed URLs or private prompt content.
      if (!response.headersSent) response.writeHead(502)
      response.end('{"error":"Agent request failed"}')
    } finally { clearTimeout(timer) }
  })
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  server(createRunner(), process.env.AGENT_SERVICE_TOKEN || '').listen(Number(process.env.PORT || 8111), process.env.HOST || '127.0.0.1')
}
