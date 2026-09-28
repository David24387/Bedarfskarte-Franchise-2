#!/usr/bin/env python3
import csv, json, os, time, urllib.request, urllib.error, http.client, socket, math
from pathlib import Path

API_KEY=os.environ.get('ORS_API_KEY','').strip()
ENDPOINT='https://api.heigit.org/openrouteservice/v2/isochrones/driving-car'
RANGE_SECONDS=30*60
MIN_REQUEST_INTERVAL=3.4
MAX_RETRIES=8
EXPECTED_CENTERS=390
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
            'User-Agent':'Euromaster-Bedarfskarte/2.3'
        },method='POST')
        try:
            with urllib.request.urlopen(req,timeout=90) as r: return json.load(r)
        except urllib.error.HTTPError as e:
            msg=e.read().decode('utf-8','replace'); last_error=f'ORS HTTP {e.code}: {msg[:500]}'
            if e.code in (429,500,502,503,504) and attempt<MAX_RETRIES:
                retry_after=e.headers.get('Retry-After')
                try: wait=max(float(retry_after),10.0) if retry_after else min(15.0*attempt,90.0)
                except: wait=min(15.0*attempt,90.0)
                print(f'ORS HTTP {e.code} – warte {wait:.0f}s, Versuch {attempt}/{MAX_RETRIES}',flush=True); time.sleep(wait); continue
            break
        except (urllib.error.URLError,http.client.BadStatusLine,http.client.RemoteDisconnected,ConnectionError,TimeoutError,socket.timeout) as e:
            last_error=f'ORS Netzwerkfehler: {e}'
            if attempt<MAX_RETRIES:
                wait=min(10.0*attempt,60.0); print(f'Temporärer ORS/Netzwerkfehler ({type(e).__name__}) – warte {wait:.0f}s, Versuch {attempt}/{MAX_RETRIES}',flush=True); time.sleep(wait); continue
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
    except Exception as e: print(f'Vorhandene Isochronen konnten nicht als Cache gelesen werden: {e}',flush=True)
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
        lat=num(get(d,'Lat.','Lat','Latitude')); lon=num(get(d,'Long.','Long','Lng','Longitude')); bu=bu_type(get(d,'BU')); name=norm(get(d,'Ort','KST','Netzkennung'))
        if lat is None or lon is None or bu=='Unknown': skipped.append((line_no,name,net,norm(get(d,'BU')))); continue
        centers.append({'lat':lat,'lng':lon,'buType':bu,'name':name,'net':net})
    print(f'{len(centers)} gültige FRA+ERM Standorte erkannt; {len(skipped)} übersprungen.',flush=True)
    if len(centers)!=EXPECTED_CENTERS: raise SystemExit(f'ABBRUCH: Erwartet {EXPECTED_CENTERS}, erkannt {len(centers)}.')

    cache=load_cache(); features=[]; failures=[]; last_request_started=0.0
    for i,c in enumerate(centers,1):
        k=key_for(c)
        if k in cache:
            f=cache[k]; f['properties']={'buType':c['buType'],'name':c['name'],'net':c['net'],'minutes':30,'lat':c['lat'],'lng':c['lng']}; features.append(f)
            print(f'Cache {i}/{len(centers)}: {c["name"]} ({c["net"]}, {c["buType"]})',flush=True); continue
        elapsed=time.monotonic()-last_request_started
        if last_request_started and elapsed<MIN_REQUEST_INTERVAL: time.sleep(MIN_REQUEST_INTERVAL-elapsed)
        print(f'Neu {i}/{len(centers)}: {c["name"]} ({c["net"]}, {c["buType"]})',flush=True); last_request_started=time.monotonic()
        try:
            data=request_isochrone(c['lng'],c['lat']); fs=data.get('features') or []
            if not fs: raise RuntimeError('Keine Isochrone zurückgegeben')
            f=fs[0]; f['properties']={'buType':c['buType'],'name':c['name'],'net':c['net'],'minutes':30,'lat':c['lat'],'lng':c['lng']}; features.append(f)
            # Fortschritt lokal sichern, damit ein späterer Fehler nicht alles verwirft.
            write_output(features)
        except Exception as e:
            failures.append((i,c,str(e))); print(f'FEHLER Standort {i}: {c["name"]} – {e}. Lauf wird fortgesetzt.',flush=True)

    # Zweite Runde nur für Fehlschläge; kleine Koordinatenverschiebung als ORS-Routing-Fallback.
    for i,c,first_error in list(failures):
        print(f'Fallback für Standort {i}: {c["name"]}',flush=True)
        success=False
        for dlat,dlng in ((0.00015,0),(0,0.00015),(-0.00015,0),(0,-0.00015)):
            try:
                time.sleep(MIN_REQUEST_INTERVAL)
                data=request_isochrone(c['lng']+dlng,c['lat']+dlat); fs=data.get('features') or []
                if not fs: continue
                f=fs[0]; f['properties']={'buType':c['buType'],'name':c['name'],'net':c['net'],'minutes':30,'lat':c['lat'],'lng':c['lng'],'routingFallback':True}; features.append(f); write_output(features); success=True; break
            except Exception as e: print(f'Fallback fehlgeschlagen ({dlat},{dlng}): {e}',flush=True)
        if success: failures=[x for x in failures if x[0]!=i]

    # Strikte Endvalidierung: exakt ein Fahrzeitgebiet je Standort.
    feature_keys=[key_for({'net':(f.get('properties') or {}).get('net',''),'lat':float((f.get('properties') or {}).get('lat')),'lng':float((f.get('properties') or {}).get('lng'))}) for f in features]
    expected_keys=[key_for(c) for c in centers]
    missing=[k for k in expected_keys if k not in feature_keys]
    duplicates=len(feature_keys)-len(set(feature_keys))
    if failures or missing or duplicates or len(features)!=EXPECTED_CENTERS:
        print(f'VALIDIERUNG FEHLGESCHLAGEN: features={len(features)}, missing={len(missing)}, duplicates={duplicates}, failures={len(failures)}',flush=True)
        for _,c,e in failures: print(f'OFFEN: {c["name"]} ({c["net"]}, {c["buType"]}) – {e}',flush=True)
        raise SystemExit(1)
    write_output(features)
    print(f'ERFOLG: {len(features)} Standorte = {len(features)} eindeutig zugeordnete 30-Minuten-Fahrzeitgebiete.',flush=True)

if __name__=='__main__': main()
