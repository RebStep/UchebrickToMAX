import { createHash, createHmac, randomBytes, randomInt } from 'node:crypto';
const HHMM = /^([01]\d|2[0-3]):[0-5]\d$/;
const COLUMNS = `tz, to_char(quiet_from, 'HH24:MI') AS quiet_from, to_char(quiet_to, 'HH24:MI') AS quiet_to,
  repeat_min, repeat_max, work_schedule, remind_mode, to_char(morning_at, 'HH24:MI') AS morning_at, ics_token, alice_private_token,
  EXISTS (SELECT 1 FROM alice_links WHERE user_id = users.id AND identity_hash NOT LIKE 'p:%') AS alice_linked`;
export function parseSettings(body) {
  if (!body || typeof body !== 'object' || Array.isArray(body)) {
    throw new Error('bad_body');
  }
  const out = {};
  const allowed = ['quiet_from', 'quiet_to', 'repeat_min', 'repeat_max', 'work_schedule', 'remind_mode', 'morning_at'];
  if (Object.keys(body).some((key) => !allowed.includes(key))) {
    throw new Error('bad_field');
  }
  for (const key of ['quiet_from', 'quiet_to', 'morning_at']) {
    if (!Object.hasOwn(body, key)) {
      continue;
    }
    if (key === 'morning_at' && body[key] === null) {
      out[key] = null;
      continue;
    }
    if (typeof body[key] !== 'string' || !HHMM.test(body[key])) {
      throw new Error('bad_time');
    }
    if (key === 'morning_at' && body[key] >= '12:00') {
      throw new Error('bad_morning_time');
    }
    out[key] = body[key];
  }
  for (const [key, min, max] of [['repeat_min', 5, 1440], ['repeat_max', 1, 20]]) {
    if (!Object.hasOwn(body, key)) {
      continue;
    }
    if (!Number.isInteger(body[key]) || body[key] < min || body[key] > max) {
      throw new Error('bad_repeat');
    }
    out[key] = body[key];
  }
  for (const [key, values] of [['work_schedule', ['classic', 'school', 'evening']], ['remind_mode', ['all', 'selected', 'none']]]) {
    if (!Object.hasOwn(body, key)) {
      continue;
    }
    if (!values.includes(body[key])) {
      throw new Error('bad_setting');
    }
    out[key] = body[key];
  }
  if (!Object.keys(out).length) {
    throw new Error('bad_empty_patch');
  }
  return out;
}
export function registerSettings(app, db, aliceSecret) {
  const origin = (req) => {
    const proto = String(req.headers['x-forwarded-proto'] || 'https').split(',')[0].trim();
    const host = String(req.headers['x-forwarded-host'] || req.headers.host || '').split(',')[0].trim();
    return `${proto}://${host}`;
  };
  const settingsOf = async (req) => {
    let { rows } = await db.query(`SELECT ${COLUMNS} FROM users WHERE id = $1`, [req.userId]);
    if (!rows[0]) {
      return null;
    }
    if (!rows[0].ics_token) {
      ;
      ({ rows } = await db.query(`UPDATE users SET ics_token = COALESCE(ics_token, $2) WHERE id = $1 RETURNING ${COLUMNS}`, [req.userId, randomBytes(18).toString('base64url')]));
    }
    const { ics_token: token, alice_private_token: alicePrivate, ...rest } = rows[0];
    return {
      ...rest,
      alice_enabled: Boolean(aliceSecret),
      alice_private_url: alicePrivate ? `${origin(req)}/alice/u/${alicePrivate}` : null,
      ics_url: `${origin(req)}/ics/${token}.ics`,
    };
  };
  app.get('/api/settings', async (req, reply) => {
    const settings = await settingsOf(req);
    if (settings) {
      return { settings };
    }
    return reply.code(404).send({ error: 'not_found' });
  });
  app.put('/api/settings', async (req, reply) => {
    const fields = parseSettings(req.body);
    const entries = Object.entries(fields);
    const sets = entries.map(([key], i) => `${key} = $${i + 2}`);
    const params = [req.userId, ...entries.map(([, value]) => value)];
    const reschedule = Object.hasOwn(fields, 'work_schedule') || Object.hasOwn(fields, 'remind_mode');
    const query = reschedule
      ? `WITH changed AS (UPDATE users SET ${sets.join(', ')} WHERE id = $1 RETURNING id)
         UPDATE tasks SET needs_schedule = true FROM changed WHERE tasks.user_id = changed.id AND tasks.status = 'active'`
      : `UPDATE users SET ${sets.join(', ')} WHERE id = $1`;
    const result = await db.query(query, params);
    if (!reschedule && result.rowCount !== 1) {
      return reply.code(404).send({ error: 'not_found' });
    }
    const settings = await settingsOf(req);
    if (settings) {
      return { settings };
    }
    return reply.code(404).send({ error: 'not_found' });
  });
  app.post('/api/settings/browser-link', async (req) => {
    const token = randomBytes(32).toString('base64url');
    await db.query("INSERT INTO login_tokens (token_hash, user_id, expires_at) VALUES ($1, $2, now() + interval '10 minutes')", [createHash('sha256').update(token).digest('hex'), req.userId]);
    return { url: `${origin(req)}/?t=${encodeURIComponent(token)}` };
  });
  app.post('/api/settings/logout', async (req) => {
    await db.query(`WITH changed AS (UPDATE users SET browser_revoked_at = clock_timestamp() WHERE id = $1 RETURNING id)
      DELETE FROM login_tokens WHERE user_id IN (SELECT id FROM changed)`, [req.userId]);
    return { ok: true };
  });
  app.post('/api/settings/alice/code', async (req, reply) => {
    if (!aliceSecret) {
      return reply.code(503).send({ error: 'alice_disabled' });
    }
    for (let attempt = 0; attempt < 5; attempt++) {
      const code = String(randomInt(1000000)).padStart(6, '0');
      try {
        await db.query(`INSERT INTO alice_link_codes (user_id, code_hash, expires_at) VALUES ($1, $2, now() + interval '5 minutes')
          ON CONFLICT (user_id) DO UPDATE SET code_hash = EXCLUDED.code_hash, expires_at = EXCLUDED.expires_at`, [req.userId, createHmac('sha256', aliceSecret).update(code).digest('hex')]);
        return { code, expires_in: 300 };
      }
      catch (e) {
        if (e.code !== '23505') {
          throw e;
        }
      }
    }
    return reply.code(503).send({ error: 'try_again' });
  });
  app.delete('/api/settings/alice', async (req) => {
    await db.query(`WITH cleared AS (DELETE FROM alice_link_codes WHERE user_id = $1)
      DELETE FROM alice_links WHERE user_id = $1 AND identity_hash NOT LIKE 'p:%'`, [req.userId]);
    return { ok: true };
  });
  app.post('/api/settings/alice/private', async (req) => {
    const reset = req.body?.reset === true;
    const token = randomBytes(24).toString('base64url');
    const { rows: [row] } = await db.query(`UPDATE users SET alice_private_token = ${reset ? '$2' : 'COALESCE(alice_private_token, $2)'}
       WHERE id = $1 RETURNING alice_private_token`, [req.userId, token]);
    return { url: `${origin(req)}/alice/u/${row.alice_private_token}` };
  });
  app.delete('/api/settings/alice/private', async (req) => {
    await db.query(`WITH cleared AS (UPDATE users SET alice_private_token = NULL WHERE id = $1)
      DELETE FROM alice_links WHERE user_id = $1 AND identity_hash LIKE 'p:%'`, [req.userId]);
    return { ok: true };
  });
}
