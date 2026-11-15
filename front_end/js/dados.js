const desenvolvimento = ["localhost", "127.0.0.1"].includes(location.hostname) && location.port === "5500";
const api = desenvolvimento ? `${location.protocol}//${location.hostname}:8000/api` : "/api";
const chaveSessao = "plantsync.sessao";

export class ErroApi extends Error {
  constructor(status, mensagem) {
    super(mensagem);
    this.status = status;
  }
}

export function linkPagina(nome, parametros = {}) {
  const url = new URL(nome, location.href);
  for (const [chave, valor] of Object.entries(parametros)) url.searchParams.set(chave, valor);
  return url.href;
}

export function encerrarSessao() {
  sessionStorage.removeItem(chaveSessao);
}

export function salvarSessao(sessao) {
  if (!sessao?.token || !Number.isFinite(Date.parse(sessao.expira_em))) {
    throw new ErroApi(0, "O servidor não devolveu uma sessão válida.");
  }
  sessionStorage.setItem(chaveSessao, JSON.stringify(sessao));
}

export function sessaoAtual() {
  try {
    const sessao = JSON.parse(sessionStorage.getItem(chaveSessao));
    if (sessao?.token && Date.parse(sessao.expira_em) > Date.now()) return sessao;
  } catch {
    // Uma sessão local ilegível equivale a uma sessão expirada.
  }
  encerrarSessao();
  return null;
}

function avisarSessaoExpirada() {
  encerrarSessao();
  window.dispatchEvent(new Event("sessao-expirada"));
}

export async function requisitar(caminho, { method = "GET", body, publica = false } = {}) {
  const headers = { Accept: "application/json" };
  if (!publica) {
    const sessao = sessaoAtual();
    if (!sessao) {
      avisarSessaoExpirada();
      throw new ErroApi(401, "Entre novamente para continuar.");
    }
    headers.Authorization = `Bearer ${sessao.token}`;
  }
  if (body !== undefined) headers["Content-Type"] = "application/json";

  let resposta;
  try {
    resposta = await fetch(api + caminho, {
      method, headers, body: body === undefined ? undefined : JSON.stringify(body),
      cache: "no-store", credentials: "omit", referrerPolicy: "no-referrer",
      signal: AbortSignal.timeout(caminho === "/sincronizar" ? 90000 : 12000),
    });
  } catch {
    throw new ErroApi(0, "Não foi possível conectar à API do PlantSync. Confira se o servidor está ativo e tente novamente.");
  }
  const dados = await resposta.json().catch(() => null);
  if (resposta.status === 401 && !publica) avisarSessaoExpirada();
  if (!resposta.ok) {
    const padrao = resposta.status === 404 ? "Registro não encontrado." : "Não foi possível concluir a solicitação.";
    throw new ErroApi(resposta.status, typeof dados?.erro === "string" ? dados.erro : padrao);
  }
  if (dados === null && resposta.status !== 204) throw new ErroApi(0, "A API enviou uma resposta inesperada.");
  return dados;
}
