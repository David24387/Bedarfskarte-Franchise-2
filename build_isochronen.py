#!/usr/bin/env python3
import csv, json, os, time, urllib.request, urllib.error, http.client, socket
from pathlib import Path

API_KEY=os.environ.get('ORS_API_KEY','').strip()
ENDPOINT='https://api.heigit.org/openrouteservice/v2/isochrones/driving-car'
RANGE_SECONDS=30*60
MIN_REQUEST_INTERVAL=3.5
MAX_RETRIES=3
EXPECTED_CENTERS=390
BATCH_SIZE=int(os.environ.get('ISOCHRONE_BATCH_SIZE','25'))
CACHE_FILE=Path('isochronen.json')

if not API_KEY:
    raise SystemExit('ORS_API_KEY fehlt. Bitte als GitHub Actions Secret anlegen.')

def norm(s): return (s or '').strip()
def num(s):
    try: return float(norm(s).replace(',','.'))
    except: return None

def find_header(rows):
    for i,row in enumerate(rows[:10]):
        t=' '.join(row).lower()
        if 'lat' in t and ('long' in t or 'lng' in t): return i
    return 0

def get(row,*names):
    low={str(k).strip().lower():v for k,v in row.items() if k is not None}
    for n in names:
        if n.lower() in low: return low[n.lower()]
    return ''

def bu_type(v):
    x=norm(v).lower()
    if x=='mixed': return 'Mixed'
    if x=='heavy': return 'Heavy'
    if x=='light': return 'Light'
    if 'mixed' in x or ('light' in x and 'heavy' in x): return 'Mixed'
    if 'heavy' in x: return 'Heavy'
    if 'light' in x: return 'Light'
    return 'Unknown'

def key_for(c):
    return f'{c["net"]}|{c["lat"]:.6f}|{c["lng"]:.6f}'

def request_isochrone(lon,lat):
    body=json.dumps({'locations':[[lon,lat]],'range':[RANGE_SECONDS],'range_type':'time','location_type':'start'}).encode()
    last_error=None
    for attempt in range(1,MAX_RETRIES+1):
        req=urllib.request.Request(ENDPOINT,data=body,headers={
            'Authorization':API_KEY,'Content-Type':'application/json','Accept':'application/geo+json',
            'User-Agent':'Euromaster-Bedarfskarte/3.0'
        },method='POST')
        try:
            with urllib.request.urlopen(req,timeout=45) as r: return json.load(r)
        except urllib.error.HTTPError as e:
            msg=e.read().decode('utf-8','replace'); last_error=f'ORS HTTP {e.code}: {msg[:300]}'
            if e.code in (429,500,502,503,504) and attempt<MAX_RETRIES:
                retry_after=e.headers.get('Retry-After')
                try: wait=max(float(retry_after),8.0) if retry_after else min(8.0*attempt,20.0)
                except: wait=min(8.0*attempt,20.0)
                print(f'ORS HTTP {e.code} – warte {wait:.0f}s, Versuch {attempt}/{MAX_RETRIES}',flush=True)
                time.sleep(wait); continue
            break
        except (urllib.error.URLError,http.client.BadStatusLine,http.client.RemoteDisconnected,ConnectionError,TimeoutError,socket.timeout) as e:
            last_error=f'ORS Netzwerkfehler: {e}'
            if attempt<MAX_RETRIES:
                wait=min(6.0*attempt,15.0); print(f'Netzwerkfehler – warte {wait:.0f}s, Versuch {attempt}/{MAX_RETRIES}',flush=True)
                time.sleep(wait); continue
            break
    raise RuntimeError(last_error or 'ORS Anfrage fehlgeschlagen')

def load_cache():
    cache={}
    if not CACHE_FILE.exists(): return cache
    try:
        old=json.loads(CACHE_FILE.read_text(encoding='utf-8'))
        for f in old.get('features',[]):
            p=f.get('properties') or {}
            try:
                c={'net':norm(p.get('net')),'lat':float(p.get('lat')),'lng':float(p.get('lng'))}
                if c['net'] in ('01 - ERM','02 - FRA'): cache[key_for(c)]=f
            except: pass
    except Exception as e: print(f'Cache konnte nicht gelesen werden: {e}',flush=True)
    print(f'{len(cache)} vorhandene Fahrzeitgebiete als Cache erkannt.',flush=True)
    return cache

def write_output(features):
    out={'type':'FeatureCollection','properties':{'minutes':30,'profile':'driving-car','source':'openrouteservice / OpenStreetMap'},'features':features}
    CACHE_FILE.write_text(json.dumps(out,ensure_ascii=False,separators=(',',':')),encoding='utf-8')

def main():
    rows=list(csv.reader(Path('daten.csv').open(encoding='utf-8-sig',newline='')))
    hi=find_header(rows); headers=[norm(x) for x in rows[hi]]; centers=[]; skipped=[]
    for line_no,vals in enumerate(rows[hi+1:],hi+2):
        d={headers[i]:vals[i] if i<len(vals) else '' for i in range(len(headers)) if headers[i]}
        net=norm(get(d,'Stammdaten Filialnetz Netz','Netz'))
        if net not in ('02 - FRA','01 - ERM'): continue
        lat=num(get(d,'Lat.','Lat','Latitude')); lon=num(get(d,'Long.','Long','Lng','Longitude')); bt=bu_type(get(d,'BU')); name=norm(get(d,'Ort','KST','Netzkennung'))
        if lat is None or lon is None or bt=='Unknown': skipped.append((line_no,name,net,norm(get(d,'BU')))); continue
        centers.append({'lat':lat,'lng':lon,'buType':bt,'name':name,'net':net})
    print(f'{len(centers)} gültige FRA+ERM Standorte erkannt; {len(skipped)} übersprungen.',flush=True)
    if len(centers)!=EXPECTED_CENTERS: raise SystemExit(f'ABBRUCH: Erwartet {EXPECTED_CENTERS}, erkannt {len(centers)}.')

    cache=load_cache()
    expected={key_for(c):c for c in centers}
    # Nur Cache-Einträge behalten, die noch zu einem aktuellen Standort gehören.
    cache={k:f for k,f in cache.items() if k in expected}
    missing=[c for c in centers if key_for(c) not in cache]
    print(f'Aktuell vollständig: {len(cache)}/{EXPECTED_CENTERS}; offen: {len(missing)}.',flush=True)
    if not missing:
        features=[]
        for c in centers:
            f=cache[key_for(c)]; f['properties']={'buType':c['buType'],'name':c['name'],'net':c['net'],'minutes':30,'lat':c['lat'],'lng':c['lng']}; features.append(f)
        write_output(features); print('ERFOLG: 390/390 Fahrzeitgebiete.',flush=True); return

    todo=missing[:BATCH_SIZE]
    print(f'Dieser Lauf bearbeitet maximal {len(todo)} fehlende Standorte.',flush=True)
    failures=[]; last_request_started=0.0
    for pos,c in enumerate(todo,1):
        elapsed=time.monotonic()-last_request_started
        if last_request_started and elapsed<MIN_REQUEST_INTERVAL: time.sleep(MIN_REQUEST_INTERVAL-elapsed)
        print(f'Neu {pos}/{len(todo)} | gesamt offen {len(missing)}: {c["name"]} ({c["net"]}, {c["buType"]})',flush=True)
        last_request_started=time.monotonic()
        try:
            data=request_isochrone(c['lng'],c['lat']); fs=data.get('features') or []
            if not fs: raise RuntimeError('Keine Isochrone zurückgegeben')
            f=fs[0]; f['properties']={'buType':c['buType'],'name':c['name'],'net':c['net'],'minutes':30,'lat':c['lat'],'lng':c['lng']}
            cache[key_for(c)]=f
        except Exception as e:
            # Genau ein kurzer Routing-Fallback statt vier langer Retry-Ketten.
            try:
                time.sleep(MIN_REQUEST_INTERVAL)
                data=request_isochrone(c['lng']+0.00015,c['lat']+0.00015); fs=data.get('features') or []
                if not fs: raise RuntimeError('Keine Fallback-Isochrone zurückgegeben')
                f=fs[0]; f['properties']={'buType':c['buType'],'name':c['name'],'net':c['net'],'minutes':30,'lat':c['lat'],'lng':c['lng'],'routingFallback':True}
                cache[key_for(c)]=f
            except Exception as e2:
                failures.append((c,str(e2))); print(f'OFFEN: {c["name"]} – {e2}',flush=True)

    # Immer in der Reihenfolge der 390 aktuellen Standorte schreiben.
    features=[]
    for c in centers:
        k=key_for(c)
        if k in cache:
            f=cache[k]; f['properties'].update({'buType':c['buType'],'name':c['name'],'net':c['net'],'minutes':30,'lat':c['lat'],'lng':c['lng']}); features.append(f)
    write_output(features)
    remaining=[c for c in centers if key_for(c) not in cache]
    print(f'BATCH BEENDET: {len(features)}/{EXPECTED_CENTERS} gespeichert; noch {len(remaining)} offen.',flush=True)
    for c in remaining[:30]: print(f'FEHLT: {c["name"]} ({c["net"]}, {c["buType"]})',flush=True)
    # Ein Batch mit Fortschritt ist ein erfolgreicher Lauf. Weitere Läufe ergänzen nur den Rest.

if __name__=='__main__': main()
