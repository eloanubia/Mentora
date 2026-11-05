# Token (JWT) e Autenticacao (proteção de rotas)
#   requer_login -> 401 se não houver token válido; guarda g.id_usuario
#   requer_admin -> 401 sem login, 403 se a conta não for do tipo 'admin'
#                   (o tipo é conferido NO BANCO a cada pedido, então promover/rebaixar
#                    um admin vale na hora, sem precisar sair e entrar de novo)
import os
import time
from functools import wraps

import jwt
from flask import g, request

from erros import ErroApi


class Token:
    def __init__(self):
        self.segredo = os.getenv("JWT_SECRET")
        if not self.segredo:
            raise RuntimeError("Defina JWT_SECRET no arquivo .env")
        self.horas = int(os.getenv("JWT_HORAS", "12"))

    def gerar(self, id_usuario):
        agora = int(time.time())
        return jwt.encode(
            {"sub": str(id_usuario), "iat": agora, "exp": agora + self.horas * 3600},
            self.segredo, algorithm="HS256")

    def ler(self, token):
        # devolve o id do usuário ou lança ErroApi 401
        try:
            dados = jwt.decode(token, self.segredo, algorithms=["HS256"])
            return int(dados["sub"])
        except (jwt.PyJWTError, KeyError, ValueError):
            raise ErroApi("Sessão inválida ou expirada. Entre novamente.", 401)


class Autenticacao:
    def __init__(self, token, db=None):
        self.token = token
        self.db = db

    def _id_do_pedido(self):
        cabecalho = request.headers.get("Authorization", "")
        partes = cabecalho.split()
        if len(partes) != 2 or partes[0].lower() != "bearer":
            raise ErroApi("Faça login para continuar.", 401)
        return self.token.ler(partes[1])

    def _tipo_no_banco(self, id_usuario):
        conexao = self.db.conectar()
        try:
            with conexao.cursor() as cur:
                cur.execute("SELECT tipo FROM usuario WHERE id_usuario = %s", (id_usuario,))
                linha = cur.fetchone()
                return linha["tipo"] if linha else None
        finally:
            conexao.close()

    def requer_login(self, funcao):
        @wraps(funcao)
        def protegida(*args, **kwargs):
            g.id_usuario = self._id_do_pedido()
            return funcao(*args, **kwargs)
        return protegida

    def requer_admin(self, funcao):
        @wraps(funcao)
        def protegida(*args, **kwargs):
            g.id_usuario = self._id_do_pedido()
            tipo = self._tipo_no_banco(g.id_usuario)
            if tipo is None:
                raise ErroApi("Sessão inválida ou expirada. Entre novamente.", 401)
            if tipo != "admin":
                raise ErroApi("Acesso restrito a administradores.", 403)
            return funcao(*args, **kwargs)
        return protegida
