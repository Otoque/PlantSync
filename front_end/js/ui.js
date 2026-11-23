export function escapar(valor) {
  return String(valor ?? "").replace(/[&<>"']/g, caractere =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[caractere]);
}

const dataRecife = new Intl.DateTimeFormat("pt-BR", {
  dateStyle: "short", timeStyle: "short", timeZone: "America/Recife",
});

export function formatarData(valor) {
  const data = new Date(valor);
  return valor && Number.isFinite(data.getTime()) ? dataRecife.format(data) : "—";
}

export function numero(valor, casas = 1) {
  return typeof valor === "number" && Number.isFinite(valor)
    ? valor.toLocaleString("pt-BR", { maximumFractionDigits: casas }) : "—";
}

const niveis = {
  VERDE: ["verde", "Verde"], AMARELO: ["amarelo", "Amarelo"],
  LARANJA: ["laranja", "Laranja"], VERMELHO: ["vermelho", "Vermelho"],
  SEM_DADOS: ["neutro", "Sem leituras"],
};

export function pilula(nivel) {
  const [tom, rotulo] = niveis[nivel] ?? niveis.SEM_DADOS;
  return `<span class="pilula ${tom}">${rotulo}</span>`;
}

export function nomeFruta(fruta) {
  const nome = fruta === "uva" ? "Uva de mesa" : String(fruta ?? "").replace(/[-_]/g, " ");
  return nome ? nome[0].toUpperCase() + nome.slice(1) : "Fruta";
}

export function faixa(valor) {
  return valor ? `${numero(valor.temp_min_c)} a ${numero(valor.temp_max_c)} °C` : "—";
}

export function mostrarResultadoDaSincronizacao(aviso, resultado) {
  const falhas = resultado.falhas ?? [];
  const resumo = `${resultado.novas} novas leituras. ${resultado.descartadas} descartadas.`;
  aviso.textContent = falhas.length
    ? `${resumo} Falha nos canais: ${falhas.map(item => item.canal).join(", ")}.` : resumo;
  aviso.classList.toggle("erro", falhas.length > 0);
}
