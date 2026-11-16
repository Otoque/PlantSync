async function lerJson(caminho) {
  const resposta = await fetch(caminho, { signal: AbortSignal.timeout(5000) });
  if (!resposta.ok) return null;
  return resposta.json();
}

export async function mostrarTrajeto(codigo) {
  if (!/^[A-Za-z0-9_-]{8}$/.test(codigo) || !window.L) return;
  const rota = await lerJson(`./mapas/publicos/${codigo}.json`);
  if (!rota?.pontos || rota.pontos.length < 2) return;
  const secao = document.getElementById("trajeto-publico");
  const quadro = document.getElementById("mapa-publico");
  document.getElementById("trajeto-destino").textContent = `${rota.origem} → ${rota.destino}`;
  secao.hidden = false;
  const mapa = L.map(quadro, { scrollWheelZoom: false, minZoom: 4, maxZoom: 10 });
  mapa.fitBounds(rota.pontos, { padding: [25, 25], maxZoom: 9 });
  const camada = mapa.createPane("rota");
  camada.style.zIndex = "430";
  const estilo = { pane: "rota", color: "#17637c" };
  L.polyline(rota.pontos, { ...estilo, weight: 4, dashArray: "8 7" }).addTo(mapa);
  for (const [ponto, nome] of [[rota.pontos[0], rota.origem], [rota.pontos.at(-1), rota.destino]]) {
    const legenda = document.createElement("span");
    legenda.textContent = nome;
    L.circleMarker(ponto, { ...estilo, radius: 6, fillColor: "white", fillOpacity: 1 })
      .addTo(mapa).bindTooltip(legenda);
  }
  const malha = await lerJson("./mapas/nordeste.geojson");
  if (malha) {
    L.geoJSON(malha, {
      style: { color: "#859888", fillColor: "#e9eedc", fillOpacity: 1, weight: 1.2 },
      interactive: false,
    }).addTo(mapa);
    mapa.attributionControl.addAttribution("Malha IBGE");
  }
}
