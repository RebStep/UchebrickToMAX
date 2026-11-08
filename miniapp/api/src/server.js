import pg from 'pg';
import { buildApp } from './app.js';
const need = (name) => {
  const v = process.env[name];
  if (!v) {
    throw new Error(`Не задана переменная окружения ${name}`);
  }
  return v;
};
const app = buildApp({
  db: new pg.Pool({ connectionString: need('DATABASE_URL'), max: 5 }),
  botToken: need('MAX_BOT_TOKEN'),
  sessionSecret: need('SESSION_SECRET'),
  aliceSecret: process.env.ALICE_SECRET,
  logger: true,
});
await app.listen({ host: '0.0.0.0', port: Number(process.env.PORT ?? 3000) });
