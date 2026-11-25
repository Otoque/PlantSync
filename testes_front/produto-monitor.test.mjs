import test from "node:test";
import assert from "node:assert/strict";
import { readingsTable } from "../front_end/js/produto-monitor.js";

const lote = { range: [2, 8] };
const leitura = (extra = {}) => ({
  data_hora: "2026-10-24T21:00:00Z", temperatura_c: 5, umidade_pct: 80, fonte: "ESP32", ambiente: "Bau", fase: "em_transito", ...extra,
});

test("readingsTable marca leitura dentro da faixa", () => {
  const html = readingsTable([leitura()], lote);
  assert.match(html, /Dentro da faixa/);
  assert.match(html, /5 °C/);
  assert.match(html, /80%/);
  assert.match(html, /Em trânsito/);
});

test("readingsTable marca leitura abaixo e acima da faixa", () => {
  assert.match(readingsTable([leitura({ temperatura_c: 1 })], lote), /Abaixo da faixa/);
  assert.match(readingsTable([leitura({ temperatura_c: 9 })], lote), /Acima da faixa/);
});

test("readingsTable nos limites exatos considera dentro da faixa", () => {
  assert.match(readingsTable([leitura({ temperatura_c: 2 })], lote), /Dentro da faixa/);
  assert.match(readingsTable([leitura({ temperatura_c: 8 })], lote), /Dentro da faixa/);
});

test("readingsTable sem faixa ou sem temperatura mostra traco", () => {
  assert.doesNotMatch(readingsTable([leitura()], {}), /faixa/);
  assert.doesNotMatch(readingsTable([leitura({ temperatura_c: null })], lote), /faixa/);
});

test("readingsTable ordena da leitura mais recente para a mais antiga", () => {
  const html = readingsTable([
    leitura({ data_hora: "2026-10-24T10:00:00Z", temperatura_c: 11.1 }),
    leitura({ data_hora: "2026-10-24T20:00:00Z", temperatura_c: 22.2 }),
  ], lote);
  assert.ok(html.indexOf("22,2") < html.indexOf("11,1"));
});

test("readingsTable escapa texto vindo do sensor", () => {
  const html = readingsTable([leitura({ fonte: "<script>x</script>" })], lote);
  assert.doesNotMatch(html, /<script>/);
  assert.match(html, /&lt;script&gt;/);
});

test("readingsTable sem leituras mostra mensagem de vazio", () => {
  assert.match(readingsTable([], lote), /Nenhuma leitura registrada/);
  assert.match(readingsTable(undefined, lote), /Nenhuma leitura registrada/);
});
