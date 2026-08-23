import { mkdir, writeFile } from "node:fs/promises";

const username = "0x7byte";
const formatDate = (value) => new Intl.DateTimeFormat("en", {
  month: "short",
  day: "2-digit",
  timeZone: "UTC",
}).format(new Date(value));
const escapeXml = (value) => String(value)
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&apos;");
const truncate = (value, limit) => value.length > limit ? `${value.slice(0, limit - 1)}…` : value;

async function loadEvents() {
  try {
    const response = await fetch(`https://api.github.com/users/${username}/events/public?per_page=100`, {
      headers: { Accept: "application/vnd.github+json", "User-Agent": "0x7byte-profile-activity" },
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const events = await response.json();
    const lines = [];
    for (const event of events) {
      if (event.type === "PushEvent") {
        const commit = event.payload?.commits?.at(-1);
        lines.push({
          date: formatDate(event.created_at),
          repo: event.repo?.name?.replace(`${username}/`, "") ?? "repository",
          message: commit?.message?.split("\n")[0] ?? "pushed updates",
        });
      } else if (event.type === "CreateEvent" && event.payload?.ref_type === "repository") {
        lines.push({ date: formatDate(event.created_at), repo: event.repo?.name?.replace(`${username}/`, "") ?? "repository", message: "created repository" });
      }
      if (lines.length === 4) break;
    }
    return lines.length ? lines : [{ date: "LIVE", repo: username, message: "public activity will appear here" }];
  } catch {
    return [{ date: "LIVE", repo: username, message: "public activity feed refreshes daily" }];
  }
}

const lines = await loadEvents();
const rowHeight = 38;
const height = 105 + lines.length * rowHeight;
const rows = lines.map((line, index) => {
  const y = 88 + index * rowHeight;
  return `<text x="34" y="${y}" fill="#a78bfa" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="13" font-weight="700">${escapeXml(line.date)}</text>
  <text x="146" y="${y}" fill="#22d3ee" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="13" font-weight="700">${escapeXml(truncate(line.repo, 26))}</text>
  <text x="382" y="${y}" fill="#cbd5e1" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="13">${escapeXml(truncate(line.message, 58))}</text>`;
}).join("\n");

const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="900" height="${height}" viewBox="0 0 900 ${height}" role="img" aria-labelledby="title description">
  <title id="title">0x7byte public activity tape</title>
  <desc id="description">Recent public GitHub activity for 0x7byte, refreshed automatically.</desc>
  <defs><linearGradient id="line" x1="0" x2="1"><stop stop-color="#22d3ee"/><stop offset="0.5" stop-color="#a78bfa"/><stop offset="1" stop-color="#22d3ee"/></linearGradient></defs>
  <rect width="900" height="${height}" rx="12" fill="#0d1117"/>
  <rect width="900" height="3" fill="url(#line)"/>
  <text x="34" y="40" fill="#22d3ee" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="15" font-weight="700" letter-spacing="2">PUBLIC ACTIVITY // LATEST</text>
  <text x="34" y="62" fill="#64748b" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="12">GitHub events · refreshed by the daily profile job</text>
  <line x1="34" y1="72" x2="866" y2="72" stroke="#263244"/>
  ${rows}
</svg>`;

await mkdir("assets", { recursive: true });
await writeFile("assets/public-activity.svg", svg, "utf8");
