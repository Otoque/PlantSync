import {api, key, list, lotPath, post, publicConfig, publicUrl, session, setSession, tripPath} from './produto-api.js';
import {drawMap, drawReadings, readingsTable} from './produto-monitor.js';
import {openAction, settingsView} from './produto-formularios.js';
import {date, empty, esc, number, setTimezone, table} from './produto-texto.js';
import {activeTracking, closeTracking, dropTracking, startTracking} from './produto-rastreio.js';

export {date, empty, esc, number, table} from './produto-texto.js';

const app = document.getElementById('app');
const modal = document.getElementById('dialog');
const toastElement = document.getElementById('toast');
const viewLoading = document.getElementById('view-loading');
const phases = ['Preparação', 'Aguardando despacho', 'Em trânsito', 'Recebido'];
const roleNames = {gestor:'Gestor de operações', administrador:'Administrador da empresa', cliente:'Cliente'};
const nav = [
  ['inicio','◫','Visão geral','consultar'], ['lotes','▤','Lotes','consultar'], ['viagens','↗','Viagens','consultar'],
  ['ambientes','▧','Ambientes e sensores','operar'], ['alertas','◷','Alertas','consultar'], ['etiquetas','▦','Etiquetas QR','etiquetas'],
  ['configuracoes','⚙','Configurações']
];
const brand = '<span class="brand-mark" aria-hidden="true"></span>PlantSync';
const selected = new Set();
const configPromise = publicConfig();
let context;
let resources = {};
let cleanupView;
let request;
let toastTimer;
let loginNotice = '';
let search = '';
let phaseFilter = '';
const lotPageSize = 100;
let lotOffset = 0;
let lotRequest;
let lotSearchTimer;
let listMode = false;
let detailTab = 'visao';
let preferences = 'perfil';
let readingsOffset = null;
let historyOffset = 0;
let currentProfile;
let modalOpener;

export const tag = (value, color='') => `<span class="tag ${color}">${esc(value)}</span>`;
export const button = (label, action, id, style='') => `<button type="button" class="btn ${style}" data-action="${action}"${id == null ? '' : ` data-id="${esc(id)}"`}>${esc(label)}</button>`;
export const info = (label, value) => `<div class="info-row"><span>${esc(label)}</span><span>${esc(value || '—')}</span></div>`;
const formatTemp = value => value == null ? '—' : `${number(value)} °C`;
const interval = lot => Array.isArray(lot.range) && lot.range.every(value => value != null) ? `${lot.range.map(number).join(' a ')} °C` : '—';
const outOfRange = lot => lot.temperature != null && interval(lot) !== '—' && (lot.temperature < lot.range[0] || lot.temperature > lot.range[1]);
const phase = value => phases[value] || '—';
const phaseTag = value => tag(phase(value), ['', 'orange', 'blue', 'green'][value]);
const initials = name => String(name || 'PlantSync').trim().split(/\s+/).slice(0, 2).map(part => part[0]).join('').toUpperCase();
const lotHref = lot => `#lote/${key(lot.id)}`;
const permitted = permission => list(context?.empresa?.permissoes).includes(permission);
const can = (lot, command) => list(lot?.permissions).includes(command);
const company = () => context?.empresa;
const profile = () => ({...session?.usuario,...context?.usuario,...currentProfile});

function heading(title, subtitle='', actions='') {
  return `<div class="heading"><div><h1>${esc(title)}</h1>${subtitle ? `<p>${esc(subtitle)}</p>` : ''}</div>${actions ? `<div class="actions">${actions}</div>` : ''}</div>`;
}

export function panel(title, body, action='') {
  return `<section class="panel"><div class="panel-head"><h2>${esc(title)}</h2>${action}</div><div class="panel-body">${body}</div></section>`;
}

export function toast(message) {
  clearTimeout(toastTimer);
  toastElement.textContent = message;
  toastElement.hidden = false;
  toastTimer = setTimeout(() => { toastElement.hidden = true; }, 5500);
}

function route() {
  const [screen, encoded, modifier] = location.hash.slice(1).split('/');
  try { return [screen || 'inicio', encoded ? decodeURIComponent(encoded) : '', modifier || '']; }
  catch { return ['inicio', '']; }
}

function navigate(path) {
  if (location.hash === `#${path}`) load({focus:'#conteudo'});
  else location.hash = path;
}

function showTracking() {
  const target = document.getElementById('tracking-banner');
  if (!target) return;
  const tracking = activeTracking;
  if (!tracking) { target.replaceChildren(); return; }
  target.innerHTML = `<div class="notice tracking-banner"><div role="status"><strong>Rastreio por celular · ${esc(tracking.id)}</strong><br>${esc(tracking.status)}${tracking.lastSent ? ` Último envio em ${date(tracking.lastSent)}.` : ''}</div>${button('Encerrar rastreio','stop-tracking',tracking.id)}</div>`;
}

function commit(content) {
  cleanupView?.();
  cleanupView = undefined;
  app.innerHTML = content;
}

function shell(content, active, title) {
  const person = profile();
  const enterprise = company();
  const accountLinks = person?.plataforma ? [['empresas','▣','Empresas']] : [];
  const links = enterprise ? [...nav, ...accountLinks] : [...accountLinks, ['configuracoes', '⚙', 'Configurações']];
  const visible = links.filter(([, , , permission]) => !permission || permitted(permission));
  const companyLabel = enterprise?.nome || 'Selecionar empresa';
  const hasCompanyChoice = list(session?.empresas).length > 0;
  const activeName = roleNames[enterprise?.papel] || (person?.plataforma ? 'Administrador da plataforma' : 'Minha conta');
  const companyButton = button(companyLabel, 'company', null, 'company-selector');
  commit(`<div class="layout"><aside class="sidebar"><a class="brand" href="#inicio">${brand}</a>
    ${hasCompanyChoice ? `<button type="button" class="company" data-action="company"><span class="avatar">${esc(initials(companyLabel))}</span><span><strong>${esc(companyLabel)}</strong><br><small>${esc(activeName)}</small></span><span class="company-down" aria-hidden="true">⌄</span></button>` : ''}
    <div><span class="nav-label">Operação</span><nav class="nav-group" aria-label="Painel">${visible.map(([path,icon,label]) => `<a class="nav-link ${active === path ? 'active' : ''}" href="#${path}" ${active === path ? 'aria-current="page"' : ''}><span class="nav-icon" aria-hidden="true">${icon}</span>${esc(label)}</a>`).join('')}</nav></div>
    <div class="sidebar-bottom"><div class="user"><span class="avatar" aria-hidden="true">${esc(initials(person?.nome))}</span><span><strong>${esc(person?.nome)}</strong><small>${esc(activeName)}</small></span>${button('Sair','logout',null,'text')}</div></div>
    </aside><div class="workspace"><header class="topbar"><div class="breadcrumb">PlantSync <span>/</span> ${esc(title)}</div><div class="topbar-right"><span class="company-name">${esc(enterprise?.nome || '')}</span><div class="mobile-controls">${hasCompanyChoice ? companyButton : ''}${button('Sair','logout',null,'text')}</div><span class="avatar" aria-label="${esc(person?.nome)}">${esc(initials(person?.nome))}</span></div></header><main class="main" id="conteudo" tabindex="-1"><div id="tracking-banner"></div>${content}</main></div></div>`);
  showTracking();
}

function login() {
  const redirect = route()[0] === 'aceitar-convite';
  commit(`<main class="login-page" id="conteudo" tabindex="-1"><section class="login-story"><a href="#login" class="brand">${brand}</a><div><h1>Cuidado em cada etapa da carga.</h1><p>Da câmara fria à entrega, acompanhe as condições e as pessoas responsáveis pelo caminho.</p><div class="login-illustration"><strong>Da origem ao destino</strong><div class="login-line"></div><div class="actions login-stages"><small>Preparação</small><span>→</span><small>Transporte</small><span>→</span><small>Entrega</small></div></div></div><small>Rastreabilidade para quem produz, transporta e recebe.</small></section><section class="login-side"><form class="login-form" data-form="login"><h2>Bem-vindo de volta.</h2><p class="muted">Entre para acompanhar sua operação.</p><label class="field">Usuário ou e-mail<input name="usuario" required autocomplete="username"></label><label class="field">Senha<input name="senha" type="password" required autocomplete="current-password"></label><button type="submit" class="btn primary">Entrar →</button><p class="error-message" role="alert">${esc(loginNotice)}</p>${redirect ? button('Aceitar convite','accept-invite') : button('Tenho um convite','accept-invite',null,'text')}</form></section></main>`);
}

function metric(label, value, accent=false) {
  return `<div class="panel metric ${accent ? 'accent' : ''}"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`;
}

function lotName(lot) { return [lot.fruit, lot.variety].filter(Boolean).join(' · '); }
function lotTable(lots, selectable=false) {
  return table([...(selectable?['Selecionar']:[]), 'Lote','Destino e cliente','Fase','Última medição','Responsável'], lots.map(lot => `<tr>${selectable ? `<td><input type="checkbox" aria-label="Selecionar ${esc(lot.id)}" data-select="${esc(lot.id)}" ${selected.has(lot.id) ? 'checked' : ''}></td>` : ''}<td><a href="${lotHref(lot)}"><strong>${esc(lot.id)}</strong><small>${esc(lotName(lot))}</small></a></td><td>${esc(lot.destination || '—')}<small>${esc(lot.client)}</small></td><td>${phaseTag(lot.phase)}${lot.pending ? '<small>Despacho a validar</small>' : ''}</td><td><span class="temperature ${outOfRange(lot) ? 'warn' : ''}">${formatTemp(lot.temperature)}</span><small>Faixa ${esc(interval(lot))}</small></td><td>${esc(lot.owner || '—')}<small>${esc(lot.trip || 'Sem viagem atribuída')}</small></td></tr>`), 'Nenhum lote para exibir.');
}

function lotCard(lot) {
  return `<a href="${lotHref(lot)}" class="lot-card"><div class="lot-card-head"><span class="lot-code">${esc(lot.id)}</span>${lot.boxes != null ? tag(`${number(lot.boxes)} caixas`) : ''}</div><h3>${esc(lotName(lot))}</h3><p class="owner">${esc(lot.client)}</p><p class="destination">${esc(lot.destination)}</p>${lot.pending ? `<p>${tag('Despacho a validar','orange')}</p>` : ''}<footer><span class="temperature ${outOfRange(lot) ? 'warn' : ''}">${formatTemp(lot.temperature)}</span><span>Faixa ${esc(interval(lot))}</span></footer>${lot.owner ? `<footer class="lot-owner"><span><span class="mini-avatar" aria-hidden="true">${esc(initials(lot.owner))}</span>${esc(lot.owner)}</span><span aria-hidden="true">↗</span></footer>` : ''}</a>`;
}

function lotBoard() {
  const lots = list(resources.lots).slice(0, lotPageSize);
  return listMode ? `<section class="panel">${lotTable(lots)}</section>` : `<div class="board">${phases.map((label, index) => {
    const group = lots.filter(lot => lot.phase === index);
    return `<section class="board-column"><div class="column-title"><span class="phase-dot ${['','loaded','transit','closed'][index]}"></span>${label}<span class="count">${group.length}</span></div>${group.map(lotCard).join('') || empty('Nenhum lote nesta fase')}</section>`;
  }).join('')}</div>`;
}

function lotListPath(offset = lotOffset) {
  const query = new URLSearchParams({limit:lotPageSize + 1,offset});
  if (search.trim()) query.set('busca',search.trim());
  if (phaseFilter) query.set('fase',phaseFilter);
  return `/lotes?${query}`;
}

function lotPagination() {
  const length = list(resources.lots).length;
  if (lotOffset === 0 && length <= lotPageSize) return '';
  const range = length ? `${lotOffset + 1}–${lotOffset + Math.min(length,lotPageSize)}` : 'Nenhum lote nesta página';
  return `<div class="pagination">${lotOffset > 0 ? button('← Anterior','lot-page',-1) : ''}<small>${range}</small>${length > lotPageSize ? button('Próxima →','lot-page',1) : ''}</div>`;
}

function viewLots() {
  shell(heading('Cada lote, no seu caminho.', 'Acompanhe as etapas, as condições e quem está responsável.', permitted('operar') ? button('＋ Novo lote','new-lot',null,'primary') : '')
    + `<div class="toolbar"><div class="search"><input id="lot-search" maxlength="240" placeholder="Buscar lote, fruta ou cliente" aria-label="Buscar lotes" value="${esc(search)}"></div><select id="phase-filter" aria-label="Filtrar fase"><option value="">Todas as fases</option>${phases.map((label,index) => `<option value="${index}" ${phaseFilter === String(index) ? 'selected' : ''}>${label}</option>`).join('')}</select><div class="segmented mode"><button data-view="board" class="${listMode ? '' : 'active'}" aria-pressed="${!listMode}">Fluxo</button><button data-view="list" class="${listMode ? 'active' : ''}" aria-pressed="${listMode}">Lista</button></div></div><p id="lot-status" role="status"></p><div id="lot-results">${lotBoard()}</div><nav id="lot-pages" aria-label="Páginas de lotes">${lotPagination()}</nav>`, 'lotes','Lotes');
}

async function refreshLots(offset, direction) {
  const results = document.getElementById('lot-results');
  if (!results) return;
  request?.abort();
  lotRequest?.abort();
  lotRequest = new AbortController();
  const {signal} = lotRequest;
  const currentSession = session;
  const status = document.getElementById('lot-status');
  const pages = document.getElementById('lot-pages');
  const active = document.activeElement;
  const isCurrent = () => !signal.aborted && currentSession === session && results.isConnected;
  status.textContent = 'Carregando lotes…';
  results.setAttribute('aria-busy','true');
  try {
    const lots = await api(lotListPath(offset),{signal});
    if (!isCurrent()) return;
    lotOffset = offset;
    resources.lots = lots;
    results.innerHTML = lotBoard();
    pages.innerHTML = lotPagination();
    status.textContent = '';
    if (direction && active?.dataset.action === 'lot-page') {
      (pages.querySelector(`button[data-id="${direction}"]`) || pages.querySelector('button') || document.getElementById('lot-search'))?.focus();
    }
  } catch (error) {
    if (isCurrent()) status.textContent = error.message;
  } finally {
    if (isCurrent()) results.removeAttribute('aria-busy');
  }
}

function alertRow(alert) {
  const id = alert.lotId ?? alert.lote_id;
  const label = ({calor:'Temperatura acima da faixa',frio:'Temperatura abaixo da faixa',ausencia:'Ausência de medições',saida:'Saída detectada'})[alert.type] || 'Ocorrência de conservação';
  const description = alert.message || alert.mensagem || alert.descricao;
  return `<div class="stop"><div><strong>${esc(label)}</strong>${description ? `<small>${esc(description)}</small>` : ''}${alert.startedAt ? `<small>${date(alert.startedAt)}</small>` : ''}</div>${id ? `<a href="#lote/${key(id)}" class="btn">Ver lote ↗</a>` : ''}</div>`;
}

function viewOverview() {
  const lots = list(resources.lots);
  const active = lots.filter(lot => lot.phase < 3);
  const deviations = active.filter(outOfRange);
  const pending = lots.filter(lot => lot.pending);
  const alerts = list(resources.alerts);
  const trips = list(resources.trips).filter(trip => trip.phase === 2 || trip.phase === 'em_transito');
  const activeTrip = trips[0];
  const mapContent = activeTrip ? `<div id="route-map" class="map" aria-label="Posições registradas da viagem"></div><p id="map-state" role="status" class="map-key"></p><a href="#viagem/${key(activeTrip.id)}">${esc(activeTrip.id)} · Ver viagem ↗</a>` : empty('Nenhuma viagem em andamento.');
  const attention = deviations.slice(0,5).map(lot=>`<a href="${lotHref(lot)}" class="lot-card"><div class="lot-card-head"><strong>${esc(lot.id)} · ${esc(lot.fruit)}</strong>${tag(lot.temperature < lot.range[0] ? 'Abaixo da faixa' : 'Acima da faixa','orange')}</div><p class="temperature warn">${formatTemp(lot.temperature)} <small>· Faixa ${esc(interval(lot))}</small></p><footer><span>${lot.latestAt ? date(lot.latestAt) : ''}</span><span>Ver lote ↗</span></footer></a>`).join('') + alerts.slice(0,5).map(alertRow).join('');
  shell(heading(company()?.papel === 'cliente' ? 'Suas cargas, acompanhadas.' : 'Uma visão de toda a operação.', company()?.nome, permitted('operar') ? button('＋ Novo lote','new-lot',null,'primary') : '')
    + `<div class="metrics">${metric('Lotes em acompanhamento', active.length, true)}${metric('Em trânsito', lots.filter(lot => lot.phase === 2).length)}${metric('Desvios de temperatura', deviations.length)}${metric('Recebidos', lots.filter(lot => lot.phase === 3).length)}</div>`
    + pending.map(lot => `<div class="notice"><p><strong>Despacho a validar.</strong> O lote ${esc(lot.id)} tem saída registrada e aguarda validação.</p><a class="btn" href="${lotHref(lot)}">Ver lote ↗</a></div>`).join('')
    + `<div class="columns">${panel('Viagens em andamento', mapContent, '<a href="#viagens"><small>Ver viagens ↗</small></a>')}${panel('Precisa da sua atenção', attention || empty('Nenhum desvio recente ou alerta nos lotes disponíveis.'), '<a href="#alertas"><small>Ver alertas ↗</small></a>')}</div><section class="panel section-space"><div class="panel-head"><h2>Lotes em acompanhamento</h2><a href="#lotes"><small>Abrir fluxo ↗</small></a></div>${lotTable(active)}</section>`, 'inicio','Visão geral');
  if (activeTrip) cleanupView = drawMap(activeTrip, resources.positions, resources.positionError);
}

function flow(lot) {
  const current = [0,1,3,5][lot.phase];
  const times = [lot.preparedAt, lot.loadedAt, lot.departedAt, lot.departedAt, lot.receivedAt];
  return `<div class="panel flow">${['Preparação','Carregamento','Despacho','Em trânsito','Recebimento','Laudo'].map((label,index) => {
    const pending = index === 2 && lot.pending;
    const confirmed = Boolean(times[index]) && index < current && !pending;
    const unrecorded = index < current || (index === current && lot.legacy && index !== 5);
    const status = pending ? 'A validar' : times[index] ? date(times[index]) : unrecorded ? `Sem registro${lot.legacy ? ' (legado)' : ''}` : index === current && index !== 5 ? 'Em andamento' : '—';
    return `<div class="step ${confirmed ? 'done' : ''} ${index === current ? 'current' : ''} ${pending ? 'provisional' : ''}"><span class="step-circle" aria-hidden="true">${pending ? '!' : confirmed ? '✓' : index === current ? '•' : '○'}</span><strong>${label}</strong><small>${esc(status)}</small></div>`;
  }).join('')}</div>`;
}

const eventNames = {preparar:'Preparação registrada',preparado:'Preparação registrada',carregar:'Carregamento registrado',carregado:'Carregamento registrado',despachar:'Despacho confirmado',despachado:'Despacho confirmado',receber:'Recebimento registrado',recebido:'Recebimento registrado',retornar:'Retorno de fase',retornado:'Retorno de fase','validar-despacho':'Despacho validado',despacho_validado:'Despacho validado',saida_detectada:'Saída detectada'};

function history(events) {
  return list(events).length ? `<ol class="timeline">${events.map(event => `<li><time datetime="${esc(event.efetivo_em)}">${date(event.efetivo_em)}</time><strong>${esc(eventNames[event.tipo] || String(event.tipo || 'Movimentação').replaceAll('_',' '))}</strong><p>${esc([event.autor,event.empresa].filter(Boolean).join(' · '))}</p>${event.fase_anterior != null && event.fase_atual != null ? `<p>${esc(phase(event.fase_anterior))} → ${esc(phase(event.fase_atual))}</p>` : ''}${event.motivo ? `<p>${esc(event.motivo)}</p>` : ''}${event.registrado_em && event.registrado_em !== event.efetivo_em ? `<p>Registrado em ${date(event.registrado_em)}</p>` : ''}</li>`).join('')}</ol>` : empty('Nenhuma movimentação registrada.');
}

function pagination(resource, action) {
  const total = Number(resource?.total || 0);
  const offset = Number(resource?.offset || 0);
  const length = list(resource?.items).length;
  if (total <= length && offset === 0) return '';
  return `<div class="pagination">${offset > 0 ? button('← Anterior',action,-1) : ''}<small>${offset+1}–${offset+length} de ${total}</small>${offset + length < total ? button('Próxima →',action,1) : ''}</div>`;
}

function viewDetail() {
  const lot = resources.lot;
  const measures = resources.readings;
  const latest = list(measures?.items).reduce((result, reading) => !result || Date.parse(reading.data_hora) > Date.parse(result.data_hora) ? reading : result, null);
  const moves = [['retornar','Retornar fase'],['confirmar-transferencia','Confirmar transferência'],['validar-despacho','Validar despacho'],['preparar','Registrar preparação'],['carregar','Registrar carregamento'],['despachar','Confirmar despacho'],['receber','Registrar recebimento']];
  const actions = moves.filter(([command]) => can(lot,command) && (command !== 'preparar' || !lot.preparedAt))
    .map(([command,label]) => button(label,command,lot.id, command === 'retornar' ? '' : 'primary')).join('') + (can(lot,'editar') ? button('Editar lote','edit-lot',lot.id) : '');
  const tabs = [['visao','Acompanhamento'],['medicoes','Medições'],['historico','Histórico e responsáveis']];
  if (can(lot,'compartilhar')) tabs.push(['acessos','Compartilhamento']);
  if (!tabs.some(([name]) => name === detailTab)) detailTab = 'visao';
  let body;
  if (detailTab === 'historico') {
    body = panel('Rastreabilidade do lote', history(resources.history?.items) + pagination(resources.history,'history-page'));
  } else if (detailTab === 'acessos') {
    body = panel('Empresas participantes', table(['Empresa','Permissões','Situação','Ações'], list(resources.shares).map(share => `<tr><td>${esc(share.company || share.companyId)}</td><td>${esc(list(share.rights).join(', '))}</td><td>${tag(share.status, share.status === 'aceito' ? 'green' : '')}</td><td>${['pendente','aceito'].includes(share.status) ? button('Revogar','revoke-share',share.id,'danger') : ''}</td></tr>`), 'Nenhuma empresa tem acesso compartilhado.'), button('＋ Compartilhar lote','share',lot.id));
  } else {
    const temperatureStatus = lot.temperature == null ? tag('Sem medição') : outOfRange(lot) ? tag(lot.temperature < lot.range[0] ? 'Abaixo da faixa' : 'Acima da faixa','orange') : interval(lot) !== '—' ? tag('Dentro da faixa','green') : '';
    const latestAt = Date.parse(lot.latestAt);
    const last = `<div class="reading"><strong class="temperature ${outOfRange(lot) ? 'warn' : ''}">${formatTemp(lot.temperature)}</strong><span class="muted">Faixa esperada<br><b>${esc(interval(lot))}</b></span>${latest?.umidade_pct != null && Date.parse(latest.data_hora) === latestAt ? `<span class="last-humidity"><small>Umidade</small><br><b>${number(latest.umidade_pct)}%</b></span>` : ''}</div>`;
    const partial = measures?.total > list(measures?.items).length ? `<p class="muted">Gráfico com ${number(measures.items.length)} de ${number(measures.total)} leituras. Consulte a aba Medições para navegar pelo histórico.</p>` : '';
    const measurements = panel('Condições de conservação', last + (lot.latestAt ? `<p class="muted">Última medição em ${date(lot.latestAt)}</p>` : '') + partial + '<div id="readings-chart"></div>', temperatureStatus);
    const supplement = detailTab === 'medicoes' ? panel('Leituras e origem', readingsTable(measures?.items, lot) + pagination(measures, 'readings-page'), list(measures?.items).length ? button('Exportar CSV','export-readings',lot.id) : '') : panel('Últimas movimentações', history(list(resources.history?.items).slice(0,4)), '<button class="btn text" data-detail="historico">Ver histórico ↗</button>');
    const responsibility = panel('Responsabilidade atual', `${lot.owner ? `<div class="actions"><span class="avatar" aria-hidden="true">${esc(initials(lot.owner))}</span><strong>${esc(lot.owner)}</strong></div>` : empty('Responsabilidade ainda não registrada.')}${info('Ambiente e sensor',lot.sensor)}${lot.waitMinutes != null ? info('Espera antes da saída',`${number(lot.waitMinutes)} min`) : ''}${lot.tripId || lot.trip ? `<div class="info-row"><span>Viagem</span><a href="#viagem/${key(lot.tripId || lot.trip)}">${esc(lot.tripId || lot.trip)} ↗</a></div>` : info('Viagem','A atribuir')}`);
    const analysis = measures?.analysis || lot.analysis;
    const risk = analysis && typeof analysis === 'object' ? panel('Risco acumulado', analysisHTML(analysis,lot.seal)) : '';
    const ownLot = can(lot,'compartilhar');
    const publicActions = `${lot.publicCode && can(lot,'etiquetas') ? button('Gerar etiqueta','qr-lot',lot.id) : ''}${lot.publicCode ? button('Página pública ↗','open-public',lot.id) : ''}${can(lot,'laudo') ? `<a class="btn" href="#laudo/${key(lot.id)}">Consultar laudo ↗</a>` : ''}${can(lot,'laudo') && ownLot ? button('Gerar link de laudo','issue-report',lot.id) + button('Revogar links','revoke-report',lot.id,'danger') : ''}`;
    const trace = panel('Rastreabilidade', info('Cliente',lot.client) + info('Destino',lot.destination) + (publicActions ? `<div class="actions section-space">${publicActions}</div>` : ''));
    body = `<div class="columns"><div class="stack">${measurements}${supplement}</div><div class="stack">${responsibility}${risk}${trace}</div></div>`;
  }
  const subtitle = [lot.id, lot.boxes != null ? `${number(lot.boxes)} caixas` : '', lot.weightKg != null ? `${number(lot.weightKg)} kg` : lot.weight].filter(Boolean).join(' / ');
  shell('<a href="#lotes" class="btn text">← Todos os lotes</a>' + heading(lotName(lot) || lot.id, subtitle, actions) + flow(lot)
    + (lot.pending ? '<div class="notice"><p><strong>Em trânsito · despacho a validar.</strong> A confirmação de quem assumiu a carga está pendente.</p></div>' : '')
    + `<nav class="tabbar" aria-label="Detalhes do lote">${tabs.map(([name,label]) => `<button type="button" data-detail="${name}" class="${detailTab === name ? 'active' : ''}" aria-pressed="${detailTab === name}">${label}</button>`).join('')}</nav>${body}`, 'lotes',lot.id);
  if (['visao','medicoes'].includes(detailTab)) cleanupView = drawReadings(list(measures?.items), list(resources.history?.items), lot);
}

function analysisHTML(analysis, seal) {
  const category = seal?.elegivel === true ? analysis.nivel?.replaceAll('_',' ') : analysis.amostras ? 'Avaliação pendente' : 'Sem medições';
  const entries = [['Exposição ao calor',analysis.graus_hora_acima], ['Exposição ao frio',analysis.graus_hora_abaixo]];
  const details = analysis.amostras ? entries.filter(([,value]) => typeof value === 'number').map(([label,value]) => info(label, `${number(value)} °C·h`)).join('') : '';
  const stages = list(analysis.etapas);
  const gaps = list(analysis.lacunas);
  const stagesHTML = stages.length ? `<details class="section-space"><summary>Exposição por etapa</summary>${table(['Etapa','Responsável','Calor','Frio'],stages.map(stage=>`<tr><td>${esc(phase(stage.fase))}</td><td>${esc(stage.responsavel || '—')}</td><td>${number(stage.graus_hora_acima)} °C·h</td><td>${number(stage.graus_hora_abaixo)} °C·h</td></tr>`))}</details>` : '';
  const gapsHTML = gaps.length ? `<details class="section-space"><summary>Períodos sem cobertura contínua</summary>${table(['Etapa','De','Até'],gaps.map(gap=>`<tr><td>${esc(phase(gap.fase))}</td><td>${date(gap.inicio)}</td><td>${date(gap.fim)}</td></tr>`))}</details>` : '';
  const observations = analysis.amostras ? info('Leituras fora da faixa',number(analysis.amostras_fora_faixa)) : '';
  return `${tag(category || 'Avaliação pendente', seal?.elegivel === true ? ({VERDE:'green',AMARELO:'orange',LARANJA:'orange',VERMELHO:'red'})[analysis.nivel] : '')}${details}${observations}${seal?.elegivel === true && analysis.recomendacao ? `<p class="section-space">${esc(analysis.recomendacao)}</p>` : ''}${stagesHTML}${gapsHTML}`;
}

function viewReport() {
  const report = resources.report;
  const revision = report.revision;
  const reportHref = `#laudo/${key(report.id)}`;
  const latest = report.latestIssuedRevision;
  const status = revision ? `Revisão ${revision.id} · Emitida em ${date(revision.issuedAt)}` : latest ? `Última revisão emitida em ${date(latest.issuedAt)}.${report.hasUnissuedChanges ? ' Há dados posteriores à emissão.' : ''}` : 'Dados atuais do lote';
  const revisions = resources.revisions ? panel('Revisões emitidas',table(['Revisão','Emissão','Motivo','Medições'],list(resources.revisions).map(item=>`<tr><td><a href="${reportHref}/${key(item.id)}">Revisão ${esc(item.id)} ↗</a></td><td>${date(item.issuedAt)}</td><td>${esc(item.reason || '—')}</td><td>${number(item.readingCount)}</td></tr>`),'Nenhum laudo foi emitido.')) : '';
  const section = `<a class="btn text" href="${revision ? reportHref : `#lote/${key(report.id)}`}">← ${revision ? 'Ver laudo atual' : 'Voltar ao lote'}</a>${heading('Laudo de conservação',`${report.id} · ${report.fruit} · ${status}`)}${panel('Risco acumulado',analysisHTML(report.analysis || {},report.seal))}<div class="stack section-space">${panel('Medições','<div id="readings-chart"></div>')}${panel('Histórico',history(report.events))}${revisions}</div>`;
  shell(section,'lotes','Laudo');
  cleanupView = drawReadings(list(report.readings),list(report.events),report);
}

const tripStatus = trip => typeof trip.phase === 'number' ? phase(trip.phase) : ({planejada:'Planejada', aguardando:'Aguardando despacho',em_transito:'Em trânsito',concluida:'Concluída'})[trip.phase] || trip.phase || '—';
const tripRoute = trip => [trip.origin, ...list(trip.stops).map(stop => stop.name)].filter(Boolean).join(' → ');
function viewTrips() {
  const rows = list(resources.trips).map(trip => `<tr><td><a href="#viagem/${key(trip.id)}"><strong>${esc(trip.id)} ↗</strong></a></td><td><strong>${esc(trip.vehicle || '—')}</strong><small>${esc(trip.carrier)}</small></td><td>${esc(tripRoute(trip) || '—')}</td><td>${list(trip.lotIds).length}</td><td>${tag(tripStatus(trip),'blue')}</td></tr>`);
  shell(heading('Viagens','Veículos, lotes embarcados e entregas em um só lugar.', permitted('operar') ? button('＋ Nova viagem','new-trip',null,'primary') : '') + `<section class="panel">${table(['Viagem','Veículo e transportadora','Percurso','Lotes visíveis','Situação'],rows,'Nenhuma viagem disponível.')}</section>`, 'viagens','Viagens');
}

function viewTrip() {
  const trip = resources.trip;
  const operate = list(trip.permissions).includes('operar');
  const track = operate && !activeTracking && (!trip.tracking || trip.tracking.source === 'celular') ? button(trip.tracking ? 'Retomar rastreio no celular' : 'Iniciar rastreio no celular','start-tracking',trip.id,'primary') : '';
  const linked = list(resources.lots).filter(lot => String(lot.tripId || lot.trip) === String(trip.id) || list(trip.lotIds).some(id => String(id) === String(lot.id)));
  const stops = list(trip.stops).map(stop => `<div class="stop"><span class="stop-point" aria-hidden="true"></span><div><strong>${esc(stop.name)}</strong>${stop.receivedAt ? `<small>Recebimento em ${date(stop.receivedAt)}</small>` : ''}</div></div>`).join('');
  const mapMarkup = '<div id="route-map" class="map" aria-label="Posições registradas da viagem"></div><p id="map-state" role="status" class="map-key"></p><div id="position-list"></div>';
  const stop = operate && trip.tracking && !activeTracking ? button('Encerrar fonte ativa','stop-remote-tracking',trip.id) : '';
  const dispatch = operate && linked.some(lot=>can(lot,'despachar')) ? button('Despachar viagem','dispatch-trip',trip.id) : '';
  shell('<a href="#viagens" class="btn text">← Todas as viagens</a>' + heading(`Viagem ${trip.id}`, [trip.vehicle, trip.carrier, tripStatus(trip)].filter(Boolean).join(' · '), dispatch + track + stop)
    + `<div class="columns">${panel('Localização da viagem',mapMarkup)}<div class="stack">${panel('Paradas previstas',trip.origin ? info('Origem',trip.origin) + (stops || empty('Nenhuma parada cadastrada.')) : stops || empty('Nenhuma parada cadastrada.'))}${panel('Responsabilidade',info('Transportadora',trip.carrier) + info('Responsável',trip.responsible) + info('Fonte de localização',trip.source === 'celular' ? 'Celular' : trip.source === 'externa' ? 'Sistema externo' : null) + (trip.tracking?.actor ? info('Fonte ativada por',trip.tracking.actor) : ''))}</div></div><section class="panel section-space"><div class="panel-head"><h2>Lotes da viagem</h2></div>${lotTable(linked)}</section>`, 'viagens', trip.id);
  cleanupView = drawMap(trip, resources.positions, resources.positionError, true);
}

const environmentType = value => ({camara:'Câmara fria',compartimento:'Compartimento'})[value] || value || 'Ambiente';
function viewEnvironments() {
  const cards = list(resources.environments).map(item => `<section class="panel environment"><span class="environment-symbol" aria-hidden="true">${item.type === 'camara' ? '❄' : '▧'}</span><h2>${esc(item.name)}</h2><p class="muted">${esc(environmentType(item.type))}</p>${info('Sensor',item.sensor || item.sensorId)}${info('Lotes associados',list(item.lotIds).join(', ') || 'Nenhum')}</section>`).join('');
  const sensors = list(resources.sensors).map(sensor => `<tr><td><strong>${esc(sensor.name)}</strong>${sensor.channel ? `<small>Canal ${esc(sensor.channel)}</small>` : ''}</td><td>${esc(sensor.type === 'thingspeak' ? 'ThingSpeak' : sensor.type === 'manual' ? 'Manual' : sensor.type)}</td><td>${esc(list(resources.environments).find(item => item.id === sensor.environmentId)?.name || 'Sem vínculo')}</td><td>${date(sensor.latestAt)}</td><td><div class="actions">${permitted('operar') ? (sensor.environmentId ? button('Desvincular','unlink-sensor',sensor.id) : button('Vincular','link-sensor',sensor.id)) + (sensor.type === 'manual' ? button('Registrar leitura','manual-reading',sensor.id) : '') : ''}</div></td></tr>`);
  shell(heading('Ambientes e sensores','Acompanhe as fontes de medição da operação.',permitted('operar') ? button('＋ Novo ambiente','new-environment',null,'primary') : '') + (cards ? `<div class="cards-three">${cards}</div>` : panel('Ambientes',empty('Nenhum ambiente cadastrado.')))
    + `<section class="panel section-space"><div class="panel-head"><h2>Sensores cadastrados</h2><div class="actions">${permitted('operar') ? button('＋ Novo sensor','new-sensor') : ''}${(permitted('integrar') || permitted('operar')) && list(resources.sensors).some(sensor=>sensor.type==='thingspeak') ? button('Sincronizar ThingSpeak','sync') : ''}</div></div>${table(['Sensor','Fonte','Ambiente','Última medição','Ações'],sensors,'Nenhum sensor cadastrado.')}</section>`, 'ambientes','Ambientes e sensores');
}

function viewAlerts() {
  const alerts = list(resources.alerts);
  const labels = {aberta:'Aberta',reconhecida:'Reconhecida',resolvida:'Resolvida'};
  shell(heading('Alertas de conservação','Acompanhe e trate as ocorrências registradas nos lotes.') + panel('Ocorrências', alerts.map(alert => `${alertRow(alert)}<div class="actions alert-actions">${alert.status ? tag(labels[alert.status] || alert.status, alert.status === 'resolvida' ? 'green' : 'orange') : ''}${permitted('operar') && alert.status !== 'resolvida' ? button('Tratar alerta','treat-alert',alert.id ?? alert._id) : ''}</div>`).join('') || empty('Nenhum alerta registrado.')), 'alertas','Alertas');
}

function labelHTML(lot, config) {
  const url = publicUrl(lot.publicCode, config);
  return `<article class="qr-label"><div class="qr-image" data-qr="${esc(url)}" aria-label="Código QR para a página pública"></div><div><small>PLANTSYNC</small><h3>${esc(lot.id)}</h3><p>${esc(lotName(lot))}</p>${lot.producer ? `<small>${esc(lot.producer)}</small>` : ''}${lot.origin ? `<small>${esc(lot.origin)}</small>` : ''}<a href="${esc(url)}" target="_blank" rel="noopener noreferrer" class="qr-link">Conferir página pública ↗</a></div></article>`;
}

function fillQR(container) {
  container.querySelectorAll('[data-qr]').forEach(element => {
    if (!globalThis.QRCode) throw new Error('A geração de códigos QR está indisponível.');
    new globalThis.QRCode(element, {text:element.dataset.qr, width:100, height:100, colorDark:'#20352d', colorLight:'#ffffff', correctLevel:globalThis.QRCode.CorrectLevel.M});
  });
}

const eligible = () => list(resources.lots).filter(lot => lot.publicCode && can(lot,'etiquetas'));
function viewLabels() {
  const lots = eligible();
  const checked = lots.filter(lot => selected.has(lot.id));
  shell(heading('Etiquetas e QR','Selecione os lotes, confira os vínculos e prepare a impressão.', checked.length ? button(`Imprimir ${checked.length} ${checked.length === 1 ? 'etiqueta' : 'etiquetas'}`,'print',null,'primary') : '')
    + `<section class="panel"><div class="panel-head"><h2>Selecionar lotes</h2>${lots.length ? button('Selecionar todos','select-all') : ''}</div>${lotTable(lots,true)}</section><div class="heading section-space"><h2>Prévia de impressão</h2><small>A4 · etiquetas individuais</small></div><div class="label-grid">${checked.map(lot => labelHTML(lot,resources.qrConfig)).join('') || empty('Selecione um lote para visualizar a etiqueta.')}</div>`, 'etiquetas','Etiquetas QR');
  fillQR(app);
}

function viewSettings() {
  const data = settingsView({tab:preferences, resources, person:profile(), enterprise:company(), permitted});
  shell(heading('Configurações','Gerencie sua conta e a operação da empresa.') + data, 'configuracoes', 'Configurações');
}

function viewPlatform() {
  const rows = list(resources.companies).map(item => `<tr><td><strong>${esc(item.nome)}</strong></td><td>${tag(item.ativo ? 'Ativa' : 'Inativa',item.ativo ? 'green' : '')}</td><td><div class="actions">${button('Editar','edit-company',item.id)}${item.ativo ? button('Convidar administrador','invite-company-admin',item.id) : ''}</div></td></tr>`);
  shell(heading('Empresas na plataforma','Cadastro e situação das organizações.',button('＋ Nova empresa','new-company',null,'primary')) + `<section class="panel">${table(['Empresa','Situação','Ações'],rows,'Nenhuma empresa cadastrada.')}</section>`, 'empresas','Empresas');
}

function failure(error, screen) {
  shell(heading(error.status === 403 ? 'Acesso indisponível' : 'Não foi possível abrir esta página', error.message, button('Tentar novamente','refresh')),'',nav.find(([path])=>path === screen)?.[2] || 'Operação');
}

async function positions(id, signal) {
  try {
    const path = `${tripPath(id)}/posicoes?limit=500`;
    const data = await api(path,{signal});
    return {positions:data.total>500 ? await api(`${path}&offset=${data.total-500}`,{signal}) : data};
  }
  catch (error) {
    if (error.name === 'AbortError') throw error;
    return {positionError:error.status === 403 ? 'As posições desta viagem não estão disponíveis para sua conta.' : error.message};
  }
}

const fetchRoutes = {
  inicio: {lots:'/lotes',trips:'/viagens',alerts:'/alertas'},
  viagens: {trips:'/viagens'}, ambientes: {environments:'/ambientes',sensors:'/sensores'},
  alertas: {alerts:'/alertas'}, etiquetas: {lots:'/lotes'}, empresas: {companies:'/empresas'}
};
const views = {inicio:viewOverview,lotes:viewLots,lote:viewDetail,laudo:viewReport,viagens:viewTrips,viagem:viewTrip,ambientes:viewEnvironments,alertas:viewAlerts,etiquetas:viewLabels,configuracoes:viewSettings,empresas:viewPlatform};

async function loadData(screen, id, signal, modifier) {
  const endpoints = {...fetchRoutes[screen]};
  if (screen === 'lotes') endpoints.lots = lotListPath();
  if (screen === 'lote') {
    const path = lotPath(id);
    const lot = await api(path,{signal});
    if (detailTab === 'acessos' && can(lot,'compartilhar')) endpoints.shares = `${path}/compartilhamentos`;
    else {
      endpoints.history = `${path}/historico?limit=100&offset=${historyOffset}`;
      if (detailTab !== 'historico') {
        const offset = readingsOffset ?? Math.max(0,Math.floor(((lot.analysis?.amostras || 1)-1)/500)*500);
        endpoints.readings = `${path}/leituras?limit=500&offset=${offset}`;
      }
    }
    const entries = await Promise.all(Object.entries(endpoints).map(async ([label,path]) => [label,await api(path,{signal})]));
    return {lot,...Object.fromEntries(entries)};
  }
  if (screen === 'viagem') Object.assign(endpoints,{trip:tripPath(id),lots:'/lotes'});
  if (screen === 'laudo') {
    const path = `${lotPath(id)}/laudo`;
    const report = await api(modifier ? `${path}/revisoes/${key(modifier)}` : path,{signal});
    const revisions = Object.hasOwn(report,'latestIssuedRevision') ? await api(`${path}/revisoes`,{signal}) : undefined;
    return {report,revisions};
  }
  if (screen === 'configuracoes') {
    if (permitted('administrar') && preferences === 'equipe') Object.assign(endpoints,{team:'/equipe',invites:'/equipe/convites'});
    if (permitted('administrar') && preferences === 'papeis') endpoints.roles = '/papeis';
    if (permitted('administrar') && preferences === 'empresa') endpoints.enterprise = '/configuracoes/empresa';
    if (permitted('operar') && preferences === 'frutas') endpoints.fruits = '/frutas';
    if (permitted('administrar') && preferences === 'fluxo') endpoints.flow = '/configuracoes/fluxo';
    if (permitted('integrar') && preferences === 'integracoes') endpoints.integrations = '/integracoes';
    if (permitted('consultar') && preferences === 'acessos') endpoints.receivedShares = '/compartilhamentos';
  }
  const entries = await Promise.all(Object.entries(endpoints).map(async ([label,path]) => [label,await api(path,{signal,withoutCompany:screen === 'empresas'})]));
  const data = Object.fromEntries(entries);
  if (screen === 'inicio') {
    const trip = list(data.trips).find(item => item.phase === 2 || item.phase === 'em_transito');
    if (trip) Object.assign(data,await positions(trip.id,signal));
  }
  if (screen === 'viagem') Object.assign(data,await positions(id,signal));
  if (screen === 'etiquetas') data.qrConfig = await configPromise;
  return data;
}

async function load({focus} = {}) {
  request?.abort();
  lotRequest?.abort();
  clearTimeout(lotSearchTimer);
  request = new AbortController();
  const {signal} = request;
  const currentSession = session;
  let [screen,id,modifier] = route();
  if (session && focus) {
    viewLoading.textContent = 'Carregando…';
    const previous = app.querySelector('main');
    previous?.setAttribute('aria-busy','true');
    previous?.setAttribute('inert','');
  }
  try {
    if (!session) { login(); return; }
    const checked = await Promise.all([session.companyId == null ? null : api('/contexto',{signal}), currentProfile || api('/perfil',{signal,withoutCompany:true})]);
    if (signal.aborted || currentSession !== session) return;
    [context,currentProfile] = checked;
    setTimezone(currentProfile.fuso);
    if (screen === 'aceitar-convite') {
      screen = 'configuracoes';
    }
    if (screen === 'login' || !views[screen]) screen = 'inicio';
    if (screen === 'inicio' && !company() && profile()?.plataforma) screen = 'empresas';
    if (screen === 'inicio' && company() && !permitted('consultar')) screen = 'configuracoes';
    if (!company() && !['configuracoes','empresas'].includes(screen)) {
      shell(heading('Sua conta está ativa','Selecione uma empresa ou aceite um convite para abrir a operação.',button('Aceitar convite','accept-invite')), '', 'Conta');
      return;
    }
    const rule = nav.find(([path]) => path === screen)?.[3];
    if ((rule && !permitted(rule)) || (screen === 'empresas' && !profile()?.plataforma)) {
      shell(heading('Acesso indisponível','Sua conta não tem acesso a esta página.'),'','Operação');
      return;
    }
    const data = await loadData(screen,id,signal,modifier);
    if (signal.aborted || currentSession !== session) return;
    resources = data;
    views[screen]();
    if (route()[0] === 'aceitar-convite' && !modal.open) await handleAction('accept-invite');
  } catch (error) {
    if (error.name === 'AbortError' || signal.aborted || currentSession !== session) return;
    failure(error,screen);
  } finally {
    if (!signal.aborted) {
      viewLoading.textContent = '';
      const main = app.querySelector('main');
      main?.removeAttribute('aria-busy');
      main?.removeAttribute('inert');
      if (focus && !modal.open) (app.querySelector(focus) || main)?.focus({preventScroll:true});
    }
  }
}

function downloadReadings() {
  const fields = ['data_hora','temperatura_c','umidade_pct','luminosidade_lux','fonte','ambiente','fase'];
  const escapeCell = value => {
    const input = String(value ?? '');
    const safe = typeof value === 'string' && /^[\s]*[=+@-]/.test(input) ? `'${input}` : input;
    return `"${safe.replaceAll('"','""')}"`;
  };
  const content = [fields.join(';'), ...list(resources.readings?.items).map(item => fields.map(field => escapeCell(item[field])).join(';'))].join('\r\n');
  const href = URL.createObjectURL(new Blob(['\uFEFF',content], {type:'text/csv;charset=utf-8'}));
  const anchor = Object.assign(document.createElement('a'), {href,download:`plantSync-${resources.lot.id}-leituras.csv`});
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(href),1000);
}

async function chooseCompany(values) {
  const next = list(session?.empresas).find(item => String(item.id) === String(values.companyId));
  if (!next) throw new Error('Escolha uma empresa autorizada.');
  if (next.id === session.companyId) return;
  await closeTracking('Troca de empresa pelo operador.');
  setSession({...session, companyId:next.id});
  context = undefined;
  resources = {};
  lotOffset = 0;
  selected.clear();
  preferences = 'perfil';
  commit('<main id="conteudo" class="main"><p role="status">Abrindo a empresa…</p></main>');
  navigate('inicio');
}

async function handleAction(action, id, opener) {
  if (action === 'close') { modal.close(); return; }
  if (action === 'refresh') { await load({focus:'#conteudo'}); return; }
  if (action === 'lot-page') {
    if (document.getElementById('lot-results')?.hasAttribute('aria-busy')) return;
    await refreshLots(Math.max(0, lotOffset + Number(id) * lotPageSize), Number(id));
    return;
  }
  if (action === 'logout') {
    const previous = session;
    await closeTracking('Sessão encerrada pelo operador.');
    try { await post('/logout',undefined,{withoutCompany:true}); }
    finally {
      if (session === previous) setSession(null);
      context = undefined;
      currentProfile = undefined;
      selected.clear();
      navigate('login');
    }
    return;
  }
  if (action === 'readings-page') { readingsOffset = Math.max(0,(resources.readings?.offset || 0) + Number(id)*500); await load(); return; }
  if (action === 'history-page') { historyOffset = Math.max(0,historyOffset + Number(id)*100); await load(); return; }
  if (action === 'start-tracking') { await startTracking(resources.trip); await load(); return; }
  if (action === 'stop-tracking') { await closeTracking(); toast('Rastreio encerrado.'); await load(); return; }
  if (action === 'sync') {
    const result = await post('/sincronizar');
    const totals = list(result.canais).reduce((sum,item)=>sum+Number(item.novas || 0),0);
    const failures = list(result.falhas).length;
    toast(`${totals} novas leituras.${failures ? ` Falha em ${failures} ${failures === 1 ? 'sensor' : 'sensores'}.` : ''}`);
    await load();
    return;
  }
  if (action === 'export-readings') { downloadReadings(); return; }
  if (action === 'select-all') { eligible().forEach(lot => selected.add(lot.id)); viewLabels(); return; }
  if (action === 'qr-lot') { selected.add(resources.lot.id); navigate('etiquetas'); return; }
  if (action === 'open-public') { window.open(publicUrl(resources.lot.publicCode,await configPromise),'_blank','noopener,noreferrer'); return; }
  if (action === 'print') {
    const target = document.getElementById('print-area');
    target.innerHTML = eligible().filter(lot => selected.has(lot.id)).map(lot => labelHTML(lot,resources.qrConfig)).join('');
    fillQR(target);
    window.print();
    return;
  }
  if (opener && !modal.open) modalOpener = opener;
  await openAction(action,id,{resources,modal,chooseCompany,profile,company,permitted,refresh:load,
    updateProfile: async data => { currentProfile = data; await load(); }});
}

function finishLogin(data) {
  const companies = list(data.empresas);
  setSession({...data,companyId:companies[0]?.id ?? null});
  context = undefined;
  currentProfile = undefined;
  lotOffset = 0;
  loginNotice = '';
  if (location.hash && route()[0] !== 'login') load();
  else navigate('inicio');
}

document.addEventListener('click', event => {
  if (event.target.closest('.skip-link')) {
    event.preventDefault();
    document.getElementById('conteudo')?.focus();
    return;
  }
  const control = event.target.closest('button');
  if (!control) return;
  const {action,id,detail,settings,view} = control.dataset;
  if (detail) {
    detailTab = detail;
    readingsOffset = null;
    historyOffset = 0;
    load({focus:`.tabbar [data-detail="${CSS.escape(detail)}"]`});
  }
  if (settings) {
    preferences = settings;
    load({focus:`[data-settings="${CSS.escape(settings)}"]`});
  }
  if (view) {
    listMode = view === 'list';
    document.getElementById('lot-results').innerHTML = lotBoard();
    for (const option of document.querySelectorAll('[data-view]')) {
      const active = option.dataset.view === view;
      option.classList.toggle('active',active);
      option.setAttribute('aria-pressed',String(active));
    }
  }
  if (action && !control.disabled) {
    control.disabled = true;
    handleAction(action,id,control).catch(error => toast(error.message)).finally(() => { control.disabled = false; });
  }
});

document.addEventListener('input', event => {
  if (event.target.id !== 'lot-search') return;
  search = event.target.value;
  lotRequest?.abort();
  clearTimeout(lotSearchTimer);
  document.getElementById('lot-results').setAttribute('aria-busy','true');
  lotSearchTimer = setTimeout(() => refreshLots(0),180);
});

document.addEventListener('change', event => {
  if (event.target.id === 'phase-filter') {
    phaseFilter = event.target.value;
    clearTimeout(lotSearchTimer);
    refreshLots(0);
  }
  const id = event.target.dataset.select;
  if (id != null) {
    const lot = eligible().find(item => String(item.id) === id);
    if (!lot) return;
    if (event.target.checked) selected.add(lot.id); else selected.delete(lot.id);
    viewLabels();
    [...document.querySelectorAll('[data-select]')].find(input => input.dataset.select === id)?.focus();
  }
});

document.addEventListener('submit', async event => {
  if (event.target.dataset.form !== 'login') return;
  event.preventDefault();
  const form = event.target;
  const submit = form.querySelector('[type="submit"]');
  const errorElement = form.querySelector('[role="alert"]');
  if (submit.disabled) return;
  submit.disabled = true;
  errorElement.textContent = '';
  try { finishLogin(await post('/login',Object.fromEntries(new FormData(form)),{anonymous:true})); }
  catch (error) { errorElement.textContent = error.message; }
  finally { submit.disabled = false; }
});

window.addEventListener('hashchange', () => {
  detailTab = 'visao';
  readingsOffset = null;
  historyOffset = 0;
  load({focus:'#conteudo'});
});
window.addEventListener('plantsync:sessao-expirada', () => {
  context = undefined;
  currentProfile = undefined;
  resources = {};
  selected.clear();
  dropTracking();
  if (modal.open) modal.close();
  loginNotice = 'Sua sessão expirou. Entre novamente para continuar.';
  load();
});
window.addEventListener('plantsync:rastreio', showTracking);
window.addEventListener('plantsync:erro-rastreio',event=>{ toast(event.detail); load(); });
window.addEventListener('plantsync:posicao-enviada',event=>{ if (route()[0] === 'viagem' && route()[1] === event.detail) load(); });
modal.addEventListener('close',()=>{
  if (modal.open) return;
  modal.replaceChildren();
  const opener = modalOpener;
  modalOpener = undefined;
  if (opener?.isConnected && !opener.disabled) opener.focus({preventScroll:true});
});
load();
