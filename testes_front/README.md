# Testes do front-end

Testes automatizados dos módulos JavaScript do painel (`front_end/js/`) e verificações estáticas das páginas HTML. Usam apenas o executor de testes que já vem com o Node.js: não há `package.json` nem dependências para instalar.

## Requisito

Node.js 20 ou mais novo (`node --version`).

## Como rodar

```bash
cd testes_front
node --test
```

Para um arquivo só: `node --test ui.test.mjs`.

## O que cada arquivo cobre

| Arquivo | O que verifica |
|---|---|
| `ui.test.mjs` | Escape de HTML, datas no fuso de Recife, números em pt-BR, pílulas de risco, nome de fruta e aviso de sincronização. |
| `produto-texto.test.mjs` | Funções de texto e tabela do painel principal, incluindo fuso e valores vazios. |
| `dados.test.mjs` | Sessão do usuário, expiração, cabeçalhos das requisições e tradução de erros da API. |
| `produto-api.test.mjs` | Cliente da API v1: cabeçalhos de token e empresa, mensagens de erro, erro 429, link público do QR. |
| `produto-monitor.test.mjs` | Tabela de leituras: faixa de temperatura, ordenação e escape de texto do sensor. |
| `estatico.test.mjs` | Arquivos referenciados pelos HTML, imports entre módulos, JSON válidos, ids da página, ausência de credenciais, `localStorage`, `eval` e scripts externos. |

## Como funcionam

Os módulos foram feitos para o navegador. O arquivo `ambiente.mjs` simula `location`, `sessionStorage` e eventos, e substitui o `fetch` por respostas falsas. Assim os testes não abrem navegador, não acessam a rede e não chamam a API real.

Estes testes ficam fora de `front_end/` de propósito, para não serem publicados junto com o painel pelos servidores de `tools/`.
