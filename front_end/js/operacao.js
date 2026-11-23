import { requisitar, linkPagina } from "./dados.js";
import { escapar, formatarData, numero, pilula, nomeFruta, faixa, mostrarResultadoDaSincronizacao } from "./ui.js";

const janelaTresHoras = 3 * 60 * 60 * 1000;
const meiaHora = 30 * 60 * 1000;
const limiteDePontosIndividuais = 60;
const formatarHora = new Intl.DateTimeFormat("pt-BR", {
  day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit",
  timeZone: "America/Recife",
});
let graficoAtivo;

function horaDaAmostra(amostra) {
  return new Date(amostra.data_hora).getTime();
}

function mediasDaViagem(leituras) {
  const intervalos = new Map();
  for (const leitura of leituras) {
    const hora = Math.floor(horaDaAmostra(leitura) / meiaHora) * meiaHora;
    const intervalo = intervalos.get(hora) || { soma: 0, total: 0 };
    intervalo.soma += leitura.temperatura_c;
    intervalo.total += 1;
    intervalos.set(hora, intervalo);
  }
  return [...intervalos].map(([x, grupo]) => ({ x, y: grupo.soma / grupo.total }));
}

function mostrarGrafico(elemento, leituras, limites) {
  const caixa = elemento.querySelector("[data-grafico]");
  if (!leituras.length || !globalThis.Chart) {
    caixa.hidden = true;
    return;
  }
  const linha = (label, data, borderColor, extras = {}) => ({
    label, data, borderColor, backgroundColor: borderColor, ...extras,
  });
  const inicio = horaDaAmostra(leituras[0]);
  const fim = horaDaAmostra(leituras.at(-1));
  const ponto = (leitura) => ({ x: horaDaAmostra(leitura), y: leitura.temperatura_c });
  const marcador = (rotulo, leitura, cor, estilo) => linha(rotulo, [ponto(leitura)], cor, {
    showLine: false, pointRadius: 7, pointHoverRadius: 9, pointStyle: estilo, order: -1,
  });
  const minima = elemento.querySelector("[data-minima-medida]");
  const maxima = elemento.querySelector("[data-maxima-medida]");
  const desenhar = (periodo) => {
    graficoAtivo?.destroy();
    const recent = periodo === "recente";
    const amostras = recent ? leituras.filter((leitura) => horaDaAmostra(leitura) >= fim - janelaTresHoras) : leituras;
    const extremos = amostras.reduce((picos, atual) => ({
      baixa: atual.temperatura_c < picos.baixa.temperatura_c ? atual : picos.baixa,
      alta: atual.temperatura_c > picos.alta.temperatura_c ? atual : picos.alta,
    }), { baixa: amostras[0], alta: amostras[0] });
    minima.textContent = numero(extremos.baixa.temperatura_c) + " °C";
    maxima.textContent = numero(extremos.alta.temperatura_c) + " °C";
    const marcas = extremos.baixa === extremos.alta
      ? [marcador("Mínima e máxima medidas", extremos.baixa, "#603b70", "rectRot")]
      : [
          marcador("Mínima medida", extremos.baixa, "#1d6093", "rectRot"),
          marcador("Máxima medida", extremos.alta, "#a83c22", "triangle"),
        ];
    const mostrarMedicoes = recent || amostras.length <= limiteDePontosIndividuais;
    const dados = mostrarMedicoes ? amostras.map(ponto) : mediasDaViagem(amostras);
    const margem = inicio === fim ? 5 * 60 * 1000 : 0;
    const linhaFaixa = (label, y) => linha(label, [{ x: dados[0].x - margem, y }, { x: fim + margem, y }], "#53735e", {
      borderDash: [5, 5], pointRadius: 0, borderWidth: 1,
    });
    try {
      graficoAtivo = new globalThis.Chart(caixa.querySelector("canvas"), {
        type: "line",
        data: { datasets: [
          linha(mostrarMedicoes ? "Temperatura" : "Média de 30 min", dados, "#315a48", { borderWidth: 2, pointRadius: dados.length <= limiteDePontosIndividuais ? 3 : 0 }),
          ...marcas,
          linhaFaixa("Limite inferior", limites.temp_min_c),
          linhaFaixa("Limite superior", limites.temp_max_c),
        ] },
        options: {
          responsive: true, maintainAspectRatio: false, animation: false,
          scales: {
            x: { type: "linear", suggestedMin: recent ? Math.max(inicio, fim - janelaTresHoras) : inicio, ticks: { maxTicksLimit: 5, callback: (valor) => formatarHora.format(Number(valor)) } },
            y: { title: { display: true, text: "Temperatura (°C)" } },
          },
          plugins: { tooltip: { callbacks: { title: (itens) => formatarHora.format(itens[0].parsed.x) } } },
        },
      });
    } catch {
      caixa.hidden = true;
    }
  };
  caixa.querySelector("select").addEventListener("change", (evento) => desenhar(evento.target.value));
  desenhar("completa");
}

function tabelaDeLeituras(leituras) {
  const ultimas = leituras.slice(-10).reverse();
  return `<details>
    <summary>Últimas ${ultimas.length} leituras</summary>
    <div class="rolagem"><table class="tabela">
      <thead><tr><th scope="col">Data e hora</th><th scope="col">Temperatura</th><th scope="col">Umidade</th></tr></thead>
      <tbody>${ultimas.map((leitura) => `<tr>
        <td>${escapar(formatarData(leitura.data_hora))}</td>
        <td>${numero(leitura.temperatura_c)} °C</td>
        <td>${leitura.umidade_pct == null ? "—" : numero(leitura.umidade_pct) + "%"}</td>
      </tr>`).join("")}</tbody>
    </table></div>
  </details>`;
}

function cartaoDeRisco(titulo, grausHora, nivel, desvio) {
  return `<section class="cartao"><h3>${titulo}</h3>
    <p><strong>${grausHora == null ? "—" : numero(grausHora) + " °C·h"}</strong></p>
    <p>Risco acumulado ${pilula(nivel)}</p>
    ${desvio ? `<p><span class="pilula amarelo">Desvio detectado</span> ${desvio}</p>` : ""}
  </section>`;
}

function faixaDeUmidade(valor) {
  return `${numero(valor.umidade_min_pct)} a ${numero(valor.umidade_max_pct)}%`;
}

function periodosDaViagem(analise) {
  const trechos = analise.trechos_fora_faixa ?? [];
  const portas = analise.eventos_porta ?? [];
  if (!trechos.length && !portas.length) return "";
  const linha = (tipo, evento, medida) => `<tr><td>${tipo}</td>
    <td>${escapar(formatarData(evento.inicio))}</td>
    <td>${numero(evento.duracao_min)} min</td><td>${medida}</td></tr>`;
  return `<section class="cartao"><h2>Ocorrências da viagem</h2><div class="rolagem"><table class="tabela">
    <thead><tr><th scope="col">Tipo</th><th scope="col">Início</th><th scope="col">Duração</th><th scope="col">Extremo</th></tr></thead>
    <tbody>${trechos.map((evento) => linha(evento.lado === "abaixo" ? "Frio" : "Calor", evento, numero(evento.temp_extrema_c) + " °C")).join("")}
      ${portas.map((evento) => linha("Porta aberta", evento, numero(evento.lux_max, 0) + " lux")).join("")}</tbody>
  </table></div></section>`;
}

function mostrarCompartilhamento(endereco, elemento) {
  const qr = elemento.querySelector("[data-qr]");
  if (!qr) return;
  if (!globalThis.QRCode) {
    qr.textContent = "QR indisponível. Abra o link da página pública.";
    return;
  }
  new globalThis.QRCode(qr, { text: endereco, width: 192, height: 192 });
}

async function enderecoPublico(codigo) {
  if (!codigo) return "";
  let endereco = new URL(linkPagina("publico.html", { codigo }));
  try {
    const resposta = await fetch("./qr-publico.local.json", {
      cache: "no-store", signal: AbortSignal.timeout(1200),
    });
    if (resposta.ok) {
      const { origem } = await resposta.json();
      const url = new URL(origem);
      if (url.protocol === "http:" && !url.username && !url.password) {
        endereco = new URL("/publico.html", url);
        endereco.searchParams.set("codigo", codigo);
      }
    }
  } catch {
    // Sem configuração LAN, mantenha o link do próprio painel.
  }
  return endereco.href;
}

async function mostrarLote(id, elemento) {
  if (!/^\d+$/.test(id ?? "")) throw new Error("Lote inválido.");
  const caminho = "/lotes/" + id;
  const [lote, leituras] = await Promise.all([requisitar(caminho), requisitar(caminho + "/leituras")]);
  if (!elemento.isConnected) return;
  const analise = lote.analise;
  const ultimaLeitura = leituras.at(-1);
  const { temp_min_c: piso, temp_max_c: teto } = lote.faixa_segura;
  const desvioCalor = analise.temp_max_c != null && analise.temp_max_c > teto
    ? `Máxima medida: ${numero(analise.temp_max_c)} °C. Limite: ${numero(teto)} °C.` : "";
  const desvioFrio = analise.temp_min_c != null && analise.temp_min_c < piso
    ? `Mínima medida: ${numero(analise.temp_min_c)} °C. Limite: ${numero(piso)} °C.` : "";
  const estadoTemperatura = ultimaLeitura?.temperatura_c > teto ? "Acima da faixa"
    : ultimaLeitura?.temperatura_c < piso ? "Abaixo da faixa" : "";
  const endereco = await enderecoPublico(lote.codigo_publico);
  if (!elemento.isConnected) return;
  const urlPublica = escapar(endereco);
  const urlLaudo = lote.token_laudo ? escapar(linkPagina("laudo.html", { token: lote.token_laudo })) : "";
  limparOperacao();
  elemento.innerHTML = `<header class="cabecalho"><a href="#inicio">← Cargas</a>
    <h1>Lote ${escapar(lote.id)} · ${escapar(nomeFruta(lote.fruta))}</h1>
    <p>${escapar(lote.origem)} → ${escapar(lote.destino)}</p>
  </header>
  <section class="cartao">
    <h2>${lote.fim ? "Viagem concluída" : "Viagem em trânsito"}</h2>
    <p>Risco acumulado ${pilula(analise.nivel)} · ${escapar(analise.recomendacao)}</p>
    <dl class="ficha">
      <div><dt>Produtor</dt><dd>${escapar(lote.produtor)}</dd></div>
      <div><dt>Placa</dt><dd>${escapar(lote.dispositivo?.nome ?? "Placa padrão")}</dd></div>
      <div><dt>Início</dt><dd>${escapar(formatarData(lote.inicio))}</dd></div>
      ${lote.fim ? `<div><dt>Conclusão</dt><dd>${escapar(formatarData(lote.fim))}</dd></div>` : ""}
      <div><dt>Faixa de temperatura</dt><dd>${escapar(faixa(lote.faixa_segura))}</dd></div>
      <div><dt>Faixa de umidade</dt><dd>${faixaDeUmidade(lote.faixa_segura)}</dd></div>
    </dl>
    ${!lote.fim ? `<div class="acoes"><button type="button" class="botao" data-encerrar>Encerrar lote</button></div>
      <p data-encerrar-erro role="alert" hidden></p>` : ""}
  </section>
  <section class="cartao"><h2>Temperatura da viagem</h2>
    ${ultimaLeitura ? `<dl class="ficha">
      <div><dt>Temperatura medida</dt><dd><span data-temperatura-medida>${numero(ultimaLeitura.temperatura_c)} °C</span>
        ${estadoTemperatura ? `<span class="pilula amarelo">${estadoTemperatura}</span>` : ""}</dd></div>
      <div><dt>Umidade medida</dt><dd>${ultimaLeitura.umidade_pct == null ? "—" : numero(ultimaLeitura.umidade_pct) + "%"}</dd></div>
      <div><dt>Última leitura</dt><dd>${escapar(formatarData(ultimaLeitura.data_hora))}</dd></div>
    </dl>` : `<p class="aviso">${lote.fim ? "Este lote não recebeu leituras." : "Aguardando sincronização."}</p>`}
    ${!lote.fim ? `<div class="acoes"><button type="button" class="botao secundario" data-sincronizar-lote>Sincronizar leituras</button></div>
      <p class="aviso" data-sync-status role="status"></p>` : ""}
    ${ultimaLeitura ? `<p>Extremos do período · Mínima <strong data-minima-medida>${numero(analise.temp_min_c)} °C</strong>
      · Máxima <strong data-maxima-medida>${numero(analise.temp_max_c)} °C</strong></p>` : ""}
    <div data-grafico>
      <label class="campo">Período
        <select><option value="completa">Viagem completa</option><option value="recente">Últimas 3 horas medidas</option></select>
      </label>
      <div class="viagem-grafico" style="position:relative;height:clamp(240px, 38vw, 390px)">
        <canvas role="img" aria-label="Temperaturas medidas, extremos e faixa segura da viagem"></canvas>
      </div>
    </div>
    ${ultimaLeitura ? tabelaDeLeituras(leituras) : ""}
    <p>O percurso GPS ainda não está disponível para este lote.</p>
  </section>
  <div class="grade duas">
    ${cartaoDeRisco("Calor acima da faixa", analise.graus_hora_acima, analise.nivel_acima, desvioCalor)}
    ${cartaoDeRisco("Frio abaixo da faixa", analise.graus_hora_abaixo, analise.nivel_abaixo, desvioFrio)}
  </div>
  ${periodosDaViagem(analise)}
  ${urlPublica || urlLaudo ? `<section class="cartao"><h2>Compartilhar lote</h2>
    <div class="acoes">
      ${urlPublica ? `<a class="botao" href="${urlPublica}" target="_blank" rel="noopener noreferrer">Abrir página pública</a>` : ""}
      ${urlLaudo ? `<a class="botao" href="${urlLaudo}" target="_blank" rel="noopener noreferrer">Abrir laudo completo</a>` : ""}
    </div>
    ${urlPublica ? '<details><summary>Ver código QR público</summary><div data-qr></div></details>' : ""}
  </section>` : ""}`;

  const botaoSync = elemento.querySelector("[data-sincronizar-lote]");
  botaoSync?.addEventListener("click", async () => {
    const aviso = elemento.querySelector("[data-sync-status]");
    botaoSync.disabled = true;
    aviso.classList.remove("erro");
    aviso.textContent = "Buscando leituras no ThingSpeak…";
    try {
      const resultado = await requisitar("/sincronizar", { method: "POST" });
      if (!aviso.isConnected) return;
      await mostrarLote(id, elemento);
      const novoAviso = elemento.querySelector("[data-sync-status]");
      if (novoAviso) mostrarResultadoDaSincronizacao(novoAviso, resultado);
    } catch (erro) {
      aviso.classList.add("erro");
      aviso.textContent = erro.message;
    } finally {
      botaoSync.disabled = false;
    }
  });

  const botaoEncerrar = elemento.querySelector("[data-encerrar]");
  botaoEncerrar?.addEventListener("click", async () => {
    if (!window.confirm("Encerrar este lote agora?")) return;
    botaoEncerrar.disabled = true;
    const erro = elemento.querySelector("[data-encerrar-erro]");
    erro.hidden = true;
    try {
      await requisitar(caminho + "/encerrar", { method: "POST" });
      await renderizarOperacao({ tela: "lote", id }, elemento);
    } catch (falha) {
      erro.textContent = falha.message;
      erro.hidden = false;
      botaoEncerrar.disabled = false;
    }
  });
  mostrarCompartilhamento(endereco, elemento);
  mostrarGrafico(elemento, leituras, lote.faixa_segura);
}

async function mostrarAlertas(elemento) {
  const alertas = await requisitar("/alertas");
  elemento.innerHTML = '<header class="cabecalho"><h1>Alertas</h1><p>Ocorrências em cargas em trânsito</p></header>';
  if (!alertas.length) {
    elemento.innerHTML += '<p class="aviso">Nenhum alerta ativo.</p>';
    return;
  }
  elemento.innerHTML += `<div class="grade">${alertas.map((alerta) => {
    const tipo = alerta.tipo === "porta_aberta" ? "Porta aberta" : alerta.lado === "abaixo" ? "Frio" : "Calor";
    return `<article class="cartao"><h2>${tipo} · Lote ${escapar(alerta.lote_id)}</h2>
      ${pilula(alerta.nivel)} <span>${escapar(formatarData(alerta.data_hora))}</span>
      <p>${escapar(alerta.mensagem)}</p>
      <a class="botao" href="#lote/${encodeURIComponent(alerta.lote_id)}">Ver lote ${escapar(alerta.lote_id)}</a>
    </article>`;
  }).join("")}</div>`;
}

function formularioDeFruta(fruta) {
  const f = fruta || {};
  const limite = (campo, label, min, max) => `<label class="campo">${label}
    <input name="${campo}" type="number" step="any" min="${min}" max="${max}" required value="${escapar(f[campo] ?? "")}"></label>`;
  return `<form>
    <h2>${fruta ? "Editar faixa de " + escapar(f.nome) : "Cadastrar fruta"}</h2>
    <p>A faixa é usada nos próximos lotes. As cargas já criadas mantêm a faixa original.</p>
    ${fruta ? "" : '<label class="campo">Identificador<input name="id" pattern="[a-z0-9_\\-]+" required placeholder="Ex.: melao"></label>'}
    <label class="campo">Nome<input name="nome" required value="${escapar(f.nome ?? "")}"></label>
    <div class="grade">${limite("temp_min_c", "Temperatura mínima (°C)", -40, 80)}
      ${limite("temp_max_c", "Temperatura máxima (°C)", -40, 80)}
      ${limite("umidade_min_pct", "Umidade mínima (%)", 0, 100)}
      ${limite("umidade_max_pct", "Umidade máxima (%)", 0, 100)}</div>
    <label class="campo">Fonte da faixa<input name="fonte" required value="${escapar(f.fonte ?? "")}"></label>
    <label class="campo">Risco com frio (opcional)<input name="risco_no_frio" value="${escapar(f.risco_no_frio ?? "")}"></label>
    <p role="alert" hidden></p>
    <div class="acoes"><button type="submit" class="botao">Salvar</button>
      <button type="button" class="botao" data-cancelar>Cancelar</button></div>
  </form>`;
}

function abrirEditor(editor, fruta, aposSalvar) {
  editor.hidden = false;
  editor.innerHTML = formularioDeFruta(fruta);
  const form = editor.querySelector("form");
  const aviso = form.querySelector('[role="alert"]');
  form.querySelector("input").focus();
  form.querySelector("[data-cancelar]").addEventListener("click", () => {
    editor.hidden = true;
    editor.replaceChildren();
  });
  form.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    aviso.hidden = true;
    const campos = Object.fromEntries(new FormData(form));
    for (const chave of ["temp_min_c", "temp_max_c", "umidade_min_pct", "umidade_max_pct"]) {
      campos[chave] = Number(campos[chave]);
    }
    campos.nome = campos.nome.trim();
    campos.fonte = campos.fonte.trim();
    campos.risco_no_frio = campos.risco_no_frio.trim() || null;
    if (!campos.nome || !campos.fonte || campos.temp_min_c >= campos.temp_max_c || campos.umidade_min_pct >= campos.umidade_max_pct) {
      aviso.textContent = "Preencha nome e fonte. Os mínimos precisam ser menores que os máximos.";
      aviso.hidden = false;
      return;
    }
    const botao = form.querySelector('button[type="submit"]');
    botao.disabled = true;
    try {
      const salva = await requisitar(fruta ? "/frutas/" + encodeURIComponent(fruta.id) : "/frutas", {
        method: fruta ? "PUT" : "POST",
        body: campos,
      });
      aposSalvar(salva);
    } catch (falha) {
      aviso.textContent = falha.message;
      aviso.hidden = false;
      botao.disabled = false;
    }
  });
}

async function mostrarFrutas(elemento) {
  const frutas = await requisitar("/frutas");
  elemento.innerHTML = `<header class="cabecalho"><h1>Frutas</h1><p>Faixas de temperatura e umidade para novas cargas</p></header>
    <p role="status" data-fruta-status></p>
    <div class="acoes"><button type="button" class="botao" data-nova-fruta>Cadastrar fruta</button></div>
    <section class="cartao" data-editor hidden></section>
    <div class="grade" data-lista-frutas></div>`;
  const editor = elemento.querySelector("[data-editor]");
  const lista = elemento.querySelector("[data-lista-frutas]");
  const desenhar = () => {
    lista.innerHTML = frutas.map((fruta, indice) => `<article class="cartao">
      <h2>${escapar(fruta.nome)}</h2><p><strong>${escapar(faixa(fruta))}</strong> · Umidade ${faixaDeUmidade(fruta)}</p>
      <p>${escapar(fruta.fonte)}</p>
      ${fruta.risco_no_frio ? `<p>Risco com frio: ${escapar(fruta.risco_no_frio)}</p>` : ""}
      <button type="button" class="botao" data-editar-fruta="${indice}" aria-label="Editar faixa de ${escapar(fruta.nome)}">Editar faixa</button>
    </article>`).join("") || '<p class="aviso">Nenhuma fruta cadastrada.</p>';
  };
  const salvo = (fruta) => {
    const indice = frutas.findIndex((f) => f.id === fruta.id);
    if (indice === -1) frutas.push(fruta);
    else frutas[indice] = fruta;
    editor.hidden = true;
    editor.replaceChildren();
    elemento.querySelector("[data-fruta-status]").textContent = fruta.nome + " salva.";
    desenhar();
  };
  elemento.querySelector("[data-nova-fruta]").addEventListener("click", () => abrirEditor(editor, null, salvo));
  lista.addEventListener("click", (evento) => {
    const botao = evento.target.closest("[data-editar-fruta]");
    if (botao) abrirEditor(editor, frutas[Number(botao.dataset.editarFruta)], salvo);
  });
  desenhar();
}

export function limparOperacao() {
  graficoAtivo?.destroy();
  graficoAtivo = undefined;
}

export async function renderizarOperacao(rota, elemento) {
  if (rota.tela === "lote") return mostrarLote(rota.id, elemento);
  limparOperacao();
  if (rota.tela === "alertas") return mostrarAlertas(elemento);
  return mostrarFrutas(elemento);
}
