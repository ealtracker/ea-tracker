// Pulls the Elite Academy League schedule and standings from Modular11's public pages
// and writes data/raw.json. Same parsing as the original in-browser pull.
import { DOMParser } from 'linkedom';
import { writeFileSync } from 'node:fs';

const BASE = 'https://www.modular11.com';
const UA = process.env.EA_UA || 'EA-Tracker (independent fan site; daily public data refresh)';
const SEASON = { event: 27, start: '2026-07-01 00:00:00', end: '2027-07-31 23:59:59' };
const BRACKETS = [47, 51, 48]; // EA, EA National, EA2
const AGES = { 20: 'U11', 17: 'U12', 21: 'U13', 22: 'U14', 33: 'U15', 14: 'U16', 15: 'U17', 26: 'U19' };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const clean = s => (s || '').replace(/ /g, ' ').replace(/\s+/g, ' ').trim();
const acad = s => { const m = (s || '').match(/\/academy\/(\d+)\/[^'")]+/); return m ? { a: +m[1], c: m[0] } : null; };
const parse = t => new DOMParser().parseFromString('<!doctype html><html><body>' + t + '</body></html>', 'text/html');

async function get(path, tries = 5) {
  for (let i = 0; i < tries; i++) {
    try {
      const r = await fetch(BASE + path, { headers: { 'User-Agent': UA, 'X-Requested-With': 'XMLHttpRequest' } });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return await r.text();
    } catch (e) {
      if (i === tries - 1) throw new Error(path + ' -> ' + e.message);
      await sleep(2000 * (i + 1));
    }
  }
}

const matchesUrl = (b, page) => '/public_schedule/league/get_matches?' + new URLSearchParams({
  open_page: page, academy: 0, tournament: SEASON.event, gender: 0, age: '', brackets: b, groups: '', group: '',
  match_number: 0, status: 'all', match_type: 2, schedule: 0, team: 0, location: 0, as_referee: 0,
  report_status: 0, match_status: 0, start_date: SEASON.start, end_date: SEASON.end }).toString();

export function parseRow(x) {
  const c = x.querySelectorAll(':scope > div');
  const idg = clean(c[0]?.textContent).split(' ');
  const det = c[1];
  const loc = det?.querySelector('.container-location p');
  const dt = clean(det?.childNodes[0]?.textContent);
  const href = det?.querySelector('a')?.getAttribute('href') || '';
  const q = href.match(/query=([-\d.]+),([-\d.]+)/);
  const imgs = [...x.querySelectorAll('.container-teams-info .club-photo')].map(e => acad(e.getAttribute('style')));
  const sc = x.querySelector('.score-match-table');
  return { id: +idg[0], g: idg[1], dt, v: loc?.getAttribute('data-title') || null, lat: q ? +q[1] : null, lng: q ? +q[2] : null,
    age: clean(c[2]?.textContent), b: x.getAttribute('js-match-bracket'), d: x.getAttribute('js-match-group'),
    dh: x.getAttribute('js-match-group_home'), da: x.getAttribute('js-match-group_away'),
    r: x.getAttribute('js-match-round'), gm: x.getAttribute('js-match-game'),
    h: x.querySelector('.container-first-team p')?.getAttribute('data-title'),
    a: x.querySelector('.container-second-team p')?.getAttribute('data-title'),
    ha: imgs[0], aa: imgs[1], s: clean(sc?.textContent || x.querySelector('[js-score-block]')?.textContent) };
}
export function parseMatchesPage(t) {
  const d = parse(t);
  const m = (d.querySelector('.current-pages')?.textContent || '').match(/(\d+) page out of (\d+)/);
  return { page: m ? +m[1] : null, pages: m ? +m[2] : 1, rows: [...d.querySelectorAll('.table-content-row.hidden-xs')].map(parseRow) };
}
export function parseStandings(t, b, age) {
  const d = parse(t);
  const ids = {};
  for (const m of t.matchAll(/matchLists\['(division\d+)'\]\s*=\s*\{\s*paginationData:\s*\[([^\]]*)\]/g)) ids[m[1]] = m[2].trim();
  const out = [];
  d.querySelectorAll('.container-table-standing').forEach(block => {
    const div = clean(block.querySelector('.container-group-text p')?.getAttribute('data-title'));
    block.querySelectorAll('.form_row.main_row').forEach(r => {
      const [left, right] = r.querySelectorAll('.subrow');
      const ac = acad(left.querySelector('img')?.getAttribute('src'));
      out.push({ b, age, div, grp: r.getAttribute('js-group'), tid: ids[r.getAttribute('row')],
        rank: clean(left.querySelector('.container-rank')?.textContent),
        n: left.querySelector('.container-team-info p')?.getAttribute('data-title'),
        nums: [...right.children].map(c => clean(c.textContent)), ac: ac?.a, c: ac?.c });
    });
  });
  return out;
}

async function main() {
  const matches = [], standings = [], pages = {};
  const report = { pulledAt: new Date().toISOString(), tables: [] };
  for (const b of BRACKETS) {
    const first = parseMatchesPage(await get(matchesUrl(b, 1)));
    pages[b] = first.pages; matches.push(...first.rows);
    for (let p = 2; p <= first.pages; p++) {
      const r = parseMatchesPage(await get(matchesUrl(b, p)));
      if (r.page !== p) throw new Error(`bracket ${b}: asked for page ${p}, got ${r.page}`);
      matches.push(...r.rows);
      await sleep(250);
    }
    for (const a of Object.keys(AGES)) {
      const t = await get(`/public_schedule/league/get_teams?tournament_type=league&UID_age=${a}&UID_gender=3&UID_event=${SEASON.event}&list_type=${b}`);
      const rows = parseStandings(t, b, AGES[a]);
      standings.push(...rows);
      report.tables.push({ bracket: b, age: AGES[a], rows: rows.length, bytes: t.length, ...(rows.length ? {} : { sample: t.replace(/\s+/g, ' ').slice(0, 1500) }) });
      await sleep(250);
    }
    console.log(`bracket ${b}: ${pages[b]} pages`);
  }
  const unique = new Set(matches.map(m => m.id)).size;
  if (unique !== matches.length) throw new Error(`duplicate matches: ${matches.length} rows, ${unique} unique`);
  const bad = matches.filter(m => !/^\d+ : \d+$|^TBD$/.test(m.s) || !m.id || !m.h || !m.a);
  if (bad.length) throw new Error('unreadable match rows: ' + JSON.stringify(bad.slice(0, 3)));
  report.matchesPerBracket = Object.fromEntries(BRACKETS.map(b => [b, matches.filter(m => m.b === ({ 47: 'EA', 51: 'EA National', 48: 'EA2' })[b]).length]));
  writeFileSync('data/pull-report.json', JSON.stringify(report, null, 1));
  writeFileSync(process.argv[2] || 'data/raw.json', JSON.stringify({ pulledAt: new Date().toISOString(), source: 'modular11.com', pages, matches, standings }));
  console.log(`matches ${matches.length}, standings ${standings.length}`);
}
if (process.argv[1] && process.argv[1].endsWith('pull.mjs')) main().catch(e => { console.error(e.message); process.exit(1); });
