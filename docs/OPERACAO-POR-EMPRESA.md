# Operação por empresa

O painel principal usa `/api/v1`. Cada conta tem vínculos e permissões por empresa. O administrador da plataforma administra o serviço e provisiona organizações. O acesso operacional depende de vínculo com a empresa ou concessão específica ao lote.

## Instalação nova

1. Siga a instalação do Python e das dependências no README.
2. Copie `back_end/.env.example` para `back_end/.env` e preencha as credenciais iniciais e o canal ThingSpeak. Informe o nome da organização em `PLANTSYNC_EMPRESA_INICIAL` se quiser escolher o nome na criação.
3. Inicie o backend pelo comando de seu sistema no README. O primeiro início prepara o administrador e a empresa. Alterações posteriores de perfil, empresa e senha persistem sem depender de reescrever o ambiente inicial.
4. Abra o painel principal e entre com a conta inicial. Em Empresas, cadastre outras organizações e convide seus administradores. Em Configurações, gerencie equipe, papéis, fluxo e integrações.
5. Cadastre uma câmara fria, um sensor e a associação do equipamento ao ambiente. Depois crie o lote e inicie sua preparação nessa câmara.

## Migração de um banco existente

Pare o servidor antes da conversão e mantenha o arquivo original como backup. O comando recebe o caminho exato do banco e o nome da empresa de destino. Ele cria uma cópia de segurança adicional, verifica a integridade e publica a conversão numa transação. Repetir a conversão para a mesma empresa retorna o resumo existente.

Faça primeiro um ensaio numa cópia. Os exemplos partem da pasta `back_end`, com o ambiente virtual ativo.

Windows, em PowerShell

```powershell
Copy-Item -LiteralPath plantsync.db -Destination ensaio-operacao.db
python -B scripts/migrar_operacao.py --banco ensaio-operacao.db --empresa "Nome da empresa"
```

Linux

```bash
cp plantsync.db ensaio-operacao.db
python -B scripts/migrar_operacao.py --banco ensaio-operacao.db --empresa "Nome da empresa"
```

O nome deve corresponder à empresa inicial existente, se a conta já foi preparada. O comando recusa um destino divergente. Confira o resumo de lotes, leituras e fontes, abra a cópia com `DATABASE_URL` apontando para ela e verifique exemplos de consulta e QR. O histórico convertido recebe identificação de origem legada e mantém seus códigos públicos. Etapas não registradas no modelo anterior precisam ser interpretadas como histórico importado.

Depois do ensaio, aplique o mesmo comando ao banco de operação, usando seu caminho real. Reinicie a API. A inicialização da operação por empresa desativa o login e as rotas internas antigas, que passam a responder `410`, inclusive em uma instalação nova. Após a conversão, os códigos públicos e links de laudo antigos são encaminhados à operação atual, respeitando revogações.

Para recuperar um ensaio ou uma atualização que falhou, pare o servidor, preserve os arquivos produzidos para diagnóstico e copie o backup íntegro para o caminho configurado em `DATABASE_URL`. Confira as contagens e a versão antes de abrir a operação. Na cópia de validação desta evolução foi ensaiada a restauração do banco anterior.

## Primeiro ciclo de uma carga

1. Cadastre a câmara e associe a fonte que mede esse ambiente.
2. Cadastre o lote com fruta, cliente, destino e faixa. O início da preparação registra autor, horário, responsabilidade e associação ao ambiente.
3. Cadastre a viagem, o veículo e as paradas. Cadastre o compartimento com seu sensor.
4. Registre o carregamento do lote. O sistema encerra a permanência na câmara, inicia a permanência no compartimento e conta a espera antes do despacho.
5. Confirme o despacho individualmente ou para os lotes elegíveis da viagem. Retornos e avanços com pendências exigem as justificativas previstas no fluxo.
6. Registre o recebimento de cada lote. Os outros lotes seguem na viagem. Consulte o histórico e o laudo do lote recebido.

Um sensor representa o ambiente em que está instalado. Vários lotes podem usar suas medições durante os respectivos intervalos. A mesma instalação física não mede câmara e veículo simultaneamente. Use sensores distintos quando os ambientes precisarem ser acompanhados ao mesmo tempo.

## ThingSpeak e sensores

A placa continua enviando ao canal por sua Write API Key. No painel, cadastre o Channel ID na fonte do sensor e associe-a ao ambiente. A API importa temperatura, umidade e luz quando disponíveis e aplica a faixa de cada lote às medições compartilhadas.

Para canais privados na operação por empresa, configure a Read API Key no servidor em `PLANTSYNC_THINGSPEAK_CHAVE_<EMPRESA_ID>_<CANAL>`. Esse segredo não deve ser incluído no frontend, no QR ou em documentos. Os IDs da empresa e do canal precisam corresponder ao cadastro da fonte. Reinicie o servidor após mudar o ambiente local.

O hardware do projeto precisa manter o modelo correto da placa, o GPIO do DHT11 e as bibliotecas indicadas no README. Uma placa ESP32-C3 e um ESP32 clássico usam opções de compilação e pinagem compatíveis com sua montagem. A migração de empresas e o novo fluxo não exigem regravar uma placa que já envia corretamente as medições.

## Localização no celular

Abra a viagem com a conta responsável e inicie o rastreamento. A aplicação pede permissão ao navegador e informa envio, erro e última atualização. O rastreio permanece associado à viagem enquanto a pessoa usa as telas da mesma empresa. Encerrar, trocar de empresa ou sair da conta precisa encerrar a fonte correspondente.

No celular, utilize uma origem segura para a aplicação, com HTTPS e certificado aceito no dispositivo. Um endereço HTTP do computador na rede local pode servir páginas e QRs, mas a captura de localização depende das regras de segurança do navegador. [Especificação de geolocalização do W3C](https://www.w3.org/TR/geolocation/)

O navegador e o sistema móvel podem suspender a execução em segundo plano ou com a tela bloqueada. Verifique o dispositivo pretendido antes de prometer monitoramento contínuo. Interrupções devem ser tratadas como lacunas. Uma transportadora pode alimentar as posições pela API usando uma credencial com escopo da viagem. [Ciclo de vida de páginas no Chrome](https://developer.chrome.com/docs/web-platform/page-lifecycle-api)

O mapa carrega ruas da base OpenStreetMap e desenha somente posições e percursos registrados. A camada envia apenas a origem do painel como referência, sem a sessão ou o caminho do laudo. Ela depende de conexão e da disponibilidade do serviço; a lista textual continua acessível em caso de falha. Para uma operação com maior volume, planeje um provedor compatível com o uso: o servidor comunitário não oferece garantia de disponibilidade. [Política de uso da base OpenStreetMap](https://operations.osmfoundation.org/policies/tiles/)

## QR, impressão e laudo

Em Etiquetas QR, selecione os lotes, confira a identificação e imprima. Reimprimir conserva a identidade do lote. A leitura abre a página pública; ações operacionais exigem login, permissão e confirmação.

O endereço das etiquetas usa a origem da aplicação ou a configuração local `front_end/qr-publico.local.json`, com o campo `origem`. Confira se o endereço é acessível pelo celular e continua válido depois de trocar de rede ou porta. O QR não deve conter `127.0.0.1` quando será lido de outro aparelho.

O proxy local de consulta pública, quando usado nesta máquina, permite apenas a página pública, seus arquivos e os links de consulta por código ou segredo. Ele não publica login nem gestão de lotes. Mantenha a API interna no endereço de loopback. A origem configurada precisa corresponder ao IP atual do computador; troca de rede exige atualizar a configuração e reiniciar o proxy. Acessos a partir de outro celular e regras do firewall precisam ser conferidos na rede de destino.

Compartilhe o laudo pelo acesso autenticado concedido ou por um link específico com validade e revogação. Critérios finais do selo de conservação continuam em definição. Até sua aprovação, o documento mostra medições, exposição, lacunas e a situação de avaliação.

## Alertas e configurações

O histórico mostra a duração das etapas. Alertas de conservação e falta de medições possuem tratamento identificado. O limite de ausência pode ser configurado pela empresa. O avanço por saída detectada começa desativado e depende de uma política explícita de área, persistência, precisão e prazo.

Configurações do fluxo são versionadas. Os lotes mantêm a versão em uso; reduzir direitos de uma conta ou revogar uma concessão tem efeito na próxima requisição. Papéis, credenciais e convites devem ser revisados quando a equipe muda.

A integração térmica interrompe a exposição calculada em intervalos maiores que uma hora. Esse limite técnico evita preencher silêncio com medições inventadas; não representa uma tolerância de conservação aprovada. Notificações externas e os critérios finais de liberação ainda exigem definição e validação operacional.
