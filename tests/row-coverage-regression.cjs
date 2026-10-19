// Run: node tests/row-coverage-regression.cjs /path/to/turf.min.js
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict'),turf=require(process.argv[2]);
const html=fs.readFileSync('index.html','utf8'),iso=JSON.parse(fs.readFileSync('isochronen.json')).features;
iso.forEach(f=>f._bbox=turf.bbox(f));
const c=vm.createContext({turf,iso});
vm.runInContext(html.match(/function featureContains\([^\n]+/)[0],c);
vm.runInContext(html.slice(html.indexOf('const spatialIndex='),html.indexOf('function coverage('))+'indexIsochrones();',c);
vm.runInContext(html.match(/function coverageState\([^\n]+/)[0],c);
vm.runInContext(html.slice(html.indexOf('const rowEdges='),html.indexOf('// Heavy point-in-polygon')),c);
let count=0;const t=performance.now();
for(const z of [5,6,7,9,10])for(const lat of [47.4,48.1,50.11,51.3,53.7,54.5]){
 const span=720/2**z,lngs=Array.from({length:130},(_,x)=>10+(x-65)*span/128);
 c.lat=lat;c.lngs=lngs;
 const actual=vm.runInContext('(()=>{const rows=rowCoverage(lat,lngs);return lngs.map(lng=>rowState(rows,lat,lng))})()',c);
 const expected=vm.runInContext('lngs.map(lng=>coverageState(lat,lng))',c);
 assert.deepEqual(Array.from(actual),Array.from(expected));count+=lngs.length;
}
for(const f of iso){const polygons=f.geometry.type==='Polygon'?[f.geometry.coordinates]:f.geometry.coordinates;for(const rings of polygons)for(const ring of rings)for(let i=0;i<ring.length;i+=Math.max(1,Math.floor(ring.length/5))){const [lng,lat]=ring[i];c.lat=lat;c.lngs=[lng-1e-10,lng,lng+1e-10];const result=vm.runInContext('(()=>{const rows=rowCoverage(lat,lngs);return lngs.map(lng=>[rowState(rows,lat,lng),coverageState(lat,lng)])})()',c);for(const pair of result)assert.equal(pair[0],pair[1]);count+=3;}}
console.log({points:count,mismatches:0,ms:Math.round(performance.now()-t)});
