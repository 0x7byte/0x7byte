import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";

const username = "0x7byte";
const outputDir = resolve(process.cwd(), "assets");
const apiHeaders = { "Accept": "application/vnd.github+json", "User-Agent": "0x7byte-profile-observatory" };

function escapeXml(value) {
  return String(value).replace(/[<>&'\"]/g, (character) => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;", "'": "&apos;", '"': "&quot;" })[character]);
}
function shortDate(value) { return new Intl.DateTimeFormat("en", { month: "short", day: "2-digit", year: "numeric", timeZone: "UTC" }).format(new Date(value)); }
function truncate(value, length = 30) { return value.length > length ? `${value.slice(0, length - 1)}…` : value; }
function card({ dark, repos, followers, latest, updatedAt }) {
  const colors = dark ? { bg: "#080E1A", panel: "#0E1A2D", stroke: "#263B5D", accent: "#7DD3FC", accent2: "#A78BFA", text: "#F8FAFC", muted: "#A8B7CC", grid: "#10203A", pill: "#132747" } : { bg: "#F8FAFC", panel: "#FFFFFF", stroke: "#D7E0EC", accent: "#0369A1", accent2: "#6D28D9", text: "#0B1220", muted: "#4B5D75", grid: "#E7EEF7", pill: "#EEF6FF" };
  const latestLabel = latest ? `${truncate(latest.name)} · ${shortDate(latest.updated_at)}` : "No public repository activity yet";
  const updatedLabel = shortDate(updatedAt);
  return `<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="248" viewBox="0 0 1100 248" role="img" aria-label="0x7byte Engineering Observatory — live public GitHub profile summary">
  <defs><pattern id="grid" width="24" height="24" patternUnits="userSpaceOnUse"><path d="M 24 0 L 0 0 0 24" fill="none" stroke="${colors.grid}" stroke-width="1"/></pattern><filter id="shadow" x="-10%" y="-20%" width="120%" height="140%"><feDropShadow dx="0" dy="8" stdDeviation="12" flood-color="#000000" flood-opacity="${dark ? "0.28" : "0.10"}"/></filter></defs>
  <rect width="1100" height="248" rx="20" fill="${colors.bg}"/><rect width="1100" height="248" rx="20" fill="url(#grid)" opacity="0.8"/>
  <rect x="24" y="24" width="1052" height="200" rx="16" fill="${colors.panel}" stroke="${colors.stroke}" filter="url(#shadow)"/>
  <rect x="48" y="49" width="56" height="56" rx="14" fill="${colors.pill}" stroke="${colors.stroke}"/><text x="76" y="84" text-anchor="middle" font-family="Courier New, monospace" font-weight="800" font-size="20" fill="${colors.accent}">0x</text>
  <text x="126" y="70" font-family="Courier New, monospace" font-weight="800" font-size="20" fill="${colors.text}">0X7BYTE // ENGINEERING OBSERVATORY</text>
  <text x="126" y="94" font-family="Arial, Helvetica, sans-serif" font-size="13" fill="${colors.muted}">A public, automatically refreshed record of systems work and AI-engineering progress.</text>
  <rect x="876" y="48" width="150" height="28" rx="14" fill="${colors.pill}" stroke="${colors.stroke}"/><circle cx="895" cy="62" r="5" fill="${colors.accent2}"/><text x="909" y="67" font-family="Courier New, monospace" font-size="11" font-weight="700" fill="${colors.text}">AUTO · DAILY</text>
  <line x1="48" y1="128" x2="1052" y2="128" stroke="${colors.stroke}"/>
  <text x="48" y="151" font-family="Courier New, monospace" font-size="11" font-weight="700" fill="${colors.muted}">PUBLIC REPOSITORIES</text><text x="48" y="184" font-family="Arial, Helvetica, sans-serif" font-size="29" font-weight="800" fill="${colors.text}">${repos}</text>
  <text x="224" y="151" font-family="Courier New, monospace" font-size="11" font-weight="700" fill="${colors.muted}">FOLLOWERS</text><text x="224" y="184" font-family="Arial, Helvetica, sans-serif" font-size="29" font-weight="800" fill="${colors.text}">${followers}</text>
  <text x="400" y="151" font-family="Courier New, monospace" font-size="11" font-weight="700" fill="${colors.muted}">LATEST PUBLIC UPDATE</text><text x="400" y="177" font-family="Arial, Helvetica, sans-serif" font-size="16" font-weight="700" fill="${colors.text}">${escapeXml(latestLabel)}</text>
  <text x="400" y="201" font-family="Courier New, monospace" font-size="11" fill="${colors.muted}">refreshed ${updatedLabel} · public GitHub data only</text>
  </svg>`;
}

const [profileResponse, repositoryResponse] = await Promise.all([
  fetch(`https://api.github.com/users/${username}`, { headers: apiHeaders }),
  fetch(`https://api.github.com/users/${username}/repos?per_page=100&sort=updated`, { headers: apiHeaders }),
]);
if (!profileResponse.ok || !repositoryResponse.ok) throw new Error(`GitHub public API request failed: profile=${profileResponse.status}, repositories=${repositoryResponse.status}`);
const profile = await profileResponse.json(); const repositories = await repositoryResponse.json();
const latest = repositories.filter((repository) => !repository.fork).sort((a, b) => new Date(b.updated_at) - new Date(a.updated_at))[0];
const publicRepositoryCount = repositories.filter((repository) => !repository.fork).length;
const now = new Date().toISOString();
await mkdir(outputDir, { recursive: true });
await Promise.all([
  writeFile(resolve(outputDir, "observatory-light.svg"), card({ dark: false, repos: publicRepositoryCount, followers: profile.followers, latest, updatedAt: now })),
  writeFile(resolve(outputDir, "observatory-dark.svg"), card({ dark: true, repos: publicRepositoryCount, followers: profile.followers, latest, updatedAt: now })),
]);
console.log(`Generated profile observatory assets for ${username} at ${now}`);
