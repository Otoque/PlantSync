import {date, empty, esc, number, table} from './produto-texto.js';

const phases = {0:'Preparação',1:'Aguardando despacho',2:'Em trânsito',3:'Recebido',preparacao:'Preparação',carregamento:'Carregamento',aguardando_despacho:'Aguardando despacho',em_transito:'Em trânsito',recebimento:'Recebimento',recebido:'Recebido'};
const temperature = value => value == null ? '—' : `${number(value)} °C`;
const readingDate = reading => Date.parse(reading.data_hora);

export function readingsTable(items, lot) {
  const ordered = (items || []).slice().sort((a,b) => readingDate(b) - readingDate(a));
  return table(['Horário','Temperatura','Umidade','Origem','Etapa','Condição'], ordered.map(reading => {
    const value = reading.temperatura_c;
    const flag = value == null || lot.range?.[0] == null || lot.range?.[1] == null ? '—' : value < lot.range[0] ? 'Abaixo da faixa' : value > lot.range[1] ? 'Acima da faixa' : 'Dentro da faixa';
    return `<tr><td>${date(reading.data_hora)}</td><td>${temperature(value)}</td><td>${reading.umidade_pct == null ? '—' : `${number(reading.umidade_pct)}%`}</td><td>${esc(reading.fonte || '—')}<small>${esc(reading.ambiente)}</small></td><td>${esc(phases[reading.fase] || reading.fase || '—')}</td><td>${esc(flag)}</td></tr>`;
  }), 'Nenhuma leitura registrada para este recorte.');
}

const chartTime = timestamp => date(timestamp);
const eventTitle = {preparar:'Preparação',preparado:'Preparação',carregar:'Carregamento',carregado:'Carregamento',despachar:'Despacho',despachado:'Despacho',receber:'Recebimento',recebido:'Recebimento',retornar:'Retorno',retornado:'Retorno',saida_detectada:'Saída detectada',despacho_validado:'Despacho validado'};

function eventLines(selected, events) {
  const start = readingDate(selected[0]);
  const end = readingDate(selected.at(-1));
  const marks = events.map(event => ({x:Date.parse(event.efetivo_em), label:eventTitle[event.tipo] || String(event.tipo || '').replaceAll('_',' ')}))
    .filter(mark => mark.x >= start && mark.x <= end && mark.label);
  return {
    id:'plantSyncEvents',
    afterDatasetsDraw(chart) {
      const {ctx,chartArea,scales} = chart;
      ctx.save();
      ctx.font = '11px system-ui';
      for (const {x,label} of marks) {
        const pixel = scales.x.getPixelForValue(x);
        ctx.strokeStyle = '#647a69';
        ctx.setLineDash([3,4]);
        ctx.beginPath();
        ctx.moveTo(pixel,chartArea.top);
        ctx.lineTo(pixel,chartArea.bottom);
        ctx.stroke();
        ctx.fillStyle = '#345644';
        ctx.fillText(label,Math.max(chartArea.left,Math.min(pixel+5,chartArea.right-ctx.measureText(label).width)),chartArea.top+13);
      }
      ctx.restore();
    }
  };
}

function graphData(selected, lot) {
  const values = [];
  selected.forEach((item,index) => {
    const previous = selected[index-1];
    if (previous && (item.quebra || item.fonte_id !== previous.fonte_id || item.ambiente !== previous.ambiente)) {
      values.push({x:(readingDate(item)+readingDate(previous))/2,y:null});
    }
    values.push({x:readingDate(item),y:item.temperatura_c});
  });
  const minX = readingDate(selected[0]);
  const maxX = readingDate(selected.at(-1));
  const limits = (lot.range || []).flatMap((value,index) => typeof value === 'number' ? [{label:index === 0 ? 'Limite inferior' : 'Limite superior',data:[{x:minX,y:value},{x:maxX,y:value}],borderDash:[5,5],borderColor:'#aa753d',borderWidth:1,pointRadius:0}] : []);
  const valid = values.filter(point=>Number.isFinite(point.y));
  const minimum = valid.reduce((best,point)=>point.y<best.y?point:best);
  const maximum = valid.reduce((best,point)=>point.y>best.y?point:best);
  const extrema = minimum === maximum
    ? [{label:'Mínima e máxima',data:[minimum],showLine:false,pointStyle:'rectRounded',pointRadius:5,backgroundColor:'#245b43',order:0}]
    : [{label:'Mínima',data:[minimum],showLine:false,pointStyle:'rectRot',pointRadius:6,backgroundColor:'#316b9b',order:0},
       {label:'Máxima',data:[maximum],showLine:false,pointStyle:'triangle',pointRadius:7,backgroundColor:'#a54537',order:0}];
  return [{label:'Temperatura',data:values,borderColor:'#245b43',backgroundColor:'#245b43',borderWidth:2,pointRadius:values.length > 200 ? 0 : 2,pointHoverRadius:5,spanGaps:false,order:1}, ...limits, ...extrema];
}

export function drawReadings(items, events, lot) {
  const target = document.getElementById('readings-chart');
  const readings = items.filter(item => Number.isFinite(readingDate(item))).sort((a,b) => readingDate(a)-readingDate(b));
  if (!readings.length) {
    target.innerHTML = empty('Nenhuma leitura registrada para este lote.');
    return;
  }
  const periods = Array.from(new Set(readings.map(item => item.fase).filter(value => value != null)));
  target.innerHTML = `<div class="toolbar"><label class="field">Etapa<select id="reading-range"><option value="all">Todas as etapas</option>${periods.map(value => `<option value="${esc(value)}">${esc(phases[value] || value)}</option>`).join('')}</select></label><label class="field">Período<select id="reading-period"><option value="all">Todo o recorte</option><option value="24">Últimas 24 horas do recorte</option><option value="3">Últimas 3 horas do recorte</option><option value="custom">Personalizado</option></select></label></div><div class="toolbar" id="custom-period" hidden><label class="field">De<input type="datetime-local" id="reading-start"></label><label class="field">Até<input type="datetime-local" id="reading-end"></label></div><div id="reading-graph"></div><details class="section-space"><summary>Ver dados do gráfico em tabela</summary><div id="reading-alternative"></div></details>`;
  const container = target.querySelector('#reading-graph');
  const type = target.querySelector('#reading-range');
  const period = target.querySelector('#reading-period');
  const customPeriod = target.querySelector('#custom-period');
  const startField = target.querySelector('#reading-start');
  const endField = target.querySelector('#reading-end');
  let chart;
  function render() {
    chart?.destroy();
    const stage = readings.filter(item=>type.value === 'all' || String(item.fase) === type.value);
    const custom = period.value === 'custom';
    customPeriod.hidden = !custom;
    const end = custom && endField.value ? Date.parse(endField.value) : Infinity;
    const start = custom ? (startField.value ? Date.parse(startField.value) : -Infinity) : period.value === 'all' ? -Infinity : readingDate(stage.at(-1))-Number(period.value)*3600000;
    const selected = stage.filter(item => readingDate(item) >= start && readingDate(item) <= end);
    const values = selected.map(item => item.temperatura_c).filter(Number.isFinite);
    target.querySelector('#reading-alternative').innerHTML = readingsTable(selected,lot);
    if (!values.length) {
      container.innerHTML = empty(start > end ? 'Escolha um horário final posterior ao inicial.' : 'Nenhuma medição de temperatura neste período.');
      return;
    }
    const minimum = Math.min(...values);
    const maximum = Math.max(...values);
    container.innerHTML = `<div class="chart-box"><canvas role="img" aria-label="Temperaturas registradas no lote, limites e eventos"></canvas></div><div class="chart-sub"><span>Mínima <strong>${temperature(minimum)}</strong></span><span>Máxima <strong>${temperature(maximum)}</strong></span><span>${values.length} ${values.length === 1 ? 'medição' : 'medições'}</span></div>`;
    if (!globalThis.Chart) {
      container.querySelector('.chart-box').innerHTML = empty('Gráfico indisponível. Os dados estão na tabela abaixo.');
      return;
    }
    chart = new globalThis.Chart(container.querySelector('canvas'),{
      type:'line',data:{datasets:graphData(selected,lot)},plugins:[eventLines(selected,events)],
      options:{responsive:true,maintainAspectRatio:false,parsing:false,animation:false,
        scales:{x:{type:'linear',ticks:{maxTicksLimit:5,callback:timestamp => chartTime(timestamp)}},y:{ticks:{callback:value => temperature(value)}}},
        plugins:{legend:{position:'bottom'},tooltip:{callbacks:{title:entries => entries.length ? chartTime(entries[0].parsed.x) : '',label:item => `${item.dataset.label} ${temperature(item.parsed.y)}`}}}}
    });
  }
  type.addEventListener('change',render);
  period.addEventListener('change',render);
  startField.addEventListener('change',render);
  endField.addEventListener('change',render);
  render();
  return () => chart?.destroy();
}

function coordinates(point) {
  if (point?.latitude == null || point?.longitude == null) return null;
  const coords = [Number(point.latitude),Number(point.longitude)];
  return coords.every(Number.isFinite) && Math.abs(coords[0]) <= 90 && Math.abs(coords[1]) <= 180 ? coords : null;
}

function trajectorySegments(points) {
  const segments = [];
  for (const point of points) {
    if (!segments.length || point.break || point.sourceId !== segments.at(-1).source) segments.push({source:point.sourceId,coords:[]});
    segments.at(-1).coords.push(coordinates(point));
  }
  return segments;
}

export function drawMap(trip, result, error, showPositions=false) {
  const container = document.getElementById('route-map');
  const state = document.getElementById('map-state');
  const tableContainer = document.getElementById('position-list');
  const points = (Array.isArray(result?.items) ? result.items : []).filter(coordinates).sort((a,b) => Date.parse(a.measuredAt)-Date.parse(b.measuredAt));
  const plan = (Array.isArray(trip.plannedRoute) ? trip.plannedRoute : []).map(coordinates).filter(Boolean);
  if (showPositions && tableContainer && points.length) {
    tableContainer.innerHTML = `<details class="section-space"><summary>Ver posições em tabela</summary>${table(['Horário','Latitude','Longitude','Precisão','Fonte'], points.slice().reverse().map(point => `<tr><td>${date(point.measuredAt)}</td><td>${esc(point.latitude)}</td><td>${esc(point.longitude)}</td><td>${point.accuracy == null ? '—' : `${number(point.accuracy)} m`}</td><td>${esc(point.source === 'celular' ? 'Celular' : point.source === 'externa' ? 'Sistema externo' : point.source || '—')}</td></tr>`))}</details>`;
  }
  const latest = trip.latestPosition || points.at(-1);
  const locationMessage = error || (latest ? `Última posição em ${date(latest.measuredAt)}` : 'Nenhuma posição registrada para esta viagem.');
  state.textContent = [locationMessage, latest && Date.now()-Date.parse(latest.measuredAt)>900000 ? 'Sem atualização nos últimos 15 min' : '', plan.length > 1 ? 'Linha tracejada: percurso planejado' : '', points.length > 1 ? 'Linha contínua: posições registradas' : ''].filter(Boolean).join(' · ');
  if ((!points.length && plan.length < 2) || !globalThis.L) {
    container.hidden = true;
    return;
  }
  const L = globalThis.L;
  const map = L.map(container,{scrollWheelZoom:false,zoomAnimation:false,fadeAnimation:false,markerZoomAnimation:false});
  const base = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{
    maxZoom:19,
    referrerPolicy:'strict-origin-when-cross-origin',
    attribution:'&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap</a>'
  }).addTo(map);
  base.on('tileerror',()=>{
    state.textContent = locationMessage + ' · Base cartográfica indisponível; consulte as posições em tabela.';
  });
  const layer = L.featureGroup().addTo(map);
  if (plan.length > 1) L.polyline(plan,{color:'#a36a30',dashArray:'6 8',weight:3}).addTo(layer);
  for (const {coords} of trajectorySegments(points)) {
    if (coords.length > 1) L.polyline(coords,{color:'#245b43',weight:3}).addTo(layer);
    coords.forEach(point => L.circleMarker(point,{radius:3,color:'#245b43',fillOpacity:.8}).addTo(layer));
  }
  if (points.length) {
    const last = points.at(-1);
    const tooltip = document.createElement('span');
    tooltip.textContent = `Última posição · ${date(last.measuredAt)}${last.accuracy == null ? '' : ` · ${number(last.accuracy)} m`}`;
    L.circleMarker(coordinates(last),{radius:6,color:'#fff',weight:2,fillColor:'#245b43',fillOpacity:1}).bindTooltip(tooltip).addTo(layer);
  }
  map.fitBounds(layer.getBounds(),{padding:[24,24],maxZoom:13});
  return () => { map.stop(); map.remove(); };
}
