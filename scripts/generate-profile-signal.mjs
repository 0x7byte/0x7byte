import { writeFile, mkdir } from "node:fs/promises";

const username = "0x7byte";
const apiHeaders = {
  Accept: "application/vnd.github+json",
  "User-Agent": "0x7byte-profile-signal",
};

const escapeXml = (value) => String(value)
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&apos;");

async function getJson(url) {
  const response = await fetch(url, { headers: apiHeaders });
  if (!response.ok) {
    throw new Error(`GitHub public API returned ${response.status} for ${url}`);
  }
  return response.json();
}

const account = await getJson(`https://api.github.com/users/${username}`);
const repositories = await getJson(`https://api.github.com/users/${username}/repos?type=owner&sort=updated&per_page=100`);
const activeRepositories = repositories.filter((repository) => !repository.fork && !repository.archived);
const latest = activeRepositories[0] ?? { name: "—", language: "C", updated_at: new Date().toISOString() };
const fractalTree = activeRepositories.find((repository) => repository.name === "fractal_tree") ?? latest;
const languages = [...new Set(activeRepositories.map((repository) => repository.language).filter(Boolean))]
  .slice(0, 3)
  .join("  ·  ") || "C";
const updatedDate = new Intl.DateTimeFormat("en", { month: "short", day: "2-digit", year: "numeric", timeZone: "UTC" })
  .format(new Date(latest.updated_at));

const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="900" height="228" viewBox="0 0 900 228" role="img" aria-labelledby="title desc">
  <title id="title">0x7byte live build signal</title>
  <desc id="desc">A live public-data summary of 0x7byte GitHub work.</desc>
  <defs>
    <linearGradient id="line" x1="0" x2="1">
      <stop offset="0%" stop-color="#22d3ee"/>
      <stop offset="55%" stop-color="#a78bfa"/>
      <stop offset="100%" stop-color="#22d3ee"/>
    </linearGradient>
  </defs>
  <rect width="900" height="228" rx="14" fill="#0d1117"/>
  <rect x="0" y="0" width="900" height="4" fill="url(#line)"/>
  <text x="36" y="47" fill="#22d3ee" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="15" font-weight="700" letter-spacing="2">LIVE BUILD SIGNAL</text>
  <text x="36" y="82" fill="#f8fafc" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="24" font-weight="700">${escapeXml(fractalTree.name)}</text>
  <text x="36" y="110" fill="#94a3b8" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="14">current featured build  /  ${escapeXml(fractalTree.language ?? "C")}</text>
  <line x1="36" y1="136" x2="864" y2="136" stroke="#263244"/>
  <text x="36" y="171" fill="#a78bfa" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="13" font-weight="700">PUBLIC REPOS</text>
  <text x="36" y="202" fill="#f8fafc" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="24" font-weight="700">${account.public_repos}</text>
  <text x="244" y="171" fill="#a78bfa" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="13" font-weight="700">ACTIVE LANGUAGES</text>
  <text x="244" y="202" fill="#f8fafc" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="15" font-weight="700">${escapeXml(languages)}</text>
  <text x="634" y="171" fill="#a78bfa" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="13" font-weight="700">LATEST UPDATE</text>
  <text x="634" y="202" fill="#f8fafc" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="15" font-weight="700">${escapeXml(updatedDate)}</text>
</svg>`;

await mkdir("assets", { recursive: true });
await writeFile("assets/live-build.svg", svg, "utf8");
