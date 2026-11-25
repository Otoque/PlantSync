# Como rodar os testes

## Backend

Os testes ficam em `back_end/tests/` e usam um banco SQLite em memória, então nunca alteram o `plantsync.db`.

### Preparar o ambiente

```bash
cd back_end
python -m venv .venv
# Windows (PowerShell): .\.venv\Scripts\Activate.ps1
# Linux:                source .venv/bin/activate
pip install -r requirements.txt
```

### Executar

```bash
pytest                                  # todos os testes
pytest tests/test_datas.py -v           # um arquivo, com detalhes
pytest -k totp                          # só testes com "totp" no nome
```

### Como escrever um teste novo

1. Crie `tests/test_<assunto>.py`.
2. Nomeie as funções começando com `test_`.
3. Use `assert` para comparar o resultado com o esperado.
4. Para testar a API, use as fixtures `cliente` e `cliente_sem_login` do `conftest.py`. Para acessar o banco, use `banco`.

## Front-end

Os testes do painel ficam em `testes_front/` e usam o executor de testes do Node.js (20 ou mais novo), sem instalar nada:

```bash
cd testes_front
node --test
```

Detalhes em [`testes_front/README.md`](../testes_front/README.md).

## Testes de segurança

Os scripts em `seguranca/testes/` são diferentes: chamam uma API em execução e não rodam com o `pytest`. Veja `seguranca/README.md`.
