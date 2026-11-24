"""Modelos de segurança integrados ao banco de dados principal do PlantSync."""

from models.contas import CodigoRecuperacaoConta, Conta, SessaoMfaConta

User = Conta
RecoveryCode = CodigoRecuperacaoConta
SessaoMfa = SessaoMfaConta

__all__ = ["Conta", "CodigoRecuperacaoConta", "SessaoMfaConta", "User", "RecoveryCode", "SessaoMfa"]
