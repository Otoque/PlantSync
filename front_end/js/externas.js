import { requisitar } from "./dados.js";

const niveis = {
  VERDE: "Verde", AMARELO: "Amarelo", LARANJA: "Laranja",
  VERMELHO: "Vermelho", SEM_DADOS: "Sem dados",
};
const frutasConhecidas = new Map([["uva", "Uva de mesa"], ["manga", "Manga"]]);
const numero = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });
const horario = new Intl.DateTimeFormat("pt-BR", {
  dateStyle: "short", timeStyle: "short", timeZone: "America/Recife",
});
const meiaHora = 30 * 60 * 1000;

function elemento(id) {
  return document.getElementById(id);
}

function texto(id, valor) {
  elemento(id).textContent = valor ?? "—";
}

function data(valor) {
  const instante = Date.parse(valor);
  return Number.isFinite(instante) ? horario.format(instante) : "—";
}

function medida(valor, unidade) {
  return Number.isFinite(valor) ? `${numero.format(valor)} ${unidade}` : "—";
}

function intervalo(item) {
  return `${data(item.inicio)} → ${data(item.fim)} · ${medida(item.duracao_min, "min")}`;
}

function preencherLista(id, itens, formatar, vazio) {
  for (const item of itens) {
    const linha = document.createElement("li");
    linha.textContent = formatar(item);
    elemento(id).append(linha);
  }
  if (!itens.length) {
    const linha = document.createElement("li");
    linha.textContent = vazio;
    elemento(id).append(linha);
  }
}

function mostrarPublico(lote) {
  texto("titulo", lote.fruta);
  texto("produtor", lote.produtor);
  texto("origem", lote.origem);
  const confirmado = lote.selo_faixa_segura === true;
  const selo = elemento("selo");
  selo.hidden = false;
  selo.classList.toggle("selo-pendente", !confirmado);
  texto("selo-icone", confirmado ? "✓" : "–");
  texto("selo-titulo", confirmado ? "Transportado dentro da faixa segura" : "Selo ainda não disponível");
  texto("selo-descricao", confirmado ? "" : "O selo exige uma viagem encerrada com leituras suficientes e dentro dos critérios da faixa segura.");
}

function mostrarLaudo(lote) {
  const { analise, faixa_segura: faixa } = lote;
  texto("identificacao", `Laudo de transporte · Lote ${lote.id}`);
  texto("titulo", frutasConhecidas.get(lote.fruta) ?? lote.fruta);
  texto("produtor", lote.produtor);
  texto("origem", lote.origem);
  texto("destino", lote.destino);
  texto("inicio", data(lote.inicio));
  texto("fim", lote.fim ? data(lote.fim) : "Em trânsito");
  texto("ultima", analise.ultima_leitura ? data(analise.ultima_leitura) : "Aguardando leituras");
  texto("risco", niveis[analise.nivel] ?? "Indisponível");
  elemento("risco").dataset.nivel = analise.nivel;
  texto("recomendacao", analise.recomendacao);
  texto("faixa", `Faixa da carga: ${medida(faixa.temp_min_c, "°C")} a ${medida(faixa.temp_max_c, "°C")} · Umidade: ${medida(faixa.umidade_min_pct, "%")} a ${medida(faixa.umidade_max_pct, "%")}`);
  texto("calor", medida(analise.graus_hora_acima, "°C·h"));
  texto("frio", medida(analise.graus_hora_abaixo, "°C·h"));
  texto("calor-nivel", niveis[analise.nivel_acima]);
  texto("frio-nivel", niveis[analise.nivel_abaixo]);
  texto("leituras-resumo", analise.amostras
    ? `${numero.format(analise.amostras)} leituras · Mínima ${medida(analise.temp_min_c, "°C")} · Máxima ${medida(analise.temp_max_c, "°C")}`
    : "Nenhuma leitura disponível para este lote.");
  preencherLista("trechos", analise.trechos_fora_faixa ?? [], (trecho) => {
    const lado = trecho.lado === "acima" ? "Calor" : "Frio";
    return `${lado} · ${intervalo(trecho)} · Extremo ${medida(trecho.temp_extrema_c, "°C")}`;
  }, "Nenhum trecho registrado.");
  preencherLista("portas", analise.eventos_porta ?? [],
    (evento) => `${intervalo(evento)} · Pico de luz ${medida(evento.lux_max, "lux")}`,
    "Nenhum evento registrado.");
  elemento("imprimir").addEventListener("click", () => window.print());
  elemento("imprimir").hidden = false;
  iniciarGrafico(lote.leituras ?? [], faixa);
}

function agrupar(pontos) {
  const grupos = new Map();
  for (const ponto of pontos) {
    const janela = Math.floor(ponto.tempo / meiaHora);
    if (!grupos.has(janela)) grupos.set(janela, { tempo: 0, total: 0, quantidade: 0 });
    const grupo = grupos.get(janela);
    grupo.tempo += ponto.tempo;
    grupo.total += ponto.valor;
    grupo.quantidade += 1;
  }
  return Array.from(grupos.values(), (grupo) => ({
    tempo: grupo.tempo / grupo.quantidade,
    valor: grupo.total / grupo.quantidade,
  }));
}

function desenharCurva(pontos, faixa, leitura, inicio, fim, resumir) {
  const canvas = elemento("curva");
  const largura = canvas.clientWidth;
  const altura = canvas.clientHeight;
  if (!largura || !altura) return;
  const escala = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = Math.round(largura * escala);
  canvas.height = Math.round(altura * escala);
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  ctx.scale(escala, escala);
  const esquerda = 43;
  const topo = 12;
  const base = altura - 12;
  const direita = largura - 12;
  const { temp_min_c: piso, temp_max_c: teto } = faixa;
  let minimo = { valor: piso };
  let maximo = { valor: teto };
  for (const ponto of pontos) {
    if (ponto.valor < minimo.valor) minimo = ponto;
    if (ponto.valor > maximo.valor) maximo = ponto;
  }
  const menor = minimo.valor - 0.5;
  const maior = maximo.valor + 0.5;
  const x = (tempo) => esquerda + (direita - esquerda) * (tempo - inicio) / Math.max(1, fim - inicio);
  const y = (valor) => base - (base - topo) * (valor - menor) / (maior - menor);
  ctx.fillStyle = "#e6eee1";
  ctx.fillRect(esquerda, y(teto), direita - esquerda, y(piso) - y(teto));
  ctx.font = "11px system-ui";
  ctx.fillStyle = "#516055";
  ctx.strokeStyle = "#d9dfd3";
  for (let i = 0; i <= 4; i++) {
    const valor = menor + (maior - menor) * i / 4;
    ctx.fillText(numero.format(valor) + "°", 3, y(valor) + 4);
    ctx.beginPath();
    ctx.moveTo(esquerda, y(valor));
    ctx.lineTo(direita, y(valor));
    ctx.stroke();
  }
  const serie = resumir ? agrupar(pontos) : pontos;
  const corLinha = ctx.createLinearGradient(0, topo, 0, base);
  const acima = (y(teto) - topo) / (base - topo);
  const abaixo = (y(piso) - topo) / (base - topo);
  corLinha.addColorStop(acima, "#a04837");
  corLinha.addColorStop(acima, "#22513d");
  corLinha.addColorStop(abaixo, "#22513d");
  corLinha.addColorStop(abaixo, "#326ca6");
  ctx.strokeStyle = corLinha;
  ctx.lineWidth = 2;
  ctx.beginPath();
  serie.forEach((ponto, i) => {
    if (i === 0 || ponto.tempo - serie[i - 1].tempo > (resumir ? 2 : 1) * meiaHora) {
      ctx.moveTo(x(ponto.tempo), y(ponto.valor));
    } else {
      ctx.lineTo(x(ponto.tempo), y(ponto.valor));
    }
  });
  ctx.stroke();
  function pontoVisivel(ponto, raio, cor) {
    ctx.beginPath();
    ctx.arc(x(ponto.tempo), y(ponto.valor), raio, 0, 2 * Math.PI);
    ctx.fillStyle = cor;
    ctx.fill();
  }
  function destacarExtremo(ponto, cor) {
    if (!Number.isFinite(ponto.tempo)) return;
    pontoVisivel(ponto, 4, cor);
    const rotulo = medida(ponto.valor, "°C");
    const larguraRotulo = ctx.measureText(rotulo).width;
    const posicao = Math.max(esquerda, Math.min(x(ponto.tempo) + 7, direita - larguraRotulo));
    const alturaRotulo = ponto.valor > teto ? y(ponto.valor) + 16 : y(ponto.valor) - 8;
    ctx.fillStyle = "#fffdf8";
    ctx.fillRect(posicao - 2, alturaRotulo - 10, larguraRotulo + 4, 13);
    ctx.fillStyle = cor;
    ctx.fillText(rotulo, posicao, alturaRotulo);
  }
  if (!resumir || serie.length === 1) {
    for (const ponto of serie) pontoVisivel(ponto, 2, "#22513d");
  }
  destacarExtremo(minimo, "#326ca6");
  destacarExtremo(maximo, "#a04837");
  pontoVisivel(leitura, 4, "#202d24");
}

function iniciarGrafico(leituras, faixa) {
  const pontos = leituras.map((item) => ({
    item, tempo: Date.parse(item.data_hora), valor: item.temperatura_c,
  })).filter((ponto) => Number.isFinite(ponto.tempo) && Number.isFinite(ponto.valor));
  if (!pontos.length) return;
  const inicioViagem = pontos[0].tempo;
  const fimViagem = pontos.at(-1).tempo;
  const duracao = fimViagem - inicioViagem;
  const minimoZoom = Math.min(duracao, 3 * 60 * 60 * 1000);
  const seletor = elemento("leitura");
  const aproximar = elemento("aproximar");
  const afastar = elemento("afastar");
  let janela = duracao;
  seletor.max = String(pontos.length - 1);
  seletor.value = seletor.max;
  seletor.disabled = pontos.length === 1;
  elemento("grafico").hidden = false;
  function atualizar() {
    const atual = pontos[Number(seletor.value)];
    const inicio = Math.max(inicioViagem, Math.min(atual.tempo - janela / 2, fimViagem - janela));
    const fim = inicio + janela;
    const visiveis = pontos.filter((ponto) => ponto.tempo >= inicio && ponto.tempo <= fim);
    const resumir = janela > 3 * 60 * 60 * 1000;
    desenharCurva(visiveis, faixa, atual, inicio, fim, resumir);
    texto("grafico-janela", `${data(inicio)} → ${data(fim)} · ${resumir ? "Médias de 30 min" : "Leituras individuais"}`);
    texto("leitura-atual", `${data(atual.tempo)} · ${medida(atual.valor, "°C")} · Umidade ${medida(atual.item.umidade_pct, "%")} · Luz ${medida(atual.item.luminosidade_lux, "lux")}`);
    seletor.setAttribute("aria-valuetext", `${data(atual.tempo)} · ${medida(atual.valor, "°C")}`);
    aproximar.disabled = janela <= minimoZoom;
    afastar.disabled = janela >= duracao;
  }
  seletor.addEventListener("input", atualizar);
  aproximar.addEventListener("click", () => { janela = Math.max(minimoZoom, janela / 2); atualizar(); });
  afastar.addEventListener("click", () => { janela = Math.min(duracao, janela * 2); atualizar(); });
  new ResizeObserver(atualizar).observe(elemento("curva"));
}

async function abrirDocumento() {
  const publico = document.body.dataset.visao === "publico";
  const parametro = publico ? "codigo" : "token";
  const identificador = new URLSearchParams(location.search).get(parametro);
  if (!identificador || !/^[A-Za-z0-9_-]{1,128}$/.test(identificador)) {
    texto("estado", publico ? "Abra esta página pelo QR Code do lote." : "Abra o link completo recebido para consultar o laudo.");
    return;
  }
  const caminho = publico ? "/publico/" : "/laudos/";
  try {
    const lote = await requisitar(caminho + encodeURIComponent(identificador), { publica: true });
    if (publico) {
      mostrarPublico(lote);
      import("./mapa-publico.js").then(({ mostrarTrajeto }) => mostrarTrajeto(identificador)).catch(() => {});
    }
    else mostrarLaudo(lote);
    elemento("resultado").hidden = false;
    elemento("estado").hidden = true;
  } catch (erro) {
    texto("estado", erro.status === 404
      ? "O link não corresponde a um lote disponível."
      : "Não foi possível fazer a consulta. Recarregue a página para tentar de novo.");
  }
}

abrirDocumento();
