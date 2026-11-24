"""
Teste de Proteção contra IDOR (Controle de Acesso Baseado em Posse / Empresa)
Alinhado à arquitetura multiempresa da API v1 do PlantSync (masterv2).
"""

import os
import sys
import requests
import re

BASE_URL = os.getenv("PLANTSYNC_API_URL", "http://localhost:8000")
MISSION_CODE = os.getenv("PLANTSYNC_CODIGO_MISSAO", "PENDENTE")

USER_A_NAME = "operador_alpha_idor"
USER_A_PASS = "SenhaAlpha#123456"
USER_A_EMAIL = "alpha@plantsync.teste"

USER_B_NAME = "operador_beta_idor"
USER_B_PASS = "SenhaBeta#123456"
USER_B_EMAIL = "beta@plantsync.teste"

COMPANY_A_NAME = "Empresa Alpha Agro"
COMPANY_B_NAME = "Empresa Beta Logistica"


class HttpClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        try:
            requests.get(f"{self.base_url}/api/saude", timeout=3)
        except requests.RequestException as exc:
            raise SystemExit(f"API indisponível em {self.base_url}; inicie o backend antes do teste: {exc}")

    def post(self, url: str, **kwargs):
        return requests.post(url, timeout=15, **kwargs)

    def get(self, url: str, **kwargs):
        return requests.get(url, timeout=15, **kwargs)

    def patch(self, url: str, **kwargs):
        return requests.patch(url, timeout=15, **kwargs)

    def delete(self, url: str, **kwargs):
        return requests.delete(url, timeout=15, **kwargs)


http = HttpClient(BASE_URL)


def get_db():
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
    from models.banco import SessaoLocal
    from models.contas import Conta, Empresa, VinculoConta
    from models.operacao import Ambiente, FonteSensor, LoteOperacional
    from services.acessos import configurar_senha
    return SessaoLocal, Conta, Empresa, VinculoConta, Ambiente, FonteSensor, LoteOperacional, configurar_senha


def preparar_ambiente_e_empresas():
    """Garante duas empresas distintas e dois usuários administradores no banco."""
    SessaoLocal, Conta, Empresa, VinculoConta, Ambiente, FonteSensor, LoteOperacional, configurar_senha = get_db()
    with SessaoLocal() as sessao:
        # Empresa A
        emp_a = sessao.query(Empresa).filter_by(nome=COMPANY_A_NAME).first()
        if not emp_a:
            emp_a = Empresa(nome=COMPANY_A_NAME, ativo=True)
            sessao.add(emp_a)
            sessao.flush()

        conta_a = sessao.query(Conta).filter_by(nome=USER_A_NAME).first()
        if not conta_a:
            conta_a = Conta(nome=USER_A_NAME, email=None, sal="", senha_hash="")
            configurar_senha(conta_a, USER_A_PASS)
            sessao.add(conta_a)
            sessao.flush()
        else:
            configurar_senha(conta_a, USER_A_PASS)
            conta_a.email = None

        vinc_a = sessao.query(VinculoConta).filter_by(conta_id=conta_a.id, empresa_id=emp_a.id).first()
        if not vinc_a:
            sessao.add(VinculoConta(conta_id=conta_a.id, empresa_id=emp_a.id, papel="administrador"))

        # Empresa B
        emp_b = sessao.query(Empresa).filter_by(nome=COMPANY_B_NAME).first()
        if not emp_b:
            emp_b = Empresa(nome=COMPANY_B_NAME, ativo=True)
            sessao.add(emp_b)
            sessao.flush()

        conta_b = sessao.query(Conta).filter_by(nome=USER_B_NAME).first()
        if not conta_b:
            conta_b = Conta(nome=USER_B_NAME, email=None, sal="", senha_hash="")
            configurar_senha(conta_b, USER_B_PASS)
            sessao.add(conta_b)
            sessao.flush()
        else:
            configurar_senha(conta_b, USER_B_PASS)
            conta_b.email = None

        vinc_b = sessao.query(VinculoConta).filter_by(conta_id=conta_b.id, empresa_id=emp_b.id).first()
        if not vinc_b:
            sessao.add(VinculoConta(conta_id=conta_b.id, empresa_id=emp_b.id, papel="administrador"))

        sessao.commit()
        return emp_a.id, emp_b.id


def headers(token: str, empresa_id: int) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "X-Empresa-ID": str(empresa_id),
        "Content-Type": "application/json",
    }


def run_tests():
    if not re.fullmatch(r"[A-Z0-9]{6}", MISSION_CODE) or MISSION_CODE == "PENDENTE":
        raise SystemExit("Defina PLANTSYNC_CODIGO_MISSAO com o código oficial de 6 caracteres antes de executar.")
    print(f"=== TESTE IDOR (ISOLAMENTO MULTIEMPRESA) | MISSAO: {MISSION_CODE} ===")

    empresa_a_id, empresa_b_id = preparar_ambiente_e_empresas()

    # Login Usuário A
    r_login_a = http.post(
        f"{BASE_URL}/api/v1/login",
        json={"usuario": USER_A_NAME, "senha": USER_A_PASS},
    )
    assert r_login_a.status_code == 200, f"Falha no login User A: {r_login_a.text}"
    token_user_a = r_login_a.json()["token"]
    h_user_a = headers(token_user_a, empresa_a_id)

    # Login Usuário B
    r_login_b = http.post(
        f"{BASE_URL}/api/v1/login",
        json={"usuario": USER_B_NAME, "senha": USER_B_PASS},
    )
    assert r_login_b.status_code == 200, f"Falha no login User B: {r_login_b.text}"
    token_user_b = r_login_b.json()["token"]
    h_user_b = headers(token_user_b, empresa_b_id)

    # Criação de recursos legítimos para a Empresa B
    # Ambiente B
    r_amb_b = http.post(
        f"{BASE_URL}/api/v1/ambientes",
        headers=h_user_b,
        json={"name": "Camara Fria Beta", "type": "camara"},
    )
    if r_amb_b.status_code == 201:
        amb_b_id = r_amb_b.json()["id"]
    else:
        ambs = http.get(f"{BASE_URL}/api/v1/ambientes", headers=h_user_b).json()
        amb_b_id = ambs[0]["id"]

    # Sensor B
    r_sen_b = http.post(
        f"{BASE_URL}/api/v1/sensores",
        headers=h_user_b,
        json={"name": "Sensor Beta 99", "type": "thingspeak", "channel": 998811},
    )
    if r_sen_b.status_code == 201:
        sensor_b_id = r_sen_b.json()["id"]
    else:
        sensors_b = http.get(f"{BASE_URL}/api/v1/sensores", headers=h_user_b).json()
        sensor_b_id = sensors_b[0]["id"]

    # Lote B
    codigo_lote_b = "PS-BETA99"
    r_lote_b = http.post(
        f"{BASE_URL}/api/v1/lotes",
        headers=h_user_b,
        json={
            "id": codigo_lote_b,
            "fruitId": "manga",
            "variety": "Tommy Atkins",
            "client": "Cliente Beta",
            "destination": "Porto de Suape",
            "destinationType": "exportacao",
            "environmentId": amb_b_id,
        },
    )
    if r_lote_b.status_code not in (201, 200, 409):
        print(f"[Aviso] Criacao lote B: {r_lote_b.status_code} - {r_lote_b.text}")

    # Criação de recursos legítimos para a Empresa A
    # Ambiente A
    r_amb_a = http.post(
        f"{BASE_URL}/api/v1/ambientes",
        headers=h_user_a,
        json={"name": "Camara Fria Alpha", "type": "camara"},
    )
    if r_amb_a.status_code == 201:
        amb_a_id = r_amb_a.json()["id"]
    else:
        ambs_a = http.get(f"{BASE_URL}/api/v1/ambientes", headers=h_user_a).json()
        amb_a_id = ambs_a[0]["id"]

    # Lote A
    codigo_lote_a = "PS-ALPH99"
    http.post(
        f"{BASE_URL}/api/v1/lotes",
        headers=h_user_a,
        json={
            "id": codigo_lote_a,
            "fruitId": "manga",
            "variety": "Tommy Atkins",
            "client": "Cliente Alpha",
            "destination": "Ceasa Recife",
            "destinationType": "mercado_interno",
            "environmentId": amb_a_id,
        },
    )

    print("\n--- CENÁRIOS DE TENTATIVAS DE ATAQUE IDOR ---")

    # 1. Usuário A tenta LER recurso (Lote) da Empresa B
    r_read = http.get(f"{BASE_URL}/api/v1/lotes/{codigo_lote_b}", headers=h_user_a)
    print(f"[1] User A -> GET /api/v1/lotes/{codigo_lote_b} (esperado: 403/404) -> {r_read.status_code}")
    assert r_read.status_code in (403, 404), f"IDOR falhou na leitura: {r_read.status_code}"

    # 2. Usuário A tenta ALTERAR configuração/dados do recurso da Empresa B
    r_patch = http.patch(
        f"{BASE_URL}/api/v1/lotes/{codigo_lote_b}",
        headers=h_user_a,
        json={"variety": "VariedadeInvasora"},
    )
    print(f"[2] User A -> PATCH /api/v1/lotes/{codigo_lote_b} (esperado: 403/404) -> {r_patch.status_code}")
    assert r_patch.status_code in (403, 404), f"IDOR falhou na alteração: {r_patch.status_code}"

    # 3. Usuário A tenta ENVIAR COMANDO operacional para o recurso da Empresa B
    r_cmd = http.post(
        f"{BASE_URL}/api/v1/lotes/{codigo_lote_b}/preparar",
        headers=h_user_a,
        json={"environmentId": amb_a_id},
    )
    print(f"[3] User A -> POST /api/v1/lotes/{codigo_lote_b}/preparar (esperado: 403/404) -> {r_cmd.status_code}")
    assert r_cmd.status_code in (403, 404), f"IDOR falhou no comando: {r_cmd.status_code}"

    # 4. Usuário A tenta VINCULAR sensor pertencente à Empresa B
    r_sensor_idor = http.post(
        f"{BASE_URL}/api/v1/sensores/{sensor_b_id}/vincular",
        headers=h_user_a,
        json={"environmentId": amb_a_id},
    )
    print(f"[4] User A -> POST /api/v1/sensores/{sensor_b_id}/vincular (esperado: 403/404) -> {r_sensor_idor.status_code}")
    assert r_sensor_idor.status_code in (403, 404), f"IDOR falhou no sensor: {r_sensor_idor.status_code}"

    # 5. Tentativa de contorno: enviar spoofing de empresa_id ou owner_id no payload
    r_spoof = http.patch(
        f"{BASE_URL}/api/v1/lotes/{codigo_lote_b}",
        headers=h_user_a,
        json={"variety": "Spoof", "empresa_id": empresa_b_id},
    )
    print(f"[5] Contorno - spoofing de empresa_id no payload (esperado: 400/403/404/422) -> {r_spoof.status_code}")
    assert r_spoof.status_code in (400, 403, 404, 422), f"Spoofing aceito indevidamente: {r_spoof.status_code}"

    # 6. Tentativa de contorno: forjar cabeçalho X-Empresa-ID para empresa de terceiros sem vínculo
    h_spoof_header = {"Authorization": f"Bearer {token_user_a}", "X-Empresa-ID": str(empresa_b_id)}
    r_spoof_header = http.get(f"{BASE_URL}/api/v1/contexto", headers=h_spoof_header)
    print(f"[6] Contorno - X-Empresa-ID forjado para outra empresa (esperado: 403) -> {r_spoof_header.status_code}")
    assert r_spoof_header.status_code == 403, f"Acesso indevido via header forjado: {r_spoof_header.status_code}"

    print("\n--- CENÁRIOS DE OPERAÇÃO LEGÍTIMA PELOS DONOS ---")

    # 7. Dono legítimo (User B) acessa o próprio lote normalmente
    r_owner_b = http.get(f"{BASE_URL}/api/v1/lotes/{codigo_lote_b}", headers=h_user_b)
    print(f"[7] Dono (User B) -> GET /api/v1/lotes/{codigo_lote_b} (esperado: 200) -> {r_owner_b.status_code}")
    assert r_owner_b.status_code == 200, f"Dono legítimo B bloqueado indevidamente: {r_owner_b.text}"

    # 8. Dono legítimo (User A) acessa o próprio lote normalmente
    r_own_a = http.get(f"{BASE_URL}/api/v1/lotes/{codigo_lote_a}", headers=h_user_a)
    print(f"[8] Dono (User A) -> GET /api/v1/lotes/{codigo_lote_a} (esperado: 200) -> {r_own_a.status_code}")
    assert r_own_a.status_code == 200, f"Dono legítimo A bloqueado indevidamente: {r_own_a.text}"

    # 9. Dono legítimo (User B) altera o próprio lote normalmente
    r_patch_b = http.patch(
        f"{BASE_URL}/api/v1/lotes/{codigo_lote_b}",
        headers=h_user_b,
        json={"variety": "Palmer Atualizada"},
    )
    print(f"[9] Dono (User B) -> PATCH /api/v1/lotes/{codigo_lote_b} (esperado: 200) -> {r_patch_b.status_code}")
    assert r_patch_b.status_code == 200, f"Dono B falhou ao alterar: {r_patch_b.text}"

    print("\n=== TODOS OS TESTES DE IDOR PASSARAM COM SUCESSO! ===")


if __name__ == "__main__":
    run_tests()
