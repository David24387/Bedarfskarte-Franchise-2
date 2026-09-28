#!/usr/bin/env python3
import json, math, urllib.parse, urllib.request, urllib.error, time, statistics
from pathlib import Path

CATALOG="https://regionalatlas.statistikportal.de/taskrunner/services.json"
QUERY="https://www.gis-idmz.nrw.de/arcgis/rest/services/stba/regionalatlas/MapServer/dynamicLayer/query"
COUNTIES="https://raw.githubusercontent.com/m-ad/geofeatures-ags-germany/master/geojson/counties.json"
METRICS={
 "popDensity":{"code":"AI002-1-5","field":"AI0201","weight":.30,"label":"Bevölkerungsdichte","unit":"EW/km²"},
 "pkwDensity":{"code":"AI013-1","field":"AI1301","weight":.25,"label":"Pkw-Dichte","unit":"Pkw je 1.000 EW"},
 "income":{"code":"AI016-1","field":"AI1601","weight":.25,"label":"Verfügbares Einkommen","unit":"€ je Einwohner"},
 "workDensity":{"code":"AI007-1","field":"AI0701","weight":.20,"label":"Arbeitsplatzdichte","unit":"je 1.000 EW"},
}
LEVEL_LABEL={5:"Gemeinde / Verbandsgemeinde",3:"Kreis / kreisfreie Stadt"}
UA={"User-Agent":"Euromaster-Franchise-Potential/3.1"}
TIMEOUT=25
PAGE_SIZE=1000
MAX_PAGES=20

def get_json(url,timeout=TIMEOUT):
 req=urllib.request.Request(url,headers=UA)
 with urllib.request.urlopen(req,timeout=timeout) as r:return json.load(r)

def index_catalog(cat):
 out={}
 def walk(x):
  if isinstance(x,dict):
   if x.get('code'):out[x['code']]=x
   for v in x.values():walk(v)
  elif isinstance(x,list):
   for v in x:walk(v)
 walk(cat);return out

def years(item):return sorted([int(y) for y in (item.get('years') or {}) if str(y).isdigit()],reverse=True)
def attr(a,n):
 for k,v in (a or {}).items():
  if str(k).lower()==n.lower():return v
 return None

def ags(v,level):
 if v is None:return ''
 s=''.join(c for c in str(v).split('.')[0] if c.isdigit())
 return s.zfill(8 if level==5 else 5) if s else ''

def layer_def(code,year,level):
 table=code.lower().replace('-','_')
 sql=f"SELECT * FROM verwaltungsgrenzen_gesamt LEFT OUTER JOIN {table} ON ags = ags2 and jahr = jahr2 WHERE typ = {level} AND jahr = {year} AND (jahr2 = {year} OR jahr2 IS NULL)"
 return {"source":{"dataSource":{"geometryType":"esriGeometryPolygon","workspaceId":"gdb","query":sql,"oidFields":"id","spatialReference":{"wkid":25832},"type":"queryTable"},"type":"dataLayer"}}

def request_page(code,field,year,level,offset,geometry):
 params={'layer':json.dumps(layer_def(code,year,level),separators=(',',':')),'f':'json',
         'outFields':f'ags,gen,{field},jahr2','returnGeometry':'true' if geometry else 'false',
         'outSR':'4326','spatialRel':'esriSpatialRelIntersects','where':'1=1',
         'resultOffset':str(offset),'resultRecordCount':str(PAGE_SIZE),'orderByFields':'ags'}
 url=QUERY+'?'+urllib.parse.urlencode(params)
 return get_json(url)

def query(code,field,year,level):
 # First do a cheap attribute-only probe. Geometry is requested only after the level/year proves useful.
 try:
  probe=request_page(code,field,year,level,0,False)
 except Exception as e:
  print(f'WARN probe {code} {year} level {level}: {type(e).__name__}: {e}',flush=True);return []
 if probe.get('error'):
  print('WARN API',code,year,level,probe['error'],flush=True);return []
 probe_features=probe.get('features') or []
 usable_probe=sum(1 for f in probe_features if attr(f.get('attributes',{}),field) not in (None,''))
 if not probe_features or usable_probe==0:
  print(code,year,'level',level,': no usable probe rows',flush=True);return []

 out=[];offset=0
 for page in range(MAX_PAGES):
  try:d=request_page(code,field,year,level,offset,True)
  except Exception as e:
   print(f'WARN page {page+1} {code} {year} level {level}: {type(e).__name__}: {e}',flush=True);return []
  if d.get('error'):
   print('WARN API page',code,year,level,d['error'],flush=True);return []
  fs=d.get('features') or []
  for f in fs:
   a=f.get('attributes',{});raw=attr(a,field)
   try:v=float(raw)
   except (TypeError,ValueError):continue
   if not math.isfinite(v):continue
   rings=(f.get('geometry') or {}).get('rings')
   if not rings:continue
   out.append({'ags':ags(attr(a,'ags'),level),'name':str(attr(a,'gen') or '').strip(),'value':v,
               'geometry':{'type':'Polygon','coordinates':rings}})
  print(code,year,'level',level,'page',page+1,':',len(fs),'rows; total',len(out),flush=True)
  if len(fs)<PAGE_SIZE:break
  offset+=len(fs)
 else:
  print('WARN max pages reached for',code,year,level,flush=True);return []
 return out

def newest_finest(code,field,item):
 attempts=[]
 # Try only the newest three catalog years per level. This prevents stale/empty catalog entries from causing long runs.
 candidate_years=years(item)[:3]
 for level in (5,3):
  for year in candidate_years:
   attempts.append({'level':level,'year':year})
   started=time.monotonic();data=query(code,field,year,level)
   print('attempt seconds:',round(time.monotonic()-started,1),flush=True)
   minimum=1000 if level==5 else 350
   if len(data)>=minimum:return level,year,data,attempts
 return None,None,[],attempts

def pct(vals,v):
 a=sorted(vals);return sum(x<=v for x in a)/len(a) if a else None

def main():
 cat=index_catalog(get_json(CATALOG));metric_layers={};meta={};audit={}
 for key,m in METRICS.items():
  item=cat.get(m['code'])
  if not item:raise RuntimeError('Missing catalog indicator '+m['code'])
  print('\n===',key,m['code'],'===',flush=True)
  level,year,data,attempts=newest_finest(m['code'],m['field'],item)
  if not data:raise RuntimeError('No usable data for '+key+' attempts='+json.dumps(attempts))
  vals=[x['value'] for x in data]
  for x in data:x['pct']=pct(vals,x['value'])
  metric_layers[key]=data
  meta[key]={'code':m['code'],'field':m['field'],'label':m['label'],'unit':m['unit'],'year':year,'level':level,
             'levelLabel':LEVEL_LABEL[level],'weight':m['weight'],'attempts':attempts}
  audit[key]={'rows':len(data),'min':min(vals),'median':statistics.median(vals),'max':max(vals),'level':level,'year':year}

 geo=get_json(COUNTIES);districts=[]
 for f in geo.get('features',[]):
  aid=ags(f.get('id') or (f.get('properties') or {}).get('id'),3)
  if aid:districts.append({'ags':aid,'name':(f.get('properties') or {}).get('name',''),'geometry':f['geometry']})
 payload={'source':'Regionalatlas Deutschland – Statistische Ämter des Bundes und der Länder',
  'methodology':'Each KPI uses the finest usable official Regionalatlas geography: municipality/association where available, otherwise district. Values include source year and level. Disposable income is not commercial purchasing power.',
  'metrics':meta,'audit':audit,'metricLayers':metric_layers,'districts':districts}
 Path('regionaldaten.json').write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
 Path('regionaldaten_audit.json').write_text(json.dumps({'metrics':meta,'audit':audit},ensure_ascii=False,indent=2),encoding='utf-8')
 print('AUDIT OK',json.dumps(audit,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
