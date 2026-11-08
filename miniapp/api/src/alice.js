import { createHash, createHmac, timingSafeEqual } from 'node:crypto';
const hash = (s) => createHash('sha256').update(s).digest();
const reply = (text, endSession = true) => ({ response: { text: text.slice(0, 1000), end_session: endSession }, version: '1.0' });
const commandOf = (request) => {
  return typeof request?.command === 'string' ? request.command.trim().slice(0, 1000) : '';
};
async function converse(db, userId, identity, command, session) {
  if (!command || /^(помощь|что ты умеешь)$/i.test(command)) {
    return reply('Продиктуй задание, и я пришлю черновик в MAX. Чтобы узнать ближайшие дела, скажи «что задано».', false);
  }
  if (/что задано|что у меня|^(список|задания)$/i.test(command)) {
    const { rows } = await db.query(`SELECT t.title, t.subject, t.due_at, u.tz FROM tasks t JOIN users u ON u.id = t.user_id
         WHERE t.user_id = $1 AND t.status = 'active' ORDER BY t.due_at NULLS LAST, t.id LIMIT 5`, [userId]);
    if (!rows.length) {
      return reply('Открытых заданий нет.');
    }
    return reply(rows.map((t) => {
      const when = t.due_at ? new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long', timeZone: t.tz }).format(t.due_at) : 'без срока';
      return `${t.subject ? t.subject + ': ' : ''}${t.title.slice(0, 120)}, ${when}.`;
    }).join(' '));
  }
  if (typeof session?.session_id !== 'string' || session.session_id.length > 64 || !Number.isSafeInteger(session.message_id)) {
    return reply('Не удалось принять сообщение. Попробуй ещё раз.');
  }
  const key = hash(JSON.stringify([identity, session.session_id, session.message_id])).toString('hex');
  await db.query('INSERT INTO alice_inbox (event_key, identity_hash, text) VALUES ($1, $2, $3) ON CONFLICT DO NOTHING', [key, identity, command]);
  return reply('Приняла. Проверь и подтверди черновик в MAX.');
}
function registerPrivateAlice(app, db) {
  app.post('/alice/u/:token', { bodyLimit: 32768 }, async (req, res) => {
    if (!/^[A-Za-z0-9_-]{20,100}$/.test(req.params.token)) {
      return res.code(404).send({ error: 'not_found' });
    }
    const { rows: [user] } = await db.query('SELECT id FROM users WHERE alice_private_token = $1', [req.params.token]);
    if (!user) {
      return res.code(404).send({ error: 'not_found' });
    }
    const { request, session } = req.body ?? {};
    if (request?.original_utterance === 'ping') {
      return reply('pong');
    }
    const identity = 'p:' + hash('private:' + user.id).toString('hex');
    await db.query('INSERT INTO alice_links (identity_hash, user_id) VALUES ($1, $2) ON CONFLICT (identity_hash) DO NOTHING', [identity, user.id]);
    return converse(db, user.id, identity, commandOf(request), session);
  });
}
export function registerAlice(app, db, secret) {
  registerPrivateAlice(app, db);
  if (!secret) {
    return;
  }
  if (!/^[A-Za-z0-9_-]{32,128}$/.test(secret)) {
    throw new Error('ALICE_SECRET: требуется от 32 URL-совместимых символов');
  }
  const attempts = new Map();
  app.post('/alice/:secret', { bodyLimit: 32768 }, async (req, res) => {
    if (!timingSafeEqual(hash(req.params.secret), hash(secret))) {
      return res.code(404).send({ error: 'not_found' });
    }
    const { request, session } = req.body ?? {};
    if (request?.original_utterance === 'ping') {
      return reply('pong');
    }
    const id = session?.user?.user_id ?? session?.application?.application_id;
    if (typeof id !== 'string' || !id || id.length > 256) {
      return reply('Не удалось распознать профиль Алисы.');
    }
    const identity = hash((session?.user?.user_id ? 'user:' : 'app:') + id).toString('hex');
    const command = commandOf(request);
    const { rows: [link] } = await db.query('SELECT user_id FROM alice_links WHERE identity_hash = $1', [identity]);
    if (!link) {
      const code = /^(?:привяжи\s+)?([0-9](?:\s*[0-9]){5})$/i.exec(command)?.[1].replace(/\s/g, '');
      if (code) {
        const now = Date.now();
        if (attempts.size > 1000) {
          for (const [key, value] of attempts) {
            if (now - value.at >= 60000) {
              attempts.delete(key);
            }
          }
          if (attempts.size > 1000) {
            return reply('Попробуй через минуту.', false);
          }
        }
        const last = attempts.get(identity);
        const attempt = last && now - last.at < 60000 ? last : { at: now, count: 0 };
        if (attempt.count >= 5) {
          return reply('Попробуй через минуту.', false);
        }
        attempt.count++;
        attempts.set(identity, attempt);
        const codeHash = createHmac('sha256', secret).update(code).digest('hex');
        const { rowCount } = await db.query(`WITH code AS (DELETE FROM alice_link_codes WHERE code_hash = $1 AND expires_at > now() RETURNING user_id)
           INSERT INTO alice_links (identity_hash, user_id) SELECT $2, user_id FROM code
           ON CONFLICT (identity_hash) DO NOTHING`, [codeHash, identity]);
        if (rowCount) {
          attempts.delete(identity);
          return reply('Готово, привязала. Теперь продиктуй задание.', false);
        }
        return reply('Код не подошёл или устарел. Запроси новый код в MAX командой /link.', false);
      }
      return reply('Отправь боту в MAX команду /link и назови шесть цифр кода.', false);
    }
    return converse(db, link.user_id, identity, command, session);
  });
}
