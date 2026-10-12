const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const scope={};
vm.runInNewContext(fs.readFileSync(__dirname+'/session_api.js','utf8'),scope);
const expired={error:'Accesso non autorizzato',code:'app_session_expired'};
const old='old-session-for-local-testing-only',fresh='new-session-for-local-testing-only';
function reply(status,value) {
  return {status,ok:status===200,json:async()=>value,text:async()=>value};
}
async function main() {
  let renewals=0,executions=0;
  const api=scope.createSessionApi(old,async(path,options)=>{
    if(path==='/') {
      renewals++;
      assert.equal(options.cache,'no-store');
      await new Promise(resolve=>setImmediate(resolve));
      return reply(200,"const TOKEN='"+fresh+"';");
    }
    if(options.headers['X-App-Token']!==fresh)return reply(403,expired);
    if(options.method==='POST')executions++;
    return reply(200,{ok:true});
  });
  await Promise.all([api('state'),api('run',{action:'chat'})]);
  assert.equal(renewals,1,'Concurrent failures share one renewal');
  assert.equal(executions,1,'The rejected POST is executed once');
  await api('state');
  assert.equal(renewals,1,'Later requests retain the renewed token');
  for(const status of [401,403,500]) {
    let calls=0;
    const denied=scope.createSessionApi(old,async()=>{calls++;return reply(status,{error:'Denied'})});
    await assert.rejects(denied('state'),/Denied/);
    assert.equal(calls,1,'Do not retry unrelated errors');
  }
  let attempts=0;
  const stillExpired=scope.createSessionApi(old,async(path)=>{
    if(path==='/')return reply(200,"const TOKEN='"+fresh+"';");
    attempts++;return reply(403,expired);
  });
  await assert.rejects(stillExpired('run',{}),/Accesso non autorizzato/);
  assert.equal(attempts,2,'Only one retry per request');
  console.log('Session recovery: concurrent renewal, one POST execution, strict denial and bounded retry OK');
}
main().catch(error=>{console.error(error);process.exitCode=1});
