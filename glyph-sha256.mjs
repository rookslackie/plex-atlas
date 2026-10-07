/** Xi glyph-SHA v1. Exact nibble encoding; raw file bytes retain ordinary SHA-256. */
export const DIALECT = 'xi.glyph-sha256.v1';
export const RECEIPT_SCHEMA = 'xi.glyph-sha256.receipt.v1';
export const HEX = '0123456789abcdef';
export const GLYPHS = '∴Ω⧂⋈Ξ⟐⊚◇✦⟁∵☉◬⌬⧉∞';
export const ALPHABET = Object.freeze([...GLYPHS]);
const REVERSE = new Map(ALPHABET.map((glyph, i) => [glyph, HEX[i]]));
const STATES = new Set(['not_performed', 'hashed', 'match', 'mismatch']);
const KEYS = ['schema', 'dialect', 'algorithm', 'hex_sha256', 'glyph_tile',
  'encoding_verified', 'file_verification', 'expected_sha256'];
const trimASCII = (value) => value.replace(/^[ \t\r\n]+|[ \t\r\n]+$/g, '');

export function normalizeHex(value) {
  if (typeof value !== 'string') throw new TypeError('Expected a SHA-256 string.');
  const hex = trimASCII(value);
  if (!/^[0-9a-fA-F]{64}$/.test(hex)) throw new Error('SHA-256 must contain exactly 64 hexadecimal digits.');
  return hex.toLowerCase();
}

export function encode(value) {
  const symbols = [...normalizeHex(value)].map((digit) => ALPHABET[HEX.indexOf(digit)]).join('');
  return Array.from({ length: 8 }, (_, row) => symbols.slice(row * 8, row * 8 + 8)).join('\n');
}

export function decode(value) {
  if (typeof value !== 'string') throw new TypeError('Expected a glyph tile string.');
  const symbols = [...value.replace(/[ \t\r\n]/g, '')];
  if (symbols.length !== 64) throw new Error('A SHA-256 tile must contain exactly 64 glyphs.');
  return symbols.map((glyph, i) => {
    if (!REVERSE.has(glyph)) throw new Error(`Unknown glyph at position ${i + 1}: U+${glyph.codePointAt(0).toString(16).toUpperCase()}.`);
    return REVERSE.get(glyph);
  }).join('');
}

export function parseExpected(value) {
  if (typeof value !== 'string') throw new TypeError('Expected a SHA-256 or glyph tile.');
  const trimmed = trimASCII(value);
  return /^[0-9a-fA-F]+$/.test(trimmed) ? normalizeHex(trimmed) : decode(value);
}

export function makeReceipt(value, fileVerification = 'not_performed', expected = null) {
  const hex = normalizeHex(value);
  const receipt = {
    schema: RECEIPT_SCHEMA, dialect: DIALECT, algorithm: 'SHA-256',
    hex_sha256: hex, glyph_tile: encode(hex), encoding_verified: true,
    file_verification: fileVerification,
    expected_sha256: expected === null ? null : normalizeHex(expected),
  };
  validateReceipt(receipt);
  return Object.freeze(receipt);
}

export function validateReceipt(receipt) {
  if (!receipt || typeof receipt !== 'object' || Array.isArray(receipt)) throw new Error('Expected a receipt object.');
  if (Object.keys(receipt).length !== KEYS.length || KEYS.some((key) => !Object.hasOwn(receipt, key))) {
    throw new Error('Receipt fields must match the public v1 schema exactly.');
  }
  if (receipt.schema !== RECEIPT_SCHEMA || receipt.dialect !== DIALECT || receipt.algorithm !== 'SHA-256') {
    throw new Error('Unsupported receipt schema, dialect, or algorithm.');
  }
  const hex = normalizeHex(receipt.hex_sha256);
  if (hex !== receipt.hex_sha256 || receipt.glyph_tile !== encode(hex) || decode(receipt.glyph_tile) !== hex || receipt.encoding_verified !== true) {
    throw new Error('Receipt hex and canonical tile must agree.');
  }
  if (!STATES.has(receipt.file_verification)) throw new Error('Unknown file verification state.');
  const comparing = ['match', 'mismatch'].includes(receipt.file_verification);
  if (!comparing && receipt.expected_sha256 !== null) throw new Error('An unperformed comparison cannot carry an expected digest.');
  if (comparing) {
    const expected = normalizeHex(receipt.expected_sha256);
    if (expected !== receipt.expected_sha256 || (hex === expected) !== (receipt.file_verification === 'match')) {
      throw new Error('File comparison state contradicts its digests.');
    }
  }
  return true;
}

export async function digestBytes(bytes) {
  if (!(bytes instanceof ArrayBuffer) && !ArrayBuffer.isView(bytes)) throw new TypeError('Hashing requires raw bytes.');
  if (!globalThis.crypto?.subtle) throw new Error('SHA-256 requires a browser with Web Crypto over HTTPS or localhost.');
  const digest = new Uint8Array(await globalThis.crypto.subtle.digest('SHA-256', bytes));
  return [...digest].map((byte) => byte.toString(16).padStart(2, '0')).join('');
}

export async function hashBytes(bytes, expected = null) {
  // Parse before reading/hashing so malformed expectations never become comparisons.
  const expectedHex = expected === null ? null : parseExpected(expected);
  const hex = await digestBytes(bytes);
  return makeReceipt(hex, expectedHex === null ? 'hashed' : hex === expectedHex ? 'match' : 'mismatch', expectedHex);
}
