import {post, session, tripPath} from './produto-api.js';

const minimumInterval = 5000;
let watch;
let closing;
let starting;
export let activeTracking;

function change() { window.dispatchEvent(new Event('plantsync:rastreio')); }

function signedInWith(track) {
  return track.companyId === session?.companyId && track.token === session?.token;
}

function localStop() {
  if (watch != null) navigator.geolocation.clearWatch(watch);
  watch = undefined;
}

export function dropTracking() {
  localStop();
  activeTracking = undefined;
  change();
}

export function closeTracking(reason='Rastreio encerrado pelo operador.') {
  if (starting) return starting.catch(() => {}).then(() => closeTracking(reason));
  if (closing) return closing;
  const track = activeTracking;
  if (!track) return Promise.resolve();
  localStop();
  track.status = 'Encerrando a fonte…';
  change();
  closing = (async () => {
    try {
      await track.sending;
      if (signedInWith(track)) await post(`${tripPath(track.id)}/rastreio/encerrar`,{reason});
      dropTracking();
    } catch (error) {
      if (activeTracking === track) {
        track.status = `Coleta pausada. ${error.message} Tente encerrar a fonte novamente.`;
        change();
      }
      throw error;
    } finally { closing = undefined; }
  })();
  return closing;
}

export function startTracking(trip) {
  if (starting) return starting;
  const trackedSession = session;
  starting = (async () => {
    if (activeTracking) throw new Error('Encerre a coleta em andamento para iniciar outro rastreio.');
    if (!window.isSecureContext || !navigator.geolocation) throw new Error('Abra o PlantSync por HTTPS para usar a localização do celular.');
    const permission = await navigator.permissions?.query({name:'geolocation'}).catch(() => null);
    if (permission?.state === 'denied') throw new Error('A localização foi bloqueada. Autorize o acesso nas configurações do navegador.');
    if (trackedSession !== session) return;
    const updated = await post(`${tripPath(trip.id)}/rastreio/iniciar`,{source:'celular',version:trip.version});
    if (trackedSession !== session) return;
    const track = activeTracking = {id:trip.id,companyId:session.companyId,token:session.token,startedAt:Date.parse(updated.tracking?.startedAt),status:'Aguardando localização do celular.'};
    change();
    watch = navigator.geolocation.watchPosition(position=>sendPosition(track,position), error=>trackingError(track,error), {enableHighAccuracy:true,maximumAge:0,timeout:15000});
  })().finally(() => { starting = undefined; });
  return starting;
}

function sendPosition(track, position) {
  if (activeTracking !== track || !signedInWith(track) || closing || track.sending) return;
  if (position.timestamp < track.startedAt) {
    track.status = 'Aguardando uma medição posterior ao início do rastreio.';
    if (!track.requestedFreshPosition) {
      track.requestedFreshPosition = true;
      setTimeout(() => {
        if (activeTracking === track && watch != null && !track.lastSent) {
          navigator.geolocation.getCurrentPosition(value=>sendPosition(track,value),error=>trackingError(track,error),{maximumAge:0,timeout:10000});
        }
      },1000);
    }
    change();
    return;
  }
  if (position.timestamp <= (track.lastMeasured || 0)) return;
  if (track.lastSent && position.timestamp - track.lastSent < minimumInterval) return;
  track.lastMeasured = position.timestamp;
  track.status = 'Enviando posição do celular…';
  change();
  const {latitude,longitude,accuracy} = position.coords;
  const entryId = globalThis.crypto.randomUUID();
  track.sending = post(`${tripPath(track.id)}/posicoes`,{entryId,latitude,longitude,accuracy,measuredAt:new Date(position.timestamp).toISOString(),source:'celular'})
    .then(() => {
      track.lastSent = position.timestamp;
      track.status = document.hidden ? 'Coleta em segundo plano pode ser suspensa.' : 'Rastreio ativo.';
      window.dispatchEvent(new CustomEvent('plantsync:posicao-enviada',{detail:track.id}));
    })
    .catch(error => { track.status = error.message; })
    .finally(() => { track.sending = undefined; change(); });
}

function trackingError(track,error) {
  if (activeTracking !== track || closing) return;
  if (error.code === 1) {
    const message = 'Localização bloqueada no navegador.';
    closeTracking(message).then(() => window.dispatchEvent(new CustomEvent('plantsync:erro-rastreio',{detail:message}))).catch(() => {});
    return;
  }
  track.status = error.code === 3 ? 'Tempo esgotado ao buscar localização. Aguardando outra posição.' : 'Localização do celular indisponível.';
  change();
}

document.addEventListener('visibilitychange', () => {
  if (!activeTracking || closing || watch == null) return;
  activeTracking.status = document.hidden ? 'Coleta em segundo plano pode ser suspensa.' : 'Aguardando nova posição do celular.';
  change();
});

window.addEventListener('pagehide', () => {
  const track = activeTracking;
  if (!track) return;
  dropTracking();
  if (signedInWith(track)) post(`${tripPath(track.id)}/rastreio/encerrar`,{reason:'Painel fechado.'},{keepalive:true}).catch(() => {});
});
