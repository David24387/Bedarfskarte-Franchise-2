// Run: node tests/country-regression.cjs /path/to/turf.min.js /path/to/germany.geo.json
const fs=require('node:fs'),vm=require('node:vm'),cp=require('node:child_process'),assert=require('node:assert/strict');
const turf=require(process.argv[2]),gj=JSON.parse(fs.readFileSync(process.argv[3])),germany=gj.features[0],html=fs.readFileSync('index.html','utf8'),base=cp.execFileSync('git',['show','dfb6d75:index.html'],{encoding:'utf8'});
const old=vm.createContext({turf,germany}),next=vm.createContext({turf,germany});vm.runInContext(base.match(/function insideDE\([^\n]+/)[0],old);vm.runInContext(html.slice(html.indexOf('const COUNTRY_CELL='),html.indexOf('function bu('))+'indexCountry();',next);
const points=[];for(let lat=46;lat<=56;lat+=.025)for(let lng=4;lng<=17;lng+=.025)points.push([lat,lng]);
for(const polygon of germany.geometry.coordinates)for(const ring of polygon)for(let i=0;i<ring.length;i++){const p=ring[i],q=ring[(i+1)%ring.length];for(const d of [-1e-9,0,1e-9])points.push([p[1]+d,p[0]+d],[(p[1]+q[1])/2+d,(p[0]+q[0])/2+d]);}
for(let lat=47;lat<=55.2;lat+=.1)for(let lng=5.5;lng<=15.6;lng+=.1)for(const d of [-1e-10,0,1e-10])points.push([lat+d,lng+d]);
for(const c of [old,next])c.points=points;function run(c){const t=performance.now(),values=vm.runInContext('points.map(([lat,lng])=>insideDE(lat,lng))',c);return {ms:performance.now()-t,values:Array.from(values)}}const a=run(old),b=run(next);assert.deepEqual(b.values,a.values);console.log({points:points.length,mismatches:0,baselineMs:a.ms,optimizedMs:b.ms,speedup:a.ms/b.ms});
