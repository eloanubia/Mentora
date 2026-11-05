# AdminRepository / AdminService / AdminController  (só para usuários com tipo = 'admin')
#
# O que o administrador faz aqui:
#   1) lista os candidatos a professor (filtrando por status)
#   2) abre UM candidato e vê todos os dados do cadastro + verificação automática
#   3) vê o comprovante de formação enviado
#   4) aprova (status 'ativo'), recusa (com motivo), desativa ou reabre a análise
import re

import pymysql
from flask import Blueprint, jsonify, request, send_from_directory

from base import RepositorioBase
from erros import ErroApi
from professor import Horarios

STATUS_VALIDOS = ("pendente", "ativo", "recusado", "inativo")
NOME_COMPROVANTE = re.compile(r"^[0-9a-f]{32}\.(jpg|png|pdf)$")
MOTIVO_MAX = 200  # o motivo vai dentro da notificação do professor, então não pode ser enorme


# ---------- REPOSITÓRIO: só conversa com o banco ----------
class AdminRepository(RepositorioBase):
    def listar(self, status):
        sql = """SELECT p.id_professor, u.nome, u.email, p.formacao, p.descricao, p.status,
                        p.comprovante IS NOT NULL AS tem_comprovante
                 FROM perfil_professor p JOIN usuario u ON u.id_usuario = p.id_usuario"""
        params = ()
        if status:
            sql += " WHERE p.status = %s"
            params = (status,)
        return self._consultar(sql + " ORDER BY p.id_professor", params)

    # NOVO: todos os dados de um candidato (a tela de análise usa isto)
    def detalhe(self, id_professor):
        return self._consultar(
            """SELECT p.id_professor, u.nome, u.email, u.foto, p.formacao, p.descricao,
                      p.experiencia, p.modalidade, p.status, p.comprovante
               FROM perfil_professor p JOIN usuario u ON u.id_usuario = p.id_usuario
               WHERE p.id_professor = %s""", (id_professor,), um=True)

    # NOVO: disciplinas (com o preço de cada uma) que o candidato quer ensinar
    def disciplinas(self, id_professor):
        return self._consultar(
            """SELECT d.id_disciplina, d.nome, pd.preco FROM professor_disciplina pd
               JOIN disciplina d ON d.id_disciplina = pd.id_disciplina
               WHERE pd.id_professor = %s ORDER BY d.nome""", (id_professor,))

    # NOVO: dias e horários em que o candidato diz estar disponível
    def disponibilidade(self, id_professor):
        return self._consultar(
            "SELECT dia_semana, hora_inicio, hora_fim FROM disponibilidade WHERE id_professor = %s",
            (id_professor,))

    def comprovante(self, id_professor):
        linha = self._consultar(
            "SELECT comprovante FROM perfil_professor WHERE id_professor = %s",
            (id_professor,), um=True)
        return linha["comprovante"] if linha else None

    def alterar_status(self, id_professor, novo, texto, validar):
        # "validar" recebe o status ATUAL (lido com o registro travado) e lança ErroApi se a
        # mudança não for permitida. Assim dois cliques seguidos não geram duas notificações.
        conexao = self.db.conectar()
        try:
            with conexao.cursor() as cur:
                cur.execute("SELECT id_usuario, status FROM perfil_professor WHERE id_professor = %s FOR UPDATE",
                            (id_professor,))
                professor = cur.fetchone()
                if not professor:
                    return False
                validar(professor["status"])
                cur.execute("UPDATE perfil_professor SET status = %s WHERE id_professor = %s",
                            (novo, id_professor))
                cur.execute("INSERT INTO notificacao (id_usuario, texto) VALUES (%s, %s)",
                            (professor["id_usuario"], texto))
            conexao.commit()
            return True
        except (pymysql.MySQLError, ErroApi):
            conexao.rollback()
            raise
        finally:
            conexao.close()


# ---------- SERVIÇO: regras de negócio ----------
class AdminService:
    AVISOS = {
        "ativo": "Seu perfil foi aprovado! Você já aparece nas buscas dos alunos.",
        "recusado": "Seu perfil não foi aprovado. Revise seus dados e documentos.",
        "inativo": "Seu perfil foi desativado.",
        "pendente": "Seu perfil voltou para análise.",
    }
    # NOVO: de quais status atuais cada mudança é permitida (a API não depende só da tela)
    #   aprovar/reativar: pendente ou inativo -> ativo | recusar: só pendente
    #   desativar: só ativo | reabrir análise: qualquer um que não seja pendente
    TRANSICOES = {
        "ativo": ("pendente", "inativo"),
        "recusado": ("pendente",),
        "inativo": ("ativo",),
        "pendente": ("ativo", "recusado", "inativo"),
    }
    # limites usados na verificação automática (ajuste como a Mentora preferir)
    PRECO_MIN, PRECO_MAX = 30, 300
    MAX_DISCIPLINAS = 4

    def __init__(self, repositorio):
        self.repositorio = repositorio

    def listar(self, status):
        if status and status not in STATUS_VALIDOS:
            raise ErroApi("status inválido", 400)
        return [{
            "id": p["id_professor"], "nome": p["nome"], "email": p["email"],
            "formacao": p["formacao"], "descricao": p["descricao"], "status": p["status"],
            "tem_comprovante": bool(p["tem_comprovante"]),
        } for p in self.repositorio.listar(status)]

    # NOVO: monta a ficha completa do candidato, já com a verificação automática
    def obter(self, id_professor):
        p = self.repositorio.detalhe(id_professor)
        if not p:
            raise ErroApi("Professor não encontrado", 404)

        disciplinas = [{"id": d["id_disciplina"], "nome": d["nome"], "preco": float(d["preco"])}
                       for d in self.repositorio.disciplinas(id_professor)]

        faixas = []
        for f in self.repositorio.disponibilidade(id_professor):
            dia = Horarios.indice_do_dia(f["dia_semana"])
            ini, fim = Horarios._hora(f["hora_inicio"]), Horarios._hora(f["hora_fim"])
            if dia is not None and ini and fim:
                faixas.append((dia, f["dia_semana"], ini.strftime("%H:%M"), fim.strftime("%H:%M")))
        faixas.sort()  # ordena de segunda a domingo
        disponibilidade = [{"dia_semana": d, "hora_inicio": i, "hora_fim": f} for _, d, i, f in faixas]

        return {
            "id": p["id_professor"], "nome": p["nome"], "email": p["email"], "foto": p["foto"],
            "formacao": p["formacao"], "descricao": p["descricao"], "experiencia": p["experiencia"],
            "modalidade": p["modalidade"], "status": p["status"],
            "tem_comprovante": bool(p["comprovante"]),
            "disciplinas": disciplinas, "disponibilidade": disponibilidade,
            "verificacoes": self._verificar(p, disciplinas, disponibilidade),
        }

    # NOVO: checagens automáticas. Elas AJUDAM o admin, mas quem decide é ele.
    def _verificar(self, p, disciplinas, disponibilidade):
        precos = [d["preco"] for d in disciplinas]
        precos_ok = bool(precos) and all(self.PRECO_MIN <= x <= self.PRECO_MAX for x in precos)
        return [
            {"ok": bool(p["comprovante"]), "texto": "Comprovante de formação anexado"},
            {"ok": len((p["formacao"] or "").strip()) >= 10,
             "texto": "Formação acadêmica informada com detalhes"},
            {"ok": len((p["descricao"] or "").strip()) >= 50,
             "texto": "Apresentação com pelo menos 50 caracteres"},
            {"ok": precos_ok,
             "texto": f"Preço de cada aula entre R$ {self.PRECO_MIN} e R$ {self.PRECO_MAX} por hora"},
            {"ok": 1 <= len(disciplinas) <= self.MAX_DISCIPLINAS,
             "texto": f"Quantidade de disciplinas razoável (1 a {self.MAX_DISCIPLINAS}) — "
                      f"informado: {len(disciplinas)}"},
            {"ok": len(disponibilidade) > 0, "texto": "Disponibilidade informada"},
            {"ok": bool(p["foto"]), "texto": "Foto de perfil enviada"},
        ]

    def alterar_status(self, id_professor, dados):
        novo = dados.get("status")
        novo = novo.strip() if isinstance(novo, str) else ""
        if novo not in STATUS_VALIDOS:
            raise ErroApi("status deve ser: " + ", ".join(STATUS_VALIDOS), 400)

        texto = self.AVISOS[novo]
        motivo = dados.get("motivo")
        if motivo is not None and not isinstance(motivo, str):
            raise ErroApi("motivo deve ser um texto", 400)
        motivo = (motivo or "").strip()
        if novo == "recusado":
            # NOVO: recusar exige motivo, e o professor recebe o motivo na notificação
            if not motivo:
                raise ErroApi("Informe o motivo da recusa", 400)
            if len(motivo) > MOTIVO_MAX:
                raise ErroApi(f"O motivo deve ter no máximo {MOTIVO_MAX} caracteres", 400)
            texto += " Motivo: " + motivo

        def validar(atual):
            if atual == novo:
                raise ErroApi("O professor já está com esse status", 409)
            if atual not in self.TRANSICOES[novo]:
                raise ErroApi(f"Não é possível mudar de '{atual}' para '{novo}'", 409)

        if not self.repositorio.alterar_status(id_professor, novo, texto, validar):
            raise ErroApi("Professor não encontrado", 404)
        return {"id": id_professor, "status": novo}

    def nome_do_comprovante(self, id_professor):
        nome = self.repositorio.comprovante(id_professor)
        if not nome or not NOME_COMPROVANTE.match(nome):
            raise ErroApi("Comprovante não encontrado", 404)
        return nome


# ---------- CONTROLLER: endpoints HTTP ----------
class AdminController:
    def __init__(self, service, autenticacao, arquivos):
        self.service = service
        self.arquivos = arquivos
        self.bp = Blueprint("admin", __name__)
        so_admin = autenticacao.requer_admin
        self.bp.add_url_rule("/api/admin/professores", view_func=so_admin(self.listar), methods=["GET"])
        # NOVO: ficha completa de um candidato
        self.bp.add_url_rule("/api/admin/professores/<int:id_professor>",
                             view_func=so_admin(self.obter), methods=["GET"])
        self.bp.add_url_rule("/api/admin/professores/<int:id_professor>",
                             view_func=so_admin(self.alterar), methods=["PATCH"])
        self.bp.add_url_rule("/api/admin/professores/<int:id_professor>/comprovante",
                             view_func=so_admin(self.comprovante), methods=["GET"])

    def listar(self):
        return jsonify(self.service.listar(request.args.get("status"))), 200

    def obter(self, id_professor):
        return jsonify(self.service.obter(id_professor)), 200

    def alterar(self, id_professor):
        dados = request.get_json(silent=True)
        if not isinstance(dados, dict):
            dados = {}
        return jsonify(self.service.alterar_status(id_professor, dados)), 200

    def comprovante(self, id_professor):
        nome = self.service.nome_do_comprovante(id_professor)
        return send_from_directory(self.arquivos.pasta("comprovantes"), nome)
