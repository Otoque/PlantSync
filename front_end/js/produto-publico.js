import {api, key} from './produto-api.js';
import {date, esc, number} from './produto-texto.js';
import {drawReadings, readingsTable} from './produto-monitor.js';

const title = document.getElementById('titulo');
const status = document.getElementById('estado');
const summary = document.getElementById('resumo');
const details = document.getElementById('dados');
const sealElement = document.getElementById('selo');
const report = document.getElementById('laudo');

function row(label,value) {
  if (value == null || value === '') return;
  const dt = document.createElement('dt');
  const dd = document.createElement('dd');
  dt.textContent = label;
  dd.textContent = value;
  details.append(dt,dd);
}

function showSummary(lot, isReport) {
  title.textContent = isReport ? `Laudo · ${lot.fruit}` : lot.fruit;
  row('Lote',lot.id);
  row('Produzido por',lot.producer);
  row('Origem',lot.origin);
  if (isReport && lot.revision) row('Emissão da revisão',date(lot.revision.issuedAt));
  if (lot.seal?.elegivel === true) {
    sealElement.textContent = lot.seal.titulo || 'Selo de conservação';
    sealElement.className = 'tag green section-space';
    sealElement.hidden = false;
  }
  summary.hidden = false;
  status.hidden = true;
}

function showReport(lot) {
  document.getElementById('publico').classList.add('report-page');
  const analysis = lot.analysis || {};
  const readings = Array.isArray(lot.readings) ? lot.readings : [];
  const events = Array.isArray(lot.events) ? lot.events : [];
  if (lot.seal?.elegivel === false && lot.seal.motivo) {
    sealElement.textContent = lot.seal.motivo;
    sealElement.hidden = false;
  }
  const risk = lot.seal?.elegivel === true && analysis.nivel ? `<p>Nível de risco <strong>${esc(analysis.nivel.replaceAll('_',' ').toLocaleLowerCase('pt-BR'))}</strong></p>` : '<p>Avaliação pendente</p>';
  report.innerHTML = `<section class="section-space"><h2>Conservação da carga</h2>${risk}${lot.seal?.elegivel === true && analysis.recomendacao ? `<p>${esc(analysis.recomendacao)}</p>` : ''}${analysis.amostras ? `<p>${number(analysis.amostras)} medições avaliadas · Calor ${number(analysis.graus_hora_acima)} °C·h · Frio ${number(analysis.graus_hora_abaixo)} °C·h</p>` : ''}<div id="readings-chart" class="section-space"></div></section><section class="section-space"><h2>Medições</h2>${lot.readingCount > readings.length ? `<p>Exibindo ${readings.length} de ${lot.readingCount} medições.</p>` : ''}${readingsTable(readings,lot)}</section><section class="section-space"><h2>Histórico</h2>${events.length ? `<ol class="timeline section-space">${events.map(event=>`<li><time>${date(event.efetivo_em)}</time><strong>${esc(String(event.tipo || '').replaceAll('_',' '))}</strong><p>${esc([event.autor,event.empresa,event.motivo].filter(Boolean).join(' · '))}</p></li>`).join('')}</ol>` : '<p>Nenhum evento registrado.</p>'}</section>`;
  report.hidden = false;
  drawReadings(readings,events,lot);
}

async function open() {
  const url = new URL(location.href);
  const code = url.searchParams.get('codigo');
  try {
    let path;
    const isReport = url.hash.startsWith('#laudo/');
    if (isReport) {
      const token = decodeURIComponent(url.hash.slice(7));
      url.hash = '';
      history.replaceState(null,'',url);
      path = `/laudos/${key(token)}`;
    } else if (code) path = `/publico/${key(code)}`;
    else throw new Error('Use o código QR da etiqueta para consultar o lote.');
    const lot = await api(path,{anonymous:true});
    showSummary(lot,isReport);
    if (isReport) showReport(lot);
  } catch (error) {
    status.textContent = error.message;
  }
}

open();
