// Verificacoes estaticas do front-end: arquivos referenciados, imports, JSON e segredos.
import test from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const raiz = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const front = join(raiz, "front_end");

const ler = caminho => readFileSync(caminho, "utf8");
const paginas = readdirSync(front).filter(nome => nome.endsWith(".html"));
const modulos = readdirSync(join(front, "js")).filter(nome => nome.endsWith(".js"));

function arquivosDe(pasta, ignorar = []) {
  const achados = [];
  for (const nome of readdirSync(pasta)) {
    if (ignorar.includes(nome)) continue;
    const caminho = join(pasta, nome);
    statSync(caminho).isDirectory() ? achados.push(...arquivosDe(caminho, ignorar)) : achados.push(caminho);
  }
  return achados;
}

const local = ref => ref && !/^([a-z]+:|\/\/|#|data:)/i.test(ref);

test("existem paginas HTML e modulos JS para verificar", () => {
  assert.ok(paginas.length >= 4);
  assert.ok(modulos.length >= 10);
});

for (const pagina of paginas) {
  const html = ler(join(front, pagina));

  test(`${pagina}: declara idioma, titulo e viewport`, () => {
    assert.match(html, /<html[^>]*\blang="pt-BR"/i);
    assert.match(html, /<title>[^<]+<\/title>/i);
    assert.match(html, /<meta[^>]+name="viewport"/i);
  });

  test(`${pagina}: scripts e estilos locais existem`, () => {
    const refs = [...html.matchAll(/<(?:script|link)\b[^>]*?(?:src|href)="([^"]+)"/gi)].map(m => m[1]).filter(local);
    for (const ref of refs) {
      const arquivo = join(front, ref.split(/[?#]/)[0]);
      assert.ok(existsSync(arquivo), `${pagina} referencia ${ref}, que nao existe`);
    }
  });

  test(`${pagina}: nao usa scripts de outros dominios`, () => {
    const externos = [...html.matchAll(/<script\b[^>]*\bsrc="(https?:\/\/[^"]+)"/gi)].map(m => m[1]);
    assert.deepEqual(externos, []);
  });

  test(`${pagina}: nao repete ids`, () => {
    const ids = [...html.matchAll(/\sid="([^"]+)"/g)].map(m => m[1]);
    assert.equal(new Set(ids).size, ids.length, `ids repetidos em ${pagina}`);
  });
}

for (const modulo of modulos) {
  test(`js/${modulo}: imports relativos apontam para arquivos existentes`, () => {
    const codigo = ler(join(front, "js", modulo));
    const imports = [...codigo.matchAll(/(?:import|export)\s[^;]*?from\s+['"]([^'"]+)['"]/g)].map(m => m[1]);
    for (const ref of imports.filter(local)) {
      assert.ok(existsSync(resolve(front, "js", ref)), `${modulo} importa ${ref}, que nao existe`);
    }
  });
}

test("o painel principal carrega seu modulo de entrada", () => {
  assert.match(ler(join(front, "index.html")), /type="module"\s+src="js\/produto\.js"/);
});

test("ids buscados por produto.js existem no index.html ou sao criados pelo proprio JS", () => {
  const html = ler(join(front, "index.html"));
  const codigo = ler(join(front, "js", "produto.js"));
  const usados = new Set([...codigo.matchAll(/getElementById\('([^']+)'\)/g)].map(m => m[1]));
  assert.ok(usados.size > 0);
  const existe = id => new RegExp(`id=["'\\\\]*${id}\\b`).test(html) || new RegExp(`id=["'\\\\]*${id}\\b`).test(codigo);
  for (const id of usados) assert.ok(existe(id), `o id ${id} nao existe no HTML nem e criado pelo JS`);
});

test("arquivos JSON do front-end sao validos", () => {
  const jsons = arquivosDe(front, ["vendor"]).filter(c => /\.(json|geojson)$/.test(c));
  assert.ok(jsons.length > 0);
  for (const arquivo of jsons) assert.doesNotThrow(() => JSON.parse(ler(arquivo)), arquivo);
});

test("o GeoJSON do Nordeste tem features", () => {
  const dados = JSON.parse(ler(join(front, "mapas", "nordeste.geojson")));
  assert.equal(dados.type, "FeatureCollection");
  assert.ok(dados.features.length > 0);
});

test("o front-end nao contem credenciais embutidas", () => {
  const suspeitos = [
    /api_key\s*[=:]\s*['"][A-Za-z0-9]{12,}['"]/i,
    /write[_ ]?api[_ ]?key\s*[=:]\s*['"][A-Za-z0-9]{8,}['"]/i,
    /senha\s*[=:]\s*['"][^'"]{6,}['"]/i,
    /-----BEGIN [A-Z ]*PRIVATE KEY-----/,
    /\bBearer\s+[A-Za-z0-9._-]{20,}/,
  ];
  const arquivos = arquivosDe(front, ["vendor"]).filter(c => /\.(js|html|css|json|txt)$/.test(c));
  for (const arquivo of arquivos) {
    const texto = ler(arquivo);
    for (const regra of suspeitos) assert.doesNotMatch(texto, regra, `possivel credencial em ${arquivo}`);
  }
});

test("o front-end nao grava o token em localStorage", () => {
  for (const modulo of modulos) assert.doesNotMatch(ler(join(front, "js", modulo)), /localStorage/, modulo);
});

test("o front-end nao usa eval nem new Function", () => {
  for (const modulo of modulos) assert.doesNotMatch(ler(join(front, "js", modulo)), /\beval\s*\(|new Function\s*\(/, modulo);
});

test("arquivos locais de configuracao do QR nao estao versionados", () => {
  assert.equal(existsSync(join(front, "qr-publico.local.json")), false);
});
