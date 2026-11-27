"""
Evidência do ANTES do controle de IDOR.

Executa exatamente os mesmos cenários de test_idor.py (importados de lá), mas
sem falhar quando um ataque passa: para cada tentativa cruzada registra se a
API ACEITOU ou BLOQUEOU a requisição.

Serve para mostrar o comportamento da API quando a checagem de posse/empresa
está desativada. Essa desativação é um patch LOCAL e TEMPORÁRIO, aplicado só
para capturar a evidência e revertido em seguida; ele nunca vai para o Git.
O procedimento está em seguranca/README.md.

Contra a API normal (controle ativo), este script mostra todas as tentativas
como BLOQUEADAS.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import test_idor as base  # noqa: E402


def resumo(resposta) -> str:
    """Trecho curto da resposta, para mostrar o que o atacante recebeu."""
    texto = " ".join(resposta.text.split())
    return texto if len(texto) <= 160 else texto[:157] + "..."


def main():
    base.validar_codigo_missao()
    print(f"=== TESTE IDOR - ANTES DO CONTROLE (checagem de posse desativada) | MISSAO: {base.MISSION_CODE} ===")
    print("'esperado' indica a resposta correta com o controle ativo.")
    cenario = base.preparar_cenario()

    print("\n--- CENÁRIOS DE TENTATIVAS DE ATAQUE IDOR ---")
    ataques = base.cenarios_ataque(cenario)
    aceitos = 0
    for rotulo, bloqueio, _, requisicao in ataques:
        resposta = requisicao()
        if resposta.status_code in bloqueio:
            print(f"{rotulo} -> {resposta.status_code} | BLOQUEADO")
        else:
            aceitos += 1
            print(f"{rotulo} -> {resposta.status_code} | ACEITO (vulnerável)")
            print(f"    resposta: {resumo(resposta)}")

    print("\n--- CENÁRIOS DE OPERAÇÃO LEGÍTIMA PELOS DONOS ---")
    for rotulo, _, _, requisicao in base.cenarios_legitimos(cenario):
        print(f"{rotulo} -> {requisicao().status_code}")

    print(f"\n=== RESULTADO ANTES: {aceitos} de {len(ataques)} tentativas cruzadas foram ACEITAS ===")


if __name__ == "__main__":
    main()
