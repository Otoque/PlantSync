import { requisitar } from "./dados.js";
import { escapar, faixa, nomeFruta, pilula } from "./ui.js";

const siglas = {
  21: "MA", 22: "PI", 23: "CE", 24: "RN", 25: "PB",
  26: "PE", 27: "AL", 28: "SE", 29: "BA",
};

function posicao(lote) {
  const { latitude, longitude } = lote.ultima_posicao ?? {};
  return Number.isFinite(latitude) && Number.isFinite(longitude) &&
    Math.abs(latitude) <= 90 && Math.abs(longitude) <= 180 ? [latitude, longitude] : null;
}

function linkDoLote(lote) {
  const link = document.createElement("a");
  link.href = `#lote/${encodeURIComponent(lote.id)}`;
  link.textContent = `Abrir lote ${lote.id} · ${nomeFruta(lote.fruta)}`;
  return link;
}

async function desenharTrajetos(mapa, lotes, signal) {
  const endereco = new URL("../mapas/trajetos-planejados.json", import.meta.url);
  const resposta = await fetch(endereco, { signal });
  if (!resposta.ok) throw new Error("Trajetos indisponíveis");
  const catalogo = await resposta.json();
  if (signal.aborted) return [];

  const camada = mapa.createPane("trajetos-planejados");
  camada.style.zIndex = "430";
  const pontos = [];
  for (const lote of lotes) {
    const caminho = catalogo.find(trajeto => trajeto.origem === lote.origem && trajeto.destino === lote.destino);
    if (!caminho) continue;
    const cor = lote.status === "em_transito" ? "#17637c" : "#7d5942";
    const painel = document.createElement("div");
    const titulo = document.createElement("strong");
    titulo.textContent = `${lote.origem} → ${lote.destino}`;
    const legenda = document.createElement("p");
    legenda.textContent = "Rota planejada · traçado aproximado";
    painel.append(titulo, legenda, linkDoLote(lote));
    const estilo = { pane: "trajetos-planejados", color: cor };
    L.polyline(caminho.pontos, { ...estilo, weight: 4, dashArray: "8 7" }).addTo(mapa).bindPopup(painel);
    for (const ponto of [caminho.pontos[0], caminho.pontos.at(-1)]) {
      L.circleMarker(ponto, { ...estilo, radius: 5, fillColor: "#fff", fillOpacity: 1 })
        .addTo(mapa).bindPopup(painel.cloneNode(true));
    }
    pontos.push(...caminho.pontos);
  }
  return pontos;
}

async function montarMapa(el, lotes) {
  const painel = el.querySelector("#mapa");
  const nota = el.querySelector("#mapa-nota");
  const estado = el.querySelector("#mapa-estado");
  const localizados = lotes.filter(lote => posicao(lote));
  if (!window.L) {
    painel.classList.add("mapa-falha");
    painel.textContent = "Não foi possível abrir o mapa.";
    nota.textContent = "A lista de cargas continua disponível.";
    return;
  }
  const mapa = L.map(painel, { scrollWheelZoom: false, minZoom: 4, maxZoom: 10 });
  const valeEPortos = [[-13.1, -42.3], [-6.8, -34.2]];
  mapa.fitBounds(valeEPortos);
  let texto = localizados.length ? "O mapa mostra os lotes que têm coordenadas registradas."
    : "Mapa da região. Nenhum lote tem posição registrada pelo sensor.";
  nota.textContent = texto;
  const pontos = [];
  for (const lote of localizados) {
    const ponto = posicao(lote);
    L.circleMarker(ponto, { color: "#21392d", fillColor: "#f4ba62", fillOpacity: 1, radius: 8, pane: "markerPane" })
      .addTo(mapa).bindPopup(linkDoLote(lote));
    pontos.push(ponto);
  }
  if (pontos.length) mapa.fitBounds(pontos, { padding: [30, 30], maxZoom: 9 });
  const carregamento = new AbortController();
  el.addEventListener("sair-tela", () => {
    carregamento.abort();
    mapa.remove();
  }, { once: true });

  const signal = AbortSignal.any([carregamento.signal, AbortSignal.timeout(8000)]);
  const trajetos = desenharTrajetos(mapa, lotes, signal).then(rotas => {
    if (rotas.length && el.isConnected && !signal.aborted) {
      texto = `Tracejado: rotas planejadas, com traçado aproximado. ${localizados.length ? "Marcadores dourados: posições do sensor." : "Sem posições GPS registradas."}`;
      nota.textContent = texto + (estado.hidden ? "" : " A base cartográfica não pôde ser carregada.");
      mapa.fitBounds([...rotas, ...pontos], { padding: [25, 25], maxZoom: 9 });
    }
  }).catch(() => {
    if (el.isConnected && !carregamento.signal.aborted) {
      nota.textContent += " Não foi possível carregar as rotas planejadas.";
    }
  });

  try {
    const resposta = await fetch(new URL("../mapas/nordeste.geojson", import.meta.url), {
      signal,
    });
    if (!resposta.ok) throw new Error("Malha indisponível");
    const malha = await resposta.json();
    if (carregamento.signal.aborted || !el.isConnected) return;
    if (malha.type !== "FeatureCollection" || !malha.features?.length) throw new Error("Malha inválida");
    L.geoJSON(malha, {
      style: { color: "#859888", fillColor: "#e9eedc", fillOpacity: 1, weight: 1.2 },
      onEachFeature(estado, camada) {
        const sigla = siglas[estado.properties?.codarea];
        if (sigla) camada.bindTooltip(sigla, {
          permanent: true, direction: "center", className: "mapa-uf", interactive: false,
        });
      },
      interactive: false,
    }).addTo(mapa);
    mapa.attributionControl.addAttribution('<a href="https://servicodados.ibge.gov.br/api/docs/malhas?versao=3">Malha IBGE</a>');
  } catch {
    if (carregamento.signal.aborted || !el.isConnected) return;
    estado.hidden = false;
    nota.textContent = `${texto} A base cartográfica não pôde ser carregada.`;
  }
  await trajetos;
}

function montarLista(el, lotes) {
  const lista = el.querySelector("#lista-cargas");
  const botoes = [...el.querySelectorAll("[data-filtro]")];
  function mostrar(filtro) {
    for (const botao of botoes) {
      botao.setAttribute("aria-pressed", String(botao.dataset.filtro === filtro));
    }
    const filtrados = lotes.filter(lote => lote.status === filtro);
    lista.innerHTML = filtrados.length ? filtrados.map(lote => `
      <a class="carga" href="#lote/${escapar(encodeURIComponent(lote.id))}">
        <span class="carga-titulo"><strong>Lote ${escapar(lote.id)} · ${escapar(nomeFruta(lote.fruta))}</strong>${pilula(lote.risco?.nivel)}</span>
        <span class="carga-rota">${escapar(lote.origem)} → ${escapar(lote.destino)}</span>
        <span class="carga-rota">Faixa de temperatura ${escapar(faixa(lote.faixa_segura))}</span>
      </a>`).join("") : `<p class="aviso">${filtro === "em_transito" ? "Nenhuma carga em trânsito." : "Nenhuma carga concluída."}</p>`;
  }
  for (const botao of botoes) {
    botao.textContent += ` · ${lotes.filter(lote => lote.status === botao.dataset.filtro).length}`;
    botao.addEventListener("click", () => mostrar(botao.dataset.filtro));
  }
  mostrar("em_transito");
}

async function montarCadastro(el, ativo) {
  const caixa = el.querySelector("#cadastro");
  if (ativo) {
    caixa.innerHTML = '<p class="suave">Encerre a carga em trânsito para iniciar outra.</p>';
    return;
  }
  caixa.innerHTML = `
    <details class="cartao"><summary>Nova carga</summary>
      <form>
        <div class="grade duas">
          <label class="campo">Fruta<select name="fruta" required><option value="">Selecione</option></select></label>
          <label class="campo">Produtor<input name="produtor" required></label>
          <label class="campo">Origem<input name="origem" required></label>
          <label class="campo">Destino<input name="destino" required></label>
          <label class="campo">Tipo de destino<select name="tipo_destino" required><option value="porto">Porto</option><option value="mercado_interno">Mercado interno</option></select></label>
        </div>
        <p class="suave">O lote começa ao cadastrar e recebe a faixa padrão da fruta selecionada.</p>
        <p class="aviso erro" role="alert"></p>
        <button class="botao" type="submit" disabled>Cadastrar carga</button>
      </form>
    </details>`;
  const form = caixa.querySelector("form");
  const botao = form.querySelector("button");
  const aviso = form.querySelector("[role=alert]");
  try {
    const frutas = await requisitar("/frutas");
    for (const fruta of frutas) form.elements.fruta.add(new Option(fruta.nome, fruta.id));
    botao.disabled = !frutas.length;
    if (!frutas.length) aviso.textContent = "Cadastre uma fruta antes de criar o lote.";
  } catch (erro) {
    aviso.textContent = erro.message;
  }
  form.addEventListener("submit", async evento => {
    evento.preventDefault();
    if (botao.disabled) return;
    botao.disabled = true;
    aviso.textContent = "";
    try {
      const body = Object.fromEntries(new FormData(form));
      for (const chave of ["produtor", "origem", "destino"]) {
        body[chave] = body[chave].trim();
        if (!body[chave]) throw new Error("Preencha produtor, origem e destino.");
      }
      const lote = await requisitar("/lotes", { method: "POST", body });
      if (el.isConnected) location.hash = `#lote/${encodeURIComponent(lote.id)}`;
    } catch (erro) {
      aviso.textContent = erro.message;
    } finally {
      botao.disabled = false;
    }
  });
}

export async function renderizarInicio(el) {
  const lotes = await requisitar("/lotes");
  if (!el.isConnected) return;
  el.innerHTML = `
    <div class="inicio-topo"><header class="cabecalho">
      <h1>Cargas</h1><p>Acompanhe os lotes em trânsito e concluídos.</p>
    </header>
    <button class="botao secundario" id="sincronizar" type="button">Sincronizar leituras</button></div>
    <p class="aviso" id="aviso-sync" role="status"></p>
    <div class="grade-inicio">
      <section class="cartao cartao-mapa" aria-labelledby="mapa-titulo">
        <div class="mapa-topo"><h2 id="mapa-titulo">Mapa de cargas</h2></div>
        <div class="mapa-figura">
          <div id="mapa" class="mapa" aria-label="Mapa da região das cargas"></div>
          <p id="mapa-estado" class="mapa-estado" role="status" hidden>Base cartográfica indisponível</p>
        </div>
        <p class="mapa-nota" id="mapa-nota"></p>
      </section>
      <div>
        <section class="cartao" aria-labelledby="viagens-titulo">
          <h2 id="viagens-titulo">Viagens</h2>
          <div class="abas" aria-label="Filtrar cargas">
            <button class="botao" type="button" data-filtro="em_transito">Em trânsito</button>
            <button class="botao" type="button" data-filtro="encerrado">Concluídas</button>
          </div>
          <div id="lista-cargas" class="lista-cargas" aria-live="polite"></div>
        </section>
        <div id="cadastro"></div>
      </div>
    </div>`;
  montarLista(el, lotes);
  montarMapa(el, lotes);

  const botao = el.querySelector("#sincronizar");
  const aviso = el.querySelector("#aviso-sync");
  botao.addEventListener("click", async () => {
    botao.disabled = true;
    aviso.classList.remove("erro");
    aviso.textContent = "Buscando leituras no ThingSpeak…";
    try {
      const resultado = await requisitar("/sincronizar", { method: "POST" });
      if (!el.isConnected) return;
      el.dispatchEvent(new Event("sair-tela"));
      await renderizarInicio(el);
      if (el.isConnected) el.querySelector("#aviso-sync").textContent = `${resultado.novas} novas leituras. ${resultado.descartadas} descartadas.`;
    } catch (erro) {
      aviso.classList.add("erro");
      aviso.textContent = erro.message;
    } finally {
      botao.disabled = false;
    }
  });
  await montarCadastro(el, lotes.some(lote => lote.status === "em_transito"));
}
