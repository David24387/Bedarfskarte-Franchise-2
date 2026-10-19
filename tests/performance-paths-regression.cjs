// Run: node tests/performance-paths-regression.cjs /path/to/turf.min.js
const fs=require('fs'),vm=require('vm'),cp=require('child_process'),assert=require('assert/strict'),turf=require(process.argv[2]);
const old=cp.execFileSync('git',['show',(process.env.BASELINE_REF||'HEAD')+':index.html'],{encoding:'utf8'}),html=fs.readFileSync('index.html','utf8');
const regional=JSON.parse(fs.readFileSync('regionaldaten.json')).regions;
const contexts=[old,html].map(source=>{const c=vm.createContext({turf,regional:structuredClone(regional)});vm.runInContext(source.match(/function potential\([^\n]+/)[0],c);return c});
let tested=0;for(let i=0;i<regional.length;i+=113){const r=regional[i];if(!r.geometry)continue;const [lng,lat]=turf.centroid({type:'Feature',properties:{},geometry:r.geometry}).geometry.coordinates;for(const c of contexts){c.lat=lat;c.lng=lng}assert.equal(vm.runInContext('potential(lat,lng,true)',contexts[0]),vm.runInContext('potential(lat,lng,true)',contexts[1]));tested++}
const c=vm.createContext({samples:new Uint8Array([1,2,3,4,5]),calls:0,demandWorker:{postMessage(){throw Error('Completed samples must bypass worker')}},map:{unproject(){throw Error('Completed samples must bypass projection')}}});
vm.runInContext(html.slice(html.indexOf('function prepareDemandSamples('),html.indexOf('function cancelDemandTile(')),c);
vm.runInContext('prepareDemandSamples({},null,null,null,samples,result=>{if(result!==samples)throw Error("Cache was not reused");calls++})',c);assert.equal(c.calls,1);
console.log({identicalRegionalPopups:tested,completeTileBypassesWorker:true});
