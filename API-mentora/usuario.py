# UsuarioRepository / UsuarioService / UsuarioController
#   POST /api/cadastro (ou /api/usuarios)  {nome, email, senha} -> 201 {usuario, token}
#   POST /api/login                         {email, senha}       -> 200 {usuario, token}
#   GET  /api/me                            -> dados do usuário logado (inclui "tipo")
#   PUT  /api/me                            {nome, telefone, data_nascimento}
import re
from datetime import date

import bcrypt
import pymysql
from flask import Blueprint, g, jsonify, request

from base import RepositorioBase
from erros import ErroApi

EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
SENHA_MIN, SENHA_MAX_BYTES = 8, 72  # o bcrypt só lê os 72 primeiros bytes
# usado quando o e-mail não existe, para o login levar o mesmo tempo nos dois casos
HASH_FALSO = bcrypt.hashpw(b"mentora-hash-falso", bcrypt.gensalt())


def _texto(valor, campo, obrigatorio=True, maximo=100):
    if valor is None or valor == "":
        if obrigatorio:
            raise ErroApi(f"Informe {campo}", 400)
        return None
    if not isinstance(valor, str):
        raise ErroApi(f"{campo} deve ser um texto", 400)
    valor = valor.strip()
    if obrigatorio and not valor:
        raise ErroApi(f"Informe {campo}", 400)
    if len(valor) > maximo:
        raise ErroApi(f"{campo} deve ter no máximo {maximo} caracteres", 400)
    return valor or None


# ---------- REPOSITÓRIO ----------
class UsuarioRepository(RepositorioBase):
    CAMPOS = "id_usuario, nome, email, telefone, data_nascimento, foto, tipo"

    def por_email(self, email):
        return self._consultar("SELECT id_usuario, nome, email, senha, tipo FROM usuario WHERE email = %s",
                               (email,), um=True)

    def por_id(self, id_usuario):
        return self._consultar(f"SELECT {self.CAMPOS} FROM usuario WHERE id_usuario = %s",
                               (id_usuario,), um=True)

    def criar(self, nome, email, senha_hash):
        conexao = self.db.conectar()
        try:
            with conexao.cursor() as cur:
                cur.execute("INSERT INTO usuario (nome, email, senha) VALUES (%s, %s, %s)",
                            (nome, email, senha_hash))
                novo = cur.lastrowid
            conexao.commit()
            return novo
        except pymysql.err.IntegrityError:
            conexao.rollback()
            raise ErroApi("Este e-mail já está cadastrado", 409)
        except pymysql.MySQLError:
            conexao.rollback()
            raise
        finally:
            conexao.close()

    def atualizar(self, id_usuario, nome, telefone, nascimento):
        conexao = self.db.conectar()
        try:
            with conexao.cursor() as cur:
                cur.execute("UPDATE usuario SET nome = %s, telefone = %s, data_nascimento = %s "
                            "WHERE id_usuario = %s", (nome, telefone, nascimento, id_usuario))
            conexao.commit()
        except pymysql.MySQLError:
            conexao.rollback()
            raise
        finally:
            conexao.close()


# ---------- SERVIÇO ----------
class UsuarioService:
    def __init__(self, repositorio, token):
        self.repositorio = repositorio
        self.token = token

    @staticmethod
    def _publico(u):
        nasc = u.get("data_nascimento")
        return {"id": u["id_usuario"], "nome": u["nome"], "email": u["email"], "tipo": u["tipo"],
                "telefone": u.get("telefone"), "foto": u.get("foto"),
                "data_nascimento": nasc.isoformat() if nasc else None}

    def cadastrar(self, dados):
        nome = _texto(dados.get("nome"), "o nome")
        email = _texto(dados.get("email"), "o e-mail", maximo=150).lower()
        senha = dados.get("senha")
        if not EMAIL.match(email):
            raise ErroApi("E-mail inválido", 400)
        if not isinstance(senha, str) or len(senha) < SENHA_MIN:
            raise ErroApi(f"A senha deve ter pelo menos {SENHA_MIN} caracteres", 400)
        if len(senha.encode("utf-8")) > SENHA_MAX_BYTES:
            raise ErroApi("A senha é longa demais (máximo de 72 bytes)", 400)
        senha_hash = bcrypt.hashpw(senha.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        novo = self.repositorio.criar(nome, email, senha_hash)
        usuario = self._publico(self.repositorio.por_id(novo))
        return {"usuario": usuario, "token": self.token.gerar(novo)}

    def entrar(self, dados):
        email = dados.get("email")
        senha = dados.get("senha")
        if not isinstance(email, str) or not isinstance(senha, str) or not email.strip() or not senha:
            raise ErroApi("Informe e-mail e senha", 400)
        u = self.repositorio.por_email(email.strip().lower())
        hash_banco = (u["senha"] if u else "").encode("utf-8")
        try:
            confere = bcrypt.checkpw(senha.encode("utf-8")[:SENHA_MAX_BYTES],
                                     hash_banco if u else HASH_FALSO)
        except ValueError:  # hash inválido no banco (ex.: dados de exemplo)
            confere = False
        if not u or not confere:
            raise ErroApi("E-mail ou senha incorretos", 401)
        return {"usuario": self._publico(self.repositorio.por_id(u["id_usuario"])),
                "token": self.token.gerar(u["id_usuario"])}

    def meu_usuario(self, id_usuario):
        u = self.repositorio.por_id(id_usuario)
        if not u:
            raise ErroApi("Usuário não encontrado", 404)
        return self._publico(u)

    def atualizar(self, id_usuario, dados):
        atual = self.repositorio.por_id(id_usuario)
        if not atual:
            raise ErroApi("Usuário não encontrado", 404)
        nome = _texto(dados.get("nome", atual["nome"]), "o nome")
        telefone = _texto(dados.get("telefone", atual["telefone"]), "o telefone", False, 20)
        nasc = dados.get("data_nascimento", atual["data_nascimento"])
        if isinstance(nasc, date):
            nasc = nasc.isoformat()
        nasc = _texto(nasc, "a data de nascimento", False, 10)
        if nasc:
            try:
                if date.fromisoformat(nasc) > date.today():
                    raise ValueError
            except ValueError:
                raise ErroApi("Data de nascimento inválida (use AAAA-MM-DD)", 400)
        self.repositorio.atualizar(id_usuario, nome, telefone, nasc)
        return self.meu_usuario(id_usuario)


# ---------- CONTROLLER ----------
class UsuarioController:
    def __init__(self, service, autenticacao):
        self.service = service
        self.bp = Blueprint("usuario", __name__)
        # /api/cadastro é o que o site usa; /api/usuarios é um apelido (mesma função)
        self.bp.add_url_rule("/api/cadastro", "cadastro", self.cadastrar, methods=["POST"])
        self.bp.add_url_rule("/api/usuarios", "usuarios", self.cadastrar, methods=["POST"])
        self.bp.add_url_rule("/api/login", view_func=self.entrar, methods=["POST"])
        self.bp.add_url_rule("/api/me", "me_ver", autenticacao.requer_login(self.me), methods=["GET"])
        self.bp.add_url_rule("/api/me", "me_atualizar",
                             autenticacao.requer_login(self.atualizar_me), methods=["PUT"])

    @staticmethod
    def _json():
        dados = request.get_json(silent=True)
        return dados if isinstance(dados, dict) else {}

    def cadastrar(self):
        return jsonify(self.service.cadastrar(self._json())), 201

    def entrar(self):
        return jsonify(self.service.entrar(self._json())), 200

    def me(self):
        return jsonify(self.service.meu_usuario(g.id_usuario)), 200

    def atualizar_me(self):
        return jsonify(self.service.atualizar(g.id_usuario, self._json())), 200
