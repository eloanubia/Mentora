# NotificacaoRepository / NotificacaoService / NotificacaoController
# Vale para qualquer usuário logado (aluno ou professor).
from datetime import datetime

from flask import Blueprint, g, jsonify, request

from base import RepositorioBase, iso
from erros import ErroApi


class NotificacaoRepository(RepositorioBase):
    def listar(self, id_usuario, limite):
        return self._consultar(
            """SELECT id_notificacao, texto, lida, data_criacao FROM notificacao
               WHERE id_usuario = %s ORDER BY data_criacao DESC, id_notificacao DESC LIMIT %s""",
            (id_usuario, limite))

    def contar_nao_lidas(self, id_usuario):
        return self._consultar(
            "SELECT COUNT(*) AS total FROM notificacao WHERE id_usuario = %s AND lida = FALSE",
            (id_usuario,), um=True)["total"]

    def existe(self, id_notificacao, id_usuario):
        return self._consultar(
            "SELECT 1 FROM notificacao WHERE id_notificacao = %s AND id_usuario = %s",
            (id_notificacao, id_usuario), um=True) is not None

    def _atualizar(self, sql, params):
        conexao = self.db.conectar()
        try:
            with conexao.cursor() as cursor:
                cursor.execute(sql, params)
            conexao.commit()
        finally:
            conexao.close()

    def marcar_lida(self, id_notificacao, id_usuario):
        self._atualizar(
            "UPDATE notificacao SET lida = TRUE WHERE id_notificacao = %s AND id_usuario = %s",
            (id_notificacao, id_usuario))

    def marcar_todas(self, id_usuario):
        self._atualizar("UPDATE notificacao SET lida = TRUE WHERE id_usuario = %s", (id_usuario,))


class NotificacaoService:
    LIMITE_PADRAO = 50
    LIMITE_MAX = 100

    def __init__(self, repositorio):
        self.repositorio = repositorio

    @staticmethod
    def _quando(data, agora):
        if not data:
            return None
        hora = data.strftime("%H:%M")
        dias = (agora.date() - data.date()).days
        if dias == 0:
            return f"Hoje · {hora}"
        if dias == 1:
            return f"Ontem · {hora}"
        return f"{data:%d/%m} · {hora}"

    def listar(self, id_usuario, limite=None, agora=None):
        agora = agora or datetime.now()
        if limite in (None, ""):
            limite = self.LIMITE_PADRAO
        else:
            try:
                limite = max(1, min(int(limite), self.LIMITE_MAX))
            except ValueError:
                raise ErroApi("limit deve ser um número inteiro", 400)
        itens = [
            {"id": n["id_notificacao"], "texto": n["texto"], "lida": bool(n["lida"]),
             "data": iso(n["data_criacao"]), "quando": self._quando(n["data_criacao"], agora)}
            for n in self.repositorio.listar(id_usuario, limite)
        ]
        return {"nao_lidas": self.repositorio.contar_nao_lidas(id_usuario), "itens": itens}

    def marcar_lida(self, id_usuario, id_notificacao):
        if not self.repositorio.existe(id_notificacao, id_usuario):
            raise ErroApi("Notificação não encontrada", 404)
        self.repositorio.marcar_lida(id_notificacao, id_usuario)

    def marcar_todas(self, id_usuario):
        self.repositorio.marcar_todas(id_usuario)


class NotificacaoController:
    def __init__(self, service, autenticacao):
        self.service = service
        self.bp = Blueprint("notificacoes", __name__)
        protegida = autenticacao.requer_login
        self.bp.add_url_rule("/api/notificacoes", view_func=protegida(self.listar), methods=["GET"])
        self.bp.add_url_rule("/api/notificacoes/lidas", view_func=protegida(self.marcar_todas),
                             methods=["POST"])
        self.bp.add_url_rule("/api/notificacoes/<int:id_notificacao>/lida",
                             view_func=protegida(self.marcar_lida), methods=["POST"])

    def listar(self):
        return jsonify(self.service.listar(g.id_usuario, request.args.get("limit"))), 200

    def marcar_lida(self, id_notificacao):
        self.service.marcar_lida(g.id_usuario, id_notificacao)
        return jsonify({"mensagem": "Notificação marcada como lida"}), 200

    def marcar_todas(self):
        self.service.marcar_todas(g.id_usuario)
        return jsonify({"mensagem": "Todas as notificações foram marcadas como lidas"}), 200
