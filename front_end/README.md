# Painel PlantSync

Na raiz do repositório, sirva o frontend em HTTP:

```powershell
python -m http.server 5500 --bind 127.0.0.1 --directory front_end
```

- [Painel com API](http://127.0.0.1:5500/): inicie também o backend na porta 8000. Consulte o modelo `back_end/.env.example` para configurar o usuário e o canal `CANAL_THINGSPEAK` no ambiente local do backend. O mesmo host (localhost ou 127.0.0.1) é usado nas duas portas.
- Em um servidor com origem única, sirva esta pasta na raiz e encaminhe `/api` para o backend. Antes de publicar uma instância, confira as limitações na seção de segurança do [contrato da API](../docs/api-contrato.md).

O painel consulta a API. A malha local do Nordeste vem da [API de malhas geográficas do IBGE](https://servicodados.ibge.gov.br/api/docs/malhas?versao=3), endpoint `/api/v3/malhas/regioes/NE`, com qualidade mínima e divisão por UF. Ela não depende de um serviço de blocos de mapa. Marcadores aparecem somente para lotes com coordenadas informadas pela API. A lista continua disponível se o arquivo da malha não carregar.
