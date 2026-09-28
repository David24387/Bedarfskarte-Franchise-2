#!/usr/bin/env python3
import json, math, urllib.parse, urllib.request, time, statistics
from pathlib import Path

CATALOG="https://regionalatlas.statistikportal.de/taskrunner/services.json"
QUERY="https://www.gis-idmz.nrw.de/arcgis/rest/services/stba/regionalatlas/MapServer/dynamicLayer/query"
COUNTIES="https://raw.githubusercontent.com/m-ad/geofeatures-ags-germany/master/geojson/counties.json"
METRICS={
 "popDensity":{"code":"AI002-1-5","field":"AI0201","weight":.30,"label":"Bevölkerungsdichte","unit":"EW/km²","valid":(0.1,30000)},
 "pkwDensity":{"code":"AI013-1","field":"AI1301","weight":.25,"label":"Pkw-Dichte","unit":"Pkw je 1.000 EW","valid":(100,2000)},
 "income":{"code":"AI016-1","field":"AI1601","weight":.25,"label":"Verfügbares Einkommen","unit":"€ je Einwohner","valid":(10000,100000)},
 "workDensity":{"code":"AI007-1","field":"AI0701","weight":.20,"label":"Arbeitsplatzdichte","unit":"je 1.000 EW","valid":(0,5000)},
}
LEVEL_LABEL={5:"Gemeinde / Verbandsgemeinde",3:"Kreis / kreisfreie Stadt"}
UA={"User-Agent":"Euromaster-Franchise-Potential/3.3"}
TIMEOUT=25; PAGE_SIZE=1000; MAX_PAGES=20
GEOMETRY_PRECISION=4
MAX_ALLOWABLE_OFFSET=0.001

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
 if geometry:
  params['geometryPrecision']=str(GEOMETRY_PRECISION)
  params['maxAllowableOffset']=str(MAX_ALLOWABLE_OFFSET)
 url=QUERY+'?'+urllib.parse.urlencode(params)
 return get_json(url)

def query(code,field,year,level,valid_range):
 try:probe=request_page(code,field,year,level,0,False)
 except Exception as e:
  print(f'WARN probe {code} {year} level {level}: {type(e).__name__}: {e}',flush=True);return []
 if probe.get('error'):print('WARN API',code,year,level,probe['error'],flush=True);return []
 if not any(attr(f.get('attributes',{}),field) not in (None,'') for f in (probe.get('features') or [])):
  print(code,year,'level',level,': no usable probe rows',flush=True);return []
 out=[];offset=0;invalid=0;lo,hi=valid_range
 for page in range(MAX_PAGES):
  try:d=request_page(code,field,year,level,offset,True)
  except Exception as e:
   print(f'WARN page {page+1} {code} {year} level {level}: {type(e).__name__}: {e}',flush=True);return []
  if d.get('error'):print('WARN API page',code,year,level,d['error'],flush=True);return []
  fs=d.get('features') or []
  for f in fs:
   a=f.get('attributes',{});raw=attr(a,field)
   try:v=float(raw)
   except (TypeError,ValueError):continue
   if not math.isfinite(v) or not (lo<=v<=hi):invalid+=1;continue
   rings=(f.get('geometry') or {}).get('rings')
   if not rings:continue
   out.append({'ags':ags(attr(a,'ags'),level),'name':str(attr(a,'gen') or '').strip(),'value':v,'geometry':{'type':'Polygon','coordinates':rings}})
  print(code,year,'level',level,'page',page+1,':',len(fs),'rows; valid',len(out),'invalid',invalid,flush=True)
  if len(fs)<PAGE_SIZE:break
  offset+=len(fs)
 else:return []
 return out

def newest_finest(code,field,item,valid_range):
 attempts=[]
 for level in (5,3):
  for year in years(item)[:3]:
   attempts.append({'level':level,'year':year});started=time.monotonic();data=query(code,field,year,level,valid_range)
   print('attempt seconds:',round(time.monotonic()-started,1),flush=True)
   if len(data)>=(1000 if level==5 else 350):return level,year,data,attempts
 return None,None,[],attempts

def add_percentiles(data):
 vals=sorted(x['value'] for x in data);n=len(vals)
 import bisect
 for x in data:x['pct']=bisect.bisect_right(vals,x['value'])/n

def round_geometry(g,precision=4):
 def rec(x):
  if isinstance(x,list):return [rec(v) for v in x]
  if isinstance(x,float):return round(x,precision)
  return x
 return {'type':g.get('type'),'coordinates':rec(g.get('coordinates',[]))}

def lookup_for_metric(rows,level):
 return {x['ags']:x for x in rows if x.get('ags')}

def build_regions(metric_layers,meta):
 # The map already consumes a flat `regions` array. Population density is the
 # finest available layer and therefore defines the displayed local geometry.
 # Metrics only available at district level are joined via the first 5 AGS digits.
 base=metric_layers['popDensity']
 lookups={k:lookup_for_metric(v,meta[k]['level']) for k,v in metric_layers.items()}
 regions=[];missing={k:0 for k in METRICS}
 for b in base:
  aid=b.get('ags',''); values={}; pcts={}; levels={}
  for key in METRICS:
   level=meta[key]['level']
   key_id=aid if level==5 else aid[:5]
   row=lookups[key].get(key_id)
   if row:
    values[key]=row['value'];pcts[key]=row['pct'];levels[key]=meta[key]['levelLabel']
   else:
    values[key]=None;pcts[key]=None;levels[key]=meta[key]['levelLabel'];missing[key]+=1
  available=[(METRICS[k]['weight'],pcts[k]) for k in METRICS if pcts[k] is not None]
  weight_sum=sum(w for w,_ in available)
  score=round(100*sum(w*p for w,p in available)/weight_sum) if weight_sum else None
  regions.append({
   'ags':aid,'name':b.get('name',''),'geometry':round_geometry(b['geometry']),
   'score':score,'popDensity':values['popDensity'],'pkwDensity':values['pkwDensity'],
   'income':values['income'],'workDensity':values['workDensity'],'dataLevels':levels
  })
 print('map regions:',len(regions),'missing joins:',missing,flush=True)
 return regions,missing

def main():
 cat=index_catalog(get_json(CATALOG));metric_layers={};meta={};audit={}
 for key,m in METRICS.items():
  item=cat.get(m['code'])
  if not item:raise RuntimeError('Missing catalog indicator '+m['code'])
  print('\n===',key,m['code'],'===',flush=True)
  level,year,data,attempts=newest_finest(m['code'],m['field'],item,m['valid'])
  if not data:raise RuntimeError('No usable data for '+key)
  add_percentiles(data);vals=[x['value'] for x in data];metric_layers[key]=data
  meta[key]={'code':m['code'],'field':m['field'],'label':m['label'],'unit':m['unit'],'year':year,'level':level,'levelLabel':LEVEL_LABEL[level],'weight':m['weight'],'attempts':attempts}
  audit[key]={'rows':len(data),'min':min(vals),'median':statistics.median(vals),'max':max(vals),'level':level,'year':year}

 regions,missing_joins=build_regions(metric_layers,meta)
 geo=get_json(COUNTIES);districts=[]
 for f in geo.get('features',[]):
  aid=ags(f.get('id') or (f.get('properties') or {}).get('id'),3)
  if aid:districts.append({'ags':aid,'name':(f.get('properties') or {}).get('name',''),'geometry':round_geometry(f['geometry'])})
 payload={'source':'Regionalatlas Deutschland – Statistische Ämter des Bundes und der Länder','methodology':'Each KPI uses the finest usable official Regionalatlas geography. The web-map regions use the finest population-density geometry; district-level KPIs are joined by AGS and clearly retain their source level. Score is a weighted percentile score over all available KPIs. Disposable income is not commercial purchasing power.','metrics':meta,'audit':audit,'regions':regions,'metricLayers':metric_layers,'districts':districts}
 raw=json.dumps(payload,ensure_ascii=False,separators=(',',':'))
 size=len(raw.encode('utf-8'))
 print('regionaldaten.json size:',round(size/1024/1024,2),'MB',flush=True)
 if size>90*1024*1024:raise RuntimeError(f'regionaldaten.json still too large: {size/1024/1024:.1f} MB')
 Path('regionaldaten.json').write_text(raw,encoding='utf-8')
 Path('regionaldaten_audit.json').write_text(json.dumps({'metrics':meta,'audit':audit,'mapRegions':len(regions),'missingJoins':missing_joins,'fileSizeMB':round(size/1024/1024,2)},ensure_ascii=False,indent=2),encoding='utf-8')
 print('AUDIT OK',json.dumps(audit,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
