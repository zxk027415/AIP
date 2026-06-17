/**
 * Removes duplicate keys from ZH_EN_MAP in dataTranslation.ts (keeps last occurrence).
 * Run: node scripts/dedupe-zh-en-map.mjs
 */
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const filePath = path.join(__dirname, '../src/utils/dataTranslation.ts');
let s = fs.readFileSync(filePath, 'utf8');

const startMarker = 'const ZH_EN_MAP: Record<string, string> = {';
const spreadMarker = '\n  ...WORKFLOW_OPERATOR_ZH_EN,';
const i0 = s.indexOf(startMarker);
if (i0 === -1) throw new Error('start marker not found');
const i1 = s.indexOf(spreadMarker, i0);
if (i1 === -1) throw new Error('spread marker not found');

const before = s.slice(0, i0 + startMarker.length);
const body = s.slice(i0 + startMarker.length, i1);
const after = s.slice(i1);

const lines = body.split('\n');
const keyRe = /^(\s*)'((?:\\.|[^'\\])*)':\s*/;

/** @type {Map<string, number>} last line index for each key */
const lastIdx = new Map();
lines.forEach((line, idx) => {
  const m = line.match(keyRe);
  if (m) lastIdx.set(m[2], idx);
});

const outLines = lines.filter((line, idx) => {
  const m = line.match(keyRe);
  if (!m) return true;
  return lastIdx.get(m[2]) === idx;
});

const newBody = outLines.join('\n');
fs.writeFileSync(filePath, before + newBody + after, 'utf8');
console.log('dedupe done:', filePath, 'lines', lines.length, '->', outLines.length);
