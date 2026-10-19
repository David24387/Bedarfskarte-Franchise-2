// Run: node tests/coverage-regression.cjs /path/to/turf.min.js
const fs=require('node:fs'),vm=require('node:vm'),cp=require('node:child_process'),assert=require('node:assert/strict');
const turf=require(process.argv[2]);
const base=cp.execFileSync('git',['show',(process.env.BASELINE_REF||'HEAD')+':index.html'],{encoding:'utf8'});
const head=fs.readFileSync('index.html','utf8');
const iso=JSON.parse(fs.readFileSync('isochronen.json')).features;
iso.forEach(f=>f._bbox=turf.bbox(f));
function context(html){const c=vm.createContext({turf,iso});const contains=html.match(/function featureContains\([^\n]+/)[0];const coverage=html.match(/function coverage\([^\n]+/)[0];const index=html.includes('const spatialIndex=')?html.slice(html.indexOf('const spatialIndex='),html.indexOf('function coverage(')):'';vm.runInContext(contains+'\n'+index+'\n'+coverage+(index?'\nindexIsochrones();':''),c);return c;}
const old=context(base),next=context(head),points=[];
for(let lat=47;lat<=55.2;lat+=.08)for(let lng=5.5;lng<=15.5;lng+=.08)points.push([lat,lng]);
for(const f of iso){const b=f._bbox;points.push([b[1],b[0]],[b[3],b[2]],[(b[1]+b[3])/2,(b[0]+b[2])/2]);const coords=f.geometry.type==='Polygon'?f.geometry.coordinates:f.geometry.coordinates.flat();for(const ring of coords)for(let i=0;i<ring.length;i+=Math.max(1,Math.floor(ring.length/10)))points.push([ring[i][1],ring[i][0]]);}
// Exact cell borders and adjacent floating point values.
for(let lat=47;lat<=55;lat+=.5)for(let lng=5.5;lng<=15.5;lng+=.5)for(const d of [-1e-10,0,1e-10])points.push([lat+d,lng+d]);
function run(c){c.points=points;const start=performance.now();const result=vm.runInContext('points.map(([lat,lng])=>{const s=coverage(lat,lng);return [s.light,s.heavy,s.state,s.near.map(f=>iso.indexOf(f))]})',c);return{ms:performance.now()-start,result:JSON.parse(JSON.stringify(result))};}
const a=run(old),b=run(next);assert.deepEqual(b.result,a.result);
for(const path of ['daten.csv','isochronen.json','regionaldaten.json'])assert.equal(cp.execFileSync('git',['diff',process.env.BASELINE_REF||'HEAD','--',path],{encoding:'utf8'}),'');
console.log(JSON.stringify({points:points.length,mismatches:0,baselineMs:a.ms,optimizedMs:b.ms,speedup:a.ms/b.ms,dataFilesUnchanged:true},null,2));
