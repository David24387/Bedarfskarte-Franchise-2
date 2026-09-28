#!/usr/bin/env python3
import json, math, urllib.parse, urllib.request, time, statistics
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
UA={"User-Agent":"Euromaster-Franchise-Potential/3.0"}

def get_json(url):
 req=urllib.request.Request(url,headers=UA)
 with urllib.request.urlopen(req,timeout=120) as r:return json.load(r)

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

def query(code,field,year,level):
 table=code.lower().replace('-','_')
 sql=f"SELECT * FROM verwaltungsgrenzen_gesamt LEFT OUTER JOIN {table} ON ags = ags2 and jahr = jahr2 WHERE typ = {level} AND jahr = {year} AND (jahr2 = {year} OR jahr2 IS NULL)"
 layer={"source":{"dataSource":{"geometryType":"esriGeometryPolygon","workspaceId":"gdb","query":sql,"oidFields":"id","spatialReference":{"wkid":25832},"type":"queryTable"},"type":"dataLayer"}}
 q=urllib.parse.urlencode({'layer':json.dumps(layer,separators=(',',':')),'f':'json','outFields':f'ags,gen,{field},jahr2','returnGeometry':'true','outSR':'4326','spatialRel':'esriSpatialRelIntersects','where':'1=1','resultRecordCount':'20000'})
 d=get_json(QUERY+'?'+q)
 if d.get('error'):raise RuntimeError(str(d['error']))
 out=[]
 for f in d.get('features',[]):
  a=f.get('attributes',{});raw=attr(a,field)
  try:v=float(raw)
  except:continue
  if not math.isfinite(v):continue
  g=f.get('geometry') or {}; rings=g.get('rings')
  if not rings:continue
  # Esri rings -> GeoJSON Polygon. Regionalatlas admin geometries are adequate for point lookup.
  geom={'type':'Polygon','coordinates':rings}
  out.append({'ags':ags(attr(a,'ags'),level),'name':str(attr(a,'gen') or '').strip(),'value':v,'geometry':geom})
 print(code,year,'level',level,':',len(out),'usable rows')
 return out

def newest_finest(code,field,item):
 # Prefer municipality data. If the indicator has no usable municipality values, fall back to districts.
 attempts=[]
 for level in (5,3):
  for year in years(item):
   attempts.append({'level':level,'year':year})
   data=query(code,field,year,level)
   minimum=1000 if level==5 else 350
   if len(data)>=minimum:return level,year,data,attempts
   time.sleep(.15)
 return None,None,[],attempts

def pct(vals,v):
 a=sorted(vals)
 return sum(x<=v for x in a)/len(a) if a else None

def main():
 cat=index_catalog(get_json(CATALOG)); metric_layers={};meta={};audit={}
 for key,m in METRICS.items():
  item=cat.get(m['code'])
  if not item:raise RuntimeError('Missing catalog indicator '+m['code'])
  level,year,data,attempts=newest_finest(m['code'],m['field'],item)
  if not data:raise RuntimeError('No usable data for '+key)
  vals=[x['value'] for x in data]
  for x in data:x['pct']=pct(vals,x['value'])
  metric_layers[key]=data
  meta[key]={'code':m['code'],'field':m['field'],'label':m['label'],'unit':m['unit'],'year':year,'level':level,'levelLabel':LEVEL_LABEL[level],'weight':m['weight'],'attempts':attempts}
  audit[key]={'rows':len(data),'min':min(vals),'median':statistics.median(vals),'max':max(vals),'level':level,'year':year}

 # Keep district geometry layer for robust nationwide fallback / hotspot rendering.
 geo=get_json(COUNTIES); districts=[]
 for f in geo.get('features',[]):
  aid=ags(f.get('id') or (f.get('properties') or {}).get('id'),3)
  if aid:districts.append({'ags':aid,'name':(f.get('properties') or {}).get('name',''),'geometry':f['geometry']})

 payload={'source':'Regionalatlas Deutschland – Statistische Ämter des Bundes und der Länder',
  'methodology':'Each KPI uses the finest usable official Regionalatlas geography: municipality/association where available, otherwise district. Values include source year and level. Disposable income is not commercial purchasing power.',
  'metrics':meta,'audit':audit,'metricLayers':metric_layers,'districts':districts}
 Path('regionaldaten.json').write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
 Path('regionaldaten_audit.json').write_text(json.dumps({'metrics':meta,'audit':audit},ensure_ascii=False,indent=2),encoding='utf-8')
 print('AUDIT OK',json.dumps(audit,ensure_ascii=False))

if __name__=='__main__':main()
