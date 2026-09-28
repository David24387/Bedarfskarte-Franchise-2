#!/usr/bin/env python3
import json, math, urllib.parse, urllib.request, time, statistics
from pathlib import Path

CATALOG="https://regionalatlas.statistikportal.de/taskrunner/services.json"
QUERY="https://www.gis-idmz.nrw.de/arcgis/rest/services/stba/regionalatlas/MapServer/dynamicLayer/query"
COUNTIES="https://raw.githubusercontent.com/m-ad/geofeatures-ags-germany/master/geojson/counties.json"

# IMPORTANT: these are official Regionalatlas indicators. "income" is disposable income,
# NOT commercial purchasing power. Labels/units are carried into regionaldaten.json.
METRICS={
    "popDensity":{"code":"AI002-1-5","field":"AI0201","weight":.30,"label":"Bevölkerungsdichte","unit":"EW/km²"},
    "pkwDensity":{"code":"AI013-1","field":"AI1301","weight":.25,"label":"Pkw-Dichte","unit":"Pkw je 1.000 EW"},
    "income":{"code":"AI016-1","field":"AI1601","weight":.25,"label":"Verfügbares Einkommen","unit":"€ je Einwohner"},
    "workDensity":{"code":"AI007-1","field":"AI0701","weight":.20,"label":"Arbeitsplatzdichte","unit":"je 1.000 EW"},
}
LEVEL=3
LEVEL_LABEL="Kreis / kreisfreie Stadt"
UA={"User-Agent":"Euromaster-Franchise-Potential/2.0"}

def get_json(url):
    req=urllib.request.Request(url,headers=UA)
    with urllib.request.urlopen(req,timeout=90) as r:return json.load(r)

def index_catalog(cat):
    out={}
    def walk(x):
        if isinstance(x,dict):
            if x.get("code"):out[x["code"]]=x
            for v in x.values():walk(v)
        elif isinstance(x,list):
            for v in x:walk(v)
    walk(cat);return out

def available_years(item):
    ys=[int(y) for y in (item.get("years") or {}) if str(y).isdigit()]
    if not ys:raise RuntimeError("Keine Jahre: "+str(item.get("code")))
    return sorted(ys,reverse=True)

def attr_ci(attrs,name):
    target=name.lower()
    for k,v in (attrs or {}).items():
        if str(k).lower()==target:return v
    return None

def normalize_ags(value):
    if value is None:return ""
    s=str(value).strip()
    if s.endswith(".0"):s=s[:-2]
    digits="".join(ch for ch in s if ch.isdigit())
    return digits.zfill(5) if digits else ""

def query_metric(code,field,year,level=LEVEL):
    table=code.lower().replace("-","_")
    sql=(f"SELECT * FROM verwaltungsgrenzen_gesamt LEFT OUTER JOIN {table} "
         f"ON ags = ags2 and jahr = jahr2 WHERE typ = {level} AND jahr = {year} "
         f"AND (jahr2 = {year} OR jahr2 IS NULL)")
    layer={"source":{"dataSource":{"geometryType":"esriGeometryPolygon","workspaceId":"gdb","query":sql,
        "oidFields":"id","spatialReference":{"wkid":25832},"type":"queryTable"},"type":"dataLayer"}}
    q=urllib.parse.urlencode({"layer":json.dumps(layer,separators=(",",":")),"f":"json",
        "outFields":f"ags,gen,{field},jahr2","returnGeometry":"false","spatialRel":"esriSpatialRelIntersects",
        "where":"1=1","resultRecordCount":"20000"})
    d=get_json(QUERY+"?"+q)
    if d.get("error"):raise RuntimeError(str(d["error"]))
    out={}; raw_count=len(d.get("features",[]))
    for f in d.get("features",[]):
        a=f.get("attributes",{});ags=normalize_ags(attr_ci(a,"ags"));raw=attr_ci(a,field)
        if not ags:continue
        try:v=float(raw)
        except (TypeError,ValueError):continue
        if not math.isfinite(v):continue
        out[ags]={"value":v,"name":str(attr_ci(a,"gen") or "").strip()}
    print(f"{code} {year} Ebene {level}: {raw_count} Features, {len(out)} Werte")
    return out

def newest_data(code,field,item):
    tried=[]
    for year in available_years(item):
        tried.append(year);data=query_metric(code,field,year)
        if data:return year,data,tried
        time.sleep(.2)
    raise RuntimeError(f"Keine Daten für {code}; Jahre {tried}")

def pct(vals,v):
    a=sorted(x for x in vals if isinstance(x,(int,float)) and math.isfinite(x))
    return sum(x<=v for x in a)/len(a) if a else None

def audit_metric(key,m,data,geom):
    vals=[d["value"] for d in data.values() if math.isfinite(d["value"])]
    matched=set(data)&set(geom);missing_geom=sorted(set(data)-set(geom));missing_data=sorted(set(geom)-set(data))
    if not vals:raise RuntimeError(f"AUDIT {key}: keine numerischen Werte")
    # Broad plausibility guards: catch unit/field/API mistakes, not regional outliers.
    guards={"popDensity":(1,10000),"pkwDensity":(1,2000),"income":(5000,100000),"workDensity":(1,3000)}
    lo,hi=guards[key];bad=[(ags,d["value"]) for ags,d in data.items() if d["value"]<lo or d["value"]>hi]
    report={"rows":len(data),"geometryMatches":len(matched),"missingGeometry":len(missing_geom),
            "missingData":len(missing_data),"min":min(vals),"median":statistics.median(vals),"max":max(vals),
            "plausibilityWarnings":len(bad),"warningExamples":bad[:10]}
    print("AUDIT",key,json.dumps(report,ensure_ascii=False))
    if len(matched)<390:raise RuntimeError(f"AUDIT {key}: nur {len(matched)} Kreis-Geometrien zugeordnet")
    if len(bad)>10:raise RuntimeError(f"AUDIT {key}: {len(bad)} unplausible Werte – Feld/Einheit prüfen")
    return report

def main():
    cat=index_catalog(get_json(CATALOG));geo=get_json(COUNTIES)
    geom={normalize_ags(f.get("id") or (f.get("properties") or {}).get("id")):f["geometry"] for f in geo.get("features",[])}
    geom={k:v for k,v in geom.items() if k};print("Kreisgeometrien:",len(geom))
    rows={};years={};meta={};audit={}
    for key,m in METRICS.items():
        item=cat.get(m["code"])
        if not item:raise RuntimeError("Fehlt im Katalog: "+m["code"])
        year,data,tried=newest_data(m["code"],m["field"],item);years[key]=year
        audit[key]=audit_metric(key,m,data,geom)
        meta[key]={"code":m["code"],"field":m["field"],"label":m["label"],"unit":m["unit"],
                   "year":year,"level":LEVEL,"levelLabel":LEVEL_LABEL,"yearsTried":tried,"weight":m["weight"]}
        for ags,d in data.items():
            rows.setdefault(ags,{"ags":ags,"name":d["name"]})
            if d["name"] and not rows[ags].get("name"):rows[ags]["name"]=d["name"]
            rows[ags][key]=d["value"]
        time.sleep(.3)
    common=set(rows)&set(geom);regs=[rows[a] for a in sorted(common)]
    if len(regs)<390:raise RuntimeError(f"Gesamtaudit fehlgeschlagen: nur {len(regs)} Regionen")
    for key in METRICS:
        vals=[r[key] for r in regs if key in r]
        for r in regs:r[key+"Pct"]=pct(vals,r[key]) if key in r else None
    for r in regs:
        num=den=0
        for key,m in METRICS.items():
            p=r.get(key+"Pct")
            if p is not None:num+=p*m["weight"];den+=m["weight"]
        r["score"]=round(100*num/den) if den else None;r["geometry"]=geom[r["ags"]]
        r["dataLevel"]=LEVEL_LABEL
    ranked=sorted([r for r in regs if r["score"] is not None],key=lambda x:x["score"],reverse=True)
    for i,r in enumerate(ranked,1):r["rank"]=i;r["rankTotal"]=len(ranked)
    payload={"source":"Regionalatlas Deutschland – Statistische Ämter des Bundes und der Länder",
             "methodology":"Amtliche Regionalatlas-KPIs auf Kreisebene. Verfügbares Einkommen ist keine Kaufkraft. Score = gewichtete Deutschland-Perzentile.",
             "level":{"typ":LEVEL,"label":LEVEL_LABEL},"years":years,"metrics":meta,"audit":audit,"regions":regs}
    Path("regionaldaten.json").write_text(json.dumps(payload,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
    Path("regionaldaten_audit.json").write_text(json.dumps({"level":payload["level"],"metrics":meta,"audit":audit},ensure_ascii=False,indent=2),encoding="utf-8")
    print("AUDIT OK – erzeugt:",len(regs),"Kreise",years)

if __name__=="__main__":main()
