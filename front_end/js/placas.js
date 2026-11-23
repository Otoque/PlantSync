import { requisitar } from "./dados.js";
import { escapar } from "./ui.js";

function mostrarPlacas(lista, placas) {
  lista.innerHTML = placas.map(placa => `
    <article class="cartao">
      <h2>${escapar(placa.nome)}</h2>
      <p>Canal ThingSpeak ${escapar(placa.canal)}</p>
      <span class="pilula ${placa.ocupado ? "amarelo" : "verde"}">${placa.ocupado ? "Indisponível" : "Disponível"}</span>
    </article>`).join("");
}

export async function renderizarPlacas(el) {
  const placas = await requisitar("/dispositivos");
  if (!el.isConnected) return;
  el.innerHTML = `
    <header class="cabecalho"><h1>Placas</h1><p>Cadastre cada ESP32 com um canal ThingSpeak próprio.</p></header>
    <section class="cartao">
      <h2>Nova placa</h2>
      <form>
        <div class="grade duas">
          <label class="campo">Nome da placa<input name="nome" maxlength="80" required placeholder="Ex.: ESP32 do caminhão 2"></label>
          <label class="campo">Channel ID do ThingSpeak<input name="canal" type="number" min="1" max="2147483647" step="1" required></label>
        </div>
        <p class="suave">Use o número do canal. A chave de escrita fica na placa.</p>
        <div class="acoes"><button class="botao" type="submit">Cadastrar placa</button><a href="#inicio">Voltar às cargas</a></div>
        <p class="aviso" role="status"></p>
      </form>
    </section>
    <div class="grade duas" aria-label="Placas cadastradas"></div>`;
  const form = el.querySelector("form");
  const aviso = form.querySelector("[role=status]");
  const botao = form.querySelector("button");
  const lista = el.querySelector("[aria-label='Placas cadastradas']");
  mostrarPlacas(lista, placas);
  form.addEventListener("submit", async evento => {
    evento.preventDefault();
    if (botao.disabled) return;
    const dados = new FormData(form);
    botao.disabled = true;
    aviso.textContent = "";
    aviso.classList.remove("erro");
    try {
      const placa = await requisitar("/dispositivos", {
        method: "POST", body: { nome: dados.get("nome").trim(), canal: Number(dados.get("canal")) },
      });
      placas.push(placa);
      mostrarPlacas(lista, placas);
      form.reset();
      aviso.textContent = "Placa cadastrada. Selecione-a ao criar uma carga.";
    } catch (erro) {
      aviso.classList.add("erro");
      aviso.textContent = erro.message;
    } finally {
      botao.disabled = false;
    }
  });
}
