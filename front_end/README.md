# Painel PlantSync

Na raiz do repositório, sirva o frontend em HTTP:

```powershell
python tools/servir_painel_local.py
```

- [Painel com API](http://127.0.0.1:5500/): inicie também o backend na porta 8000. Consulte o modelo `back_end/.env.example` para configurar o usuário e o canal `CANAL_THINGSPEAK` no ambiente local do backend. O mesmo host (localhost ou 127.0.0.1) é usado nas duas portas.
- Em um servidor com origem única, sirva esta pasta na raiz e encaminhe `/api` para o backend. Antes de publicar uma instância, confira as limitações na seção de segurança do [contrato da API](../docs/api-contrato.md).

O painel utiliza a API `/api/v1`, com empresas, papéis e permissões. O mapa carrega ruas do OpenStreetMap e exibe posições registradas por celular ou integração autorizada. Sem posições, informa a ausência de localização. A tabela continua disponível se a base cartográfica falhar. Consulte [Operação por empresa](../docs/OPERACAO-POR-EMPRESA.md) para o fluxo atual e a configuração do rastreio.

## Abrir o QR no celular, na mesma rede

1. Deixe a API na porta 8000 e o painel na porta 5500, conforme o [guia principal](../README.md). Descubra o IPv4 e o prefixo da rede Wi-Fi do computador. No Windows, use `ipconfig`; por exemplo, a máscara `255.255.255.0` corresponde a `/24`. No Linux, use `ip -4 addr`. Use o IP e o prefixo da sua máquina nos exemplos a seguir.
2. Na raiz do repositório, abra outro terminal e execute `python tools/servir_qr_local.py 192.168.1.20/24`. No Linux, use `python3` ou o Python do ambiente do backend. Esse servidor usa a porta 5501 e só oferece a página pública e os recursos que ela usa.
3. Crie `front_end/qr-publico.local.json` com o IP usado no passo anterior:

```json
{"origem": "http://192.168.1.20:5501"}
```

4. Atualize o painel, abra um lote e gere o QR de novo. Se o celular ainda não alcançar a página na mesma rede, confira se a rede permite comunicação entre aparelhos e se o firewall do computador libera a porta TCP 5501 para a sua sub-rede.

## Percurso e selo

O painel distingue o percurso observado de uma rota planejada quando ela foi registrada. Os arquivos regionais e catálogos antigos não representam GPS nem são preenchidos automaticamente com movimento simulado.

O QR atual abre `publico-lote.html?codigo=...` com um resumo do lote. Gráfico e histórico ficam no laudo autenticado ou no link secreto com validade e revogação. Os critérios do selo estão pendentes: a avaliação não declara liberação automática da carga. Configurações locais e segredos permanecem fora do Git.
