import { ALPHABET, HEX, encode, parseExpected, hashBytes, makeReceipt } from './glyph-sha256.mjs';
const DEEPSEEK = 'c24a170c1d3871ec526ff7a56be34096f5467f0e7a9fa4438d10768acc907480';
const COLORS = ['#d9a95b','#6fb3a8','#9c7bb0','#c98a7a','#e7d3a8','#8fb6d9','#b6a37c','#7fa77a','#d98fb0','#a8c7a0','#c7b3e6','#e0b070','#78a0a0','#b08a6a','#9fb0c8','#efe6da'];
const field = document.getElementById('fingerprint');
const status = document.getElementById('status');
const fileButton = document.getElementById('verify-file');
const form = document.getElementById('codec-form');
let receipt = makeReceipt(DEEPSEEK);
let busy = false;

function message(text, state = 'ok') { status.textContent = text; status.dataset.state = state; }
function render(value) {
  receipt = value;
  const grid = document.getElementById('tile');
  grid.replaceChildren();
  for (const digit of value.hex_sha256) {
    const n = HEX.indexOf(digit);
    const cell = document.createElement('span');
    cell.textContent = ALPHABET[n]; cell.title = digit; cell.style.color = COLORS[n];
    grid.appendChild(cell);
  }
  grid.setAttribute('aria-label', `SHA-256 glyph fingerprint for ${value.hex_sha256}`);
  document.getElementById('hex-result').textContent = value.hex_sha256;
  document.getElementById('receipt').textContent = JSON.stringify(value, null, 2);
}

form.addEventListener('submit', (event) => {
  event.preventDefault();
  if (busy) return;
  try {
    const hex = parseExpected(field.value);
    field.value = encode(hex);
    render(makeReceipt(hex));
    message('Digest encoding round-trip verified. File verification has not been run.');
  } catch (error) { message(error.message, 'error'); }
});

fileButton.addEventListener('click', async () => {
  if (busy) return;
  try {
    const input = document.getElementById('local-file');
    const file = input.files[0];
    if (!file) throw new Error('Choose a file to verify.');
    if (file.size > 128 * 1024 * 1024) throw new Error('This file exceeds the 128 MiB browser limit. Use the streaming Python verifier for this backup.');
    const expected = field.value.replace(/[ \t\r\n]/g, '') === '' ? null : parseExpected(field.value);
    busy = true; fileButton.disabled = true; form.querySelector('button').disabled = true;
    field.disabled = true; input.disabled = true;
    message('Reading and hashing the selected bytes on this device…');
    const result = await hashBytes(await file.arrayBuffer(), expected);
    render(result);
    if (result.file_verification === 'match') message('File verified locally. Its SHA-256 matches the expected fingerprint.');
    else if (result.file_verification === 'mismatch') message('File mismatch. The fingerprint shown is the actual SHA-256 of the selected bytes.', 'mismatch');
    else message('File hashed locally. Enter an expected fingerprint to verify a match.');
  } catch (error) { message(error.message, 'error'); }
  finally {
    busy = false; fileButton.disabled = false; form.querySelector('button').disabled = false;
    field.disabled = false; document.getElementById('local-file').disabled = false;
  }
});

document.addEventListener('click', async (event) => {
  const button = event.target.closest('button[data-copy]');
  if (!button) return;
  const text = button.dataset.copy === 'tile' ? receipt.glyph_tile
    : button.dataset.copy === 'hex' ? receipt.hex_sha256 : JSON.stringify(receipt, null, 2);
  try { await navigator.clipboard.writeText(text); message(`Copied ${button.dataset.copy}.`); }
  catch { message('Clipboard access is unavailable. Select the displayed result and copy it.', 'error'); }
});

for (let i = 0; i < 16; i++) {
  const cell = document.createElement('span');
  const symbol = document.createElement('b');
  symbol.textContent = ALPHABET[i]; symbol.style.color = COLORS[i];
  cell.append(symbol, document.createTextNode(HEX[i]));
  document.getElementById('legend').appendChild(cell);
}
const query = new URLSearchParams(location.search).get('digest');
try {
  const hex = query === null ? DEEPSEEK : parseExpected(query);
  field.value = encode(hex); render(makeReceipt(hex));
  message('Digest encoding round-trip verified. File verification has not been run.');
} catch (error) { field.value = encode(DEEPSEEK); render(receipt); message(error.message, 'error'); }
