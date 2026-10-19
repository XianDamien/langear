import { createServer } from 'node:http'
import { type AddressInfo } from 'node:net'
import { afterEach, expect, it } from 'vitest'
import { server } from '../src/server.js'
import { createRunner } from '../src/planner.js'

const servers: ReturnType<typeof createServer>[] = []
afterEach(async () => { await Promise.all(servers.map(s => new Promise<void>(r => { s.closeAllConnections(); s.close(() => r()) }))); servers.length = 0 })
async function listen(s: ReturnType<typeof createServer>) {
  servers.push(s); await new Promise<void>(r => s.listen(0, '127.0.0.1', r))
  return `http://127.0.0.1:${(s.address() as AddressInfo).port}`
}
it('requires the internal token and preserves per-request context', async () => {
  const token = 'private-service-token-with-32-characters'
  const base = await listen(server(async (_kind, context) => context, token))
  expect((await fetch(base + '/scenario', { method: 'POST', body: '{}' })).status).toBe(401)
  const results = await Promise.all(['first', 'second'].map(async owner => {
    const response = await fetch(base + '/scenario', { method: 'POST', headers: { Authorization: `Bearer ${token}` }, body: JSON.stringify({ owner }) })
    expect(response.status).toBe(200); return response.json()
  }))
  expect(results).toEqual([{ owner: 'first' }, { owner: 'second' }])
})
it('runs the real pi tool loop against a model transport and submits schema-validated results', async () => {
  const model = await listen(createServer(async (request, response) => {
    const chunks: Buffer[] = []; for await (const chunk of request) chunks.push(chunk)
    const payload = JSON.parse(Buffer.concat(chunks).toString())
    expect(payload.enable_thinking).toBe(false)
    expect(payload.messages[0].role).toBe('system')
    const context = payload.messages.find((m: { role: string; name?: string }) => m.role === 'tool')
    const args = context ? {
      title: JSON.parse(context.content).title, setup_en: 'Buy some fruit.', setup_zh: '买水果', learner_role: 'Customer', agent_role: 'Shopkeeper',
      goals: [{ id: 'buy', description_en: 'Buy fruit.', description_zh: '买水果' }],
      target_expressions: ['an apple', 'please'].map(english => ({ english, meaning_zh: '表达', source: { attempt_id: 'attempt', card_id: 'card' } })),
    } : {}
    const name = context ? 'submit_result' : 'get_practice_context'
    response.writeHead(200, { 'Content-Type': 'text/event-stream' })
    response.write('data: ' + JSON.stringify({ id: 'test', object: 'chat.completion.chunk', choices: [{ index: 0, delta: { role: 'assistant', tool_calls: [{ index: 0, id: 'call-' + name, type: 'function', function: { name, arguments: JSON.stringify(args) } }] }, finish_reason: null }] }) + '\n\n')
    response.write('data: ' + JSON.stringify({ id: 'test', object: 'chat.completion.chunk', choices: [{ index: 0, delta: {}, finish_reason: 'tool_calls' }] }) + '\n\n')
    response.end('data: [DONE]\n\n')
  }))
  process.env.AGENT_BASE_URL = model; process.env.AGENT_API_KEY = 'test-key'
  const run = createRunner()
  const results = await Promise.all(['Learner A', 'Learner B'].map(title => run('scenario', { title })))
  expect(results.map(result => (result as { title: string }).title)).toEqual(['Learner A', 'Learner B'])
})
