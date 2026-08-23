import { mkdir, writeFile } from "node:fs/promises";

const owner = "0x7byte";
const repository = "fractal_tree";
const endpoint = `https://api.github.com/repos/${owner}/${repository}`;

const response = await fetch(endpoint, {
  headers: {
    Accept: "application/vnd.github+json",
    "User-Agent": "0x7byte-profile-refresh",
  },
});

if (!response.ok) {
  throw new Error(`Could not read public project data: ${response.status}`);
}

const project = await response.json();
const updated = new Intl.DateTimeFormat("en", {
  day: "2-digit",
  month: "short",
  year: "numeric",
  timeZone: "UTC",
}).format(new Date(project.updated_at));

const themes = {
  light: { background: "#ffffff", border: "#d0d7de", text: "#1f2328", muted: "#57606a", accent: "#0969da" },
  dark: { background: "#0d1117", border: "#30363d", text: "#f0f6fc", muted: "#8b949e", accent: "#58a6ff" },
};

function escapeXml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&apos;");
}

function render(theme) {
  const values = themes[theme];
  return `<svg xmlns="http://www.w3.org/2000/svg" width="880" height="146" viewBox="0 0 880 146" role="img" aria-labelledby="title desc">
  <title id="title">Featured public project</title>
  <desc id="desc">Current public project signal for ${escapeXml(project.name)}.</desc>
  <rect x="0.5" y="0.5" width="879" height="145" rx="8" fill="${values.background}" stroke="${values.border}"/>
  <circle cx="36" cy="38" r="7" fill="${values.accent}"/>
  <text x="54" y="43" fill="${values.muted}" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="15" font-weight="600" letter-spacing="1.5">FEATURED PUBLIC PROJECT</text>
  <text x="29" y="86" fill="${values.text}" font-family="ui-monospace,SFMono-Regular,Menlo,monospace" font-size="25" font-weight="700">${escapeXml(project.name)}</text>
  <text x="29" y="119" fill="${values.muted}" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="16">${escapeXml(project.language || "C")} · source updated ${escapeXml(updated)}</text>
  <text x="705" y="86" fill="${values.accent}" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="16" font-weight="600">open source ↗</text>
</svg>`;
}

await mkdir("assets", { recursive: true });
await Promise.all(
  Object.keys(themes).map((theme) =>
    writeFile(`assets/project-signal-${theme}.svg`, render(theme)),
  ),
);
