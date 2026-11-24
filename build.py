import json,re,sys,os,datetime as D,collections
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from zoneinfo import ZoneInfo
SRC=sys.argv[1] if len(sys.argv)>1 else 'data/raw.json'
OUT=sys.argv[2] if len(sys.argv)>2 else 'site/index.html'
P=json.load(open(SRC))
COMPS=['EA','EA National','EA2'];BI={47:0,51:1,48:2}
pulled=D.datetime.fromisoformat(P['pulledAt'].replace('Z','+00:00'))
local=pulled.astimezone(ZoneInfo('America/Los_Angeles'))
asof=local.strftime('%b %-d, %Y, %-I:%M %p')+' Pacific'
OVR={1363:'FC1 Academy',1379:'Atletico Rojo',902:'Seattle Celtic',1408:'FLYTE SC- Inland Empire',1355:'Steel United TX',1335:'Soccer Chance Academy',1333:'Oregon Surf SC',1606:'Saints Soccer Academy',1591:'Culver City Football Club',923:'Fram Soccer Club',1121:'LAIFC'}
teams=[];ix={};cl=collections.defaultdict(collections.Counter)
for r in P['standings']:
    n=r['n'].strip();k=(BI[r['b']],r['age'],n);N=r['nums']
    div=re.sub(r'^\s*U\d+ | Division\s*$','',r['div'].strip()).strip()
    ix[k]=len(teams)
    teams.append([n,r['ac'],BI[r['b']],r['age'],div,int(r['tid']),int(r['rank']),int(N[0]),int(N[2]),int(N[3]),int(N[5]),int(N[4]),int(N[6]),int(N[7]),N[1]])
    cl[r['ac']][re.sub(r' \(\d+\)$| \d+$','',n)]+=1
clubs={k:OVR.get(k,v.most_common(1)[0][0]) for k,v in cl.items()}
venues=[];vi={};matches=[];no=set();now=local.replace(tzinfo=None)
tally=collections.defaultdict(lambda:[0,0,0,0,0,0])
tbd=[];fut=[];mid=0
for m in P['matches']:
    c=COMPS.index(m['b']);when=D.datetime.strptime(m['dt'].upper(),'%m/%d/%y %I:%M%p')
    sides=[]
    for nm,ac,dv in((m['h'],m['ha'],m['dh']),(m['a'],m['aa'],m['da'])):
        nm=nm.strip();k=(c,m['age'],nm)
        if k not in ix:
            no.add(nm);ix[k]=len(teams);teams.append([nm,ac['a'],c,m['age'],dv,None,None,None,None,None,None,None,None,None,None]);clubs.setdefault(ac['a'],nm)
        sides.append(ix[k])
    s=re.fullmatch(r'(\d+) : (\d+)',m['s'])
    if not s and m['s']!='TBD': raise SystemExit('score '+m['s'])
    hs,as_=(int(s[1]),int(s[2])) if s else (None,None)
    vk=(m['v'],m['lat'],m['lng'])
    if vk not in vi: vi[vk]=len(venues);venues.append(list(vk))
    matches.append([m['id'],when.strftime('%Y-%m-%dT%H:%M'),sides[0],sides[1],hs,as_,vi[vk]])
    if s:
        for t,g,a in((sides[0],hs,as_),(sides[1],as_,hs)):
            x=tally[t];x[0]+=1;x[4]+=g;x[5]+=a;x[1 if g>a else 2 if g==a else 3]+=1
        if when>now: fut.append([m['id'],m['age'],m['b'],m['h'].strip(),m['s'].replace(' ',''),m['a'].strip(),when.strftime('%b %-d, %Y')])
    else:
        if when<now: tbd.append(m['id'])
        elif when.hour==0 and when.minute==0: mid+=1
# A competition with matches but no published table (the league stopped publishing EA National tables
# on Nov 19, 2026): calculate its table from the league's own match scores and label it on the site.
# As soon as the league publishes the table again, the official one is used instead.
CALC=[]
official_comps={BI[r['b']] for r in P['standings']}
match_comps={t[2] for t in teams}
NIDS=json.load(open('data/national-ids.json'))['ids'] if os.path.exists('data/national-ids.json') else {}
import hashlib
for c in sorted(match_comps-official_comps):
    CALC.append(c)
    grp=collections.defaultdict(list)
    for i,t in enumerate(teams):
        if t[2]!=c: continue
        x=tally.get(i,[0]*6)
        t[8],t[9],t[10],t[11],t[12],t[13]=x
        t[7]=x[1]*3+x[2]
        t[14]=f"{t[7]/x[0]:.2f}" if x[0] else '0.00'
        tid=NIDS.get(f'{t[3]}|{t[0]}') if c==1 else None
        t[5]=tid or 9_000_000+int(hashlib.md5(f'{c}|{t[3]}|{t[0]}'.encode()).hexdigest(),16)%1_000_000
        grp[(t[3],t[4])].append(i)
    # Order used by the league's own tables (checked against the last official tables, Nov 18, 2026:
    # it reproduces 1,130 of 1,140 neighbouring pairs): points per game, then total points,
    # then head-to-head points, goal difference, fewest goals against, most goals scored.
    h2h=collections.defaultdict(int)
    for m in matches:
        if m[4] is None or teams[m[2]][2]!=c: continue
        h,a,hs,as_=m[2],m[3],m[4],m[5]
        h2h[(h,a)]+=3 if hs>as_ else 1 if hs==as_ else 0
        h2h[(a,h)]+=3 if as_>hs else 1 if hs==as_ else 0
    from fractions import Fraction
    def tcmp(a,b):
        A,B=teams[a],teams[b]
        for x,y in ((Fraction(A[7],A[8]) if A[8] else -1,Fraction(B[7],B[8]) if B[8] else -1),(A[7],B[7]),(h2h[(a,b)],h2h[(b,a)]),
                    (A[12]-A[13],B[12]-B[13]),(-A[13],-B[13]),(A[12],B[12])):
            if x!=y: return -1 if x>y else 1
        return 0
    import functools
    for ids in grp.values():
        ids.sort(key=lambda i:teams[i][0].lower())
        ids.sort(key=functools.cmp_to_key(tcmp))
        r=0
        for n,i in enumerate(ids):
            if n==0 or tcmp(ids[n-1],i)!=0: r=n+1
            teams[i][6]=r
if CALC: no={t[0] for t in teams if t[6] is None}
ok=diff=0;bad=[]
for i,t in enumerate(teams):
    if t[6] is None or t[2] in CALC: continue
    x=tally.get(i,[0]*6)
    if [t[8],t[9],t[10],t[11],t[12],t[13],t[7]]==[x[0],x[1],x[2],x[3],x[4],x[5],x[1]*3+x[2]]: ok+=1
    else: diff+=1;bad.append(t[0])
# Results-based national rankings per competition and age (same method as the site describes),
# saved daily so the site can show movement against the ranking from about a week earlier.
def rank_groups():
    out={}
    groups=collections.defaultdict(list)
    for i,t in enumerate(teams):
        if t[8] is not None and t[8]>=3: groups[(t[2],t[3])].append(i)
    for g,ids in groups.items():
        key=lambda i:(teams[i][7]/teams[i][8],(teams[i][12]-teams[i][13])/teams[i][8],teams[i][12]/teams[i][8],teams[i][8])
        ids.sort(key=lambda i:(tuple(-x for x in key(i)),teams[i][0]))
        r=0;prev=None
        for n,i in enumerate(ids):
            k=key(i)
            if k!=prev: r=n+1;prev=k
            out[i]=r
    return out
nat=rank_groups()
tkey=lambda t:f"{t[2]}|{t[3]}|{t[0]}"
HIST='data/history'
os.makedirs(HIST,exist_ok=True)
today=local.date()
snap={tkey(teams[i]):r for i,r in nat.items()}
json.dump(snap,open(f'{HIST}/{today.isoformat()}.json','w'),separators=(',',':'))
base=None
for f in sorted(os.listdir(HIST)):
    d=D.date.fromisoformat(f[:10])
    if d<=today-D.timedelta(days=6): base=(d,f)
prevr=json.load(open(f'{HIST}/{base[1]}')) if base else {}
for i,t in enumerate(teams):
    r=nat.get(i)
    p=prevr.get(tkey(t))
    t.append(r)
    t.append((p-r) if (r is not None and p is not None) else None)
CRESTS=sorted(int(f[:-5]) for f in os.listdir('crests') if f.endswith('.webp')) if os.path.isdir('crests') else []
import site_extras as X
SITE=os.environ.get('SITE_URL','https://ealtracker.com/').rstrip('/')+'/'
SLUGS=X.club_slugs({str(k):v for k,v in clubs.items()})
# Ranking history for the trend charts: daily for the last 14 days, then one per week, up to 26 points.
def rank_history():
    files=sorted(f for f in os.listdir(HIST) if f.endswith('.json'))
    days=[D.date.fromisoformat(f[:10]) for f in files]
    keep=[];seen=set()
    for d in sorted(days,reverse=True):
        if d>today-D.timedelta(days=14): keep.append(d);continue
        wk=d.isocalendar()[:2]
        if wk not in seen: seen.add(wk);keep.append(d)
    keep=sorted(keep[:26])
    snaps=[json.load(open(f'{HIST}/{d.isoformat()}.json')) for d in keep]
    out={}
    for i,t in enumerate(teams):
        r=[sn.get(tkey(t)) for sn in snaps]
        if any(x is not None for x in r): out[i]=r
    sizes={}
    for j,sn in enumerate(snaps):
        for k in sn:
            g=k.rsplit('|',1)[0];sizes.setdefault(g,[0]*len(snaps))[j]+=1
    return dict(d=[d.isoformat() for d in keep],r=out,n=sizes)
RH=rank_history()
COLORS={int(k):v for k,v in json.load(open('crests/colors.json')).items()} if os.path.exists('crests/colors.json') else {}
data=dict(site=SITE,slugs=SLUGS,season='2026–27',comps=COMPS,asOfLong=asof,asOfIso=local.isoformat(),clubs=clubs,teams=teams,matches=matches,venues=venues,crests=CRESTS,colors=COLORS,rh=RH,
 moveSince=base[0].strftime('%b %-d, %Y') if base else None,
 analytics=bool(X.analytics_snippet(os.environ.get('GOATCOUNTER_CODE',''))),calc=CALC,calcSince='Nov 19, 2026',check=dict(ok=ok,diff=diff,total=ok+diff,tbdPast=tbd,futureScored=fut,midnight=mid,noTable=sorted(no)))
js=json.dumps(data,ensure_ascii=False,separators=(',',':')).replace('</','<\\/')
FEEDBACK=os.environ.get('FEEDBACK_ENDPOINT','').strip()
if not re.fullmatch(r'https://[^\s"<>]+',FEEDBACK): FEEDBACK=''
html=open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'template.html'),encoding='utf8').read().replace('__DATA__',js).replace('__SITE__',SITE).replace('<!--ANALYTICS-->',X.analytics_snippet(os.environ.get('GOATCOUNTER_CODE',''))).replace('__FEEDBACK__',json.dumps(FEEDBACK))
os.makedirs(os.path.dirname(OUT) or '.',exist_ok=True)
open(OUT,'w',encoding='utf8').write(html)
if CRESTS:
    import shutil
    cd=os.path.join(os.path.dirname(OUT) or '.','crests');os.makedirs(cd,exist_ok=True)
    for c in CRESTS: shutil.copyfile(f'crests/{c}.webp',f'{cd}/{c}.webp')
SITE_DIR=os.path.dirname(OUT) or '.'
ncal=X.write_calendars(data,SITE_DIR,SITE)
nshare=X.write_share_pages(data,SITE_DIR,SITE,SLUGS)
print('calendars',ncal,'share pages',nshare)
open('data/latest.json','w',encoding='utf8').write(json.dumps(data,ensure_ascii=False,separators=(',',':')))
prev=os.environ.get('PREV_MATCHES')
if prev and len(matches)<0.9*int(prev): raise SystemExit(f'match count dropped from {prev} to {len(matches)}; not publishing')
if diff: print(f'::warning::{diff} official table lines do not match the match results; shown on the Data notes page')
print(asof,'teams',len(teams),'clubs',len(clubs),'crests',len(CRESTS),'ranked',len(nat),'moves since',data['moveSince'],'matches',len(matches),'KB',len(html)//1024,'check',ok,diff,bad[:5],'tbd',len(tbd),'fut',len(fut),'mid',mid,'noTable',sorted(no),'calculated',[COMPS[c] for c in CALC])
