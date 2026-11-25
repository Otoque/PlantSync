import test from "node:test";
import assert from "node:assert/strict";
import { date, empty, esc, number, setTimezone, table } from "../front_end/js/produto-texto.js";

test("esc neutraliza HTML e aceita valores vazios", () => {
  assert.equal(esc("<b>&\"'"), "&lt;b&gt;&amp;&quot;&#39;");
  assert.equal(esc(null), "");
  assert.equal(esc(undefined), "");
});

test("number formata em pt-BR com ate 2 casas", () => {
  assert.equal(number(1234.567), "1.234,57");
  assert.equal(number(3), "3");
});

test("number devolve traco para null e undefined", () => {
  assert.equal(number(null), "—");
  assert.equal(number(undefined), "—");
});

test("date converte para o fuso escolhido", () => {
  setTimezone("America/Recife");
  const recife = date("2026-10-24T21:00:00Z");
  assert.match(recife, /18:00/);
  setTimezone("UTC");
  assert.match(date("2026-10-24T21:00:00Z"), /21:00/);
});

test("date devolve traco para valor ausente ou invalido", () => {
  for (const valor of [null, undefined, "", "xyz"]) assert.equal(date(valor), "—");
});

test("setTimezone com fuso invalido volta para Sao Paulo", () => {
  setTimezone("Fuso/Invalido");
  assert.match(date("2026-10-24T21:00:00Z"), /18:00/); // UTC-3, como Recife
});

test("empty escapa a mensagem", () => {
  assert.equal(empty("<x>"), '<p class="empty">&lt;x&gt;</p>');
});

test("table monta cabecalho e linhas", () => {
  const html = table(["A", "B"], ["<tr><td>1</td><td>2</td></tr>"]);
  assert.match(html, /<th scope="col">A<\/th><th scope="col">B<\/th>/);
  assert.match(html, /<tbody><tr><td>1<\/td><td>2<\/td><\/tr><\/tbody>/);
});

test("table escapa os titulos das colunas", () => {
  assert.match(table(["<i>"], ["<tr></tr>"]), /&lt;i&gt;/);
});

test("table sem linhas mostra a mensagem de vazio", () => {
  assert.match(table(["A"], []), /Nenhum registro encontrado\./);
  assert.match(table(["A"], [], "Sem itens"), /Sem itens/);
});
