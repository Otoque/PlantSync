"""
Erros que os services levantam quando uma regra falha ou algo nao funciona.

O app.py transforma cada um na resposta HTTP certa, entao as rotas
nao precisam de try/except:
    ErroDeRegra        -> 400 (dado invalido ou regra de negocio)
    ErroNaoAutenticado -> 401 (sem login valido)
    ErroNaoEncontrado  -> 404 (lote ou fruta que nao existe)
    ErroThingSpeak     -> 502 (o ThingSpeak nao respondeu)
"""


class ErroDeRegra(Exception):
    pass


class ErroNaoAutenticado(Exception):
    pass


class ErroNaoEncontrado(Exception):
    pass


class ErroThingSpeak(Exception):
    pass
