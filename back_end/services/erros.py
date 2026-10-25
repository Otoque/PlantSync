"""
Erros que os services levantam quando uma regra nao e cumprida.

O app.py transforma cada um na resposta HTTP certa, entao as rotas
nao precisam de try/except:
    ErroDeRegra    -> 400 (dado invalido ou regra de negocio)
    NaoEncontrado  -> 404 (lote ou fruta que nao existe)
"""


class ErroDeRegra(Exception):
    pass


class NaoEncontrado(Exception):
    pass
