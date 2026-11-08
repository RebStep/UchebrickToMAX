import { createHash, randomBytes } from 'node:crypto';
import { createReadStream } from 'node:fs';
import { mkdir, unlink, writeFile } from 'node:fs/promises';
import path from 'node:path';
import Fastify, { LogController } from 'fastify';
import { validateInitData } from './validate.js';
import { sessionClaims, signSession } from './session.js';
import { buildCalendar } from './ics.js';
import { registerAlice } from './alice.js';
import { registerSettings } from './settings.js';
import { registerObjects } from './objects.js';
const KINDS = new Set(['homework', 'todo', 'event', 'project', 'olympiad']);
const COLUMNS = `t.id::int AS id, t.title, t.subject, t.kind, t.due_at, t.location, t.note, t.reg_deadline, t.duration_min, t.registered, t.status,
  t.pos_x AS x, t.pos_y AS y, t.created_at, u.tz, t.next_remind_at, u.work_schedule,
  COALESCE((SELECT json_agg(json_build_object('id', l.id::int, 'url', l.url, 'x', l.pos_x, 'y', l.pos_y) ORDER BY l.id)
            FROM task_links l WHERE l.task_id = t.id), '[]'::json) AS links,
  COALESCE((SELECT json_agg(json_build_object('id', a.id::int, 'kind', a.kind, 'name', a.name, 'size', a.size_bytes, 'x', a.pos_x, 'y', a.pos_y) ORDER BY a.id)
            FROM attachments a JOIN attachment_tasks at ON at.attachment_id = a.id WHERE at.task_id = t.id), '[]'::json) AS attachments`;
const MAX_UPLOAD = 20 * 1024 * 1024;
const MAX_VOICE = 10 * 1024 * 1024;
const STORED_NAME = /^[0-9a-f]{32}$/;
const IMAGE_EXT = /\.(jpe?g|png|gif|webp|heic|bmp)$/i;
function linkUrl(value) {
  if (typeof value !== 'string') {
    throw new Error('bad_url');
  }
  const v = value.trim();
  if (!v || v.length > 2000) {
    throw new Error('bad_url');
  }
  let u;
  try {
    u = new URL(/^[a-z][a-z0-9+.-]*:\/\//i.test(v) ? v : `https://${v}`);
  }
  catch {
    throw new Error('bad_url');
  }
  if (u.protocol !== 'http:' && u.protocol !== 'https:') {
    throw new Error('bad_url');
  }
  return u.toString();
}
function text(value, max) {
  if (value === null || value === undefined) {
    return null;
  }
  if (typeof value !== 'string') {
    throw new Error('bad_text');
  }
  const v = value.trim();
  if (v.length > max) {
    throw new Error('too_long');
  }
  return v || null;
}
function moment(value) {
  if (value === null || value === undefined || value === '') {
    return null;
  }
  if (typeof value !== 'string') {
    throw new Error('bad_date');
  }
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) {
    throw new Error('bad_date');
  }
  return d.toISOString();
}
function duration(v) {
  if (v == null) {
    return null;
  }
  if (!Number.isInteger(v) || v < 1 || v > 1440) {
    throw new Error('bad_duration');
  }
  return v;
}
const FIELDS = {
  title: (v) => {
    const s = text(v, 500);
    if (!s) {
      throw new Error('empty_title');
    }
    return s;
  },
  subject: (v) => text(v, 60),
  kind: (v) => {
    if (!KINDS.has(v)) {
      throw new Error('bad_kind');
    }
    return v;
  },
  due_at: moment,
  location: (v) => text(v, 300),
  note: (v) => text(v, 2000),
  reg_deadline: moment,
  duration_min: duration,
  registered: (v) => {
    if (typeof v !== 'boolean') {
      throw new Error('bad_registered');
    }
    return v;
  },
};
export function parseFields(body, required) {
  if (body !== undefined && (body === null || typeof body !== 'object' || Array.isArray(body))) {
    throw new Error('bad_body');
  }
  const unknown = Object.keys(body ?? {}).filter((k) => !Object.hasOwn(FIELDS, k));
  if (unknown.length) {
    throw new Error('bad_field');
  }
  const out = {};
  for (const [name, check] of Object.entries(FIELDS)) {
    if (body && Object.hasOwn(body, name)) {
      out[name] = check(body[name]);
    }
  }
  if (required && !out.title) {
    throw new Error('empty_title');
  }
  return out;
}
const OLY_COLUMNS = `id::int AS id, name, level, subject, location, note, registered, reg_opens, reg_deadline,
  links, reminders_muted, tours`;
export function parseOlympiad(body) {
  if (!body || typeof body !== 'object' || Array.isArray(body)) {
    throw new Error('bad_body');
  }
  const name = text(body.name, 300);
  if (!name) {
    throw new Error('empty_name');
  }
  const tours = body.tours ?? [];
  if (!Array.isArray(tours) || tours.length > 20) {
    throw new Error('bad_tours');
  }
  const links = body.links ?? [];
  if (!Array.isArray(links) || links.length > 20) {
    throw new Error('bad_links');
  }
  if (body.reminders_muted !== undefined && typeof body.reminders_muted !== 'boolean') {
    throw new Error('bad_reminders');
  }
  const regOpens = moment(body.reg_opens);
  const regDeadline = moment(body.reg_deadline);
  if (regOpens && regDeadline && regOpens > regDeadline) {
    throw new Error('bad_registration_dates');
  }
  return {
    name, level: text(body.level, 100), subject: text(body.subject, 60), location: text(body.location, 300),
    note: text(body.note, 2000), registered: body.registered === true,
    reg_opens: regOpens, reg_deadline: regDeadline, links: [...new Set(links.map(linkUrl))],
    reminders_muted: body.reminders_muted ?? null,
    tours: tours.map((t) => {
      if (!t || typeof t !== 'object' || Array.isArray(t)) {
        throw new Error('bad_tours');
      }
      const start = moment(t.starts_at);
      const end = moment(t.deadline);
      if (start && end && start > end) {
        throw new Error('bad_tour_dates');
      }
      const tour = { title: text(t.title, 200) ?? 'Тур', starts_at: start, deadline: end, done: t.done === true };
      if (Object.hasOwn(t, 'duration_min')) {
        tour.duration_min = duration(t.duration_min);
      }
      return tour;
    }),
  };
}
export function buildApp({ db, botToken, sessionSecret, logger = false, aliceSecret = '', filesDir = process.env.FILES_DIR || '/data/files' }) {
  const app = Fastify({
    logger, logController: new LogController({
      disableRequestLogging: (req) => /^\/(?:alice|ics)\//.test(req.url),
    })
  });
  app.addContentTypeParser('application/octet-stream', { parseAs: 'buffer', bodyLimit: MAX_UPLOAD }, (req, body, done) => done(null, body));
  app.addContentTypeParser('application/json', { parseAs: 'string' }, (req, body, done) => {
    if (body === '') {
      return done(null, undefined);
    }
    try {
      done(null, JSON.parse(body));
    }
    catch {
      done(new Error('bad_json'));
    }
  });
  app.setErrorHandler((err, req, reply) => {
    if (err.message && /^(bad_|empty_|too_)/.test(err.message)) {
      return reply.code(400).send({ error: err.message });
    }
    if (err.statusCode && err.statusCode < 500) {
      return reply.code(err.statusCode).send({ error: 'bad_request' });
    }
    req.log.error(err);
    return reply.code(500).send({ error: 'server_error' });
  });
  app.get('/api/health', async () => {
    await db.query('SELECT 1');
    return { ok: true };
  });
  registerAlice(app, db, aliceSecret);
  app.post('/api/auth', async (req, reply) => {
    const parsed = validateInitData(req.body?.initData, botToken);
    if (!parsed) {
      return reply.code(401).send({ error: 'bad_init_data' });
    }
    const { user } = parsed;
    await db.query(`INSERT INTO users (id, first_name) VALUES ($1, $2)
       ON CONFLICT (id) DO UPDATE SET first_name = EXCLUDED.first_name`, [user.id, user.first_name ?? null]);
    return { token: signSession(user.id, sessionSecret), user: { id: user.id, first_name: user.first_name ?? null } };
  });
  app.post('/api/auth/link', async (req, reply) => {
    const token = req.body?.token;
    if (typeof token !== 'string' || token.length < 16 || token.length > 200) {
      return reply.code(401).send({ error: 'bad_link' });
    }
    const hash = createHash('sha256').update(token).digest('hex');
    const { rows } = await db.query(`UPDATE login_tokens SET used_at = now()
       WHERE token_hash = $1 AND used_at IS NULL AND expires_at > now()
       RETURNING user_id, used_at, (SELECT first_name FROM users WHERE id = login_tokens.user_id) AS first_name`, [hash]);
    if (!rows.length) {
      return reply.code(401).send({ error: 'bad_link' });
    }
    const { user_id: id, first_name, used_at: usedAt } = rows[0];
    return {
      token: signSession(Number(id), sessionSecret, 30 * 24 * 3600, usedAt?.getTime()),
      user: { id: Number(id), first_name }
    };
  });
  app.get('/ics/:file', async (req, reply) => {
    const m = /^([A-Za-z0-9_-]{20,100})\.ics$/.exec(req.params.file);
    if (!m) {
      return reply.code(404).send('not found');
    }
    const { rows: users } = await db.query('SELECT id FROM users WHERE ics_token = $1', [m[1]]);
    if (!users.length) {
      return reply.code(404).send('not found');
    }
    const { rows } = await db.query(`SELECT ${COLUMNS} FROM tasks t JOIN users u ON u.id = t.user_id
       WHERE t.user_id = $1 AND t.status = 'active' AND t.due_at IS NOT NULL
       ORDER BY t.due_at`, [users[0].id]);
    const { rows: olympiads } = await db.query('SELECT o.*, u.tz FROM olympiads o JOIN users u ON u.id = o.user_id WHERE o.user_id = $1', [users[0].id]);
    return reply
      .header('Content-Type', 'text/calendar; charset=utf-8')
      .header('Cache-Control', 'private, no-store')
      .header('Content-Disposition', 'inline; filename="uchebrik.ics"')
      .send(buildCalendar(rows, { host: req.hostname || 'uchebrick', olympiads }));
  });
  app.addHook('preHandler', async (req, reply) => {
    if (!['/api/tasks', '/api/files', '/api/olympiads', '/api/notes', '/api/settings', '/api/voice', '/api/objects'].some((p) => req.url.startsWith(p))) {
      return;
    }
    const header = req.headers.authorization ?? '';
    const claims = sessionClaims(header.replace(/^Bearer /, ''), sessionSecret);
    if (!claims) {
      return reply.code(401).send({ error: 'unauthorized' });
    }
    const { rows } = await db.query('SELECT true AS revoked FROM users WHERE id = $1 AND browser_revoked_at > to_timestamp($2::double precision / 1000)', [claims.uid, claims.iat]);
    if (rows[0]?.revoked === true) {
      return reply.code(401).send({ error: 'unauthorized' });
    }
    req.userId = claims.uid;
  });
  const taskId = (req) => {
    const id = Number(req.params.id);
    if (!Number.isInteger(id) || id <= 0) {
      throw new Error('bad_id');
    }
    return id;
  };
  const one = async (id, userId) => {
    const { rows } = await db.query(`SELECT ${COLUMNS} FROM tasks t JOIN users u ON u.id = t.user_id WHERE t.id = $1 AND t.user_id = $2`, [id, userId]);
    return rows[0] ?? null;
  };
  app.get('/api/tasks', async (req) => {
    const { rows } = await db.query(`SELECT ${COLUMNS}
       FROM tasks t JOIN users u ON u.id = t.user_id
       WHERE t.user_id = $1 AND t.status IN ('active', 'done')
       ORDER BY (t.status = 'done'), t.due_at NULLS LAST, t.id`, [req.userId]);
    return { tasks: rows };
  });
  app.post('/api/tasks', async (req, reply) => {
    const f = parseFields(req.body, true);
    const { rows } = await db.query(`INSERT INTO tasks (user_id, title, subject, kind, due_at, location, note, reg_deadline, duration_min, registered, needs_schedule)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, true) RETURNING id::int AS id`, [req.userId, f.title, f.subject ?? null, f.kind ?? 'homework', f.due_at ?? null, f.location ?? null, f.note ?? null,
    f.reg_deadline ?? null, f.duration_min ?? null, f.registered ?? false]);
    return reply.code(201).send({ task: await one(rows[0].id, req.userId) });
  });
  app.patch('/api/tasks/:id', async (req, reply) => {
    const id = taskId(req);
    const f = parseFields(req.body, false);
    const names = Object.keys(f);
    if (!names.length) {
      return reply.code(400).send({ error: 'bad_empty_patch' });
    }
    const sets = names.map((n, i) => `${n} = $${i + 3}`);
    if (['due_at', 'kind', 'duration_min', 'reg_deadline', 'registered'].some((field) => field in f)) {
      sets.push('needs_schedule = true');
    }
    const { rowCount } = await db.query(`UPDATE tasks SET ${sets.join(', ')} WHERE id = $1 AND user_id = $2`, [id, req.userId, ...names.map((n) => f[n])]);
    if (rowCount !== 1) {
      return reply.code(404).send({ error: 'not_found' });
    }
    return { task: await one(id, req.userId) };
  });
  app.delete('/api/tasks/:id', async (req, reply) => {
    const id = taskId(req);
    const { rows: linked } = await db.query('SELECT l.attachment_id FROM attachment_tasks l JOIN tasks t ON t.id = l.task_id WHERE t.id = $1 AND t.user_id = $2', [id, req.userId]);
    const { rowCount } = await db.query('DELETE FROM tasks WHERE id = $1 AND user_id = $2', [id, req.userId]);
    if (rowCount !== 1) {
      return reply.code(404).send({ error: 'not_found' });
    }
    if (linked.length) {
      const { rows } = await db.query(`DELETE FROM attachments a WHERE a.id = ANY($1::bigint[]) AND a.user_id = $2
           AND NOT EXISTS (SELECT 1 FROM attachment_tasks l WHERE l.attachment_id = a.id) RETURNING path`, [linked.map((r) => r.attachment_id), req.userId]);
      for (const r of rows ?? []) {
        if (STORED_NAME.test(r.path)) {
          await unlink(path.join(filesDir, r.path)).catch(() => { });
        }
      }
    }
    return { deleted: true };
  });
  const position = (body) => {
    const { x, y } = body ?? {};
    if (![x, y].every((v) => typeof v === 'number' && Number.isFinite(v) && Math.abs(v) < 1e6)) {
      throw new Error('bad_position');
    }
    return [x, y];
  };
  app.put('/api/tasks/:id/position', async (req, reply) => {
    const id = taskId(req);
    const [x, y] = position(req.body);
    const { rowCount } = await db.query('UPDATE tasks SET pos_x = $3, pos_y = $4 WHERE id = $1 AND user_id = $2', [id, req.userId, x, y]);
    if (rowCount !== 1) {
      return reply.code(404).send({ error: 'not_found' });
    }
    return { ok: true };
  });
  app.get('/api/tasks/:id', async (req, reply) => {
    const task = await one(taskId(req), req.userId);
    if (!task) {
      return reply.code(404).send({ error: 'not_found' });
    }
    return { task };
  });
  app.post('/api/tasks/:id/links', async (req, reply) => {
    const id = taskId(req);
    const url = linkUrl(req.body?.url);
    const { rows } = await db.query(`INSERT INTO task_links (task_id, url)
       SELECT id, $3 FROM tasks WHERE id = $1 AND user_id = $2
       RETURNING id::int AS id`, [id, req.userId, url]);
    if (!rows.length) {
      return reply.code(404).send({ error: 'not_found' });
    }
    return reply.code(201).send({ link: { id: rows[0].id, url } });
  });
  app.patch('/api/tasks/:id/links/:linkId/attach', async (req, reply) => {
    const target = taskId(req);
    const linkId = Number(req.params.linkId);
    if (!Number.isSafeInteger(target) || !Number.isSafeInteger(linkId) || linkId <= 0) {
      throw new Error('bad_id');
    }
    const { rows } = await db.query(`UPDATE task_links l SET task_id = target.id
       FROM tasks source, tasks target
       WHERE l.id = $3 AND source.id = l.task_id AND source.user_id = $2
         AND target.id = $1 AND target.user_id = $2
       RETURNING l.id::int AS id`, [target, req.userId, linkId]);
    if (!rows.length) {
      return reply.code(404).send({ error: 'not_found' });
    }
    return { ok: true };
  });
  app.delete('/api/tasks/:id/links/:linkId', async (req, reply) => {
    const id = taskId(req);
    const linkId = Number(req.params.linkId);
    if (!Number.isInteger(linkId) || linkId <= 0) {
      throw new Error('bad_id');
    }
    const { rowCount } = await db.query(`DELETE FROM task_links l USING tasks t
       WHERE l.id = $3 AND l.task_id = t.id AND t.id = $1 AND t.user_id = $2`, [id, req.userId, linkId]);
    if (rowCount !== 1) {
      return reply.code(404).send({ error: 'not_found' });
    }
    return { deleted: true };
  });
  const saveUpload = async (req, reply, taskId) => {
    const name = text(req.query?.name ?? 'Файл', 200) || 'Файл';
    if (!Buffer.isBuffer(req.body) || req.body.length === 0) {
      throw new Error('bad_file');
    }
    const mime = String(req.headers['x-file-type'] || '').slice(0, 100) || null;
    const kind = (mime && mime.startsWith('image/')) || IMAGE_EXT.test(name) ? 'photo' : 'doc';
    const coord = (v) => {
      if (v === undefined || v === '') {
        return null;
      }
      return Number(v);
    };
    const [x, y] = [coord(req.query?.x), coord(req.query?.y)];
    if (![x, y].every((v) => v === null || (Number.isFinite(v) && Math.abs(v) < 1e6))) {
      throw new Error('bad_position');
    }
    const stored = randomBytes(16).toString('hex');
    await mkdir(filesDir, { recursive: true });
    await writeFile(path.join(filesDir, stored), req.body);
    const { rows } = taskId === null
      ? await db.query(`INSERT INTO attachments (user_id, kind, name, mime, size_bytes, path, pos_x, pos_y)
         VALUES ($1, $2, $3, $4, $5, $6, $7, $8) RETURNING id::int AS id`, [req.userId, kind, name, mime, req.body.length, stored, x, y])
      : await db.query(`WITH t AS (SELECT id, user_id FROM tasks WHERE id = $1 AND user_id = $2),
              a AS (INSERT INTO attachments (user_id, kind, name, mime, size_bytes, path, pos_x, pos_y)
                    SELECT user_id, $3, $4, $5, $6, $7, $8, $9 FROM t RETURNING id),
              l AS (INSERT INTO attachment_tasks (attachment_id, task_id) SELECT a.id, t.id FROM a, t),
              q AS (INSERT INTO attachment_deliveries (attachment_id) SELECT id FROM a)
         SELECT id::int AS id FROM a`, [taskId, req.userId, kind, name, mime, req.body.length, stored, x, y]);
    if (!rows.length) {
      await unlink(path.join(filesDir, stored)).catch(() => { });
      return reply.code(404).send({ error: 'not_found' });
    }
    return reply.code(201).send({ file: { id: rows[0].id, kind, name, size: req.body.length, task_id: taskId, x, y } });
  };
  app.post('/api/voice', async (req, reply) => {
    if (!Buffer.isBuffer(req.body) || req.body.length === 0) {
      throw new Error('bad_file');
    }
    if (req.body.length > MAX_VOICE) {
      return reply.code(413).send({ error: 'too_big' });
    }
    const { rows: busy } = await db.query("SELECT count(*)::int AS n FROM voice_jobs WHERE user_id = $1 AND status IN ('pending', 'working') AND created_at > now() - interval '10 minutes'", [req.userId]);
    if (busy[0].n >= 3) {
      return reply.code(429).send({ error: 'too_many' });
    }
    const stored = randomBytes(16).toString('hex');
    await mkdir(filesDir, { recursive: true });
    await writeFile(path.join(filesDir, stored), req.body);
    const { rows } = await db.query('INSERT INTO voice_jobs (user_id, path) VALUES ($1, $2) RETURNING id::int AS id', [req.userId, stored]);
    return reply.code(201).send({ id: rows[0].id });
  });
  app.get('/api/voice/:id', async (req, reply) => {
    const { rows } = await db.query('SELECT status, result, error FROM voice_jobs WHERE id = $1 AND user_id = $2', [taskId(req), req.userId]);
    if (!rows.length) {
      return reply.code(404).send({ error: 'not_found' });
    }
    return rows[0];
  });
  app.post('/api/tasks/:id/files', async (req, reply) => saveUpload(req, reply, taskId(req)));
  app.post('/api/files', async (req, reply) => saveUpload(req, reply, null));
  app.get('/api/files', async (req) => {
    const { rows } = await db.query(`SELECT id::int AS id, kind, name, size_bytes AS size, pos_x AS x, pos_y AS y FROM attachments a
       WHERE user_id = $1 AND NOT EXISTS (SELECT 1 FROM attachment_tasks l WHERE l.attachment_id = a.id) ORDER BY id`, [req.userId]);
    return { files: rows };
  });
  const ownTaskOrNull = (v) => {
    if (v === null) {
      return null;
    }
    if (!Number.isInteger(v) || v <= 0) {
      throw new Error('bad_task_id');
    }
    return v;
  };
  app.patch('/api/files/:id', async (req, reply) => {
    const f = await ownFile(req);
    if (!f) {
      return reply.code(404).send({ error: 'not_found' });
    }
    const target = ownTaskOrNull(req.body?.task_id);
    if (target === null) {
      await db.query('DELETE FROM attachment_tasks WHERE attachment_id = $1', [f.id]);
      return { ok: true };
    }
    const { rows } = await db.query(`INSERT INTO attachment_tasks (attachment_id, task_id)
       SELECT $1, id FROM tasks WHERE id = $3 AND user_id = $2 ON CONFLICT DO NOTHING RETURNING task_id`, [f.id, req.userId, target]);
    const { rows: own } = rows.length ? { rows } : await db.query('SELECT id FROM tasks WHERE id = $1 AND user_id = $2', [target, req.userId]);
    if (!own.length) {
      return reply.code(404).send({ error: 'not_found' });
    }
    return { ok: true };
  });
  app.delete('/api/files/:id/links/:taskId', async (req, reply) => {
    const f = await ownFile(req);
    if (!f) {
      return reply.code(404).send({ error: 'not_found' });
    }
    const target = ownTaskOrNull(Number(req.params.taskId));
    await db.query('DELETE FROM attachment_tasks WHERE attachment_id = $1 AND task_id = $2', [f.id, target]);
    if (req.query?.drop === '1') {
      const { rows } = await db.query(`DELETE FROM attachments a WHERE a.id = $1 AND NOT EXISTS (SELECT 1 FROM attachment_tasks l WHERE l.attachment_id = a.id)
         RETURNING path`, [f.id]);
      if (rows.length) {
        await unlink(path.join(filesDir, f.path)).catch(() => { });
      }
      return { ok: true, deleted: rows.length > 0 };
    }
    return { ok: true, deleted: false };
  });
  const NOTE_COLUMNS = 'id::int AS id, task_id::int AS task_id, text, pos_x AS x, pos_y AS y';
  const noteText = (v) => {
    const t = text(v, 2000);
    if (!t) {
      throw new Error('empty_note');
    }
    return t;
  };
  const noteId = (req) => {
    const id = Number(req.params.id);
    if (!Number.isInteger(id) || id <= 0) {
      throw new Error('bad_id');
    }
    return id;
  };
  app.get('/api/notes', async (req) => {
    const { rows } = await db.query(`SELECT ${NOTE_COLUMNS} FROM notes WHERE user_id = $1 ORDER BY id`, [req.userId]);
    return { notes: rows };
  });
  app.post('/api/notes', async (req, reply) => {
    const body = req.body ?? {};
    const target = body.task_id === undefined ? null : ownTaskOrNull(body.task_id);
    const [x, y] = body.x === undefined && body.y === undefined ? [null, null] : position(body);
    const { rows } = await db.query(`INSERT INTO notes (user_id, task_id, text, pos_x, pos_y)
       SELECT $1, $2, $3, $4, $5 WHERE $2::bigint IS NULL OR EXISTS (SELECT 1 FROM tasks WHERE id = $2 AND user_id = $1)
       RETURNING ${NOTE_COLUMNS}`, [req.userId, target, noteText(body.text), x, y]);
    if (!rows.length) {
      return reply.code(404).send({ error: 'not_found' });
    }
    return reply.code(201).send({ note: rows[0] });
  });
  app.patch('/api/notes/:id', async (req, reply) => {
    const body = req.body ?? {};
    const sets = [];
    const params = [noteId(req), req.userId];
    if (body.text !== undefined) {
      params.push(noteText(body.text));
      sets.push(`text = $${params.length}`);
    }
    let check = 'true';
    if (body.task_id !== undefined) {
      params.push(ownTaskOrNull(body.task_id));
      const n = params.length;
      sets.push(`task_id = $${n}`);
      check = `($${n}::bigint IS NULL OR EXISTS (SELECT 1 FROM tasks WHERE id = $${n} AND user_id = $2))`;
    }
    if (!sets.length) {
      throw new Error('bad_empty_patch');
    }
    const { rows } = await db.query(`UPDATE notes SET ${sets.join(', ')}, updated_at = now() WHERE id = $1 AND user_id = $2 AND ${check} RETURNING ${NOTE_COLUMNS}`, params);
    if (!rows.length) {
      return reply.code(404).send({ error: 'not_found' });
    }
    return { note: rows[0] };
  });
  app.put('/api/notes/:id/position', async (req, reply) => {
    const [x, y] = position(req.body);
    const { rowCount } = await db.query('UPDATE notes SET pos_x = $3, pos_y = $4 WHERE id = $1 AND user_id = $2', [noteId(req), req.userId, x, y]);
    if (rowCount !== 1) {
      return reply.code(404).send({ error: 'not_found' });
    }
    return { ok: true };
  });
  app.delete('/api/notes/:id', async (req, reply) => {
    const { rowCount } = await db.query('DELETE FROM notes WHERE id = $1 AND user_id = $2', [noteId(req), req.userId]);
    if (rowCount !== 1) {
      return reply.code(404).send({ error: 'not_found' });
    }
    return { deleted: true };
  });
  const ownFile = async (req) => {
    const id = Number(req.params.id);
    if (!Number.isInteger(id) || id <= 0) {
      throw new Error('bad_id');
    }
    const { rows } = await db.query('SELECT a.id, a.name, a.mime, a.path FROM attachments a WHERE a.id = $1 AND a.user_id = $2', [id, req.userId]);
    const f = rows[0];
    if (f && STORED_NAME.test(f.path)) {
      return f;
    }
    return null;
  };
  app.get('/api/files/:id', async (req, reply) => {
    const f = await ownFile(req);
    if (!f) {
      return reply.code(404).send({ error: 'not_found' });
    }
    return reply
      .header('Content-Type', f.mime || 'application/octet-stream')
      .header('Content-Disposition', `inline; filename*=UTF-8''${encodeURIComponent(f.name)}`)
      .header('Cache-Control', 'private, max-age=3600')
      .header('X-Content-Type-Options', 'nosniff')
      .send(createReadStream(path.join(filesDir, f.path)));
  });
  app.put('/api/tasks/:id/links/:linkId/position', async (req, reply) => {
    const linkId = Number(req.params.linkId);
    if (!Number.isInteger(linkId) || linkId <= 0) {
      throw new Error('bad_id');
    }
    const [x, y] = position(req.body);
    const { rowCount } = await db.query(`UPDATE task_links l SET pos_x = $4, pos_y = $5 FROM tasks t
       WHERE l.id = $1 AND l.task_id = t.id AND t.id = $2 AND t.user_id = $3`, [linkId, taskId(req), req.userId, x, y]);
    if (rowCount !== 1) {
      return reply.code(404).send({ error: 'not_found' });
    }
    return { ok: true };
  });
  app.put('/api/files/:id/position', async (req, reply) => {
    const [x, y] = position(req.body);
    const f = await ownFile(req);
    if (!f) {
      return reply.code(404).send({ error: 'not_found' });
    }
    await db.query('UPDATE attachments SET pos_x = $2, pos_y = $3 WHERE id = $1', [f.id, x, y]);
    return { ok: true };
  });
  app.delete('/api/files/:id', async (req, reply) => {
    const f = await ownFile(req);
    if (!f) {
      return reply.code(404).send({ error: 'not_found' });
    }
    await db.query('DELETE FROM attachments WHERE id = $1', [f.id]);
    await unlink(path.join(filesDir, f.path)).catch(() => { });
    return { deleted: true };
  });
  app.post('/api/tasks/:id/done', async (req) => {
    const { rowCount } = await db.query(`UPDATE tasks SET status = 'done', done_at = now(), next_remind_at = NULL
       WHERE id = $1 AND user_id = $2 AND status = 'active'`, [taskId(req), req.userId]);
    return { changed: rowCount === 1 };
  });
  app.post('/api/tasks/:id/undone', async (req) => {
    const { rowCount } = await db.query(`UPDATE tasks SET status = 'active', done_at = NULL, needs_schedule = true
       WHERE id = $1 AND user_id = $2 AND status = 'done'`, [taskId(req), req.userId]);
    return { changed: rowCount === 1 };
  });
  app.get('/api/olympiads', async (req) => {
    const { rows } = await db.query(`SELECT ${OLY_COLUMNS} FROM olympiads WHERE user_id = $1 ORDER BY reg_deadline NULLS LAST, id`, [req.userId]);
    return { olympiads: rows };
  });
  const OLY_VALUES = (o) => {
    return [o.name, o.level, o.subject, o.location, o.note, o.registered, o.reg_opens, o.reg_deadline,
    o.links, o.reminders_muted, JSON.stringify(o.tours)];
  };
  app.post('/api/olympiads', async (req, reply) => {
    const { rows } = await db.query(`INSERT INTO olympiads (user_id, name, level, subject, location, note, registered, reg_opens, reg_deadline,
                              links, reminders_muted, tours)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, COALESCE($11, false), $12::jsonb) RETURNING ${OLY_COLUMNS}`, [req.userId, ...OLY_VALUES(parseOlympiad(req.body))]);
    return reply.code(201).send({ olympiad: rows[0] });
  });
  app.put('/api/olympiads/:id', async (req, reply) => {
    const { rows } = await db.query(`UPDATE olympiads SET name = $3, level = $4, subject = $5, location = $6, note = $7, registered = $8,
         reg_opens = $9, reg_deadline = $10, links = $11, reminders_muted = COALESCE($12, reminders_muted), tours = $13::jsonb
       WHERE id = $1 AND user_id = $2 RETURNING ${OLY_COLUMNS}`, [taskId(req), req.userId, ...OLY_VALUES(parseOlympiad(req.body))]);
    if (!rows[0]) {
      return reply.code(404).send({ error: 'not_found' });
    }
    return { olympiad: rows[0] };
  });
  app.put('/api/olympiads/:id/registered', async (req, reply) => {
    const value = req.body?.registered;
    if (typeof value !== 'boolean') {
      throw new Error('bad_registered');
    }
    const { rowCount } = await db.query('UPDATE olympiads SET registered = $3 WHERE id = $1 AND user_id = $2', [taskId(req), req.userId, value]);
    if (rowCount !== 1) {
      return reply.code(404).send({ error: 'not_found' });
    }
    return { ok: true };
  });
  app.delete('/api/olympiads/:id', async (req, reply) => {
    const { rowCount } = await db.query('DELETE FROM olympiads WHERE id = $1 AND user_id = $2', [taskId(req), req.userId]);
    if (rowCount !== 1) {
      return reply.code(404).send({ error: 'not_found' });
    }
    return { deleted: true };
  });
  registerSettings(app, db, aliceSecret);
  registerObjects(app, db, filesDir);
  return app;
}
