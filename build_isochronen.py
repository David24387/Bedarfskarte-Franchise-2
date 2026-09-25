#!/usr/bin/env python3
import csv, json, os, sys, time, urllib.request, urllib.error
from pathlib import Path

API_KEY=os.environ.get('ORS_API_KEY','').strip()
ENDPOINT='https://api.heigit.org/openrouteservice/v2/isochrones/driving-car'
RANGE_SECONDS=30*60

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
    if 'mixed' in x or ('light' in x and 'heavy' in x): return 'Mixed'
    if 'heavy' in x: return 'Heavy'
    if 'light' in x: return 'Light'
    return 'Unknown'

def request_isochrone(lon,lat):
    body=json.dumps({'locations':[[lon,lat]],'range':[RANGE_SECONDS],'range_type':'time','location_type':'start'}).encode()
    req=urllib.request.Request(ENDPOINT,data=body,headers={
        'Authorization':API_KEY,'Content-Type':'application/json','Accept':'application/geo+json','User-Agent':'Euromaster-Bedarfskarte/2.0'
    },method='POST')
    with urllib.request.urlopen(req,timeout=90) as r:
        return json.load(r)

def main():
    p=Path('daten.csv')
    rows=list(csv.reader(p.open(encoding='utf-8-sig',newline='')))
    hi=find_header(rows); headers=[norm(x) for x in rows[hi]]
    centers=[]
    for vals in rows[hi+1:]:
        d={headers[i]: vals[i] if i<len(vals) else '' for i in range(len(headers)) if headers[i]}
        lat=num(get(d,'Lat.','Lat','Latitude')); lon=num(get(d,'Long.','Long','Lng','Longitude'))
        if lat is None or lon is None: continue
        bu=bu_type(get(d,'BU'))
        if bu=='Unknown': continue
        centers.append({'lat':lat,'lng':lon,'buType':bu,'name':norm(get(d,'Ort','KST','Netzkennung'))})
    if not centers: raise SystemExit('Keine Center mit Koordinaten/BU in daten.csv gefunden.')

    features=[]
    for i,c in enumerate(centers,1):
        print(f'Isochrone {i}/{len(centers)}: {c["name"]} ({c["buType"]})',flush=True)
        try:
            data=request_isochrone(c['lng'],c['lat'])
        except urllib.error.HTTPError as e:
            msg=e.read().decode('utf-8','replace')
            raise RuntimeError(f'ORS HTTP {e.code}: {msg[:500]}')
        fs=data.get('features') or []
        if not fs: raise RuntimeError(f'Keine Isochrone für {c["name"]}')
        f=fs[0]
        f['properties']={'buType':c['buType'],'name':c['name'],'minutes':30,'lat':c['lat'],'lng':c['lng']}
        features.append(f)
        time.sleep(.15)
    out={'type':'FeatureCollection','properties':{'minutes':30,'profile':'driving-car','source':'openrouteservice / OpenStreetMap'},'features':features}
    Path('isochronen.json').write_text(json.dumps(out,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    print(f'Erzeugt: {len(features)} 30-Minuten-Fahrzeitgebiete')

if __name__=='__main__': main()
