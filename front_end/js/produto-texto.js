export const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[char]);
export const number = value => value == null ? '—' : Number(value).toLocaleString('pt-BR', {maximumFractionDigits:2});
let timeZone = 'America/Sao_Paulo';

export function setTimezone(value) {
  try { timeZone = new Intl.DateTimeFormat('pt-BR',{timeZone:value}).resolvedOptions().timeZone; }
  catch { timeZone = 'America/Sao_Paulo'; }
}

export function date(value) {
  if (value == null || value === '') return '—';
  const instant = new Date(value);
  return Number.isFinite(instant.getTime()) ? instant.toLocaleString('pt-BR',{timeZone,dateStyle:'short',timeStyle:'short'}) : '—';
}
export const empty = message => `<p class="empty">${esc(message)}</p>`;

export function table(headers, rows, emptyMessage='Nenhum registro encontrado.') {
  return rows.length ? `<div class="table-wrap"><table><thead><tr>${headers.map(label => `<th scope="col">${esc(label)}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody></table></div>` : empty(emptyMessage);
}
