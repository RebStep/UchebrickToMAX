import { createHmac, timingSafeEqual } from 'node:crypto';
const b64 = (buf) => Buffer.from(buf).toString('base64url');
export function signSession(userId, secret, ttlSec = 12 * 3600, now = Date.now()) {
  const payload = b64(JSON.stringify({ uid: userId, iat: now, exp: Math.floor(now / 1000) + ttlSec }));
  const sig = b64(createHmac('sha256', secret).update(payload).digest());
  return `${payload}.${sig}`;
}
export function verifySession(token, secret, now = Date.now()) {
  return sessionClaims(token, secret, now)?.uid ?? null;
}
export function sessionClaims(token, secret, now = Date.now()) {
  if (typeof token !== 'string' || !/^[\w-]+\.[\w-]+$/.test(token)) {
    return null;
  }
  const [payload, sig] = token.split('.');
  if (!payload || !sig) {
    return null;
  }
  const expected = createHmac('sha256', secret).update(payload).digest();
  const given = Buffer.from(sig, 'base64url');
  if (given.length !== expected.length || !timingSafeEqual(given, expected)) {
    return null;
  }
  try {
    const { uid, exp, iat = 0 } = JSON.parse(Buffer.from(payload, 'base64url').toString());
    if (exp * 1000 > now && Number.isSafeInteger(uid) && uid > 0 && Number.isSafeInteger(iat) && iat <= now) {
      return { uid, iat };
    }
    return null;
  }
  catch {
    return null;
  }
}
