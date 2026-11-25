import test from "node:test";
import assert from "node:assert/strict";
import { instalarNavegador, respostaJson, simularFetch } from "./ambiente.mjs";

const alvo = instalarNavegador({ href: "http://127.0.0.1:5500/index.html" });
const modulo = await import("../front_end/js/produto-api.js");
const { ApiError, api, baseUrl, key, list, lotPath, publicUrl, setSession, tripPath } = modulo;

const futuro = () => new Date(Date.now() + 3600_000).toISOString();

test.beforeEach(() => setSession(null));

test("key codifica caracteres especiais para a URL", () => {
  assert.equal(key("a b/c"), "a%20b%2Fc");
  assert.equal(key(12), "12");
});

test("lotPath e tripPath montam os caminhos da API", () => {
  assert.equal(lotPath(7), "/lotes/7");
  assert.equal(tripPath("x/y"), "/viagens/x%2Fy");
});

test("list devolve array ou lista vazia", () => {
  assert.deepEqual(list([1, 2]), [1, 2]);
  assert.deepEqual(list(null), []);
  assert.deepEqual(list({ a: 1 }), []);
});

test("baseUrl aponta para a porta 8000 nas portas de desenvolvimento", () => {
  assert.equal(baseUrl().href, "http://127.0.0.1:8000/api/v1/");
});

test("baseUrl mantem a origem em outros enderecos", () => {
  instalarNavegador({ href: "https://plantsync.exemplo.com/index.html" });
  assert.equal(baseUrl().href, "https://plantsync.exemplo.com/api/v1/");
  instalarNavegador({ href: "http://127.0.0.1:5500/index.html" });
});

test("publicUrl monta o link publico do lote", () => {
  assert.equal(publicUrl("ABC123"), "http://127.0.0.1:5500/publico-lote.html?codigo=ABC123");
});

test("publicUrl usa a origem configurada e garante a barra final", () => {
  const url = publicUrl("X1", { origem: "https://192.168.0.10:5501/app" });
  assert.equal(url, "https://192.168.0.10:5501/app/publico-lote.html?codigo=X1");
});

test("publicUrl recusa protocolo nao HTTP e credenciais na URL", () => {
  assert.throws(() => publicUrl("X", { origem: "javascript:alert(1)" }), /HTTP ou HTTPS/);
  assert.throws(() => publicUrl("X", { origem: "https://user:senha@host.com" }), /HTTP ou HTTPS/);
});

test("api envia token e empresa nos cabecalhos", async () => {
  setSession({ token: "t9", companyId: 4, expira_em: futuro() });
  const chamadas = simularFetch(respostaJson(200, { ok: 1 }));
  assert.deepEqual(await api("/contexto"), { ok: 1 });
  assert.equal(chamadas[0].url, "http://127.0.0.1:8000/api/v1/contexto");
  assert.equal(chamadas[0].opcoes.headers.Authorization, "Bearer t9");
  assert.equal(chamadas[0].opcoes.headers["X-Empresa-ID"], "4");
});

test("api anonima nao envia credenciais", async () => {
  setSession({ token: "t9", companyId: 4, expira_em: futuro() });
  const chamadas = simularFetch(respostaJson(200, {}));
  await api("/publico/A", { anonymous: true });
  assert.equal(chamadas[0].opcoes.headers.Authorization, undefined);
  assert.equal(chamadas[0].opcoes.headers["X-Empresa-ID"], undefined);
});

test("api withoutCompany omite o cabecalho da empresa", async () => {
  setSession({ token: "t9", companyId: 4, expira_em: futuro() });
  const chamadas = simularFetch(respostaJson(200, {}));
  await api("/empresas", { withoutCompany: true });
  assert.equal(chamadas[0].opcoes.headers["X-Empresa-ID"], undefined);
  assert.equal(chamadas[0].opcoes.headers.Authorization, "Bearer t9");
});

test("api devolve null em resposta 204", async () => {
  simularFetch(respostaJson(204, undefined));
  assert.equal(await api("/algo", { method: "DELETE" }), null);
});

test("api traduz erros HTTP em mensagens para o usuario", async () => {
  const casos = [
    [403, {}, "Você não tem permissão para esta ação."],
    [404, {}, "Registro não encontrado."],
    [409, {}, "O registro mudou ou a ação conflita com o estado atual."],
    [500, {}, "O PlantSync não conseguiu concluir esta operação. Tente novamente."],
    [400, { erro: "texto da API" }, "texto da API"],
    [422, { detail: [{ msg: "x" }] }, "Confira os campos e informe valores válidos."],
  ];
  for (const [status, corpo, esperado] of casos) {
    simularFetch(respostaJson(status, corpo));
    await assert.rejects(api("/x"), erro => erro instanceof ApiError && erro.status === status && erro.message === esperado);
  }
});

test("api informa o tempo de espera quando recebe 429", async () => {
  simularFetch(respostaJson(429, {}, { "Retry-After": "30" }));
  await assert.rejects(api("/login"), erro => erro.message === "Aguarde 30 segundos e tente novamente.");
  simularFetch(respostaJson(429, {}));
  await assert.rejects(api("/login"), erro => erro.message === "Muitas tentativas. Aguarde e tente novamente.");
});

test("api limpa a sessao e avisa quando recebe 401", async () => {
  setSession({ token: "t9", expira_em: futuro() });
  let avisou = false;
  alvo.addEventListener("plantsync:sessao-expirada", () => (avisou = true), { once: true });
  simularFetch(respostaJson(401, {}));
  await assert.rejects(api("/contexto"), erro => erro.status === 401);
  assert.equal(avisou, true);
  assert.equal(modulo.session, null);
});

test("api converte falha de rede em ApiError com status 0", async () => {
  simularFetch(new TypeError("fetch failed"));
  await assert.rejects(api("/x"), erro => erro.status === 0 && /conectar ao servidor/.test(erro.message));
});

test("api repassa o cancelamento (AbortError) sem converter", async () => {
  const cancelado = Object.assign(new Error("abortado"), { name: "AbortError" });
  simularFetch(cancelado);
  await assert.rejects(api("/x"), erro => erro.name === "AbortError");
});
