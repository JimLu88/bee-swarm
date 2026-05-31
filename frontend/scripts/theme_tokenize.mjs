// v7 Wave2 一次性运维脚本: 把组件里硬编码深色 → CSS 令牌 var(--xxx).
// 用法: node scripts/theme_tokenize.mjs  (跑完手动 npx tsc --noEmit 校验)
import { readFileSync, writeFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

const ROOT = "components/v2";

const RULES = [
  // ---- 遮罩 overlay (深色半透明黑 0.4-0.7) ----
  [/background:\s*"rgba\(0,\s*0,\s*0,\s*0\.[4-7]\d*\)"/g, 'background: "var(--overlay)"'],
  // ---- 深色 surface 十六进制 ----
  [/"#0f0f12"/g, '"var(--bg-card)"'],
  [/"#0a0a0c"/g, '"var(--bg)"'],
  [/"#0a0a0a"/g, '"var(--bg)"'],
  [/"#14141a"/g, '"var(--bg-elev)"'],
  [/"#15151a"/g, '"var(--bg-elev)"'],
  [/"#1a1a1e"/g, '"var(--bg-card)"'],
  [/"#1a1a1f"/g, '"var(--bg-card)"'],
  // ---- 主文字 (浅色字 → 令牌) ----
  [/(color:\s*)"#ffffff"/g, '$1"var(--text)"'],
  [/(color:\s*)"#fff"/g, '$1"var(--text)"'],
  [/(color:\s*)"#ededed"/g, '$1"var(--text)"'],
  [/(color:\s*)"#f5f5f5"/g, '$1"var(--text)"'],
  [/(color:\s*)"#eee"/g, '$1"var(--text)"'],
  [/(color:\s*)"#e0e0e0"/g, '$1"var(--text-dim)"'],
  [/(color:\s*)"#ddd"/g, '$1"var(--text-dim)"'],
  [/(color:\s*)"#ccc"/g, '$1"var(--text-dim)"'],
  [/(color:\s*)"#bbb"/g, '$1"var(--text-dim)"'],
  [/(color:\s*)"#bbbbbb"/g, '$1"var(--text-dim)"'],
  [/(color:\s*)"#aaa"/g, '$1"var(--text-dim)"'],
  [/(color:\s*)"#999"/g, '$1"var(--text-faint)"'],
  [/(color:\s*)"#888"/g, '$1"var(--text-faint)"'],
  [/(color:\s*)"#888888"/g, '$1"var(--text-faint)"'],
  [/(color:\s*)"#777"/g, '$1"var(--text-faint)"'],
  [/(color:\s*)"#666"/g, '$1"var(--text-faint)"'],
  // ---- 边框/分隔 (白色半透明) ----
  [/rgba\(255,\s*255,\s*255,\s*0\.18\)/g, 'var(--border-strong)'],
  [/rgba\(255,\s*255,\s*255,\s*0\.2\d*\)/g, 'var(--border-strong)'],
  [/rgba\(255,\s*255,\s*255,\s*0\.1[0-9]?\)/g, 'var(--border)'],
  // ---- 浅背景 (白色极低透明) ----
  [/rgba\(255,\s*255,\s*255,\s*0\.0[1-5]\)/g, 'var(--bg-subtle)'],
  [/rgba\(255,\s*255,\s*255,\s*0\.0[6-9]\)/g, 'var(--bg-hover)'],
  // ---- 强调蓝 #90caf9 → info (浅蓝白底看不清) ----
  [/"#90caf9"/g, '"var(--info)"'],
  [/rgba\(144,\s*202,\s*249,\s*0\.\d+\)/g, 'var(--info-bg)'],
  // ---- 强调黄 #facc15 → accent (黄字白底看不清) ----
  [/"#facc15"/g, '"var(--accent)"'],
  [/rgba\(250,\s*204,\s*21,\s*0\.\d+\)/g, 'var(--accent-bg)'],
  // ---- 深色内嵌底 rgba(0,0,0,0.15-0.3) → bg-subtle (输入框/代码块, 白底下变黑) ----
  [/background:\s*"rgba\(0,\s*0,\s*0,\s*0\.(1[5-9]|2\d?|3)\)"/g, 'background: "var(--bg-subtle)"'],
  // ---- 扫漏的浅灰字 (白底看不清) → text / text-dim ----
  [/(color:\s*)"#f0f0f0"/g, '$1"var(--text)"'],
  [/(color:\s*)"#d0d0d0"/g, '$1"var(--text-dim)"'],
  [/(color:\s*)"#c8c8c8"/g, '$1"var(--text-dim)"'],
];

function walk(dir) {
  let out = [];
  for (const f of readdirSync(dir)) {
    const p = join(dir, f);
    const s = statSync(p);
    if (s.isDirectory()) out = out.concat(walk(p));
    else if (f.endsWith(".tsx")) out.push(p);
  }
  return out;
}

let changed = 0;
for (const file of walk(ROOT)) {
  const orig = readFileSync(file, "utf8");
  let next = orig;
  for (const [re, rep] of RULES) next = next.replace(re, rep);
  if (next !== orig) { writeFileSync(file, next, "utf8"); changed++; console.log("tokenized:", file); }
}
console.log(`\nDone. ${changed} files changed.`);
