const sessionKey = 'plantsync.sessao.v1';
const developmentPorts = ['5500', '5501'];

function readSession() {
  try {
    const value = JSON.parse(sessionStorage.getItem(sessionKey));
    if (value?.token && Date.parse(value.expira_em) > Date.now()) return value;
    sessionStorage.removeItem(sessionKey);
  } catch {
    // Uma sessão descartada exige novo login.
  }
  return null;
}

export let session = readSession();

export function setSession(value) {
  session = value;
  if (value) sessionStorage.setItem(sessionKey, JSON.stringify(value));
  else sessionStorage.removeItem(sessionKey);
}

export class ApiError extends Error {
  constructor(status, message, data) {
    super(message);
    this.status = status;
    this.data = data;
  }
}

export function baseUrl() {
  const origin = new URL(location.origin);
  if (developmentPorts.includes(origin.port) && ['127.0.0.1','localhost'].includes(origin.hostname)) origin.port = '8000';
  return new URL('/api/v1/', origin);
}

function errorMessage(response, data) {
  if (response.status === 429) {
    const retry = Number(response.headers.get('Retry-After'));
    return retry > 0 ? `Aguarde ${retry} segundos e tente novamente.` : 'Muitas tentativas. Aguarde e tente novamente.';
  }
  const detail = data?.erro || data?.detail;
  if (typeof detail === 'string') return detail;
  if (typeof detail?.message === 'string') return detail.message;
  if (Array.isArray(detail)) return 'Confira os campos e informe valores válidos.';
  return ({401:'Sua sessão expirou. Entre novamente.',403:'Você não tem permissão para esta ação.',404:'Registro não encontrado.',409:'O registro mudou ou a ação conflita com o estado atual.'})[response.status]
    || 'O PlantSync não conseguiu concluir esta operação. Tente novamente.';
}

export async function api(path, {method = 'GET', body, anonymous = false, signal, withoutCompany = false, keepalive=false} = {}) {
  const headers = {'Accept': 'application/json'};
  const requestSession = anonymous ? null : session;
  if (requestSession?.token) headers.Authorization = `Bearer ${requestSession.token}`;
  if (!withoutCompany && requestSession?.companyId != null) headers['X-Empresa-ID'] = String(requestSession.companyId);
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  let response;
  try {
    response = await fetch(new URL(path.replace(/^\//, ''), baseUrl()), {
      method, headers, body: body === undefined ? undefined : JSON.stringify(body), signal, keepalive, cache:'no-store'
    });
  } catch (error) {
    if (error.name === 'AbortError') throw error;
    throw new ApiError(0, 'Não foi possível conectar ao servidor. Confira a conexão e tente novamente.');
  }
  const data = response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401 && requestSession && requestSession === session) {
      setSession(null);
      dispatchEvent(new CustomEvent('plantsync:sessao-expirada'));
    }
    throw new ApiError(response.status, errorMessage(response, data), data);
  }
  return data;
}

export const key = value => encodeURIComponent(String(value));
export const lotPath = id => `/lotes/${key(id)}`;
export const tripPath = id => `/viagens/${key(id)}`;
export const list = value => Array.isArray(value) ? value : [];
export const post = (path, body, extras) => api(path, {method:'POST', body, ...extras});

export async function publicConfig() {
  try {
    const response = await fetch('./qr-publico.local.json', {cache:'no-store'});
    if (!response.ok) return {};
    const config = await response.json();
    return config && typeof config === 'object' ? config : {};
  } catch {
    return {};
  }
}

export function publicUrl(code, config = {}) {
  const base = new URL(config.origem || '.', location.href);
  if (!['http:', 'https:'].includes(base.protocol) || base.username || base.password) {
    throw new Error('O endereço das etiquetas precisa ser uma URL HTTP ou HTTPS válida.');
  }
  if (config.origem && !base.pathname.endsWith('/')) base.pathname += '/';
  const url = new URL('publico-lote.html', base);
  url.searchParams.set('codigo', code);
  return url.href;
}
