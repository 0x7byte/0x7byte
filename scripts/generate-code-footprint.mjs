import { mkdir, writeFile } from "node:fs/promises";

const owner = "0x7byte";
const endpoint = `https://api.github.com/users/${owner}/repos?per_page=100&type=owner`;

const response = await fetch(endpoint, {
  headers: {
    Accept: "application/vnd.github+json",
    "User-Agent": "0x7byte-profile-refresh",
  },
});

if (!response.ok) {
  throw new Error(`Could not read public repository data: ${response.status}`);
}

const repositories = (await response.json())
  .filter((repo) => !repo.fork && repo.name !== owner && repo.language)
  .map((repo) => ({
    name: repo.name,
    language: repo.language,
    size: Math.max(repo.size || 0, 1),
    updatedAt: repo.updated_at,
  }));

if (repositories.length === 0) {
  throw new Error("No public language-tagged repositories were available.");
}

const totalSize = repositories.reduce((sum, repo) => sum + repo.size, 0);
const languageSizes = new Map();
for (const repo of repositories) {
  languageSizes.set(repo.language, (languageSizes.get(repo.language) || 0) + repo.size);
}

const languages = [...languageSizes.entries()]
  .map(([name, size]) => ({ name, size, share: (size / totalSize) * 100 }))
  .sort((a, b) => b.size - a.size)
  .slice(0, 3);

const projects = [...repositories]
  .sort((a, b) => b.size - a.size)
  .slice(0, 4)
  .map((repo) => ({ ...repo, share: (repo.size / totalSize) * 100 }));

const latestUpdate = new Intl.DateTimeFormat("en", {
  day: "2-digit",
  month: "short",
  year: "numeric",
  timeZone: "UTC",
}).format(new Date(Math.max(...repositories.map((repo) => Date.parse(repo.updatedAt)))));

const themes = {
  light: {
    background: "#f6f8fa",
    surface: "#ffffff",
    border: "#d0d7de",
    text: "#1f2328",
    muted: "#57606a",
    accent: "#0969da",
    accentSoft: "#54aeff",
    track: "#eaeef2",
  },
  dark: {
    background: "#0d1117",
    surface: "#161b22",
    border: "#30363d",
    text: "#f0f6fc",
    muted: "#8b949e",
    accent: "#58a6ff",
    accentSoft: "#a5d6ff",
    track: "#21262d",
  },
};

function escapeXml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&apos;");
}

function segmentedBar(x, y, share, color, track) {
  const segments = 22;
  const filled = Math.max(1, Math.round((share / 100) * segments));
  return Array.from({ length: segments }, (_, index) => {
    const fill = index < filled ? color : track;
    return `<rect x="${x + index * 13}" y="${y}" width="9" height="11" rx="2" fill="${fill}"/>`;
  }).join("");
}

function render(theme) {
  const colors = themes[theme];
  const languageRows = languages.map((language, index) => {
    const y = 110 + index * 30;
    return `<text x="30" y="${y + 10}" fill="${colors.text}" font-family="ui-monospace,SFMono-Regular,Menlo,monospace" font-size="14">${escapeXml(language.name)}</text>
      ${segmentedBar(190, y, language.share, colors.accent, colors.track)}
      <text x="510" y="${y + 10}" fill="${colors.muted}" font-family="ui-monospace,SFMono-Regular,Menlo,monospace" font-size="14">${language.share.toFixed(1)}%</text>`;
  }).join("");
  const projectRows = projects.map((project, index) => {
    const y = 235 + index * 23;
    return `<text x="30" y="${y}" fill="${colors.text}" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="14">${escapeXml(project.name)}</text>
      <rect x="310" y="${y - 11}" width="235" height="8" rx="4" fill="${colors.track}"/>
      <rect x="310" y="${y - 11}" width="${Math.max(8, (project.share / 100) * 235)}" height="8" rx="4" fill="${colors.accentSoft}"/>
      <text x="565" y="${y}" fill="${colors.muted}" font-family="ui-monospace,SFMono-Regular,Menlo,monospace" font-size="13">${project.share.toFixed(1)}%</text>`;
  }).join("");
  return `<svg xmlns="http://www.w3.org/2000/svg" width="880" height="350" viewBox="0 0 880 350" role="img" aria-labelledby="title desc">
  <title id="title">Public code footprint</title>
  <desc id="desc">Language distribution and public project volume derived from 0x7byte public repositories.</desc>
  <rect x="0.5" y="0.5" width="879" height="349" rx="9" fill="${colors.surface}" stroke="${colors.border}"/>
  <rect x="1" y="1" width="878" height="56" rx="9" fill="${colors.background}"/>
  <text x="30" y="36" fill="${colors.accent}" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="17" font-weight="700">▥ PUBLIC CODE FOOTPRINT</text>
  <text x="850" y="36" fill="${colors.muted}" text-anchor="end" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="13">source updated ${escapeXml(latestUpdate)}</text>
  <text x="30" y="81" fill="${colors.muted}" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="14">Language mix across ${repositories.length} public source projects</text>
  ${languageRows}
  <line x1="30" y1="208" x2="850" y2="208" stroke="${colors.border}"/>
  <text x="30" y="232" fill="${colors.muted}" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="14">Public project volume</text>
  ${projectRows}
</svg>`;
}

await mkdir("assets", { recursive: true });
await Promise.all(
  Object.keys(themes).map((theme) =>
    writeFile(`assets/code-footprint-${theme}.svg`, render(theme)),
  ),
);
