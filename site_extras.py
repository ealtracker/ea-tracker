"""Extra files built alongside the site on every update:
- calendar subscriptions (.ics) for every team and for each club per competition
- a readable page per club and team (for search engines and link previews); shared links jump into the app
- an A-Z page of all clubs
- sitemap.xml and robots.txt
"""
import os, re, json, html as H, datetime as D

CK = ['ea', 'national', 'ea2']


def slugify(s):
    return re.sub(r'-+', '-', re.sub(r'[^a-z0-9]+', '-', s.lower())).strip('-') or 'club'


def club_slugs(clubs):
    out, used = {}, set()
    for cid, name in sorted(clubs.items(), key=lambda kv: kv[1].lower()):
        s = slugify(name)
        if s in used:
            s = f'{s}-{cid}'
        used.add(s)
        out[cid] = s
    return out


# ---------- calendars ----------
def _esc(s):
    return str(s).replace('\\', '\\\\').replace(';', '\\;').replace(',', '\\,').replace('\n', '\\n')


def _fold(line):
    b = line.encode('utf-8')
    if len(b) <= 75:
        return line
    parts, cur = [], b''
    for ch in line:
        e = ch.encode('utf-8')
        if len(cur) + len(e) > (75 if not parts else 74):
            parts.append(cur.decode('utf-8'))
            cur = b''
        cur += e
    parts.append(cur.decode('utf-8'))
    return '\r\n '.join(parts)


def _cal(name, desc, events):
    L = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//EAL Tracker//Elite Academy League//EN', 'CALSCALE:GREGORIAN',
         'METHOD:PUBLISH', f'X-WR-CALNAME:{_esc(name)}', f'X-WR-CALDESC:{_esc(desc)}',
         'X-PUBLISHED-TTL:PT6H', 'REFRESH-INTERVAL;VALUE=DURATION:PT6H']
    L += events
    L.append('END:VCALENDAR')
    return '\r\n'.join(_fold(l) for l in L) + '\r\n'


def _event(m, teams, venues, comps, site, stamp, prefix='', owner=None):
    mid, when, hi, ai, hs, as_, vi = m
    h, a, v = teams[hi], teams[ai], venues[vi]
    dt = D.datetime.strptime(when, '%Y-%m-%dT%H:%M')
    tbd_time = dt.hour == 0 and dt.minute == 0
    venue = 'Venue TBD' if re.match(r'^\s*TBD\b', v[0] or '', re.I) else v[0]
    if hs is not None:
        summary = f'{prefix}{h[0]} {hs}-{as_} {a[0]} (final)'
    else:
        summary = f'{prefix}{h[0]} vs {a[0]}'
    desc = [f'{comps[h[2]]} {h[3]} · {h[4]}' + (f' v {a[4]}' if a[4] != h[4] else '')]
    if hs is None and tbd_time:
        desc.append('Kickoff time not set by the league yet.')
    elif hs is None:
        desc.append('Kickoff time as listed by the league. End time is an estimate.')
    o = owner if owner is not None else h
    desc.append(f'Match {mid}. Details: {site}#team-{CK[o[2]]}-{o[5]}' if o[5] else f'Match {mid}.')
    E = ['BEGIN:VEVENT', f'UID:match-{mid}@ea-tracker', f'DTSTAMP:{stamp}']
    if tbd_time:
        E += [f'DTSTART;VALUE=DATE:{dt:%Y%m%d}', f'DTEND;VALUE=DATE:{(dt + D.timedelta(days=1)):%Y%m%d}']
    else:
        E += [f'DTSTART:{dt:%Y%m%dT%H%M%S}', f'DTEND:{(dt + D.timedelta(minutes=90)):%Y%m%dT%H%M%S}']
    E += [f'SUMMARY:{_esc(summary)}', f'LOCATION:{_esc(venue)}', f'DESCRIPTION:{_esc(chr(10).join(desc))}', 'TRANSP:OPAQUE']
    if v[1] is not None and venue != 'Venue TBD':
        E.append(f'GEO:{v[1]};{v[2]}')
    E.append('END:VEVENT')
    return E


def write_calendars(data, outdir, site):
    teams, matches, venues, comps, clubs = data['teams'], data['matches'], data['venues'], data['comps'], data['clubs']
    stamp = D.datetime.now(D.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    by_team = {}
    for m in matches:
        for side in (m[2], m[3]):
            by_team.setdefault(side, []).append(m)
    os.makedirs(f'{outdir}/cal', exist_ok=True)
    n = 0
    for i, t in enumerate(teams):
        if not t[5]:
            continue
        ms = sorted(by_team.get(i, []), key=lambda m: (m[1], m[0]))
        ev = []
        for m in ms:
            ev += _event(m, teams, venues, comps, site, stamp, owner=t)
        name = f'{t[0]} {t[3]} ({comps[t[2]]})'
        open(f'{outdir}/cal/{CK[t[2]]}-{t[5]}.ics', 'w', encoding='utf-8', newline='').write(
            _cal(name, f'{t[3]} {t[4]} schedule and results. Updated twice a day by EAL Tracker.', ev))
        n += 1
    # club calendars per competition: every match of every team the club has in it
    for cid, cname in clubs.items():
        cid = int(cid)
        for c in range(3):
            idx = {i for i, t in enumerate(teams) if t[1] == cid and t[2] == c}
            if not idx:
                continue
            ms = sorted({m[0]: m for i in idx for m in by_team.get(i, [])}.values(), key=lambda m: (m[1], m[0]))
            ev = []
            for m in ms:
                own = teams[m[2]] if m[2] in idx else teams[m[3]]
                ev += _event(m, teams, venues, comps, site, stamp, prefix=f'{teams[m[2]][3]} ', owner=own)
            open(f'{outdir}/cal/club-{cid}-{CK[c]}.ics', 'w', encoding='utf-8', newline='').write(
                _cal(f'{cname} · {comps[c]}', f'All {cname} {comps[c]} matches. Updated twice a day by EAL Tracker.', ev))
            n += 1
    return n


# ---------- club and team pages (readable by search engines; shared links open the app) ----------
PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<script>if(/[?&]s=1\\b/.test(location.search))location.replace({target_js});</script>
<title>{title}</title>
<meta name="description" content="{desc}">
<link rel="canonical" href="{url}">
<meta name="theme-color" content="#060c17">
<link rel="icon" href="{root}favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="{root}apple-touch-icon.png">
<link rel="stylesheet" href="{root}pages.css">
<meta property="og:type" content="website">
<meta property="og:site_name" content="EAL Tracker">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:url" content="{url}">
<meta property="og:image" content="{img}">
<meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{title}">
<meta name="twitter:description" content="{desc}">
<meta name="twitter:image" content="{img}">
<script type="application/ld+json">{ld}</script>
</head><body>
<header class="top"><a class="brand" href="{root}"><img src="{root}favicon.svg" alt="" width="28" height="28"><span>EAL <b>Tracker</b></span></a><a class="open" href="{target}">Open in EAL Tracker</a></header>
<main>
<nav class="crumbs" aria-label="Breadcrumb">{crumbs}</nav>
{body}
<p class="cta"><a class="open big" href="{target}">{cta}</a></p>
</main>
<footer><p>Updated {asof}. Updated automatically twice a day from the Elite Academy League's public schedule and standings.</p>
<p>Independent project. Not affiliated with or endorsed by the Elite Academy League or Modular11.</p>
<p><a href="{root}">Home</a> · <a href="{root}clubs/">All clubs A–Z</a> · <a href="{root}#rankings">National Rankings</a> · <a href="{root}#weekend">This week</a></p></footer>
</body></html>
"""

CSS = """:root{color-scheme:dark}*{box-sizing:border-box}
body{margin:0;background:#060c17;color:#eef3fb;font:16px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
a{color:#5eead4}main,footer{max-width:980px;margin:0 auto;padding:0 16px}
.top{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:14px 16px;border-bottom:1px solid rgba(150,180,225,.14)}
.brand{display:flex;align-items:center;gap:8px;color:#eef3fb;text-decoration:none;font-weight:800;letter-spacing:.06em;text-transform:uppercase}.brand b{color:#2dd4bf}
.open{display:inline-block;background:#2dd4bf;color:#04211d;font-weight:700;text-decoration:none;border-radius:999px;padding:8px 14px;font-size:.9rem;text-align:center}
.open.big{padding:12px 20px;font-size:1rem}
.crumbs{font-size:.85rem;color:#9aabc3;margin:16px 0 6px}.crumbs a{color:#9aabc3}
.hd{display:flex;gap:16px;align-items:center;margin:8px 0 6px}
.hd img{width:72px;height:72px;border-radius:16px;background:#f2f5fa;padding:6px;flex:none}
h1{font-size:clamp(1.6rem,5vw,2.4rem);line-height:1.1;margin:0;overflow-wrap:break-word}
h2{font-size:1.2rem;margin:28px 0 10px}
.lead{color:#c9d4e4;margin:10px 0 0}
.wrap{overflow-x:auto;border:1px solid rgba(150,180,225,.14);border-radius:12px;background:rgba(15,25,42,.86)}
table{border-collapse:collapse;width:100%;font-size:.92rem}
th,td{padding:8px 10px;text-align:left;border-bottom:1px solid rgba(150,180,225,.1);white-space:nowrap}
th{color:#9aabc3;font-weight:600;font-size:.78rem;text-transform:uppercase;letter-spacing:.06em}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
tr.me td{background:rgba(45,212,191,.12);font-weight:700}
td.t{white-space:normal;min-width:150px}
ul.list{columns:2 240px;padding-left:18px}ul.list li{margin:3px 0}
.note{background:rgba(226,162,59,.10);border:1px solid rgba(226,162,59,.45);border-radius:12px;padding:10px 12px;font-size:.88rem;color:#e9e1d0}
.cta{margin:28px 0}footer{color:#9aabc3;font-size:.85rem;margin-top:24px;padding-top:12px;padding-bottom:28px;border-top:1px solid rgba(150,180,225,.14)}
"""


def _ord(n):
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _agek(a):
    m = re.search(r'\d+', a or '')
    return int(m.group()) if m else 99


def _when(s):
    dt = D.datetime.strptime(s, '%Y-%m-%dT%H:%M')
    day = f"{dt:%a}, {dt:%b} {dt.day}"
    if dt.hour == 0 and dt.minute == 0:
        return day + ' · time TBD'
    return day + ' · ' + dt.strftime('%I:%M %p').lstrip('0')


def _venue(v):
    return 'Venue TBD' if re.match(r'^\s*TBD\b', v[0] or '', re.I) else v[0]


def _match_rows(ms, teams, venues, comps, focus=None, show_age=False, team_url=None):
    rows = []
    for m in ms:
        mid, when, hi, ai, hs, as_, vi = m
        h, a = teams[hi], teams[ai]

        def nm(i, t):
            u = team_url(t) if team_url else None
            label = H.escape(t[0])
            if i == focus:
                return f'<b>{label}</b>'
            return f'<a href="{u}">{label}</a>' if u else label
        sc = f'{hs}–{as_}' if hs is not None else 'v'
        age = f'<td>{H.escape(h[3])} {H.escape(comps[h[2]])}</td>' if show_age else ''
        rows.append(f'<tr><td>{H.escape(_when(when))}</td>{age}<td class="t">{nm(hi, h)}</td><td class="n">{sc}</td><td class="t">{nm(ai, a)}</td><td class="t">{H.escape(_venue(venues[vi]))}</td></tr>')
    head = f'<tr><th>Date</th>{"<th>Age</th>" if show_age else ""}<th>Home</th><th class="n"></th><th>Away</th><th>Venue</th></tr>'
    return f'<div class="wrap"><table><thead>{head}</thead><tbody>{"".join(rows)}</tbody></table></div>'


def _ld(obj):
    return json.dumps(obj, ensure_ascii=False).replace('</', '<\\/')


def write_share_pages(data, outdir, site, slugs):
    teams, comps, clubs, matches, venues = data['teams'], data['comps'], data['clubs'], data['matches'], data['venues']
    crests = set(data.get('crests') or [])
    asof = data['asOfLong']
    now = data['asOfIso'][:16]
    open(f'{outdir}/pages.css', 'w', encoding='utf-8').write(CSS)
    by_team = {}
    for m in matches:
        for side in (m[2], m[3]):
            by_team.setdefault(side, []).append(m)
    for v in by_team.values():
        v.sort(key=lambda m: (m[1], m[0]))
    key = lambda t: f'{CK[t[2]]}-{t[5]}'
    root = '../../'
    team_url = lambda t: f'{root}team/{key(t)}/' if t[5] else None
    urls = []

    def crest_img(cid, alt=''):
        return f'<img src="{root}crests/{cid}.webp" alt="{H.escape(alt)}" width="72" height="72">' if int(cid) in crests else ''

    def div_size(t):
        return sum(1 for x in teams if x[2] == t[2] and x[3] == t[3] and x[4] == t[4] and x[6] is not None)

    # ---- club pages
    for cid, name in clubs.items():
        cid = str(cid)
        tix = sorted([i for i, t in enumerate(teams) if t[1] == int(cid)], key=lambda i: (teams[i][2], _agek(teams[i][3]), teams[i][0]))
        ts = [teams[i] for i in tix]
        cs = sorted({t[2] for t in ts})
        best = sorted([t for t in ts if t[6] is not None and t[8]], key=lambda t: (t[6], -t[7]))
        bits = [f"{len(ts)} teams in {', '.join(comps[c] for c in cs)}"]
        if best:
            bits.append(f'{best[0][3]} {comps[best[0][2]]} is {_ord(best[0][6])} in {best[0][4]}')
        desc = f"{name} in the Elite Academy League {data['season']}: standings, schedules, results and rankings. " + '. '.join(bits) + '.'
        url = f'{site}club/{slugs[cid]}/'
        target = f'{root}#club-{cid}'
        body = [f'<div class="hd">{crest_img(cid, name + " crest")}<div><h1>{H.escape(name)}</h1></div></div>',
                f'<p class="lead">{H.escape(desc)}</p>']
        for c in cs:
            rows = []
            for t in [t for t in ts if t[2] == c]:
                u = team_url(t)
                nm = f'<a href="{u}">{H.escape(t[0])}</a>' if u else H.escape(t[0])
                if t[8] is not None:
                    rows.append(f'<tr><td>{H.escape(t[3])}</td><td class="t">{nm}</td><td>{H.escape(t[4])}</td><td class="n">{t[6]} of {div_size(t)}</td><td class="n">{t[8]}</td><td class="n">{t[9]}-{t[10]}-{t[11]}</td><td class="n">{t[12]}-{t[13]}</td><td class="n"><b>{t[7]}</b></td></tr>')
                else:
                    rows.append(f'<tr><td>{H.escape(t[3])}</td><td class="t">{nm}</td><td>{H.escape(t[4])}</td><td colspan="5">Not in the league table yet</td></tr>')
            body.append(f'<h2>{H.escape(comps[c])} teams</h2>' + (f'<p class="note">The league hasn\'t published {H.escape(comps[c])} standings since {H.escape(data.get("calcSince") or "")}. Positions are calculated by EAL Tracker from the league\'s match scores; teams level on points per game may be ordered differently by the league.</p>' if c in (data.get('calc') or []) else '') + f'<div class="wrap"><table><thead><tr><th>Age</th><th>Team</th><th>Division</th><th class="n">Pos</th><th class="n">GP</th><th class="n">W-D-L</th><th class="n">GF-GA</th><th class="n">Pts</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>')
        ms = sorted({m[0]: m for i in tix for m in by_team.get(i, [])}.values(), key=lambda m: (m[1], m[0]))
        up = [m for m in ms if m[4] is None and m[1] >= now][:15]
        done = [m for m in ms if m[4] is not None and m[1] <= now][-15:][::-1]
        if up:
            body.append('<h2>Next matches</h2>' + _match_rows(up, teams, venues, comps, show_age=True, team_url=team_url))
        if done:
            body.append('<h2>Latest results</h2>' + _match_rows(done, teams, venues, comps, show_age=True, team_url=team_url))
        org = {'@type': 'SportsOrganization', 'name': name, 'sport': 'Soccer', 'url': url,
               'member': [{'@type': 'SportsTeam', 'name': f'{t[0]} {t[3]} ({comps[t[2]]})', 'sport': 'Soccer', **({'url': f'{site}team/{key(t)}/'} if t[5] else {})} for t in ts]}
        if int(cid) in crests:
            org['logo'] = f'{site}crests/{cid}.webp'
        ld = {'@context': 'https://schema.org', '@graph': [org,
              {'@type': 'BreadcrumbList', 'itemListElement': [
                  {'@type': 'ListItem', 'position': 1, 'name': 'EAL Tracker', 'item': site},
                  {'@type': 'ListItem', 'position': 2, 'name': 'Clubs', 'item': f'{site}clubs/'},
                  {'@type': 'ListItem', 'position': 3, 'name': name, 'item': url}]}]}
        p = f'{outdir}/club/{slugs[cid]}'
        os.makedirs(p, exist_ok=True)
        open(f'{p}/index.html', 'w', encoding='utf-8').write(PAGE.format(
            title=H.escape(f'{name} · EA standings, schedule & results · EAL Tracker'), desc=H.escape(desc), url=url,
            img=f'{site}og/club-{cid}.png', root=root, target=target, target_js=json.dumps(target), ld=_ld(ld), asof=H.escape(asof),
            crumbs=f'<a href="{root}">EAL Tracker</a> › <a href="{root}clubs/">Clubs</a> › {H.escape(name)}',
            body='\n'.join(body), cta=f'Open {H.escape(name)} in EAL Tracker'))
        urls.append(url)

    # ---- team pages
    for i, t in enumerate(teams):
        if not t[5]:
            continue
        cname = clubs.get(t[1]) or clubs.get(str(t[1])) or t[0]
        k = key(t)
        rec = f'{t[9]}-{t[10]}-{t[11]} W-D-L' if t[8] is not None else 'not in the league table yet'
        pos = f'{_ord(t[6])} in {t[4]}' if t[6] is not None else t[4]
        desc = f"{t[0]} {t[3]} · {comps[t[2]]} · {pos} · {rec}. Schedule, results, standings and match-day weather."
        url = f'{site}team/{k}/'
        target = f'{root}#team-{k}'
        if t[8] is not None:
            pl = lambda n, w: f'{n} {w}' + ('' if n == 1 else ('es' if w == 'loss' else 's'))
            summ = f'{_ord(t[6])} of {div_size(t)} with {pl(t[7], "point")} from {pl(t[8], "game")} ({pl(t[9], "win")}, {pl(t[10], "draw")}, {pl(t[11], "loss")}; goals {t[12]}-{t[13]}).'
        else:
            summ = 'Not in the league table yet.'
        if len(t) > 15 and t[15] is not None:
            summ += f' {_ord(t[15])} in the EAL Tracker national ranking for {t[3]} {comps[t[2]]}.'
        calc_note = (f'<p class="note">The league hasn\'t published {H.escape(comps[t[2]])} standings since {H.escape(data.get("calcSince") or "")}. This table is calculated by EAL Tracker from the league\'s match scores (win 3, draw 1, loss 0, ranked by points per game); teams level on points per game may be ordered differently by the league.</p>' if t[2] in (data.get('calc') or []) else '')
        body = [f'<div class="hd">{crest_img(t[1], cname + " crest")}<div><h1>{H.escape(t[0])} {H.escape(t[3])}</h1></div></div>',
                f'<p class="lead">{H.escape(comps[t[2]])} · {H.escape(t[3])} {H.escape(t[4])} division · Elite Academy League {H.escape(data["season"])}. {H.escape(summ)}</p>']
        div = sorted([x for x in teams if x[2] == t[2] and x[3] == t[3] and x[4] == t[4] and x[6] is not None], key=lambda x: (x[6], x[0]))
        if div:
            rows = []
            for x in div:
                u = team_url(x)
                nm = H.escape(x[0]) if x is t or not u else f'<a href="{u}">{H.escape(x[0])}</a>'
                rows.append(f'<tr class="{"me" if x is t else ""}"><td class="n">{x[6]}</td><td class="t">{nm}</td><td class="n">{x[8]}</td><td class="n">{x[9]}</td><td class="n">{x[10]}</td><td class="n">{x[11]}</td><td class="n">{x[12]}-{x[13]}</td><td class="n"><b>{x[7]}</b></td></tr>')
            body.append(f'<h2>{H.escape(t[3])} {H.escape(t[4])} standings</h2>{calc_note}<div class="wrap"><table><thead><tr><th class="n">#</th><th>Team</th><th class="n">GP</th><th class="n">W</th><th class="n">D</th><th class="n">L</th><th class="n">GF-GA</th><th class="n">Pts</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>')
        ms = by_team.get(i, [])
        up = [m for m in ms if m[4] is None and m[1] >= now]
        done = [m for m in ms if m[4] is not None][::-1]
        if up:
            body.append('<h2>Schedule</h2>' + _match_rows(up, teams, venues, comps, focus=i, team_url=team_url))
        if done:
            body.append('<h2>Results</h2>' + _match_rows(done, teams, venues, comps, focus=i, team_url=team_url))
        cslug = slugs.get(str(t[1]))
        team_ld = {'@type': 'SportsTeam', 'name': f'{t[0]} {t[3]}', 'sport': 'Soccer', 'url': url}
        crumbs_ld = [{'@type': 'ListItem', 'position': 1, 'name': 'EAL Tracker', 'item': site}]
        if cslug:
            team_ld['memberOf'] = {'@type': 'SportsOrganization', 'name': cname, 'url': f'{site}club/{cslug}/'}
            crumbs_ld.append({'@type': 'ListItem', 'position': 2, 'name': cname, 'item': f'{site}club/{cslug}/'})
        crumbs_ld.append({'@type': 'ListItem', 'position': len(crumbs_ld) + 1, 'name': f'{t[0]} {t[3]}', 'item': url})
        ld = {'@context': 'https://schema.org', '@graph': [team_ld, {'@type': 'BreadcrumbList', 'itemListElement': crumbs_ld}]}
        crumbs = f'<a href="{root}">EAL Tracker</a> › ' + (f'<a href="{root}club/{cslug}/">{H.escape(cname)}</a> › ' if cslug else '') + f'{H.escape(t[3])} {H.escape(comps[t[2]])}'
        p = f'{outdir}/team/{k}'
        os.makedirs(p, exist_ok=True)
        open(f'{p}/index.html', 'w', encoding='utf-8').write(PAGE.format(
            title=H.escape(f'{t[0]} {t[3]} {comps[t[2]]} · standings & schedule · EAL Tracker'), desc=H.escape(desc), url=url,
            img=f'{site}og/club-{t[1]}.png', root=root, target=target, target_js=json.dumps(target), ld=_ld(ld), asof=H.escape(asof),
            crumbs=crumbs, body='\n'.join(body), cta=f'Open {H.escape(t[0])} {H.escape(t[3])} in EAL Tracker'))
        urls.append(url)

    # ---- all clubs A-Z
    items = ''.join(f'<li><a href="../club/{slugs[str(cid)]}/">{H.escape(n)}</a></li>' for cid, n in sorted(clubs.items(), key=lambda kv: kv[1].lower()))
    nteams = sum(1 for t in teams if t[5])
    desc = f"All {len(clubs)} Elite Academy League clubs for {data['season']}, A to Z. Standings, schedules, results and rankings for {nteams:,} teams in EA, EA National and EA2."
    os.makedirs(f'{outdir}/clubs', exist_ok=True)
    open(f'{outdir}/clubs/index.html', 'w', encoding='utf-8').write(PAGE.format(
        title='All Elite Academy League clubs A–Z · EAL Tracker', desc=H.escape(desc), url=f'{site}clubs/', img=f'{site}og/home.png', root='../',
        target='../#home', target_js=json.dumps('../#home'), asof=H.escape(asof),
        ld=_ld({'@context': 'https://schema.org', '@type': 'CollectionPage', 'name': 'Elite Academy League clubs', 'url': f'{site}clubs/'}),
        crumbs='<a href="../">EAL Tracker</a> › Clubs', body=f'<h1>Elite Academy League clubs</h1><p class="lead">{H.escape(desc)}</p><ul class="list">{items}</ul>',
        cta='Search clubs in EAL Tracker'))

    today = data['asOfIso'][:10]
    sm = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in [site, f'{site}clubs/'] + urls:
        sm.append(f'<url><loc>{H.escape(u)}</loc><lastmod>{today}</lastmod></url>')
    sm.append('</urlset>')
    open(f'{outdir}/sitemap.xml', 'w', encoding='utf-8').write('\n'.join(sm) + '\n')
    open(f'{outdir}/robots.txt', 'w', encoding='utf-8').write(f'User-agent: *\nAllow: /\nSitemap: {site}sitemap.xml\n')
    return len(urls)


def analytics_snippet(code):
    code = (code or '').strip()
    if not re.fullmatch(r'[a-z0-9-]{1,63}', code or ''):
        return ''
    return ('<script>window.goatcounter={no_onload:true};'
            'function eaCount(){if(window.goatcounter&&window.goatcounter.count)window.goatcounter.count({path:location.pathname+location.search+location.hash})}'
            "window.addEventListener('hashchange',eaCount);</script>\n"
            f'<script data-goatcounter="https://{code}.goatcounter.com/count" async src="//gc.zgo.at/count.js" onload="eaCount()"></script>')
