import test from "node:test";
import assert from "node:assert/strict";
import { instalarNavegador, respostaJson, simularFetch } from "./ambiente.mjs";

const alvo = instalarNavegador({ href: "http://127.0.0.1:5500/index.html" });
const { ErroApi, encerrarSessao, linkPagina, requisitar, salvarSessao, sessaoAtual } = await import("../front_end/js/dados.js");

const futuro = () => new Date(Date.now() + 3600_000).toISOString();
const passado = () => new Date(Date.now() - 3600_000).toISOString();

test.beforeEach(() => globalThis.sessionStorage.clear());

test("ErroApi guarda o status e a mensagem", () => {
  const erro = new ErroApi(404, "nao achei");
  assert.equal(erro.status, 404);
  assert.equal(erro.message, "nao achei");
  assert.ok(erro instanceof Error);
});

test("linkPagina monta a URL com parametros", () => {
  const link = linkPagina("laudo.html", { token: "abc", n: 2 });
  assert.equal(link, "http://127.0.0.1:5500/laudo.html?token=abc&n=2");
});

test("salvarSessao e sessaoAtual guardam e devolvem uma sessao valida", () => {
  const sessao = { token: "t1", expira_em: futuro() };
  salvarSessao(sessao);
  assert.deepEqual(sessaoAtual(), sessao);
});

test("salvarSessao recusa sessao sem token ou com data invalida", () => {
  assert.throws(() => salvarSessao({ expira_em: futuro() }), ErroApi);
  assert.throws(() => salvarSessao({ token: "t", expira_em: "xyz" }), ErroApi);
  assert.throws(() => salvarSessao(null), ErroApi);
});

test("sessaoAtual descarta sessao expirada", () => {
  salvarSessao({ token: "t1", expira_em: passado() });
  assert.equal(sessaoAtual(), null);
  assert.equal(globalThis.sessionStorage.getItem("plantsync.sessao"), null);
});

test("sessaoAtual trata JSON ilegivel como sessao expirada", () => {
  globalThis.sessionStorage.setItem("plantsync.sessao", "{quebrado");
  assert.equal(sessaoAtual(), null);
});

test("encerrarSessao remove a sessao", () => {
  salvarSessao({ token: "t1", expira_em: futuro() });
  encerrarSessao();
  assert.equal(sessaoAtual(), null);
});

test("requisitar sem sessao avisa expiracao e levanta 401", async () => {
  let avisou = false;
  alvo.addEventListener("sessao-expirada", () => (avisou = true), { once: true });
  const chamadas = simularFetch(respostaJson(200, {}));
  await assert.rejects(requisitar("/lotes"), erro => erro.status === 401);
  assert.equal(avisou, true);
  assert.equal(chamadas.length, 0);
});

test("requisitar envia o token e usa a API na porta 8000 em desenvolvimento", async () => {
  salvarSessao({ token: "t1", expira_em: futuro() });
  const chamadas = simularFetch(respostaJson(200, { ok: true }));
  assert.deepEqual(await requisitar("/lotes"), { ok: true });
  assert.equal(chamadas[0].url, "http://127.0.0.1:8000/api/lotes");
  assert.equal(chamadas[0].opcoes.headers.Authorization, "Bearer t1");
  assert.equal(chamadas[0].opcoes.credentials, "omit");
});

test("requisitar publica nao envia token", async () => {
  const chamadas = simularFetch(respostaJson(200, {}));
  await requisitar("/publico/ABC", { publica: true });
  assert.equal(chamadas[0].opcoes.headers.Authorization, undefined);
});

test("requisitar envia o corpo como JSON", async () => {
  salvarSessao({ token: "t1", expira_em: futuro() });
  const chamadas = simularFetch(respostaJson(201, { id: 1 }));
  await requisitar("/dispositivos", { method: "POST", body: { nome: "x" } });
  assert.equal(chamadas[0].opcoes.method, "POST");
  assert.equal(chamadas[0].opcoes.headers["Content-Type"], "application/json");
  assert.equal(chamadas[0].opcoes.body, '{"nome":"x"}');
});

test("requisitar usa a mensagem de erro da API", async () => {
  salvarSessao({ token: "t1", expira_em: futuro() });
  simularFetch(respostaJson(400, { erro: "dado invalido" }));
  await assert.rejects(requisitar("/lotes"), erro => erro.status === 400 && erro.message === "dado invalido");
});

test("requisitar usa mensagens padrao quando a API nao explica", async () => {
  salvarSessao({ token: "t1", expira_em: futuro() });
  simularFetch(respostaJson(404, {}));
  await assert.rejects(requisitar("/lotes/9"), erro => erro.message === "Registro não encontrado.");
  simularFetch(respostaJson(500, {}));
  await assert.rejects(requisitar("/lotes"), erro => erro.message === "Não foi possível concluir a solicitação.");
});

test("requisitar encerra a sessao quando a API responde 401", async () => {
  salvarSessao({ token: "t1", expira_em: futuro() });
  let avisou = false;
  alvo.addEventListener("sessao-expirada", () => (avisou = true), { once: true });
  simularFetch(respostaJson(401, { erro: "sessao invalida" }));
  await assert.rejects(requisitar("/lotes"), erro => erro.status === 401);
  assert.equal(avisou, true);
  assert.equal(sessaoAtual(), null);
});

test("requisitar converte falha de rede em ErroApi com status 0", async () => {
  salvarSessao({ token: "t1", expira_em: futuro() });
  simularFetch(new TypeError("fetch failed"));
  await assert.rejects(requisitar("/lotes"), erro => erro.status === 0 && /conectar à API/.test(erro.message));
});

test("requisitar rejeita resposta sem JSON valido", async () => {
  salvarSessao({ token: "t1", expira_em: futuro() });
  simularFetch(respostaJson(200, undefined));
  await assert.rejects(requisitar("/lotes"), erro => erro.status === 0 && /inesperada/.test(erro.message));
});
