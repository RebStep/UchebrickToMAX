import { unlink } from 'node:fs/promises';
import path from 'node:path';
export function parseSelection(body) {
  const kinds = ['tasks', 'files', 'notes', 'links'];
  if (!body || typeof body !== 'object' || Array.isArray(body)) {
    throw new Error('bad_selection');
  }
  for (const key of Object.keys(body)) {
    if (!kinds.includes(key)) {
      throw new Error('bad_selection');
    }
  }
  const result = {};
  for (const key of kinds) {
    const ids = body[key] === undefined ? [] : body[key];
    if (!Array.isArray(ids) || ids.length > 500 || ids.some((id) => !Number.isSafeInteger(id) || id <= 0)) {
      throw new Error('bad_selection');
    }
    result[key] = [...new Set(ids)];
  }
  let count = 0;
  for (const ids of Object.values(result)) {
    count += ids.length;
  }
  if (!count || count > 500) {
    throw new Error('bad_selection');
  }
  return result;
}
export function registerObjects(app, db, filesDir) {
  app.post('/api/objects/delete', async (req, reply) => {
    const ids = parseSelection(req.body);
    const client = await db.connect();
    let removed = [];
    try {
      await client.query('BEGIN');
      for (const [key, table] of [['tasks', 'tasks'], ['files', 'attachments'], ['notes', 'notes'], ['links', 'task_links']]) {
        if (!ids[key].length) {
          continue;
        }
        const sql = key === 'links'
          ? 'SELECT l.id FROM task_links l JOIN tasks t ON t.id = l.task_id WHERE t.user_id = $1 AND l.id = ANY($2::bigint[]) FOR UPDATE OF l'
          : `SELECT id FROM ${table} WHERE user_id = $1 AND id = ANY($2::bigint[]) FOR UPDATE`;
        const { rows } = await client.query(sql, [req.userId, ids[key]]);
        if (rows.length !== ids[key].length) {
          await client.query('ROLLBACK');
          return reply.code(404).send({ error: 'not_found' });
        }
      }
      const { rows: linked } = await client.query('SELECT attachment_id FROM attachment_tasks WHERE task_id = ANY($1::bigint[])', [ids.tasks]);
      await client.query('DELETE FROM task_links WHERE id = ANY($1::bigint[])', [ids.links]);
      await client.query('DELETE FROM notes WHERE id = ANY($1::bigint[])', [ids.notes]);
      await client.query('DELETE FROM tasks WHERE id = ANY($1::bigint[])', [ids.tasks]);
      const { rows } = await client.query(`DELETE FROM attachments a WHERE a.user_id = $1 AND
        (a.id = ANY($2::bigint[]) OR (a.id = ANY($3::bigint[]) AND NOT EXISTS
          (SELECT 1 FROM attachment_tasks l WHERE l.attachment_id = a.id))) RETURNING path`, [req.userId, ids.files, linked.map((row) => row.attachment_id)]);
      removed = rows;
      await client.query('COMMIT');
    }
    catch (e) {
      await client.query('ROLLBACK');
      throw e;
    }
    finally {
      client.release();
    }
    for (const file of removed) {
      if (/^[0-9a-f]{32}$/.test(file.path)) {
        await unlink(path.join(filesDir, file.path)).catch(() => { });
      }
    }
    return { deleted: true };
  });
}
