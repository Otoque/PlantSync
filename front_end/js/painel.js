import { encerrarSessao, linkPagina, requisitar, salvarSessao, sessaoAtual } from "./dados.js";
import { renderizarInicio } from "./inicio.js";
import { limparOperacao, renderizarOperacao } from "./operacao.js";

const principal = document.getElementById("conteudo");
const topo = document.getElementById("topbar");
const sair = document.getElementById("sair");
let proximaRota = "#inicio";
let avisoLogin = "";
let sessaoTimer;
let telaAtual;

function lerRota() {
  const hash = location.hash;
  const lote = /^#lote\/(\d+)$/.exec(hash);
  if (lote) return { tela: "lote", id: lote[1], nav: "#inicio" };
  if (["#alertas", "#frutas"].includes(hash)) return { tela: hash.slice(1), nav: hash };
  return { tela: "inicio", nav: "#inicio" };
}

function criarTela() {
  limparOperacao();
  telaAtual?.dispatchEvent(new Event("sair-tela"));
  telaAtual = document.createElement("section");
  principal.replaceChildren(telaAtual);
  return telaAtual;
}

function mostrarLogin(el) {
  el.innerHTML = `
    <div class="login">
      <div class="login-marca">
        <span class="marca">Plant<span>Sync</span></span>
        <div><h1>Controle de cargas</h1><p>Acompanhe a temperatura do lote até a entrega.</p></div>
      </div>
      <form class="login-form" aria-labelledby="titulo-login">
        <h2 id="titulo-login">Entrar no painel</h2>
        <label class="campo">Usuário<input name="usuario" autocomplete="username" autocapitalize="none" spellcheck="false" maxlength="100" required></label>
        <label class="campo">Senha<input type="password" name="senha" autocomplete="current-password" maxlength="200" required></label>
        <p class="aviso erro" role="alert"></p>
        <button class="botao" type="submit">Entrar</button>
      </form>
    </div>`;
  const form = el.querySelector("form");
  const botao = form.querySelector("button");
  const aviso = form.querySelector("[role=alert]");
  aviso.textContent = avisoLogin;
  avisoLogin = "";
  form.addEventListener("submit", async evento => {
    evento.preventDefault();
    if (botao.disabled) return;
    const credenciais = Object.fromEntries(new FormData(form));
    botao.disabled = true;
    botao.textContent = "Entrando…";
    aviso.textContent = "";
    try {
      salvarSessao(await requisitar("/login", { publica: true, method: "POST", body: credenciais }));
      form.reset();
      if (location.hash !== proximaRota) location.hash = proximaRota;
      else abrirTela(true);
    } catch (erro) {
      aviso.textContent = erro.message;
      if (erro.status === 401) {
        form.elements.senha.value = "";
        form.elements.senha.focus();
      }
    } finally {
      botao.disabled = false;
      botao.textContent = "Entrar";
    }
  });
}

async function abrirTela(moverFoco = false) {
  clearTimeout(sessaoTimer);
  const rota = lerRota();
  const sessao = sessaoAtual();
  const el = criarTela();
  topo.hidden = !sessao;
  if (moverFoco) principal.focus();
  if (topo.hidden) {
    proximaRota = rota.tela === "lote" ? location.hash : rota.nav;
    document.title = "Entrar · PlantSync";
    mostrarLogin(el);
    return;
  }
  if (sessao) {
    const restante = Date.parse(sessao.expira_em) - Date.now();
    sessaoTimer = setTimeout(() => window.dispatchEvent(new Event("sessao-expirada")), restante);
  }
  topo.querySelectorAll("nav a").forEach(a => {
    if (a.hash === rota.nav) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  });
  const titulos = { inicio: "Cargas", lote: "Detalhe do lote", alertas: "Alertas", frutas: "Frutas" };
  document.title = `${titulos[rota.tela]} · PlantSync`;
  el.innerHTML = '<p class="aviso" role="status">Carregando…</p>';
  try {
    if (rota.tela === "inicio") await renderizarInicio(el);
    else await renderizarOperacao(rota, el);
  } catch (erro) {
    if (!el.isConnected) return;
    el.innerHTML = `
      <h1>${titulos[rota.tela]}</h1>
      <p class="aviso erro" role="alert"></p>
      <button class="botao secundario" type="button">Tentar novamente</button>`;
    el.querySelector("[role=alert]").textContent = erro.message || "Não foi possível carregar esta tela.";
    el.querySelector("button").addEventListener("click", () => abrirTela(true));
  }
}

window.addEventListener("hashchange", () => {
  if (location.hash !== "#conteudo") abrirTela(true);
});
window.addEventListener("sessao-expirada", () => {
  if (topo.hidden) return;
  encerrarSessao();
  avisoLogin = "Sua sessão terminou. Entre novamente para continuar.";
  abrirTela(true);
});
sair.addEventListener("click", async () => {
  sair.disabled = true;
  let aviso = "";
  try {
    await requisitar("/logout", { method: "POST" });
  } catch (erro) {
    if (erro.status !== 401) aviso = "Você saiu neste navegador. A API não confirmou o encerramento da sessão.";
  } finally {
    encerrarSessao();
    sair.disabled = false;
    avisoLogin = aviso;
    history.replaceState(null, "", linkPagina("index.html"));
    abrirTela(true);
  }
});

abrirTela();
