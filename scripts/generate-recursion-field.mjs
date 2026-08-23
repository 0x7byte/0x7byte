import { mkdir, writeFile } from "node:fs/promises";

const sourceUrl = "https://raw.githubusercontent.com/0x7byte/fractal_tree/main/fractal_tree.c";

async function loadTreeConstants() {
  try {
    const response = await fetch(sourceUrl, { headers: { "User-Agent": "0x7byte-profile-recursion-field" } });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const code = await response.text();
    return {
      angle: code.match(/#define\s+BRANCH_ANGLE\s+(\d+)/)?.[1] ?? "20",
      thickness: code.match(/#define\s+THIKNESS\s+(\d+)/)?.[1] ?? "20",
      source: "LIVE SOURCE",
    };
  } catch {
    return { angle: "20", thickness: "20", source: "SOURCE SNAPSHOT" };
  }
}

function branch(x, y, length, angle, depth, maxDepth, segments) {
  const endX = x + Math.sin(angle) * length;
  const endY = y - Math.cos(angle) * length;
  const ratio = depth / maxDepth;
  const hue = Math.round(192 + ratio * 70);
  const width = Math.max(0.7, 5.5 * (1 - ratio));
  const opacity = 0.5 + ratio * 0.45;
  segments.push(`<line x1="${x.toFixed(2)}" y1="${y.toFixed(2)}" x2="${endX.toFixed(2)}" y2="${endY.toFixed(2)}" stroke="hsl(${hue} 92% 66%)" stroke-width="${width.toFixed(2)}" stroke-linecap="round" opacity="${opacity.toFixed(2)}"/>`);
  if (depth >= maxDepth) {
    segments.push(`<circle cx="${endX.toFixed(2)}" cy="${endY.toFixed(2)}" r="1.8" fill="#d8b4fe" opacity="0.9"/>`);
    return;
  }
  const nextLength = length * 0.69;
  branch(endX, endY, nextLength, angle - 0.37, depth + 1, maxDepth, segments);
  branch(endX, endY, nextLength, angle + 0.37, depth + 1, maxDepth, segments);
}

const constants = await loadTreeConstants();
const segments = [];
branch(450, 301, 94, 0, 0, 8, segments);

const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="900" height="390" viewBox="0 0 900 390" role="img" aria-labelledby="title description">
  <title id="title">0x7byte recursion field</title>
  <desc id="description">A recursive tree derived from the public Fractal Tree C project.</desc>
  <defs>
    <linearGradient id="border" x1="0" y1="0" x2="1" y2="0"><stop stop-color="#22d3ee"/><stop offset="0.5" stop-color="#a78bfa"/><stop offset="1" stop-color="#22d3ee"/></linearGradient>
    <radialGradient id="bloom" cx="50%" cy="76%" r="58%"><stop stop-color="#312e81" stop-opacity="0.78"/><stop offset="0.54" stop-color="#161b2f" stop-opacity="0.46"/><stop offset="1" stop-color="#0d1117" stop-opacity="0"/></radialGradient>
    <pattern id="grid" width="36" height="36" patternUnits="userSpaceOnUse"><path d="M 36 0 L 0 0 0 36" fill="none" stroke="#243044" stroke-width="0.55" opacity="0.56"/></pattern>
    <filter id="glow" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="5" result="blur"/><feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
  </defs>
  <rect width="900" height="390" rx="14" fill="#0d1117"/>
  <rect width="900" height="390" rx="14" fill="url(#grid)"/>
  <rect width="900" height="390" rx="14" fill="url(#bloom)"/>
  <rect x="0" y="0" width="900" height="4" fill="url(#border)"/>
  <text x="34" y="42" fill="#22d3ee" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="15" font-weight="700" letter-spacing="2">THE RECURSION FIELD</text>
  <text x="34" y="67" fill="#94a3b8" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="13">fractal_tree.c  //  C + raylib  //  ${constants.source}</text>
  <g filter="url(#glow)">${segments.join("")}</g>
  <line x1="93" y1="322" x2="807" y2="322" stroke="#27364f" stroke-width="1"/>
  <text x="94" y="351" fill="#a78bfa" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="13" font-weight="700">DEPTH 08</text>
  <text x="355" y="351" fill="#a78bfa" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="13" font-weight="700">ANGLE ${constants.angle}°</text>
  <text x="594" y="351" fill="#a78bfa" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="13" font-weight="700">TRUNK ${constants.thickness}px</text>
  <text x="94" y="374" fill="#d8b4fe" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="12">one function → two branches → a system that grows</text>
</svg>`;

await mkdir("assets", { recursive: true });
await writeFile("assets/recursion-field.svg", svg, "utf8");
