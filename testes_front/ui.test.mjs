import test from "node:test";
import assert from "node:assert/strict";
import { escapar, faixa, formatarData, mostrarResultadoDaSincronizacao, nomeFruta, numero, pilula } from "../front_end/js/ui.js";

test("escapar neutraliza caracteres de HTML", () => {
  assert.equal(escapar(`<img src=x onerror="a('b')">&`), "&lt;img src=x onerror=&quot;a(&#39;b&#39;)&quot;&gt;&amp;");
});

test("escapar aceita null, undefined e numeros", () => {
  assert.equal(escapar(null), "");
  assert.equal(escapar(undefined), "");
  assert.equal(escapar(0), "0");
});

test("formatarData usa o horario de Recife", () => {
  const texto = formatarData("2026-10-24T21:00:00Z");
  assert.match(texto, /24\/10\/2026/);
  assert.match(texto, /18:00/);
});

test("formatarData devolve traco para valor ausente ou invalido", () => {
  for (const valor of [null, undefined, "", "nao e data"]) assert.equal(formatarData(valor), "—");
});

test("numero formata no padrao brasileiro", () => {
  assert.equal(numero(1234.5), "1.234,5");
  assert.equal(numero(2.46, 1), "2,5");
  assert.equal(numero(2.46, 2), "2,46");
});

test("numero devolve traco para o que nao e numero finito", () => {
  for (const valor of [null, undefined, "5", NaN, Infinity]) assert.equal(numero(valor), "—");
});

test("pilula mostra o rotulo de cada nivel de risco", () => {
  assert.equal(pilula("VERDE"), '<span class="pilula verde">Verde</span>');
  assert.equal(pilula("AMARELO"), '<span class="pilula amarelo">Amarelo</span>');
  assert.equal(pilula("LARANJA"), '<span class="pilula laranja">Laranja</span>');
  assert.equal(pilula("VERMELHO"), '<span class="pilula vermelho">Vermelho</span>');
});

test("pilula usa 'Sem leituras' para nivel desconhecido", () => {
  assert.equal(pilula("QUALQUER"), '<span class="pilula neutro">Sem leituras</span>');
  assert.equal(pilula(undefined), '<span class="pilula neutro">Sem leituras</span>');
});

test("nomeFruta traduz uva e formata os demais nomes", () => {
  assert.equal(nomeFruta("uva"), "Uva de mesa");
  assert.equal(nomeFruta("manga-palmer"), "Manga palmer");
  assert.equal(nomeFruta("goiaba_vermelha"), "Goiaba vermelha");
});

test("nomeFruta tem valor padrao", () => {
  assert.equal(nomeFruta(null), "Fruta");
  assert.equal(nomeFruta(""), "Fruta");
});

test("faixa mostra o intervalo de temperatura", () => {
  assert.equal(faixa({ temp_min_c: 0.5, temp_max_c: 8 }), "0,5 a 8 °C");
  assert.equal(faixa(null), "—");
});

function avisoFalso() {
  const classes = new Set();
  return {
    textContent: "",
    classList: { toggle: (nome, ligado) => (ligado ? classes.add(nome) : classes.delete(nome)), contem: nome => classes.has(nome) },
  };
}

test("resultado da sincronizacao sem falhas", () => {
  const aviso = avisoFalso();
  mostrarResultadoDaSincronizacao(aviso, { novas: 5, descartadas: 1 });
  assert.equal(aviso.textContent, "5 novas leituras. 1 descartadas.");
  assert.equal(aviso.classList.contem("erro"), false);
});

test("resultado da sincronizacao lista os canais com falha", () => {
  const aviso = avisoFalso();
  mostrarResultadoDaSincronizacao(aviso, { novas: 0, descartadas: 0, falhas: [{ canal: 11 }, { canal: 22 }] });
  assert.match(aviso.textContent, /Falha nos canais: 11, 22\./);
  assert.equal(aviso.classList.contem("erro"), true);
});
