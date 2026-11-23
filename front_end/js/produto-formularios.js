import {api, key, list, lotPath, post, publicConfig, publicUrl, session, setSession, tripPath} from './produto-api.js';
import {button, date, empty, esc, info, number, table, tag, toast} from './produto.js';

const formRoles = [['administrador','Administrador'],['gestor','Gestor'],['cliente','Cliente']];
const accessLabels = {consultar:'Consultar',operar:'Operar',receber:'Registrar recebimento',rota:'Consultar rota',laudo:'Consultar laudo',compartilhar:'Compartilhar',etiquetas:'Gerar etiquetas',administrar:'Administrar',integrar:'Integrar'};
const transferStages = [['carregamento','No carregamento'],['despacho','No despacho'],['recebimento','No recebimento']];
const destinations = [['mercado_interno','Mercado interno'],['exportacao','Exportação']];
const flowRoles = [...formRoles,['integracao','Integração'],['automacao','Automação']];
const flowActions = [['editar','Editar lote'],['preparar','Preparar'],['carregar','Carregar'],['despachar','Despachar'],['receber','Receber'],['retornar','Retornar fase'],['validar-despacho','Validar despacho'],['confirmar-transferencia','Confirmar transferência']];
const detectionFields = [
  ['latitude','Latitude do ponto de saída',-90,90,'any'],['longitude','Longitude do ponto de saída',-180,180,'any'],
  ['radiusMeters','Raio da área de saída (m)',10,10000,1],['maxAccuracyMeters','Precisão máxima admitida (m)',.01,1000,'any'],
  ['maxAgeMinutes','Idade máxima da posição (min)',1,120,1],['persistenceSeconds','Tempo fora da área (s)',1,3600,1],
  ['autoDelaySeconds','Espera mínima para avanço (s)',1,3600,1]
];

function input(label, name, {type='text', value='', required=false, attrs='', inline=false}={}) {
  return `<label class="field ${inline ? '' : 'full'}">${esc(label)}<input name="${name}" type="${type}" value="${esc(value)}" ${required ? 'required' : ''} ${attrs}></label>`;
}

function select(label, name, items, {value,required=true,placeholder='Selecione'}={}) {
  return `<label class="field full">${esc(label)}<select name="${name}" ${required ? 'required' : ''}><option value="">${esc(placeholder)}</option>${items.map(([id,text]) => `<option value="${esc(id)}" ${String(value) === String(id) ? 'selected' : ''}>${esc(text)}</option>`).join('')}</select></label>`;
}

function note(label, name, required=false) {
  return `<label class="field full">${esc(label)}<textarea name="${name}" rows="3" maxlength="1000" ${required ? 'required' : ''}></textarea></label>`;
}

function choose(label, name, checked=false, value='1') {
  return `<label class="check-row"><input type="checkbox" name="${name}" value="${esc(value)}" ${checked ? 'checked' : ''}>${esc(label)}</label>`;
}

const toDate = value => value ? new Date(value).toISOString() : undefined;
const toNumber = value => value === '' || value == null ? undefined : Number(value);
const trim = value => value?.trim() || undefined;
const effectiveAt = () => input('Horário do evento (opcional)', 'effectiveAt', {type:'datetime-local'});
const objOptions = (values,label='name') => list(values).map(item => [item.id,item[label]]);
const patch = (path,body) => api(path,{method:'PATCH',body});
const del = path => api(path,{method:'DELETE'});

function showForm(modal, {title, description='', fields='', submitLabel='Confirmar', perform, after, done='Alteração salva.'}) {
  modal.innerHTML = `<div class="dialog-head"><h2 id="dialog-title">${esc(title)}</h2><button class="close" type="button" data-action="close" aria-label="Fechar">×</button></div><form class="dialog-body">${description ? `<p>${esc(description)}</p>` : ''}<div class="form-grid">${fields}</div><p class="error-message" role="alert"></p><div class="form-footer"><button type="button" class="btn" data-action="close">Cancelar</button><button type="submit" class="btn primary">${esc(submitLabel)}</button></div></form>`;
  if (!modal.open) modal.showModal();
  const form = modal.querySelector('form');
  form.addEventListener('submit',async event => {
    event.preventDefault();
    const submit = form.querySelector('[type="submit"]');
    const error = form.querySelector('[role="alert"]');
    if (submit.disabled) return;
    error.textContent = '';
    submit.disabled = true;
    form.querySelectorAll('[data-action="close"]').forEach(control=>{ control.disabled = true; });
    const data = new FormData(form);
    try {
      const result = await perform(Object.fromEntries(data),data);
      modal.close();
      if (done) toast(done);
      await after?.(result);
    } catch (failure) {
      if (!modal.open) toast(failure.message);
      else error.textContent = failure.message;
    } finally {
      submit.disabled = false;
      form.querySelectorAll('[data-action="close"]').forEach(control=>{ control.disabled = false; });
    }
  });
  return form;
}

function reveal(modal,title,label,value) {
  modal.innerHTML = `<div class="dialog-head"><h2 id="dialog-title">${esc(title)}</h2><button class="close" data-action="close" aria-label="Fechar">×</button></div><div class="dialog-body"><label class="field">${esc(label)}<input type="text" readonly value="${esc(value)}"></label><div class="form-footer"><button class="btn" data-action="close">Fechar</button><button class="btn primary" id="copy-value">Copiar</button></div></div>`;
  modal.showModal();
  modal.querySelector('input').addEventListener('focus', event => event.target.select());
  modal.querySelector('#copy-value').onclick = async () => {
    try { await navigator.clipboard.writeText(value); toast('Copiado.'); }
    catch { modal.querySelector('input').select(); toast('Selecione e copie o campo.'); }
  };
}

function invitationLink(token) {
  const url = new URL(location.href);
  url.search = '';
  url.hash = `aceitar-convite/${key(token)}`;
  return url.href;
}

function invite(modal,path,refresh,platform=false) {
  showForm(modal,{title:platform ? 'Convidar administrador' : 'Convidar pessoa',fields:input('E-mail','email',{type:'email',required:true}) + (platform ? '' : select('Papel','papel',formRoles)),
    perform:values=>post(path,values), after:async result => { await refresh(); reveal(modal,'Convite criado','Link de acesso',invitationLink(result.token)); }});
}

function acceptInvite(modal,refresh) {
  let supplied = '';
  try { supplied = decodeURIComponent(location.hash.split('/')[1] || ''); } catch { /* Link truncado. */ }
  showForm(modal,{title:'Aceitar convite',description:session ? 'Use o e-mail que recebeu o convite.' : 'Para uma nova conta, preencha nome e senha. Para vincular uma conta existente, entre nela primeiro.',
    fields:input('Código do convite','token',{value:supplied,required:true,attrs:'autocomplete="off"'}) + input('E-mail','email',{type:'email',required:true}) + (!session ? input('Nome','nome',{required:true}) + input('Nova senha','senha',{type:'password',required:true,attrs:'autocomplete="new-password"'}) : ''),
    perform:values=>post('/convites/aceitar',values,{anonymous:!session,withoutCompany:true}),
    after:async result => {
      if (result?.token && result?.usuario) {
        setSession({...result,companyId:list(result.empresas)[0]?.id ?? null});
      } else if (session && result?.empresa) {
        const companies = list(session.empresas).filter(item => item.id !== result.empresa.id);
        setSession({...session,empresas:[...companies,result.empresa],companyId:session.companyId ?? result.empresa.id});
      }
      if (location.hash.startsWith('#aceitar-convite')) location.hash = session ? 'inicio' : 'login';
      else await refresh();
    },done:'Convite aceito.'});
}

async function newLot(modal,refresh) {
  const [fruits,environments] = await Promise.all([api('/frutas'),api('/ambientes')]);
  const chambers = list(environments).filter(item=>item.type==='camara');
  if (!fruits.length) throw new Error('Cadastre uma fruta e sua faixa segura antes de abrir um lote.');
  if (!chambers.length) throw new Error('Cadastre uma câmara fria antes de iniciar a preparação.');
  const form = showForm(modal,{title:'Novo lote',description:'O lote começa em preparação na câmara selecionada.',submitLabel:'Criar lote',
    fields:select('Fruta','fruitId',list(fruits).map(item=>[item.id,item.nome || item.name])) + '<p class="field full muted" id="fruit-range"></p>' + input('Variedade','variety') + input('Código do lote (opcional)','id',{attrs:'pattern="PS-[A-Z0-9][A-Z0-9\\-]{0,31}" placeholder="PS-…"'}) + input('Cliente','client',{required:true}) + input('Destino','destination',{required:true}) + select('Tipo de destino','destinationType',destinations,{value:'mercado_interno'}) + input('Produtor','producer') + input('Origem','origin') + input('Caixas','boxes',{type:'number',attrs:'min="1" step="1"',inline:true}) + input('Peso (kg)','weightKg',{type:'number',attrs:'min="0.01" step="0.01"',inline:true}) + select('Câmara fria','environmentId',objOptions(chambers)) + input('Início da preparação (opcional)','preparedAt',{type:'datetime-local'}) + rangeFields(),
    perform:values=>post('/lotes',{id:trim(values.id),fruitId:values.fruitId,variety:trim(values.variety),client:values.client.trim(),destination:values.destination.trim(),destinationType:values.destinationType,producer:trim(values.producer),origin:trim(values.origin),boxes:toNumber(values.boxes),weightKg:toNumber(values.weightKg),environmentId:toNumber(values.environmentId),preparedAt:toDate(values.preparedAt),...rangeData(values)}),
    after:result=>result?.id ? (location.hash = `lote/${key(result.id)}`) : refresh(),done:'Lote criado.'});
  form.elements.fruitId.addEventListener('change',()=>{
    const fruit = fruits.find(item=>String(item.id) === form.elements.fruitId.value);
    const bounds = fruit?.faixa_segura || fruit;
    form.querySelector('#fruit-range').textContent = bounds?.temp_min_c != null && bounds?.temp_max_c != null ? `Faixa segura ${bounds.temp_min_c} a ${bounds.temp_max_c} °C` : '';
  });
}

function rangeFields() {
  return `<details class="field full"><summary>Usar uma faixa de temperatura específica</summary><div class="form-grid">${input('Mínima (°C)','minTemp',{type:'number',inline:true,attrs:'step="any"'})}${input('Máxima (°C)','maxTemp',{type:'number',inline:true,attrs:'step="any"'})}${note('Motivo para alterar faixa','reason')}</div></details>`;
}

function rangeData(values) {
  const min = toNumber(values.minTemp);
  const max = toNumber(values.maxTemp);
  const reason = trim(values.reason);
  if (min == null && max == null) return {reason};
  if (min == null || max == null || min >= max || !reason) throw new Error('Informe os dois limites em ordem crescente e justifique a faixa específica.');
  return {range:[min,max],reason};
}

function editLot(modal,lot,refresh) {
  showForm(modal,{title:'Editar lote',description:`Lote ${lot.id}`,
    fields:input('Variedade','variety',{value:lot.variety})+input('Cliente','client',{value:lot.client,required:true})+input('Destino','destination',{value:lot.destination,required:true})+select('Tipo de destino','destinationType',destinations,{value:lot.destinationType})+input('Produtor','producer',{value:lot.producer,required:true})+input('Origem','origin',{value:lot.origin})+input('Caixas','boxes',{type:'number',value:lot.boxes,attrs:'min="1" step="1"',inline:true})+input('Peso (kg)','weightKg',{type:'number',value:lot.weightKg,attrs:'min="0.01" step="0.01"',inline:true}) + rangeFields(),
    perform:values=>patch(lotPath(lot.id),{version:lot.version,variety:values.variety,client:values.client,destination:values.destination,destinationType:values.destinationType,producer:values.producer,origin:values.origin,boxes:toNumber(values.boxes) ?? null,weightKg:toNumber(values.weightKg) ?? null,...rangeData(values)}),after:refresh});
}

const moveNames = {preparar:'Registrar preparação',carregar:'Registrar carregamento',despachar:'Confirmar despacho',receber:'Registrar recebimento',retornar:'Retornar fase','validar-despacho':'Validar despacho','confirmar-transferencia':'Confirmar transferência'};
async function moveLot(modal,lot,action,refresh) {
  const loading = action === 'carregar';
  const chamber = (action === 'retornar' && lot.phase === 1) || action === 'preparar';
  const transfer = list(lot.permissions).includes('compartilhar') && ['carregar','despachar','receber'].includes(action);
  const [environments,trips,shares] = await Promise.all([loading || chamber ? api('/ambientes') : [],loading ? api('/viagens') : [],transfer ? api(`${lotPath(lot.id)}/compartilhamentos`) : []]);
  const validEnvironments = list(environments).filter(item => item.type === (loading ? 'compartimento' : 'camara'));
  const validTrips = list(trips).filter(trip=>![2,3,'em_transito','concluida'].includes(trip.phase));
  if ((loading || chamber) && !validEnvironments.length) throw new Error(`Cadastre ${loading ? 'um compartimento' : 'uma câmara fria'} para registrar esta movimentação.`);
  if (loading && !validTrips.length) throw new Error('Cadastre uma viagem para registrar o carregamento.');
  const reasonsRequired = ['retornar','validar-despacho'].includes(action);
  const form = showForm(modal,{title:moveNames[action],description:`Lote ${lot.id}`,
    fields:(loading || chamber ? select(loading ? 'Compartimento' : 'Câmara fria','environmentId',objOptions(validEnvironments)) : '')
      + (loading ? select('Viagem','tripId',validTrips.map(item=>[item.id,[item.id,item.vehicle].filter(Boolean).join(' · ')])) + '<div class="field full" id="stop-picker"></div>' : '')
      + (shares.some(item=>item.status==='aceito') ? select('Transferir responsabilidade','responsibleCompanyId',shares.filter(item=>item.status==='aceito').map(item=>[item.companyId,item.company]),{required:false,placeholder:'Seguir configuração do fluxo'}) : '') + effectiveAt() + note(reasonsRequired ? 'Justificativa' : 'Observação (opcional)','reason',reasonsRequired),
    perform:values=>post(`${lotPath(lot.id)}/${action}`,{version:lot.version,effectiveAt:toDate(values.effectiveAt),environmentId:toNumber(values.environmentId),tripId:trim(values.tripId),stopId:toNumber(values.stopId),responsibleCompanyId:toNumber(values.responsibleCompanyId),reason:trim(values.reason)}),after:refresh,done:'Movimentação registrada.'});
  if (loading) form.elements.tripId.addEventListener('change',()=>{
    const trip = validTrips.find(item=>String(item.id)===form.elements.tripId.value);
    form.querySelector('#stop-picker').innerHTML = list(trip?.stops).length ? select('Parada de destino','stopId',objOptions(trip.stops),{required:false,placeholder:'Sem parada definida'}) : '';
  });
}

function newTrip(modal,refresh) {
  showForm(modal,{title:'Nova viagem',description:'Deixe o código vazio para gerar automaticamente. Se preencher, use V- seguido de letras maiúsculas, números ou hífens, como V-001.',fields:input('Código da viagem (opcional)','id',{attrs:'placeholder="V-001" maxlength="34" pattern="V-[A-Z0-9][A-Z0-9\\-]{0,31}" title="Use V- seguido de letras maiúsculas, números ou hífens. Exemplo: V-001."'}) + input('Veículo','vehicle',{required:true}) + input('Transportadora','carrier',{required:true}) + input('Responsável','responsible',{required:true}) + input('Origem','origin') + note('Paradas de destino (uma por linha)','stops',true) + select('Fonte de localização','source',[['celular','Celular'],['externa','Sistema externo']],{required:false,placeholder:'Definir depois'}),
    perform:values=>post('/viagens',{id:trim(values.id),vehicle:values.vehicle.trim(),carrier:values.carrier.trim(),responsible:values.responsible.trim(),origin:trim(values.origin),stops:values.stops.split('\n').map(name=>name.trim()).filter(Boolean).map(name=>({name})),source:trim(values.source)}),after:refresh,done:'Viagem cadastrada.'});
}

function shareLot(modal,lot,refresh) {
  showForm(modal,{title:'Compartilhar lote',description:'Informe pelo menos um acesso e o identificador da empresa convidada.',
    fields:input('Identificador da empresa','companyId',{type:'number',required:true,attrs:'min="1" step="1"'}) + `<div class="field full">${['consultar','laudo','receber','rota','operar'].map(right=>choose(accessLabels[right],'rights',right==='consultar',right)).join('')}</div>` + input('Válido até (opcional)','expiresAt',{type:'datetime-local'}) + input('Início do acesso aos dados (opcional)','from',{type:'datetime-local'}) + input('Fim do acesso aos dados (opcional)','to',{type:'datetime-local'}),
    perform:(values,data)=>post(`${lotPath(lot.id)}/compartilhamentos`,{companyId:toNumber(values.companyId),rights:data.getAll('rights'),expiresAt:toDate(values.expiresAt),from:toDate(values.from),to:toDate(values.to)}),after:refresh,done:'Compartilhamento registrado.'});
}

function editFlow(modal,flow,refresh) {
  const selectedRoles = flow.allowedRolesByAction || {};
  const roleTable = table(['Ação',...flowRoles.map(([,label])=>label)],flowActions.map(([action,label])=>`<tr><th scope="row">${esc(label)}</th>${flowRoles.map(([role,roleLabel])=>`<td><input type="checkbox" name="permissao-${action}" value="${role}" aria-label="${esc(`${label}, ${roleLabel}`)}" ${!selectedRoles[action] || selectedRoles[action].includes(role) ? 'checked' : ''}></td>`).join('')}</tr>`));
  const detection = flow.departureDetection;
  const fields = select('Transferência de responsabilidade','transferAt',transferStages,{value:flow.transferAt})
    + choose('Exigir aceite na transferência','requireAcceptance',flow.requireAcceptance)
    + input('Minutos sem medição para alertar','absenceMinutes',{type:'number',value:flow.absenceMinutes ?? '',attrs:'min="1" max="2880" step="1"'})
    + `<details class="field full" ${detection ? 'open' : ''}><summary>Detecção por posição</summary>${choose('Detectar saída da área configurada','useDetection',Boolean(detection))}<fieldset class="form-grid detection-fields" ${detection ? '' : 'disabled'}>${choose('Avançar com despacho provisório','automatic',flow.automatic)}${detectionFields.map(([name,label,min,max,step])=>input(label,name,{type:'number',value:detection?.[name],required:true,inline:true,attrs:`min="${min}" max="${max}" step="${step}"`})).join('')}</fieldset></details>`
    + `<details class="field full"><summary>Permissões por ação e papel</summary>${roleTable}</details>`;
  const form = showForm(modal,{title:'Configurar fluxo',description:`Versão atual ${flow.version}. A publicação vale para novos lotes.`,fields,submitLabel:'Publicar fluxo',
    perform:(values,data)=>{
      const allowedRolesByAction = Object.fromEntries(flowActions.map(([action])=>[action,data.getAll(`permissao-${action}`)]).filter(([,roles])=>roles.length !== flowRoles.length));
      const departureDetection = values.useDetection ? Object.fromEntries(detectionFields.map(([name])=>[name,toNumber(values[name])])) : null;
      return patch('/configuracoes/fluxo',{version:flow.version,transferAt:values.transferAt,requireAcceptance:Boolean(values.requireAcceptance),absenceMinutes:toNumber(values.absenceMinutes) ?? null,automatic:Boolean(values.automatic),departureDetection,allowedRolesByAction});
    },after:refresh,done:'Nova versão do fluxo publicada.'});
  form.elements.useDetection.addEventListener('change',event=>{ form.querySelector('.detection-fields').disabled = !event.target.checked; });
}

function maintainFruit(modal,fruit,refresh) {
  showForm(modal,{title:fruit ? 'Editar fruta e faixa' : 'Cadastrar fruta e faixa',
    fields:input('Nome da fruta','nome',{value:fruit?.nome,required:true})
      + input('Temperatura mínima (°C)','temp_min_c',{value:fruit?.temp_min_c,type:'number',attrs:'step="any"',required:true,inline:true})
      + input('Temperatura máxima (°C)','temp_max_c',{value:fruit?.temp_max_c,type:'number',attrs:'step="any"',required:true,inline:true})
      + input('Umidade mínima (%)','umidade_min_pct',{value:fruit?.umidade_min_pct,type:'number',attrs:'min="0" max="100" step="any"',required:true,inline:true})
      + input('Umidade máxima (%)','umidade_max_pct',{value:fruit?.umidade_max_pct,type:'number',attrs:'min="0" max="100" step="any"',required:true,inline:true})
      + input('Referência da faixa de conservação','fonte',{value:fruit?.fonte,required:true})
      + input('Risco no frio (opcional)','risco_no_frio',{value:fruit?.risco_no_frio}),
    perform:values=>{
      const body = {...values,risco_no_frio:trim(values.risco_no_frio) ?? null};
      ['temp_min_c','temp_max_c','umidade_min_pct','umidade_max_pct'].forEach(name=>{ body[name] = Number(values[name]); });
      if (body.temp_min_c >= body.temp_max_c || body.umidade_min_pct > body.umidade_max_pct) throw new Error('Confira a ordem dos limites de temperatura e umidade.');
      return fruit ? patch(`/frutas/${key(fruit.id)}`,{...body,version:fruit.version}) : post('/frutas',body);
    },after:refresh,done:'Faixa de conservação salva.'});
}

export async function openAction(action,id,environment) {
  const {modal,resources,refresh,chooseCompany,profile,updateProfile} = environment;
  const {lot} = resources;
  if (action in moveNames) { await moveLot(modal,lot,action,refresh); return; }
  const show = options => showForm(modal,{after:refresh,...options});
  switch (action) {
    case 'company': show({title:'Sua organização',fields:select('Empresa','companyId',objOptions(session.empresas,'nome'),{value:session.companyId}),perform:chooseCompany,after:null,done:'Empresa selecionada.'}); break;
    case 'accept-invite': acceptInvite(modal,refresh); break;
    case 'new-lot': await newLot(modal,refresh); break;
    case 'edit-lot': editLot(modal,lot,refresh); break;
    case 'new-fruit': maintainFruit(modal,null,refresh); break;
    case 'edit-fruit': maintainFruit(modal,list(resources.fruits).find(item=>String(item.id)===id),refresh); break;
    case 'new-trip': newTrip(modal,refresh); break;
    case 'new-environment': show({title:'Novo ambiente',fields:input('Nome','name',{required:true})+select('Tipo','type',[['camara','Câmara fria'],['compartimento','Compartimento']]),perform:values=>post('/ambientes',values)}); break;
    case 'new-sensor': show({title:'Novo sensor',fields:input('Nome','name',{required:true})+select('Fonte','type',[['thingspeak','ThingSpeak'],['manual','Manual']])+input('Canal ThingSpeak (se aplicável)','channel',{type:'number',attrs:'min="1" step="1"'})+select('Ambiente (opcional)','environmentId',objOptions(resources.environments),{required:false,placeholder:'Vincular depois'}),perform:values=>post('/sensores',{name:values.name,type:values.type,channel:toNumber(values.channel),environmentId:toNumber(values.environmentId)})}); break;
    case 'link-sensor': show({title:'Vincular sensor',fields:select('Ambiente','environmentId',objOptions(resources.environments))+effectiveAt(),perform:values=>post(`/sensores/${key(id)}/vincular`,{environmentId:toNumber(values.environmentId),effectiveAt:toDate(values.effectiveAt)})}); break;
    case 'unlink-sensor': show({title:'Desvincular sensor',fields:effectiveAt(),perform:values=>post(`/sensores/${key(id)}/desvincular`,{effectiveAt:toDate(values.effectiveAt)})}); break;
    case 'manual-reading': show({title:'Registrar leitura manual',description:'Use os valores medidos e informe o horário da coleta.',fields:input('Código numérico da leitura','entryId',{type:'number',required:true,attrs:'min="1" step="1"'}) + input('Horário da medição','measuredAt',{type:'datetime-local',required:true}) + input('Temperatura (°C)','temperature',{type:'number',required:true,attrs:'step="any"'}) + input('Umidade (%)','humidity',{type:'number',attrs:'min="0" max="100" step="any"'}) + input('Luminosidade (lux)','lux',{type:'number',attrs:'min="0" step="any"'}),perform:values=>post(`/sensores/${key(id)}/leituras`,{entryId:Number(values.entryId),measuredAt:toDate(values.measuredAt),temperature:Number(values.temperature),humidity:toNumber(values.humidity),lux:toNumber(values.lux)})}); break;
    case 'dispatch-trip': show({title:'Despachar viagem',description:'Os lotes que aguardam despacho serão registrados individualmente.',fields:effectiveAt()+note('Justificativa (opcional)','reason'),perform:values=>post(`${tripPath(id)}/despachar`,{version:resources.trip.version,effectiveAt:toDate(values.effectiveAt),reason:trim(values.reason)}),after:async result=>{toast(`${list(result.dispatched).length} lotes despachados. ${list(result.skipped).length} permaneceram na fase atual.`);await refresh();},done:''}); break;
    case 'stop-remote-tracking': show({title:'Encerrar fonte de localização',description:`Viagem ${id}`,fields:note('Motivo','reason',true),perform:values=>post(`${tripPath(id)}/rastreio/encerrar`,{version:resources.trip.version,reason:values.reason})}); break;
    case 'share': shareLot(modal,lot,refresh); break;
    case 'revoke-share': show({title:'Revogar compartilhamento',description:`Confirme a remoção do acesso ao lote ${lot.id}.`,perform:()=>del(`${lotPath(lot.id)}/compartilhamentos/${key(id)}`),done:'Compartilhamento revogado.'}); break;
    case 'accept-share': show({title:'Aceitar compartilhamento',perform:()=>post(`/compartilhamentos/${key(id)}/aceitar`),done:'Acesso aceito.'}); break;
    case 'issue-report': show({title:'Gerar link secreto do laudo',description:'A emissão grava uma revisão com os dados atuais. Entregue o link apenas a quem tem autorização para consultar o laudo.',fields:input('Vencimento (opcional)','expiresAt',{type:'datetime-local'})+note('Motivo da emissão (opcional)','reason'),perform:values=>post(`${lotPath(lot.id)}/laudo`,{expiresAt:toDate(values.expiresAt),reason:trim(values.reason)}),after:async result=>{
      const url = new URL(publicUrl(lot.publicCode,await publicConfig()));
      url.search = '';
      url.hash = `laudo/${key(result.token)}`;
      reveal(modal,'Link do laudo','Link secreto',url.href);
    },done:''}); break;
    case 'revoke-report': show({title:'Revogar link do laudo',perform:()=>del(`${lotPath(lot.id)}/laudo`),done:'Link revogado.'}); break;
    case 'treat-alert': show({title:'Tratar alerta',fields:select('Situação','status',[['reconhecida','Reconhecida'],['resolvida','Resolvida']])+note('Justificativa','reason',true),perform:values=>post(`/alertas/${key(id)}/tratar`,{...values,version:list(resources.alerts).find(item=>String(item.id)===id)?.version})}); break;
    case 'new-company': show({title:'Nova empresa',fields:input('Nome','nome',{required:true}),perform:values=>post('/empresas',values,{withoutCompany:true})}); break;
    case 'edit-company': {
      const item = list(resources.companies).find(company=>String(company.id)===id);
      show({title:'Editar empresa',fields:input('Nome','nome',{value:item.nome,required:true})+choose('Empresa ativa','ativo',item.ativo),perform:values=>api(`/empresas/${key(id)}`,{method:'PATCH',body:{nome:values.nome,ativo:Boolean(values.ativo)},withoutCompany:true})});
      break;
    }
    case 'invite-company-admin': invite(modal,`/empresas/${key(id)}/convites`,refresh,true); break;
    case 'invite-member': invite(modal,'/equipe/convites',refresh); break;
    case 'revoke-invite': show({title:'Revogar convite pendente',perform:()=>del(`/equipe/convites/${key(id)}`),done:'Convite revogado.'}); break;
    case 'edit-member': {
      const item = list(resources.team).find(member=>String(member.id)===id);
      show({title:'Editar acesso',description:item.nome,fields:select('Papel','papel',formRoles,{value:item.papel})+choose('Acesso ativo','ativo',item.ativo),perform:values=>patch(`/equipe/${key(id)}`,{papel:values.papel,ativo:Boolean(values.ativo)})});
      break;
    }
    case 'change-password': show({title:'Alterar senha',fields:input('Senha atual','senha_atual',{type:'password',required:true,attrs:'autocomplete="current-password"'})+input('Nova senha','nova_senha',{type:'password',required:true,attrs:'autocomplete="new-password"'}),perform:values=>post('/conta/senha',values,{withoutCompany:true}),done:'Senha alterada.'}); break;
    case 'edit-profile': {
      const person = profile();
      const timezoneItems = new Set([person.fuso,'America/Sao_Paulo','America/Recife','America/Bahia','America/Manaus','America/Rio_Branco','America/Noronha','UTC']);
      show({title:'Editar perfil',fields:input('Nome de exibição','nome',{value:person.nome,required:true})+select('Idioma','idioma',[['pt-BR','Português do Brasil']],{value:person.idioma})+select('Fuso horário','fuso',[...timezoneItems].filter(Boolean).map(zone=>[zone,zone.replaceAll('_',' ')]),{value:person.fuso})+choose('Receber avisos de conservação','avisos_conservacao',person.avisos_conservacao),perform:values=>api('/perfil',{method:'PATCH',body:{...values,avisos_conservacao:Boolean(values.avisos_conservacao)},withoutCompany:true}),after:updateProfile});
      break;
    }
    case 'edit-enterprise': show({title:'Editar identidade da empresa',fields:input('Nome de exibição','nome',{value:resources.enterprise.nome,required:true}),perform:values=>patch('/configuracoes/empresa',values)}); break;
    case 'edit-role': {
      const role = list(resources.roles).find(item=>item.papel===id);
      show({title:'Editar permissões do papel',description:formRoles.find(([value])=>value===id)?.[1],fields:`<div class="field full">${list(role.limite).map(permission=>choose(accessLabels[permission],'permissoes',role.permissoes.includes(permission),permission)).join('')}</div>`,perform:(_,data)=>patch(`/papeis/${key(id)}`,{permissoes:data.getAll('permissoes')})});
      break;
    }
    case 'edit-flow': {
      editFlow(modal,resources.flow,refresh);
      break;
    }
    case 'new-integration': show({title:'Nova integração',description:'A credencial será exibida após o cadastro.',fields:input('Nome','nome',{required:true})+input('Vencimento','expira_em',{type:'datetime-local',required:true})+`<div class="field full">${['consultar','operar','receber','integrar'].map(right=>choose(accessLabels[right],'permissoes',false,right)).join('')}</div>`+input('Tipo de recurso (opcional)','recurso_tipo')+input('Identificador do recurso (opcional)','recurso_id'),perform:(values,data)=>post('/integracoes',{nome:values.nome,expira_em:toDate(values.expira_em),permissoes:data.getAll('permissoes'),recurso_tipo:trim(values.recurso_tipo),recurso_id:trim(values.recurso_id)}),after:async result=>{await refresh();reveal(modal,'Credencial da integração','Copie e guarde em um local seguro',result.token);}}); break;
    case 'revoke-integration': show({title:'Revogar integração',perform:()=>del(`/integracoes/${key(id)}`),done:'Credencial revogada.'}); break;
  }
}

function settingsPanel(title,body,action='') {
  return `<div class="panel-head"><h2>${esc(title)}</h2>${action}</div><div class="panel-body">${body}</div>`;
}

export function settingsView({tab,resources,person,enterprise,permitted}) {
  const tabs = [['perfil','Meu perfil']];
  if (enterprise) tabs.push(['empresa','Empresa']);
  if (permitted('consultar')) tabs.push(['acessos','Acessos recebidos']);
  if (permitted('operar')) tabs.push(['frutas','Frutas e faixas']);
  if (permitted('administrar')) tabs.push(['equipe','Equipe e acessos'],['papeis','Papéis e permissões'],['fluxo','Fluxo da operação']);
  if (permitted('integrar')) tabs.push(['integracoes','Integrações']);
  if (!tabs.some(([id])=>id===tab)) tab = 'perfil';
  let markup;
  if (tab === 'perfil') markup = settingsPanel('Meu perfil',info('Nome',person?.nome) + (person?.email ? info('E-mail',person.email) : '') + info('Idioma','Português do Brasil') + info('Fuso horário',person?.fuso?.replaceAll('_',' ')) + info('Avisos de conservação',person?.avisos_conservacao ? 'Ativados' : 'Desativados') + `<div class="actions section-space">${button('Alterar senha','change-password')}${button('Aceitar convite','accept-invite')}</div>`,button('Editar perfil','edit-profile'));
  if (tab === 'empresa') markup = settingsPanel('Identidade da empresa',info('Nome',resources.enterprise?.nome || enterprise.nome)+info('Identificador da empresa',String(enterprise.id))+info('Papel',formRoles.find(([value])=>value===enterprise.papel)?.[1] || enterprise.papel)+info('Permissões',list(enterprise.permissoes).map(value=>accessLabels[value] || value).join(', ')),resources.enterprise ? button('Editar empresa','edit-enterprise') : '');
  if (tab === 'acessos') markup = settingsPanel('Acessos recebidos',table(['Lote','Empresa','Permissões','Situação','Ações'],list(resources.receivedShares).map(share=>`<tr><td>${share.status === 'aceito' ? `<a href="#lote/${key(share.lotId)}">${esc(share.lotId)} ↗</a>` : esc(share.lotId)}</td><td>${esc(share.company)}</td><td>${esc(list(share.rights).map(value=>accessLabels[value] || value).join(', '))}</td><td>${tag(share.status,share.status==='aceito'?'green':'')}</td><td>${share.status === 'pendente' ? button('Aceitar','accept-share',share.id) : ''}</td></tr>`),'Nenhum acesso compartilhado com esta empresa.'));
  if (tab === 'equipe') {
    const pending = list(resources.invites).filter(invite=>!invite.revogado_em && !invite.usado_em && Date.parse(invite.expira_em)>Date.now());
    markup = settingsPanel('Equipe e acessos',table(['Pessoa','Papel','Situação','Ações'],list(resources.team).map(item=>`<tr><td><strong>${esc(item.nome)}</strong><small>${esc(item.email)}</small></td><td>${esc(formRoles.find(([id])=>id===item.papel)?.[1] || item.papel)}</td><td>${tag(item.ativo ? 'Ativo' : 'Inativo',item.ativo ? 'green' : '')}</td><td>${button('Editar','edit-member',item.id)}</td></tr>`),'Nenhum integrante cadastrado.') + `<h3 class="section-space">Convites pendentes</h3>${table(['E-mail','Papel','Vencimento','Ações'],pending.map(invite=>`<tr><td>${esc(invite.email)}</td><td>${esc(formRoles.find(([id])=>id===invite.papel)?.[1] || invite.papel)}</td><td>${date(invite.expira_em)}</td><td>${button('Revogar','revoke-invite',invite.id,'danger')}</td></tr>`),'Nenhum convite pendente.')}`,button('＋ Convidar pessoa','invite-member'));
  }
  if (tab === 'papeis') markup = settingsPanel('Papéis e permissões',table(['Papel','Permissões','Ações'],list(resources.roles).map(item=>`<tr><td>${esc(formRoles.find(([id])=>id===item.papel)?.[1] || item.papel)}</td><td>${esc(list(item.permissoes).map(permission=>accessLabels[permission] || permission).join(', ') || 'Nenhuma permissão concedida')}</td><td>${item.papel === 'administrador' ? tag('Permissões fixas') : button('Editar','edit-role',item.papel)}</td></tr>`),'Nenhum papel disponível.'));
  if (tab === 'frutas') markup = settingsPanel('Frutas e faixas',table(['Fruta','Temperatura','Umidade','Referência','Ações'],list(resources.fruits).map(item=>`<tr><td><strong>${esc(item.nome)}</strong>${item.risco_no_frio ? `<small>${esc(item.risco_no_frio)}</small>` : ''}</td><td>${number(item.temp_min_c)} a ${number(item.temp_max_c)} °C</td><td>${number(item.umidade_min_pct)} a ${number(item.umidade_max_pct)}%</td><td>${esc(item.fonte || '—')}</td><td>${button('Editar','edit-fruit',item.id)}</td></tr>`),'Nenhuma fruta disponível.'),button('＋ Cadastrar fruta','new-fruit'));
  if (tab === 'fluxo') {
    const flow = resources.flow;
    markup = settingsPanel('Fluxo da operação',flow ? info('Versão',String(flow.version))+info('Transferência de responsabilidade',transferStages.find(([value])=>value===flow.transferAt)?.[1] || flow.transferAt)+info('Aceite na transferência',flow.requireAcceptance ? 'Obrigatório' : 'Opcional')+info('Alerta de ausência de medição',flow.absenceMinutes ? `${flow.absenceMinutes} min` : 'Desativado')+info('Detecção de saída',flow.departureDetection ? 'Configurada' : 'Desativada')+info('Avanço por saída detectada',flow.automatic ? 'Ativado' : 'Desativado') : empty('Nenhuma configuração disponível.'),flow ? button('Editar fluxo','edit-flow') : '');
  }
  if (tab === 'integracoes') markup = settingsPanel('Integrações',table(['Integração','Permissões','Vencimento','Ações'],list(resources.integrations).map(item=>`<tr><td>${esc(item.nome)}</td><td>${esc(list(item.permissoes).map(value=>accessLabels[value] || value).join(', '))}</td><td>${date(item.expira_em)}</td><td>${item.revogado_em ? tag('Revogada') : button('Revogar','revoke-integration',item.id,'danger')}</td></tr>`),'Nenhuma integração cadastrada.'),button('＋ Nova integração','new-integration'));
  return `<div class="settings-layout"><nav class="settings-menu" aria-label="Configurações">${tabs.map(([id,label])=>`<button type="button" data-settings="${id}" class="${id===tab ? 'active' : ''}" aria-pressed="${id===tab}">${label}</button>`).join('')}</nav><section class="panel">${markup}</section></div>`;
}
