// Run from the repository root: node tests/search-regression.cjs
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const html=fs.readFileSync('index.html','utf8');
const source=html.slice(html.indexOf('let timer,'),html.indexOf(";$('centers').onchange"));
const field={value:''},moves=[],analyses=[],pending=[],warnings=[];let scheduled;
const c=vm.createContext({$:()=>field,markers:[{text:'frankfurt 60318 d_1',c:{lat:50.1,lng:8.7,ort:'Frankfurt'}}],map:{setView:(...args)=>moves.push(args)},analyze:(...args)=>analyses.push(args),AbortController,setTimeout:fn=>(scheduled=fn,1),clearTimeout:()=>{scheduled=null},fetch:(url,options)=>new Promise((resolve,reject)=>pending.push({url,options,resolve,reject})),console:{warn:(...args)=>warnings.push(args)}});
c.focusSearch=(lat,lng,zoom,title)=>{moves.push([[lat,lng],zoom]);analyses.push([lat,lng,title])};
c.placeCache=new Map();
vm.runInContext(source,c);
function input(q,fire=true){field.value=q;field.oninput();if(fire&&scheduled){const fn=scheduled;scheduled=null;fn()}}
const settle=()=>new Promise(resolve=>setImmediate(resolve));
(async()=>{
 input('Brocken');assert.equal(pending.length,1);
 input('Frankfurt');assert.equal(pending[0].options.signal.aborted,true);assert.equal(analyses.at(-1)[2],'Frankfurt – 30-Minuten-Fahrzeit');
 const afterLocal=analyses.length;pending[0].resolve({ok:true,json:async()=>[{lat:'51.8',lon:'10.6'}]});await settle();assert.equal(analyses.length,afterLocal);
 input('Zugspitze');input('');const afterClear=analyses.length;pending[1].resolve({ok:true,json:async()=>[{lat:'47.4',lon:'10.9'}]});await settle();assert.equal(analyses.length,afterClear);assert.equal(moves.at(-1)[1],6);
 input('Brocken');pending[2].resolve({ok:true,json:async()=>[{lat:'51.8',lon:'10.6'}]});await settle();assert.equal(analyses.at(-1)[2],'30-Minuten-Fahrzeit für „BROCKEN“');
 input('Fehler');pending[3].reject(new Error('Network offline'));await settle();assert.equal(warnings.length,1);
 input('ab');assert.equal(pending.length,4);
 console.log('PASS: obsolete external results, abort, local priority, clear, external result, network errors, short queries');
})().catch(e=>{console.error(e);process.exitCode=1});
