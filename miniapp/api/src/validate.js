import { createHmac, timingSafeEqual } from 'node:crypto';
export const MAX_AGE_SEC = 3600;
export function validateInitData(initData, botToken, now = Date.now()) {
  if (typeof initData !== 'string' || !initData) {
    return null;
  }
  const pairs = initData.split('&').map((p) => {
    const i = p.indexOf('=');
    if (i < 0) {
      return [p, ''];
    }
    return [p.slice(0, i), p.slice(i + 1)];
  });
  const hashes = pairs.filter(([k]) => k === 'hash');
  if (hashes.length !== 1 || !/^[0-9a-f]{64}$/i.test(hashes[0][1])) {
    return null;
  }
  if (new Set(pairs.map(([k]) => k)).size !== pairs.length) {
    return null;
  }
  let params;
  try {
    params = pairs.filter(([k]) => k !== 'hash').map(([k, v]) => [k, decodeURIComponent(v)]);
  }
  catch {
    return null;
  }
  if (params.some(([key, value]) => !/^[a-z_][a-z0-9_]*$/i.test(key) || /[\r\n]/.test(value))) {
    return null;
  }
  params.sort((a, b) => {
    if (a[0] < b[0]) {
      return -1;
    }
    if (a[0] > b[0]) {
      return 1;
    }
    return 0;
  });
  const launchParams = params.map(([k, v]) => `${k}=${v}`).join('\n');
  const secret = createHmac('sha256', 'WebAppData').update(botToken).digest();
  const expected = createHmac('sha256', secret).update(launchParams).digest();
  const given = Buffer.from(hashes[0][1], 'hex');
  if (given.length !== expected.length || !timingSafeEqual(given, expected)) {
    return null;
  }
  const data = Object.fromEntries(params);
  if (!/^\d+$/.test(data.auth_date ?? '')) {
    return null;
  }
  const authDate = Number(data.auth_date);
  const age = Math.floor(now / 1000) - authDate;
  if (!Number.isSafeInteger(authDate) || age < 0 || age > MAX_AGE_SEC) {
    return null;
  }
  let user;
  try {
    user = JSON.parse(data.user);
  }
  catch {
    return null;
  }
  if (!user || !Number.isSafeInteger(user.id) || user.id <= 0) {
    return null;
  }
  return { user, authDate };
}
