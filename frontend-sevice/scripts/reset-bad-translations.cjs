// @AI_GENERATED
const fs = require('fs');
const transFile = 'AIP-service/frontend/src/utils/dataTranslation.ts';
let c = fs.readFileSync(transFile, 'utf8');
const hasChinese = /[\u4e00-\u9fff]/;

// For entries where value still has Chinese AND key !== value,
// reset value to key so td() returns original Chinese as fallback
let fixes = 0;
c = c.replace(/  '([^']+)':\s*'([^']+)',/g, (match, key, value) => {
  if (hasChinese.test(value) && key !== value) {
    fixes++;
    return "  '" + key + "': '" + key + "',";
  }
  return match;
});

fs.writeFileSync(transFile, c, 'utf8');
console.log('Reset ' + fixes + ' entries to key=value');
// @AI_GENERATED: end
