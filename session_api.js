// Renew only the local UI session. Rejected requests have not started a job.
function createSessionApi(initialToken, fetcher=fetch) {
  let token=initialToken, refreshing=null;
  async function refresh(expected) {
    if(token!==expected)return;
    if(!refreshing)refreshing=(async()=>{
      const response=await fetcher('/',{cache:'no-store',credentials:'same-origin'});
      if(!response.ok)throw Error('Connessione al programma non disponibile.');
      const html=await response.text();
      const match=html.match(/const TOKEN='([A-Za-z0-9_-]{24,})'/);
      if(!match)throw Error('Sessione non disponibile. Aggiorna la pagina.');
      token=match[1];
    })().finally(()=>{refreshing=null});
    await refreshing;
  }
  return async function api(path,data) {
    async function request() {
      const response=await fetcher('/api/'+path,{
        method:data?'POST':'GET',cache:'no-store',credentials:'same-origin',
        headers:{'X-App-Token':token,'Content-Type':'application/json'},
        body:data?JSON.stringify(data):undefined
      });
      return {response,value:await response.json()};
    }
    const sent=token;
    let result=await request();
    if(result.response.status===403 && result.value.code==='app_session_expired') {
      await refresh(sent);
      result=await request();
    }
    if(!result.response.ok)throw Error(result.value.error||'Operazione non riuscita');
    return result.value;
  };
}
