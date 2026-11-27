"""
Teste de Autenticação de Dois Fatores (2FA com PyOTP + Códigos de Recuperação)
Alinhado às rotas reais da API v1 do PlantSync (masterv2).
"""

import os
import sys
import pyotp
import requests
import re

BASE_URL = os.getenv("PLANTSYNC_API_URL", "http://localhost:8000")
MISSION_CODE = os.getenv("PLANTSYNC_CODIGO_MISSAO", "PENDENTE")
# Os módulos da API (models/, services/) ficam em <raiz>/back_end/; assim o
# script roda de qualquer diretório, sem PYTHONPATH manual.
PASTA_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "back_end"))


# Usuário de teste exclusivo para 2FA
TEST_USER = "operador_2fa_teste"
TEST_PASS = "SenhaForte2FA#2026"
TEST_EMAIL = "operador_2fa@plantsync.teste"


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


def preparar_usuario_teste():
    """Garante a existência do usuário de teste associado a uma empresa ativa."""
    sys.path.insert(0, PASTA_BACKEND)
    from models.banco import SessaoLocal
    from models.contas import Conta, Empresa, VinculoConta
    from services.acessos import configurar_senha

    with SessaoLocal() as sessao:
        empresa = sessao.query(Empresa).filter_by(ativo=True).first()
        if not empresa:
            empresa = Empresa(nome="Empresa Teste 2FA", ativo=True)
            sessao.add(empresa)
            sessao.flush()

        conta = sessao.query(Conta).filter_by(nome=TEST_USER).first()
        if not conta:
            conta = Conta(nome=TEST_USER, email=None, sal="", senha_hash="")
            configurar_senha(conta, TEST_PASS)
            sessao.add(conta)
            sessao.flush()
        else:
            configurar_senha(conta, TEST_PASS)
            conta.email = None

        conta.totp_enabled = False
        conta.totp_secret_encrypted = None
        conta.totp_last_timestep = None

        vinculo = sessao.query(VinculoConta).filter_by(conta_id=conta.id, empresa_id=empresa.id).first()
        if not vinculo:
            vinculo = VinculoConta(conta_id=conta.id, empresa_id=empresa.id, papel="gestor")
            sessao.add(vinculo)

        sessao.commit()


def run_tests():
    if not re.fullmatch(r"[A-Z0-9]{6}", MISSION_CODE) or MISSION_CODE == "PENDENTE":
        raise SystemExit("Defina PLANTSYNC_CODIGO_MISSAO com o código oficial de 6 caracteres antes de executar.")
    print(f"=== TESTE 2FA (TOTP + RECOVERY) | MISSAO: {MISSION_CODE} ===")

    preparar_usuario_teste()

    # 1. Login inicial (modo ANTES: sem 2FA ativo, senha correta concede token direto)
    payload_login = {"usuario": TEST_USER, "senha": TEST_PASS}
    r_login = http.post(f"{BASE_URL}/api/v1/login", json=payload_login)
    print(f"[1] POST /api/v1/login -> Status: {r_login.status_code}")
    res_login = r_login.json()
    assert r_login.status_code == 200, f"Falha no login inicial: {res_login}"

    if "token" in res_login and not res_login.get("mfa_required"):
        print("[ANTES] Login com senha sem OTP aceito diretamente (2FA ainda desativado).")
        access_token_inicial = res_login["token"]
    else:
        access_token_inicial = res_login.get("token") or res_login.get("access_token")

    auth_header = {"Authorization": f"Bearer {access_token_inicial}"}

    # Ativação do 2FA
    # Setup de 2FA
    r_setup = http.post(f"{BASE_URL}/api/v1/2fa/setup", headers=auth_header)
    print(f"[Setup] POST /api/v1/2fa/setup -> Status: {r_setup.status_code}")
    assert r_setup.status_code == 200, f"Erro no setup 2FA: {r_setup.text}"
    setup_data = r_setup.json()
    provisioning_uri = setup_data["provisioning_uri"]
    recovery_codes = setup_data["recovery_codes"]
    print(f"[Setup] Provisioning URI obtida: {provisioning_uri[:35]}...")
    print(f"[Setup] Códigos de recuperação gerados: {len(recovery_codes)} códigos.")

    # Extrai o segredo TOTP da URI
    totp_obj = pyotp.parse_uri(provisioning_uri)
    totp_secret = totp_obj.secret

    # Confirmação do 2FA com código válido
    codigo_confirmacao = pyotp.TOTP(totp_secret).now()
    r_confirm = http.post(
        f"{BASE_URL}/api/v1/2fa/confirm",
        headers=auth_header,
        json={"otp_code": codigo_confirmacao},
    )
    print(f"[Confirm] POST /api/v1/2fa/confirm -> Status: {r_confirm.status_code}")
    assert r_confirm.status_code == 200, f"Erro na confirmação 2FA: {r_confirm.text}"
    print("[DEPOIS] 2FA ativado com sucesso para a conta de teste.")

    # 2. Login com 2FA ativo: senha correta não concede acesso direto sem OTP
    r_login_mfa = http.post(f"{BASE_URL}/api/v1/login", json=payload_login)
    print(f"[2a] POST /api/v1/login (com 2FA ativo) -> Status: {r_login_mfa.status_code}, mfa_required: {r_login_mfa.json().get('mfa_required')}")
    assert r_login_mfa.status_code == 200
    assert r_login_mfa.json().get("mfa_required") is True
    assert "token" not in r_login_mfa.json() or r_login_mfa.json().get("token") is None
    mfa_token = r_login_mfa.json()["mfa_token"]

    # Tentativa de verificação sem OTP
    r_sem_otp = http.post(
        f"{BASE_URL}/api/v1/2fa/verify-login",
        json={"mfa_token": mfa_token},
    )
    print(f"[2b] POST /api/v1/2fa/verify-login sem OTP (esperado 401) -> {r_sem_otp.status_code}")
    assert r_sem_otp.status_code == 401

    # 3. Código OTP incorreto -> deve ser recusado
    r_otp_errado = http.post(
        f"{BASE_URL}/api/v1/2fa/verify-login",
        json={"mfa_token": mfa_token, "otp_code": "000000"},
    )
    print(f"[3] POST /api/v1/2fa/verify-login OTP incorreto (esperado 401) -> {r_otp_errado.status_code}")
    assert r_otp_errado.status_code == 401

    # 4. Código OTP válido -> deve ser aceito
    totp = pyotp.TOTP(totp_secret)
    codigo_valido = totp.now()
    r_otp_ok = http.post(
        f"{BASE_URL}/api/v1/2fa/verify-login",
        json={"mfa_token": mfa_token, "otp_code": codigo_valido},
    )
    print(f"[4] POST /api/v1/2fa/verify-login OTP válido (esperado 200) -> {r_otp_ok.status_code}")
    assert r_otp_ok.status_code == 200
    assert "token" in r_otp_ok.json() or "access_token" in r_otp_ok.json()

    # 5. Tentativa de contorno / replay: reutilizar o mesmo código OTP já usado no mesmo ciclo
    r_login_2 = http.post(f"{BASE_URL}/api/v1/login", json=payload_login)
    mfa_token_2 = r_login_2.json().get("mfa_token")
    r_replay = http.post(
        f"{BASE_URL}/api/v1/2fa/verify-login",
        json={"mfa_token": mfa_token_2, "otp_code": codigo_valido},
    )
    print(f"[5] Contorno - reuso de OTP ja usado/replay (esperado 401) -> {r_replay.status_code}")
    assert r_replay.status_code == 401

    # 6. Tentativa de contorno: enviar mfa_token no lugar de access_token em rota protegida
    r_bypass = http.get(
        f"{BASE_URL}/api/v1/contexto",
        headers={"Authorization": f"Bearer {mfa_token_2}"},
    )
    print(f"[6] Contorno - usar mfa_token como access_token (esperado 401) -> {r_bypass.status_code}")
    assert r_bypass.status_code == 401

    # 7. Código de recuperação
    recovery_teste = recovery_codes[0]
    # 7a. 1o uso de recovery code válido -> sucesso
    r_rec_1 = http.post(
        f"{BASE_URL}/api/v1/2fa/verify-login",
        json={"mfa_token": mfa_token_2, "recovery_code": recovery_teste},
    )
    print(f"[7a] Recovery code 1o uso (esperado 200) -> {r_rec_1.status_code}")
    assert r_rec_1.status_code == 200

    # 7b. 2o uso do MESMO código de recuperação -> bloqueio
    r_login_3 = http.post(f"{BASE_URL}/api/v1/login", json=payload_login)
    mfa_token_3 = r_login_3.json().get("mfa_token")
    r_rec_2 = http.post(
        f"{BASE_URL}/api/v1/2fa/verify-login",
        json={"mfa_token": mfa_token_3, "recovery_code": recovery_teste},
    )
    print(f"[7b] Recovery code 2o uso / ja consumido (esperado 401) -> {r_rec_2.status_code}")
    assert r_rec_2.status_code == 401

    print("=== TODOS OS TESTES DE 2FA PASSARAM COM SUCESSO! ===")


if __name__ == "__main__":
    run_tests()
