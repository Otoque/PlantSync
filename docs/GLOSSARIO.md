# Glossário

- **Lote / carga**: conjunto de frutas monitorado durante o transporte.
- **Viagem**: trajeto de um lote, com leituras e histórico.
- **Leitura**: medição de temperatura e umidade enviada pelo sensor.
- **ESP32**: microcontrolador que lê o sensor e publica os dados.
- **ThingSpeak**: serviço de nuvem que recebe as medições do ESP32.
- **Canal**: espaço do ThingSpeak onde uma placa publica. Cada placa usa um canal próprio.
- **Write API Key / Read API Key**: chaves para escrever no canal (ESP32) e ler dele (API).
- **Laudo**: relatório de risco por calor e frio de um lote.
- **Alerta**: aviso gerado quando uma leitura sai dos limites da fruta.
- **Empresa**: organização que agrupa contas, lotes e dispositivos na API `/api/v1`.
- **2FA / TOTP**: segundo fator de autenticação por código temporário.
- **IDOR**: falha em que um usuário acessa recurso de outro; coberta em `seguranca/testes/`.
