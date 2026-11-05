# Peças compartilhadas pelos módulos: acesso ao banco e formatação de datas
from professor import DIAS_CURTOS

FORMATO_ISO = "%Y-%m-%dT%H:%M:%S"


def iso(data_hora):
    return data_hora.strftime(FORMATO_ISO) if data_hora else None


def rotulo_data(data_hora):
    if not data_hora:
        return None
    return f"{DIAS_CURTOS[data_hora.weekday()]} {data_hora:%d/%m} · {data_hora:%H:%M}"


class RepositorioBase:
    def __init__(self, db):
        self.db = db

    def _consultar(self, sql, params=(), um=False):
        conexao = self.db.conectar()
        try:
            with conexao.cursor() as cursor:
                cursor.execute(sql, params)
                return cursor.fetchone() if um else cursor.fetchall()
        finally:
            conexao.close()
