# DisciplinaRepository  - acesso ao banco
# DisciplinaService     - regras de negócio
# DisciplinaController  - endpoints HTTP
from flask import Blueprint, jsonify


class DisciplinaRepository:
    def __init__(self, db):
        self.db = db

    def listar(self):
        conexao = self.db.conectar()
        try:
            with conexao.cursor() as cursor:
                cursor.execute(
                    "SELECT id_disciplina, nome, descricao FROM disciplina ORDER BY nome"
                )
                return cursor.fetchall()
        finally:
            conexao.close()


class DisciplinaService:
    def __init__(self, repositorio):
        self.repositorio = repositorio

    def listar(self):
        return [
            {"id": l["id_disciplina"], "nome": l["nome"], "descricao": l["descricao"]}
            for l in self.repositorio.listar()
        ]


class DisciplinaController:
    def __init__(self, service):
        self.service = service
        self.bp = Blueprint("disciplinas", __name__)
        self.bp.add_url_rule("/api/disciplinas", view_func=self.listar, methods=["GET"])

    def listar(self):
        return jsonify(self.service.listar()), 200
