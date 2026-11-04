"""Limites fisicos usados tanto na validacao das entradas quanto na analise."""

# Faixa fisica do sensor: fora dela a leitura e defeito, nao fenomeno.
# O firmware e o pipeline analitico tambem descartam esses valores.
TEMP_FISICA_MIN = -40.0
TEMP_FISICA_MAX = 80.0
