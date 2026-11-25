// Ambiente de navegador simulado para rodar os modulos do painel no Node.
// Cada arquivo de teste roda em um processo proprio, entao nada vaza entre eles.

export function criarArmazenamento(inicial = {}) {
  const dados = new Map(Object.entries(inicial));
  return {
    getItem: chave => (dados.has(chave) ? dados.get(chave) : null),
    setItem: (chave, valor) => dados.set(chave, String(valor)),
    removeItem: chave => dados.delete(chave),
    clear: () => dados.clear(),
  };
}

// Um unico alvo de eventos por processo: reinstalar o navegador nao pode trocar o alvo
// em que os testes ja registraram seus ouvintes.
const alvoDeEventos = new EventTarget();

export function instalarNavegador({ href = "http://127.0.0.1:5500/index.html", sessao = {} } = {}) {
  const url = new URL(href);
  globalThis.location = url;
  globalThis.sessionStorage = criarArmazenamento(sessao);
  const alvo = alvoDeEventos;
  globalThis.window = alvo;
  globalThis.dispatchEvent = evento => alvo.dispatchEvent(evento);
  globalThis.addEventListener = (...args) => alvo.addEventListener(...args);
  return alvo;
}

export function respostaJson(status, corpo, cabecalhos = {}) {
  return {
    status,
    ok: status >= 200 && status < 300,
    headers: { get: nome => cabecalhos[nome] ?? null },
    json: async () => {
      if (corpo === undefined) throw new Error("sem corpo");
      return corpo;
    },
  };
}

export function simularFetch(resposta) {
  const chamadas = [];
  globalThis.fetch = async (url, opcoes) => {
    chamadas.push({ url: String(url), opcoes });
    if (resposta instanceof Error) throw resposta;
    return typeof resposta === "function" ? resposta(url, opcoes) : resposta;
  };
  return chamadas;
}
