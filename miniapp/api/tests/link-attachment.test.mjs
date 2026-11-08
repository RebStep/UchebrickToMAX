import assert from 'node:assert/strict'
import test from 'node:test'
import { buildApp } from '../src/app.js'
import { signSession } from '../src/session.js'

function fixture(t) {
  const tasks = new Map([[1, 7], [2, 7], [3, 9]])
  const links = new Map([[10, 1], [20, 3]])
  let updates = 0, revoked = false
  const db = { query: async (sql, params) => {
    if (sql.startsWith('SELECT true AS revoked')) return { rows: revoked ? [{ revoked: true }] : [] }
    assert.match(sql, /UPDATE task_links l SET task_id = target.id/)
    assert.match(sql, /source.id = l.task_id AND source.user_id = \$2/)
    assert.match(sql, /target.id = \$1 AND target.user_id = \$2/)
    updates++
    const [target, user, link] = params
    if (tasks.get(links.get(link)) !== user || tasks.get(target) !== user) return { rows: [] }
    links.set(link, target)
    return { rows: [{ id: link }] }
  } }
  const app = buildApp({ db, botToken: 'offline-test', sessionSecret: 'offline-test-secret' })
  t.after(() => app.close())
  const headers = { authorization: `Bearer ${signSession(7, 'offline-test-secret')}` }
  return { app, links, updates: () => updates, revoke: () => { revoked = true }, request: (task, link) => app.inject({ method: 'PATCH', url: `/api/tasks/${task}/links/${link}/attach`, headers }) }
}

test('link attachment requires an authenticated, non-revoked session', async (t) => {
  const f = fixture(t)
  assert.equal((await f.app.inject({ method: 'PATCH', url: '/api/tasks/2/links/10/attach' })).statusCode, 401)
  f.revoke()
  assert.equal((await f.request(2, 10)).statusCode, 401)
  assert.equal(f.updates(), 0)
})

test('moving a link preserves its identity and repeat drops are idempotent', async (t) => {
  const f = fixture(t)
  assert.equal((await f.request(2, 10)).statusCode, 200)
  assert.equal(f.links.get(10), 2)
  assert.equal((await f.request(2, 10)).statusCode, 200)
  assert.equal((await f.request(1, 10)).statusCode, 200)
  assert.equal(f.links.get(10), 1)
  assert.equal(f.links.size, 2)
})

test('foreign source links and foreign target tasks are rejected', async (t) => {
  const f = fixture(t)
  for (const [target, link] of [[3, 10], [2, 20], [2, 99], [99, 10]]) assert.equal((await f.request(target, link)).statusCode, 404)
  assert.equal(f.links.get(10), 1)
  assert.equal(f.links.get(20), 3)
})

test('invalid identifiers are rejected before attempting a link update', async (t) => {
  const f = fixture(t)
  for (const [target, link] of [[0, 10], [-1, 10], ['bad', 10], ['9007199254740992', 10], [2, 0], [2, 'bad'], [2, '9007199254740992']]) assert.equal((await f.request(target, link)).statusCode, 400)
  assert.equal(f.updates(), 0)
})
