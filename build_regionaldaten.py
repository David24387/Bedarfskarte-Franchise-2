#!/usr/bin/env python3
import json, math, urllib.parse, urllib.request, time
from pathlib import Path
CATALOG="https://regionalatlas.statistikportal.de/taskrunner/services.json"
QUERY="https://www.gis-idmz.nrw.de/arcgis/rest/services/stba/regionalatlas/MapServer/dynamicLayer/query"
COUNTIES="https://raw.githubusercontent.com/m-ad/geofeatures-ags-germany/master/geojson/counties.json"
METRICS={"popDensity":{"code":"AI002-1-5","field":"AI0201","weight":.30},"pkwDensity":{"code":"AI013-1","field":"AI1301","weight":.25},"income":{"code":"AI016-1","field":"AI1601","weight":.25},"workDensity":{"code":"AI007-1","field":"AI0701","weight":.20}}
UA={"User-Agent":"Euromaster-Franchise-Potential/1.0"}
def get_json(url):
    with urllib.request.urlopen(urllib.request.Request(url,headers=UA),timeout=90) as r:return json.load(r)
def index_catalog(cat):
    out={}
    def walk(x):
        if isinstance(x,dict):
            if x.get("code"):out[x["code"]]=x
            for v in x.values():walk(v)
        elif isinstance(x,list):
            for v in x:walk(v)
    walk(cat);return out
def latest(item):
    ys=[int(y) for y in (item.get("years") or {}) if str(y).isdigit()]
    if not ys:raise RuntimeError("Keine Jahre: "+str(item.get("code")))
    return max(ys)
def query_metric(code,field,year):
    table=code.lower().replace("-","_")
    sql=f"SELECT * FROM verwaltungsgrenzen_gesamt LEFT OUTER JOIN {table} ON ags = ags2 and jahr = jahr2 WHERE typ = 3 AND jahr = {year} AND (jahr2 = {year} OR jahr2 IS NULL)"
    layer={"source":{"dataSource":{"geometryType":"esriGeometryPolygon","workspaceId":"gdb","query":sql,"oidFields":"id","spatialReference":{"wkid":25832},"type":"queryTable"},"type":"dataLayer"}}
    q=urllib.parse.urlencode({"layer":json.dumps(layer,separators=(",",":")),"f":"json","outFields":f"ags,gen,{field},jahr2","returnGeometry":"false","spatialRel":"esriSpatialRelIntersects","where":"1=1","resultRecordCount":"1000"})
    d=get_json(QUERY+"?"+q)
    if d.get("error"):raise RuntimeError(str(d["error"]))
    out={}
    for f in d.get("features",[]):
        a=f.get("attributes",{});ags=str(a.get("ags") or "").zfill(5)
        try:v=float(a.get(field))
        except:continue
        out[ags]={"value":v,"name":str(a.get("gen") or "").strip()}
    return out
def pct(vals,v):
    a=sorted(x for x in vals if isinstance(x,(int,float)) and math.isfinite(x))
    return sum(x<=v for x in a)/len(a) if a else None
def main():
    cat=index_catalog(get_json(CATALOG));geo=get_json(COUNTIES)
    geom={str(f.get("id") or "").zfill(5):f["geometry"] for f in geo.get("features",[])}
    rows={};years={}
    for key,m in METRICS.items():
        item=cat.get(m["code"])
        if not item:raise RuntimeError("Fehlt im Katalog: "+m["code"])
        year=latest(item);years[key]=year;data=query_metric(m["code"],m["field"],year)
        for ags,d in data.items():
            rows.setdefault(ags,{"ags":ags,"name":d["name"]});rows[ags][key]=d["value"]
        time.sleep(.3)
    regs=[r for ags,r in rows.items() if ags in geom]
    for key in METRICS:
        vals=[r[key] for r in regs if key in r]
        for r in regs:r[key+"Pct"]=pct(vals,r[key]) if key in r else None
    for r in regs:
        num=den=0
        for key,m in METRICS.items():
            p=r.get(key+"Pct")
            if p is not None:num+=p*m["weight"];den+=m["weight"]
        r["score"]=round(100*num/den) if den else None;r["geometry"]=geom[r["ags"]]
    ranked=sorted([r for r in regs if r["score"] is not None],key=lambda x:x["score"],reverse=True)
    for i,r in enumerate(ranked,1):r["rank"]=i;r["rankTotal"]=len(ranked)
    Path("regionaldaten.json").write_text(json.dumps({"source":"Regionalatlas Deutschland – Statistische Ämter des Bundes und der Länder","years":years,"regions":regs},ensure_ascii=False,separators=(",",":")),encoding="utf-8")
    print("Erzeugt:",len(regs),"Kreise",years)
if __name__=="__main__":main()
