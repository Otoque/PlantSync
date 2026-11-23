# PlantSync

O PlantSync registra a temperatura e a umidade de cargas de frutas no Vale do São Francisco. O ESP32 envia as medições ao ThingSpeak. A API busca essas medições, guarda no banco local e calcula o risco por calor e frio. O painel mostra as cargas, os alertas e o laudo.

**Fluxo completo:** sensor → ESP32 → ThingSpeak → API → painel → QR.

Este guia começa do zero no Windows e no Linux. Siga o bloco de comandos do seu sistema. Você pode abrir o painel antes de ligar a placa. Para ver novas medições, a placa precisa publicar no canal que a API está lendo.

## Operação por empresa

O painel principal utiliza a API `/api/v1`, com contas individuais, empresas, permissões, ambientes, viagens e histórico por lote. O nome da primeira empresa pode ser informado em `PLANTSYNC_EMPRESA_INICIAL`. A conta configurada no ambiente inicial recebe administração da plataforma e vínculo de administrador nessa empresa. As demais contas são criadas por convite.

Se você já possui um banco com lotes e leituras, faça o ensaio de migração antes de retomar a operação. O [guia de migração e operação](docs/OPERACAO-POR-EMPRESA.md) explica a cópia, a conversão, a verificação e a recuperação. O [contrato da API por empresa](docs/API-OPERACAO.md) contém os caminhos para integrações.

## 1. Baixe o projeto

Instale o [Git](https://git-scm.com/downloads) e o [Python 3.14](https://www.python.org/downloads/). Para gravar uma placa, instale também a [Arduino IDE](https://www.arduino.cc/en/software/).

**Windows.** No instalador do Python, habilite a opção de adicionar o Python ao `PATH` se aparecer. Abra um PowerShell novo na pasta onde quer guardar o projeto:

```powershell
git clone --branch main https://github.com/Otoque/PlantSync.git
Set-Location PlantSync
python --version
```

**Linux.** Instale Git e Python pelo gerenciador de pacotes da sua distribuição. Se o Python 3.14 não estiver disponível, use a alternativa com `uv` na etapa 4. Para a IDE, siga as [instruções do Arduino para Linux](https://support.arduino.cc/hc/en-us/articles/360019833020-Download-and-install-Arduino-IDE). No terminal, na pasta onde quer guardar o projeto:

```bash
git clone --branch main https://github.com/Otoque/PlantSync.git
cd PlantSync
git --version
```

Se preferir baixar sem Git, abra o [repositório oficial](https://github.com/Otoque/PlantSync), escolha **Code → Download ZIP**, extraia o ZIP e abra um terminal na pasta extraída. A raiz é a pasta que contém `back_end`, `front_end` e `hardware`.

## 2. Escolha ou crie o canal ThingSpeak

1. Entre no [ThingSpeak](https://thingspeak.mathworks.com/) e abra **Channels → My Channels**. Combine com a equipe qual canal usar. Cada placa precisa de um canal próprio. Para criar um canal, clique em **New Channel**, dê um nome, habilite os campos na ordem da tabela e salve.
2. No canal escolhido, anote o número **Channel ID**. Na aba **API Keys**, localize a **Write API Key** (a chave que permite ao ESP32 enviar) e, se o canal for privado, a **Read API Key** (a chave que permite à API ler). As duas precisam pertencer ao mesmo canal. A documentação do [ThingSpeak sobre canais e chaves](https://www.mathworks.com/help/thingspeak/channel-control.html) explica onde encontrá-las.

| Campo | O que a placa envia |
| --- | --- |
| Field 1 | Temperatura (°C). Obrigatória para a API aceitar a leitura. |
| Field 2 | Umidade relativa do ar (%). |
| Field 3 | Intensidade do sinal Wi-Fi (dBm). |
| Field 4 | Água livre ou condensação (%). |
| Field 5 | Estimativa de luminosidade (lux), usada para identificar possível abertura da porta. O sensor de luz precisa de calibração para medir lux com precisão. |
| Field 6 | Código numérico dos alertas na placa. |
| Field 7 | Índice de risco calculado na placa (0 a 100). |

A API do painel usa os campos 1, 2 e 5 e calcula o risco da viagem com a faixa do lote. O LED e o Field 7 usam limites fixos do firmware. Mudar a faixa no painel só afeta a análise feita pela API. Mantenha a ordem dos campos ao configurar outro canal. Defina seu canal explicitamente no `.env`. O padrão do código é `3493443`.

## 3. Crie os arquivos locais

| Arquivo | Onde deve ficar | Para que serve |
| --- | --- | --- |
| `.env` | `back_end/.env` | Login do painel e configurações da API. Copie o [modelo](back_end/.env.example). |
| `credentials.h` | `hardware/plantsync-edge/credentials.h` e, ao compilar, ao lado do arquivo `.ino` | Rede Wi-Fi e chave de escrita do ESP32. Copie o [modelo](hardware/plantsync-edge/credentials.h.example). |
| `plantsync.db` | `back_end/plantsync.db` | Banco local com lotes, leituras e contas. A API cria o arquivo na primeira inicialização. |

Na raiz do clone, execute estes comandos. Eles preservam uma configuração que já exista:

**Windows:**

```powershell
if (!(Test-Path -LiteralPath back_end/.env)) {
    Copy-Item back_end/.env.example back_end/.env
}
if (!(Test-Path -LiteralPath hardware/plantsync-edge/credentials.h)) {
    Copy-Item hardware/plantsync-edge/credentials.h.example hardware/plantsync-edge/credentials.h
}
```

**Linux:**

```bash
if [ ! -e back_end/.env ]; then
    cp back_end/.env.example back_end/.env
fi
if [ ! -e hardware/plantsync-edge/credentials.h ]; then
    cp hardware/plantsync-edge/credentials.h.example hardware/plantsync-edge/credentials.h
fi
```

No `back_end/.env`, preencha uma variável por linha. Para mudar uma opção comentada no modelo, remova o `#` antes dela:

- `PLANTSYNC_USUARIO` e `PLANTSYNC_SENHA`: escolha um login local de **1 a 100 caracteres** e uma senha de **12 a 200 caracteres**.
- `CANAL_THINGSPEAK`: escreva o número do **Channel ID** depois de `=`.
- `PLANTSYNC_THINGSPEAK_CHAVE_<EMPRESA_ID>_<CANAL>`: após cadastrar a fonte, troque os identificadores pelos valores reais e preencha com a **Read API Key** se o canal for privado. Exemplo de nome: `PLANTSYNC_THINGSPEAK_CHAVE_1_1234567`. Em canal público, não é necessária. `CHAVE_LEITURA_THINGSPEAK` pertence ao contrato anterior.
- `DATABASE_URL` e `CORS_ORIGENS`: mantenha os padrões para os comandos deste guia.
- `PLANTSYNC_CHAVE_DISPOSITIVO`: só é necessária para um firmware que consulte a faixa do lote direto na API. O firmware desta `main` envia medições ao ThingSpeak e não faz essa consulta.

No `credentials.h`, mantenha as aspas e substitua os exemplos:

- `WIFI_SSID`: nome da rede Wi-Fi de **2,4 GHz** com acesso à internet. O [ESP32-C3 usa essa faixa](https://www.espressif.com/sites/default/files/documentation/esp32-c3_datasheet_en.pdf).
- `WIFI_PASSWORD`: senha dessa rede.
- `THINGSPEAK_API_KEY`: **Write API Key** do canal escolhido. O firmware usa essa chave para identificar o canal de escrita. O **Channel ID** fica no `.env` do backend.

Se o nome da rede ou a senha contém aspas duplas ou barras invertidas, escreva `\"` ou `\\` dentro das aspas do `credentials.h`.

O Git ignora esses arquivos preenchidos e o banco. Os arquivos `.example` podem ser compartilhados. Guarde uma cópia do banco se quiser preservar o histórico.

## 4. Ligue o backend e abra o painel

**Terminal 1 — API.** Comece na raiz do clone. A pasta `.venv` guarda as bibliotecas desta aplicação. Na primeira vez, crie a pasta e instale as dependências:

**Windows:**

```powershell
Set-Location back_end
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8000 --no-access-log
```

**Linux, com Python 3.14 instalado:**

```bash
cd back_end
python3.14 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m uvicorn app:app --host 127.0.0.1 --port 8000 --no-access-log
```

**Linux, se a distribuição não oferece Python 3.14.** Instale o [uv pelo guia oficial](https://docs.astral.sh/uv/getting-started/installation/). Ele baixa o Python pedido e prepara o ambiente. Entre em `back_end` a partir da raiz e execute:

```bash
cd back_end
uv venv --python 3.14 .venv
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python -m uvicorn app:app --host 127.0.0.1 --port 8000 --no-access-log
```

Nas próximas vezes, basta entrar em `back_end` e executar o último comando. Deixe o terminal aberto. O [teste da API](http://127.0.0.1:8000/api/saude) deve mostrar `{"status":"ok"}`. Depois de alterar o `.env`, pare a API com `Ctrl+C` e execute o último comando de novo.

**Terminal 2 — painel.** Abra outro terminal na **raiz do clone**, fora de `back_end`.

**Windows:**

```powershell
python tools/servir_painel_local.py
```

**Linux:**

```bash
back_end/.venv/bin/python tools/servir_painel_local.py
```

Deixe os dois terminais abertos. Acesse o [painel PlantSync](http://127.0.0.1:5500/) e entre com o usuário e a senha que você colocou no `.env`. Use esse endereço para abrir o painel pelo navegador.

## 5. Monte e grave o ESP32

Se a sua placa é um C3 Mini, leia primeiro a seção [ESP32-C3 Mini com DHT11](#esp32-c3-mini-com-dht11) para conferir a ligação do sensor.

1. Na Arduino IDE, abra **Arquivo → Preferências**. Em **URLs adicionais para gerenciadores de placas**, adicione o [endereço do pacote ESP32 da Espressif](https://espressif.github.io/arduino-esp32/package_esp32_index.json). No **Gerenciador de Placas**, instale **esp32**, da **Espressif Systems**. Consulte o [guia oficial](https://docs.espressif.com/projects/arduino-esp32/en/latest/installing.html) se o pacote não aparecer.
2. No **Gerenciador de Bibliotecas**, instale **DHT sensor library** (Adafruit), **Adafruit Unified Sensor** e **ArduinoJson**, conforme a [lista de bibliotecas](hardware/plantsync-edge/libraries.txt).
3. Com a placa desligada do USB, monte o circuito. Confirme os nomes dos pinos na documentação da sua placa. Use **3,3 V** e um **GND comum**. Os sinais ligados ao ESP32 não devem ultrapassar 3,3 V.

| Sinal | ESP32-C3 deste projeto |
| --- | --- |
| DHT11 | DATA no GPIO 4, VCC em 3V3 e GND em GND. Use um resistor de cerca de 10 kΩ entre DATA e 3V3 se o sensor ou módulo não tiver esse resistor. |
| Sensor de luz (LDR) | Saída analógica no GPIO 0. |
| Sensor capacitivo de umidade | Saída analógica no GPIO 1. |
| LED de alerta | O código usa GPIO 8 e alterna nível alto e baixo. Confira o pino, o tipo e a polaridade do LED da sua placa. GPIO 8 também é lido na partida do C3. Para um LED externo, escolha uma saída adequada na documentação da placa, use um resistor em série e ajuste `PIN_LED`. Veja a [pinagem do C3](https://docs.espressif.com/projects/esp-idf/en/stable/esp32c3/api-reference/peripherals/gpio.html). |

O [diagrama de referência](hardware/plantsync-edge/diagram.json) usa um DHT22 simulado. Para o DHT11 físico, deixe `SIMULACAO_WOKWI` comentado no firmware.

4. Prepare uma cópia local do firmware. No Arduino, o [arquivo principal `.ino` precisa ter o mesmo nome da pasta](https://arduino.github.io/arduino-cli/dev/sketch-specification/#primary-sketch-file). A cópia permite adaptar os pinos sem editar o original do repositório. Execute a partir da raiz do clone. Use um nome novo se você já tiver uma cópia com alterações.

**Windows:**

```powershell
$nome = 'PlantSync-Edge'
$sketch = Join-Path $env:LOCALAPPDATA $nome
if (Test-Path -LiteralPath $sketch) { throw 'A pasta já existe. Mude o valor de $nome antes de copiar.' }
New-Item -ItemType Directory -Path $sketch | Out-Null
Copy-Item hardware/plantsync-edge/main.ino (Join-Path $sketch "$nome.ino")
Copy-Item hardware/plantsync-edge/credentials.h (Join-Path $sketch 'credentials.h')
Write-Output "Abra este arquivo na Arduino IDE: $sketch\$nome.ino"
```

**Linux:**

```bash
(
    set -eu
    nome=PlantSync-Edge
    sketch="${XDG_DATA_HOME:-$HOME/.local/share}/$nome"
    mkdir -p "$(dirname "$sketch")"
    mkdir "$sketch"
    cp hardware/plantsync-edge/main.ino "$sketch/$nome.ino"
    cp hardware/plantsync-edge/credentials.h "$sketch/credentials.h"
    printf 'Abra este arquivo na Arduino IDE: %s\n' "$sketch/$nome.ino"
)
```

5. Na Arduino IDE, abra `PlantSync-Edge.ino` na pasta criada. Conecte a placa com um cabo USB **de dados**. Em **Ferramentas**, selecione o modelo da placa e a porta que apareceu ao conectar. No Windows ela costuma aparecer como `COM`; no Linux, como `/dev/ttyUSB0` ou `/dev/ttyACM0`, com número variável. Para um ESP32-C3 genérico, comece por **ESP32C3 Dev Module**.
6. Clique em **Verificar** para compilar e depois em **Carregar** para gravar. Abra o **Monitor Serial** a **115200 baud**. Aguarde a conexão Wi-Fi e um envio. Uma linha `[HTTP]` com código `200` e `entry_id` maior que zero indica que o ThingSpeak aceitou a leitura.

**Linux: erro de permissão na porta USB.** Confira o grupo da porta com `ls -l /dev/ttyACM0`, usando o nome que aparece na sua IDE. Se o grupo for `dialout`, execute `sudo usermod -aG dialout "$USER"` e entre novamente na sua sessão. Se a distribuição usar outro grupo ou o erro continuar, siga o [guia de acesso à porta serial no Linux](https://support.arduino.cc/hc/en-us/articles/360016495679-Fix-port-access-on-Linux).

### ESP32-C3 Mini com DHT11

1. **Identifique a placa.** Confira o modelo impresso ou a página do fabricante. Se a placa for um C3 Mini ou Super Mini sem opção própria na Arduino IDE, use **ESP32C3 Dev Module** como ponto de partida. A porta USB selecionada em **Ferramentas → Porta** é a conexão com o computador. O **GPIO** é o pino na placa onde o fio do sensor está ligado.
2. **Siga o fio de dados.** Com o USB desconectado, identifique `DATA`, `OUT` ou `S` no DHT11 e confira a qual GPIO esse fio vai. O **mesmo DHT11 mede temperatura e umidade do ar pelo mesmo fio**. `PIN_UMIDADE` no código controla outro sensor, o capacitivo que mede água livre.
3. **Faça o código corresponder à ligação.** Na sua cópia de `PlantSync-Edge.ino`, procure `#define DHTPIN`. Ele vem com o valor `4`. Se o fio DATA está no GPIO 4, deixe assim. Se estiver no GPIO 3 e a pinagem da sua placa confirmar que ele está livre, troque a linha para `#define DHTPIN 3`. Use o número do GPIO da pinagem, não a posição física do conector. Mantenha o tipo `DHT11` e a opção `SIMULACAO_WOKWI` comentada.
4. **Grave e confira a leitura.** Se o conector da placa usa USB nativo e o Monitor Serial ficar vazio após a gravação, tente **Ferramentas → USB CDC On Boot → Enabled**, grave de novo e selecione a porta que reaparecer. Se a placa usa uma ponte USB–serial separada, deixe essa opção desabilitada. Abra o Monitor Serial a **115200** e confirme que aparecem temperatura e umidade antes do envio. Veja as [orientações de serial da Espressif](https://docs.espressif.com/projects/arduino-esp32/en/latest/troubleshooting.html#serial-not-printing).

**Se você só tem o DHT11:** dá para testar temperatura e umidade no painel sem o sensor de luz e o capacitivo. Na cópia do firmware, procure `String url` dentro da função de envio e substitua apenas a montagem da URL pelo bloco abaixo. Ele envia somente temperatura, umidade do ar e sinal Wi-Fi. Ignore os avisos locais de luz e condensação nesse teste. O firmware original ainda lê esses pinos, e sem os sensores essas leituras não representam condições reais.

```cpp
String url = String("https://api.thingspeak.com/update")
             + "?api_key=" + String(THINGSPEAK_API_KEY)
             + "&field1=" + String(amostra.temperatura, 2)
             + "&field2=" + String(amostra.umidade, 2)
             + "&field3=" + String(amostra.rssi);
```

### Se você usar outra placa

- **Outro ESP32:** selecione o modelo correto na IDE. No início da cópia de `PlantSync-Edge.ino`, adapte `DHTPIN`, `PIN_LDR`, `PIN_UMIDADE` e `PIN_LED`. Escolha dois pinos com entrada analógica que funcionem com Wi-Fi ligado. Para um **ESP32 clássico (ESP-WROOM-32)**, uma adaptação possível é DHT11 no GPIO 4, luz no GPIO 34, sensor capacitivo no GPIO 35 e LED no GPIO 2 se a sua placa usar esse pino. Confira a pinagem e a polaridade do LED no manual da sua placa. Compile antes de gravar.
- **Outro sensor:** se o protocolo mudar, adapte a leitura no firmware e use a biblioteca do sensor. Um DHT22 físico, por exemplo, requer `DHTTYPE` configurado para `DHT22` e revisão dos limites de leitura, que hoje foram definidos para o DHT11. Monte os sensores analógicos usados pelo código para evitar leituras de pinos desconectados.
- **Uma placa de outra família:** use um programa compatível com a placa para [publicar no ThingSpeak por HTTPS](https://www.mathworks.com/help/thingspeak/writedata.html). Envie temperatura numérica em °C no **Field 1**, umidade em **Field 2** e luminosidade em **Field 5** se disponíveis. Use a chave de escrita do canal configurado na API. Nessa configuração, o backend e o painel continuam os mesmos.

Para quem vai programar outra placa, o envio pode ser um `POST` para `https://api.thingspeak.com/update.json`. Envie a chave de escrita no cabeçalho `THINGSPEAKAPIKEY` e use `Content-Type: application/json`. Substitua os números pelos valores lidos pelo sensor. Preserve o intervalo de 20 segundos usado no firmware do projeto durante o teste.

```json
{"field1": 2.1, "field2": 87.0, "field5": 12.0}
```

## 6. Confira o fluxo com uma leitura nova

1. Em **Ambientes e sensores**, cadastre a câmara fria e a fonte do sensor. Informe o Channel ID do ThingSpeak e associe o sensor ao ambiente. Para canal privado, configure no backend `PLANTSYNC_THINGSPEAK_CHAVE_<EMPRESA_ID>_<CANAL>` com a chave de leitura e reinicie a API.
2. Em **Lotes → Novo lote**, informe fruta, cliente, destino, quantidade e o ambiente de preparação. Confira a faixa aplicada. O cadastro registra o início da preparação e passa a considerar as leituras durante a permanência no ambiente.
3. Aguarde uma entrada do sensor posterior ao início da preparação. Confira o horário e o Field 1 no ThingSpeak. Use **Sincronizar leituras** e abra o lote para conferir temperatura, gráfico, extremos e origem. Sem leitura válida, a tela informa a ausência de dados.
4. Cadastre a viagem, as paradas e o compartimento do veículo. Associe o sensor correspondente ao compartimento e registre o carregamento. Depois confirme o despacho. A espera dentro do veículo fica separada da preparação e do transporte.
5. Em **Etiquetas QR**, selecione o lote, confira e imprima. O QR abre o resumo público. O laudo detalhado exige acesso autorizado ou link secreto válido. Os critérios finais do selo estão pendentes; a classificação verde isolada não libera a carga.
6. Registre o recebimento do lote, consulte o histórico e emita o laudo. As mudanças de fase registram autor, responsabilidade e horários. Compartilhe documentos apenas com os destinatários pretendidos.

Links com `127.0.0.1` abrem no computador que serve o painel. Para escanear pelo celular na mesma rede Wi-Fi, siga o [passo a passo de QR na rede local](front_end/README.md#abrir-o-qr-no-celular-na-mesma-rede).

O mapa usa ruas do OpenStreetMap e posições registradas na viagem pelo celular ou por integração autorizada. Temperatura no ThingSpeak não fornece GPS automaticamente. Sem posição, a tela informa a ausência de localização. Para iniciar rastreio no celular, use HTTPS e permita a localização; confira as limitações em [Operação por empresa](docs/OPERACAO-POR-EMPRESA.md#localização-no-celular).

### Acompanhar duas cargas simultâneas

1. Crie um canal ThingSpeak para cada ESP32. Grave cada placa com a **Write API Key do seu próprio canal** e confira no Monitor Serial e no ThingSpeak onde aparecem as leituras. Não use a mesma chave nas duas placas.
2. Em **Ambientes e sensores**, cadastre cada sensor com seu Channel ID e associe-o ao ambiente correto. Para canais privados, use `PLANTSYNC_THINGSPEAK_CHAVE_<EMPRESA_ID>_<CANAL>` no `.env` e reinicie a API.
3. Lotes presentes no mesmo ambiente podem compartilhar as leituras do mesmo sensor; cada lote aplica sua própria faixa. Lotes em ambientes distintos precisam dos pontos de medição correspondentes. Ao mover o sensor, registre a troca de instalação para preservar o histórico.

A atualização de um banco anterior exige a conversão explícita descrita em [Migração de um banco existente](docs/OPERACAO-POR-EMPRESA.md#migração-de-um-banco-existente). As tabelas antigas são preservadas. A consulta antiga da faixa do dispositivo atende somente a fonte padrão e recusa indicar uma faixa única quando há vários lotes monitorados.

### Trocar de canal ou de computador

1. Na operação por empresa, cadastre o novo canal como outra fonte e encerre a instalação anterior no horário correto. Os identificadores das leituras são separados por fonte. Não troque a identidade de um canal que já possui histórico.
2. Configure a chave de leitura da nova fonte, se privada, em `PLANTSYNC_THINGSPEAK_CHAVE_<EMPRESA_ID>_<CANAL>`. O `CANAL_THINGSPEAK` identifica o canal padrão usado na conversão do banco antigo.
3. Atualize a **Write API Key** em `hardware/plantsync-edge/credentials.h`, copie apenas esse arquivo para a pasta do `.ino` e grave o ESP32 novamente. Assim você preserva os ajustes de pinos feitos na sua cópia do firmware. Ao mudar de computador, copie os modelos e repita a configuração.

### Se algo não funcionar

| Sintoma | O que verificar |
| --- | --- |
| A página não abre. | Os dois terminais precisam estar abertos. Teste primeiro a API na porta 8000 e depois abra o painel na 5500. |
| O login é recusado. | Confira se o arquivo é `.env`, sem `.txt`, se está em `back_end` e se os tamanhos de usuário e senha seguem a etapa 3. Reinicie a API em um terminal sem valores antigos dessas variáveis. |
| A IDE não encontra a porta da placa. | Use um cabo de dados e teste outra porta USB. Desconecte e reconecte a placa para identificar a porta nova. No Linux, confira a permissão conforme a etapa 5. Consulte o [guia da Espressif](https://docs.espressif.com/projects/arduino-esp32/en/latest/troubleshooting.html). |
| O Monitor Serial mostra erro do DHT11. | Confira 3V3, GND, GPIO de dados, resistor de 10 kΩ e o tipo do sensor no firmware. Uma amostra inválida é descartada antes do envio. |
| O canal não recebe dados. | Confira Wi-Fi de 2,4 GHz, internet, chave de escrita, campos habilitados e Monitor Serial. HTTP `200` com `entry_id` igual a `0` indica que o envio não foi aceito. Confira se há outra placa publicando e aguarde o próximo ciclo de 20 segundos. |
| O canal recebe dados, mas o gráfico está vazio. | Confira o canal e a chave de leitura no backend. Uma variável definida no terminal pode prevalecer sobre o `.env`; confirme o canal informado pela sincronização. O lote só mostra medições dentro do seu intervalo. |

## Sobre o projeto

Projeto Integrador de Análise e Desenvolvimento de Sistemas, 4º período. A [documentação do checkpoint](docs/CHECKPOINT-01.md) apresenta o contexto. Para desenvolver ou integrar outra aplicação, consulte o [contrato da API](docs/api-contrato.md). Para analisar uma exportação de dados do canal, o script fica em [`analytics/eda_plantsync.py`](analytics/eda_plantsync.py).

| Integrante | Frente |
| --- | --- |
| Davi Clemente — `@cldavii` | Hardware / IoT |
| Ygor Sampaio | Hardware / IoT |
| Jorge Antonio Figueredo — `@Jorgefigueredoo` | Backend / Cloud |
| Nicolas Tavares da Silva — `@Otoque` | Backend / Cloud |
| Pedro Valença — `@pedrohmvalenca` | Frontend / Documentação |
