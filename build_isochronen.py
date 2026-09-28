#!/usr/bin/env python3
import csv, json, os, time, urllib.request, urllib.error, http.client, socket
from pathlib import Path

API_KEY=os.environ.get('ORS_API_KEY','').strip()
ENDPOINT='https://api.heigit.org/openrouteservice/v2/isochrones/driving-car'
RANGE_SECONDS=30*60
MIN_REQUEST_INTERVAL=3.4
MAX_RETRIES=8
EXPECTED_CENTERS=390

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

def request_isochrone(lon,lat):
    body=json.dumps({'locations':[[lon,lat]],'range':[RANGE_SECONDS],'range_type':'time','location_type':'start'}).encode()
    for attempt in range(1,MAX_RETRIES+1):
        req=urllib.request.Request(ENDPOINT,data=body,headers={
            'Authorization':API_KEY,
            'Content-Type':'application/json',
            'Accept':'application/geo+json',
            'User-Agent':'Euromaster-Bedarfskarte/2.2'
        },method='POST')
        try:
            with urllib.request.urlopen(req,timeout=90) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            msg=e.read().decode('utf-8','replace')
            if e.code in (429,500,502,503,504) and attempt<MAX_RETRIES:
                retry_after=e.headers.get('Retry-After')
                try: wait=max(float(retry_after),10.0) if retry_after else min(15.0*attempt,90.0)
                except: wait=min(15.0*attempt,90.0)
                print(f'ORS HTTP {e.code} – warte {wait:.0f}s, Versuch {attempt}/{MAX_RETRIES}',flush=True)
                time.sleep(wait)
                continue
            raise RuntimeError(f'ORS HTTP {e.code}: {msg[:500]}')
        except (urllib.error.URLError, http.client.BadStatusLine, http.client.RemoteDisconnected, ConnectionError, TimeoutError, socket.timeout) as e:
            if attempt<MAX_RETRIES:
                wait=min(10.0*attempt,60.0)
                print(f'Temporärer ORS/Netzwerkfehler ({type(e).__name__}) – warte {wait:.0f}s, Versuch {attempt}/{MAX_RETRIES}',flush=True)
                time.sleep(wait)
                continue
            raise RuntimeError(f'ORS Netzwerkfehler nach {MAX_RETRIES} Versuchen: {e}')
    raise RuntimeError('ORS Anfrage nach mehreren Versuchen fehlgeschlagen.')

def main():
    p=Path('daten.csv')
    rows=list(csv.reader(p.open(encoding='utf-8-sig',newline='')))
    hi=find_header(rows); headers=[norm(x) for x in rows[hi]]
    centers=[]; skipped=[]
    for line_no,vals in enumerate(rows[hi+1:],hi+2):
        d={headers[i]: vals[i] if i<len(vals) else '' for i in range(len(headers)) if headers[i]}
        net=norm(get(d,'Stammdaten Filialnetz Netz','Netz'))
        if net not in ('02 - FRA','01 - ERM'):
            continue
        lat=num(get(d,'Lat.','Lat','Latitude')); lon=num(get(d,'Long.','Long','Lng','Longitude'))
        bu=bu_type(get(d,'BU'))
        name=norm(get(d,'Ort','KST','Netzkennung'))
        if lat is None or lon is None or bu=='Unknown':
            skipped.append((line_no,name,net,norm(get(d,'BU')),get(d,'Lat.','Lat','Latitude'),get(d,'Long.','Long','Lng','Longitude')))
            continue
        centers.append({'lat':lat,'lng':lon,'buType':bu,'name':name,'net':net})

    print(f'{len(centers)} gültige FRA+ERM Center erkannt; {len(skipped)} wegen Koordinaten/BU übersprungen.',flush=True)
    if skipped:
        for x in skipped[:25]: print('ÜBERSPRUNGEN:',x,flush=True)
    if len(centers)!=EXPECTED_CENTERS:
        raise SystemExit(f'ABBRUCH: Erwartet werden {EXPECTED_CENTERS} gültige FRA+ERM Center, erkannt wurden {len(centers)}. Isochronen werden nicht überschrieben.')

    print(f'Erzeuge 30-Minuten-Isochronen für alle {len(centers)} Center mit max. ca. 17 Anfragen/Minute.',flush=True)
    features=[]
    last_request_started=0.0
    for i,c in enumerate(centers,1):
        elapsed=time.monotonic()-last_request_started
        if last_request_started and elapsed<MIN_REQUEST_INTERVAL:
            time.sleep(MIN_REQUEST_INTERVAL-elapsed)
        print(f'Isochrone {i}/{len(centers)}: {c["name"]} ({c["net"]}, {c["buType"]})',flush=True)
        last_request_started=time.monotonic()
        data=request_isochrone(c['lng'],c['lat'])
        fs=data.get('features') or []
        if not fs: raise RuntimeError(f'Keine Isochrone für {c["name"]}')
        f=fs[0]
        f['properties']={'buType':c['buType'],'name':c['name'],'net':c['net'],'minutes':30,'lat':c['lat'],'lng':c['lng']}
        features.append(f)

    out={'type':'FeatureCollection','properties':{'minutes':30,'profile':'driving-car','source':'openrouteservice / OpenStreetMap'},'features':features}
    Path('isochronen.json').write_text(json.dumps(out,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    print(f'Erzeugt: {len(features)} 30-Minuten-Fahrzeitgebiete')

if __name__=='__main__': main()
