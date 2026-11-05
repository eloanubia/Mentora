# AreaProfessorRepository / AreaProfessorService / AreaProfessorController
# Tudo aqui exige login E que o usuário tenha perfil de professor.
import secrets
from datetime import datetime, timedelta

import pymysql
from flask import Blueprint, g, jsonify

from base import RepositorioBase, iso, rotulo_data
from erros import ErroApi


def _float(valor):
    return float(valor) if valor is not None else None


# ---------- REPOSITÓRIO ----------
class AreaProfessorRepository(RepositorioBase):
    def perfil_do_usuario(self, id_usuario):
        return self._consultar(
            "SELECT id_professor, status FROM perfil_professor WHERE id_usuario = %s",
            (id_usuario,), um=True)

    def listar_pedidos(self, id_professor):
        return self._consultar(
            """SELECT s.id_solicitacao, s.status, s.data_hora_solicitada, s.data_solicitacao,
                      ua.nome AS aluno, d.nome AS disciplina, pd.preco
               FROM solicitacao_aula s
               JOIN usuario ua ON ua.id_usuario = s.id_usuario_aluno
               JOIN disciplina d ON d.id_disciplina = s.id_disciplina
               LEFT JOIN professor_disciplina pd
                      ON pd.id_professor = s.id_professor AND pd.id_disciplina = s.id_disciplina
               WHERE s.id_professor = %s
               ORDER BY (s.status = 'pendente') DESC, s.data_solicitacao DESC, s.id_solicitacao DESC""",
            (id_professor,))

    def responder(self, id_solicitacao, id_professor, aceitar, agora):
        # Tudo numa transação. Devolve (codigo, dados).
        # O perfil do professor é travado: dois aceites ao mesmo tempo não ocupam o mesmo horário.
        conexao = self.db.conectar()
        try:
            with conexao.cursor() as cur:
                cur.execute("SELECT id_professor FROM perfil_professor WHERE id_professor = %s FOR UPDATE",
                            (id_professor,))
                cur.execute(
                    """SELECT id_usuario_aluno, id_disciplina, data_hora_solicitada, status
                       FROM solicitacao_aula
                       WHERE id_solicitacao = %s AND id_professor = %s FOR UPDATE""",
                    (id_solicitacao, id_professor))
                sol = cur.fetchone()
                if not sol:
                    return "nao_encontrada", None
                if sol["status"] != "pendente":
                    return "ja_respondida", None

                cur.execute(
                    """SELECT ua.nome AS aluno, up.nome AS professor, d.nome AS disciplina
                       FROM usuario ua CROSS JOIN perfil_professor pr
                            JOIN usuario up ON up.id_usuario = pr.id_usuario
                            CROSS JOIN disciplina d
                       WHERE ua.id_usuario = %s AND pr.id_professor = %s AND d.id_disciplina = %s""",
                    (sol["id_usuario_aluno"], id_professor, sol["id_disciplina"]))
                nomes = cur.fetchone()

                if not aceitar:
                    cur.execute("UPDATE solicitacao_aula SET status = 'recusada' WHERE id_solicitacao = %s",
                                (id_solicitacao,))
                    cur.execute(
                        "INSERT INTO notificacao (id_usuario, texto) VALUES (%s, %s)",
                        (sol["id_usuario_aluno"],
                         f"{nomes['professor']} recusou sua solicitação de aula de {nomes['disciplina']}"))
                    conexao.commit()
                    return "ok", {"status": "recusada"}

                inicio = sol["data_hora_solicitada"]
                if not inicio:
                    return "sem_horario", None
                if inicio < agora:
                    return "passado", None

                cur.execute(
                    "SELECT preco FROM professor_disciplina WHERE id_professor = %s AND id_disciplina = %s",
                    (id_professor, sol["id_disciplina"]))
                linha_preco = cur.fetchone()
                if not linha_preco:
                    return "sem_disciplina", None

                fim = inicio + timedelta(minutes=60)
                cur.execute(
                    """SELECT 1 FROM aula a JOIN contrato c ON c.id_contrato = a.id_contrato
                       WHERE c.id_professor = %s AND a.status <> 'cancelada'
                         AND a.data_hora < %s
                         AND DATE_ADD(a.data_hora, INTERVAL COALESCE(a.duracao, 60) MINUTE) > %s
                       LIMIT 1""",
                    (id_professor, fim, inicio))
                if cur.fetchone():
                    return "ocupado", None

                preco = linha_preco["preco"]
                cur.execute(
                    """INSERT INTO contrato (id_usuario_aluno, id_professor, id_disciplina,
                           quantidade_aulas, valor_total, data_inicio, data_fim, status)
                       VALUES (%s, %s, %s, 1, %s, %s, %s, 'ativo')""",
                    (sol["id_usuario_aluno"], id_professor, sol["id_disciplina"], preco,
                     inicio.date(), inicio.date()))
                id_contrato = cur.lastrowid
                cur.execute(
                    "INSERT INTO aula (id_contrato, data_hora, duracao, status) VALUES (%s, %s, 60, 'agendada')",
                    (id_contrato, inicio))
                id_aula = cur.lastrowid
                # Pagamento SIMULADO: nasce "retido". Quando houver gateway, só quem cria
                # esta linha muda (passa a ser o webhook de pagamento).
                cur.execute(
                    "INSERT INTO pagamento (id_contrato, valor, metodo, status) VALUES (%s, %s, NULL, 'retido')",
                    (id_contrato, preco))
                cur.execute("UPDATE solicitacao_aula SET status = 'aceita' WHERE id_solicitacao = %s",
                            (id_solicitacao,))
                cur.execute(
                    "INSERT INTO notificacao (id_usuario, texto) VALUES (%s, %s)",
                    (sol["id_usuario_aluno"],
                     f"{nomes['professor']} aceitou sua aula de {nomes['disciplina']} ({rotulo_data(inicio)})"))
            conexao.commit()
            return "ok", {"status": "aceita", "id_aula": id_aula, "id_contrato": id_contrato,
                          "valor": _float(preco), "data_hora": inicio}
        except pymysql.MySQLError:
            conexao.rollback()
            raise
        finally:
            conexao.close()

    def agenda(self, id_professor, desde):
        return self._consultar(
            """SELECT a.id_aula, a.data_hora, a.duracao, a.status, a.pin, a.pin_expira,
                      ua.nome AS aluno, d.nome AS disciplina
               FROM aula a
               JOIN contrato c ON c.id_contrato = a.id_contrato
               JOIN usuario ua ON ua.id_usuario = c.id_usuario_aluno
               JOIN disciplina d ON d.id_disciplina = c.id_disciplina
               WHERE c.id_professor = %s AND a.status IN ('agendada', 'realizada')
                 AND a.confirmada_aluno = FALSE AND a.data_hora >= %s
               ORDER BY a.data_hora""",
            (id_professor, desde))

    def gerar_pin(self, id_aula, id_professor, pin, expira):
        conexao = self.db.conectar()
        try:
            with conexao.cursor() as cur:
                cur.execute(
                    """SELECT a.status, a.confirmada_aluno
                       FROM aula a JOIN contrato c ON c.id_contrato = a.id_contrato
                       WHERE a.id_aula = %s AND c.id_professor = %s FOR UPDATE""",
                    (id_aula, id_professor))
                aula = cur.fetchone()
                if not aula:
                    return "nao_encontrada"
                if aula["confirmada_aluno"]:
                    return "ja_confirmada"
                if aula["status"] not in ("agendada", "realizada"):
                    return "indisponivel"
                cur.execute(
                    "UPDATE aula SET pin = %s, pin_expira = %s, pin_tentativas = 0 WHERE id_aula = %s",
                    (pin, expira, id_aula))
            conexao.commit()
            return "ok"
        except pymysql.MySQLError:
            conexao.rollback()
            raise
        finally:
            conexao.close()

    def pagamentos(self, id_professor):
        return self._consultar(
            """SELECT p.id_pagamento, p.valor, p.status, p.data_pagamento, p.data_liberacao,
                      ua.nome AS aluno,
                      (SELECT MIN(a.data_hora) FROM aula a WHERE a.id_contrato = c.id_contrato) AS data_aula
               FROM pagamento p
               JOIN contrato c ON c.id_contrato = p.id_contrato
               JOIN usuario ua ON ua.id_usuario = c.id_usuario_aluno
               WHERE c.id_professor = %s
               ORDER BY p.data_pagamento DESC, p.id_pagamento DESC LIMIT 50""",
            (id_professor,))

    def painel(self, id_professor, inicio, fim):
        aulas = self._consultar(
            """SELECT COUNT(*) AS total FROM aula a JOIN contrato c ON c.id_contrato = a.id_contrato
               WHERE c.id_professor = %s AND a.status <> 'cancelada'
                 AND a.data_hora >= %s AND a.data_hora < %s""",
            (id_professor, inicio, fim), um=True)["total"]
        ganhos = self._consultar(
            """SELECT COALESCE(SUM(p.valor), 0) AS total FROM pagamento p
               JOIN contrato c ON c.id_contrato = p.id_contrato
               WHERE c.id_professor = %s AND p.status = 'liberado'
                 AND p.data_liberacao >= %s AND p.data_liberacao < %s""",
            (id_professor, inicio, fim), um=True)["total"]
        nota = self._consultar(
            "SELECT ROUND(AVG(nota), 2) AS nota, COUNT(*) AS total FROM avaliacao WHERE id_professor = %s",
            (id_professor,), um=True)
        alunos = self._consultar(
            """SELECT COUNT(DISTINCT id_usuario_aluno) AS total FROM contrato
               WHERE id_professor = %s AND status = 'ativo'""",
            (id_professor,), um=True)["total"]
        pendentes = self._consultar(
            "SELECT COUNT(*) AS total FROM solicitacao_aula WHERE id_professor = %s AND status = 'pendente'",
            (id_professor,), um=True)["total"]
        return {"aulas_mes": aulas, "ganhos_mes": _float(ganhos), "nota": _float(nota["nota"]),
                "avaliacoes": nota["total"], "alunos_ativos": alunos, "pedidos_pendentes": pendentes}


# ---------- SERVIÇO ----------
class AreaProfessorService:
    PIN_VALIDADE_MIN = 120
    AGENDA_DIAS_ATRAS = 7  # aulas não confirmadas ainda aparecem, para dar tempo de gerar o PIN

    def __init__(self, repositorio):
        self.repositorio = repositorio

    def _professor(self, id_usuario, exigir_ativo=False):
        perfil = self.repositorio.perfil_do_usuario(id_usuario)
        if not perfil:
            raise ErroApi("Você ainda não se cadastrou como professor", 403)
        if exigir_ativo and perfil["status"] != "ativo":
            raise ErroApi("Seu perfil ainda não foi aprovado pela equipe Mentora", 403)
        return perfil["id_professor"]

    def pedidos(self, id_usuario):
        id_professor = self._professor(id_usuario)
        return [{
            "id": p["id_solicitacao"], "aluno": p["aluno"], "disciplina": p["disciplina"],
            "valor": _float(p["preco"]), "data_hora": iso(p["data_hora_solicitada"]),
            "rotulo": rotulo_data(p["data_hora_solicitada"]), "status": p["status"],
            "solicitado_em": iso(p["data_solicitacao"]),
        } for p in self.repositorio.listar_pedidos(id_professor)]

    def responder(self, id_usuario, id_solicitacao, aceitar, agora=None):
        id_professor = self._professor(id_usuario, exigir_ativo=True)
        codigo, dados = self.repositorio.responder(
            id_solicitacao, id_professor, aceitar, agora or datetime.now())
        if codigo == "ok":
            if dados.get("data_hora"):
                dados["data_hora"] = iso(dados["data_hora"])
            return {"id": id_solicitacao, **dados}
        erros = {
            "nao_encontrada": ("Pedido não encontrado", 404),
            "ja_respondida": ("Este pedido já foi respondido", 409),
            "sem_horario": ("Este pedido não tem horário definido. Recuse e peça um novo.", 400),
            "passado": ("O horário deste pedido já passou. Recuse o pedido.", 409),
            "sem_disciplina": ("Você não ensina mais essa disciplina. Recuse o pedido.", 409),
            "ocupado": ("Você já tem uma aula nesse horário", 409),
        }
        mensagem, status = erros[codigo]
        raise ErroApi(mensagem, status)

    def agenda(self, id_usuario, agora=None):
        agora = agora or datetime.now()
        id_professor = self._professor(id_usuario)
        desde = agora - timedelta(days=self.AGENDA_DIAS_ATRAS)
        itens = []
        for a in self.repositorio.agenda(id_professor, desde):
            pin_ok = bool(a["pin"]) and (not a["pin_expira"] or a["pin_expira"] >= agora)
            itens.append({
                "id": a["id_aula"], "aluno": a["aluno"], "disciplina": a["disciplina"],
                "data_hora": iso(a["data_hora"]), "rotulo": rotulo_data(a["data_hora"]),
                "dia": rotulo_data(a["data_hora"]).split(" · ")[0],
                "hora": a["data_hora"].strftime("%H:%M"),
                "duracao": a["duracao"], "pin_ativo": pin_ok,
            })
        return itens

    def gerar_pin(self, id_usuario, id_aula, agora=None):
        agora = agora or datetime.now()
        id_professor = self._professor(id_usuario)
        pin = f"{secrets.randbelow(10000):04d}"  # secrets: aleatório de verdade, não previsível
        expira = agora + timedelta(minutes=self.PIN_VALIDADE_MIN)
        codigo = self.repositorio.gerar_pin(id_aula, id_professor, pin, expira)
        erros = {
            "nao_encontrada": ("Aula não encontrada", 404),
            "ja_confirmada": ("Esta aula já foi confirmada pelo aluno", 409),
            "indisponivel": ("Não é possível gerar PIN para esta aula", 409),
        }
        if codigo != "ok":
            mensagem, status = erros[codigo]
            raise ErroApi(mensagem, status)
        return {"pin": pin, "expira_em": iso(expira), "valido_por_minutos": self.PIN_VALIDADE_MIN}

    def pagamentos(self, id_usuario):
        id_professor = self._professor(id_usuario)
        return [{
            "id": p["id_pagamento"], "aluno": p["aluno"], "valor": _float(p["valor"]),
            "status": p["status"], "data_aula": iso(p["data_aula"]),
            "rotulo": rotulo_data(p["data_aula"]), "liberado_em": iso(p["data_liberacao"]),
        } for p in self.repositorio.pagamentos(id_professor)]

    def painel(self, id_usuario, agora=None):
        agora = agora or datetime.now()
        id_professor = self._professor(id_usuario)
        inicio = agora.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        proximo = (inicio + timedelta(days=32)).replace(day=1)
        return self.repositorio.painel(id_professor, inicio, proximo)


# ---------- CONTROLLER ----------
class AreaProfessorController:
    def __init__(self, service, autenticacao):
        self.service = service
        self.bp = Blueprint("area_professor", __name__)
        protegida = autenticacao.requer_login
        regras = [
            ("/api/professor/pedidos", self.pedidos, ["GET"]),
            ("/api/professor/pedidos/<int:id_solicitacao>/aceitar", self.aceitar, ["POST"]),
            ("/api/professor/pedidos/<int:id_solicitacao>/recusar", self.recusar, ["POST"]),
            ("/api/professor/agenda", self.agenda, ["GET"]),
            ("/api/professor/pagamentos", self.pagamentos, ["GET"]),
            ("/api/professor/painel", self.painel, ["GET"]),
            ("/api/aulas/<int:id_aula>/pin", self.gerar_pin, ["POST"]),
        ]
        for caminho, funcao, metodos in regras:
            self.bp.add_url_rule(caminho, view_func=protegida(funcao), methods=metodos)

    def pedidos(self):
        return jsonify(self.service.pedidos(g.id_usuario)), 200

    def aceitar(self, id_solicitacao):
        return jsonify({"mensagem": "Pedido aceito. A aula foi agendada.",
                        "pedido": self.service.responder(g.id_usuario, id_solicitacao, True)}), 200

    def recusar(self, id_solicitacao):
        return jsonify({"mensagem": "Pedido recusado.",
                        "pedido": self.service.responder(g.id_usuario, id_solicitacao, False)}), 200

    def agenda(self):
        return jsonify(self.service.agenda(g.id_usuario)), 200

    def pagamentos(self):
        return jsonify(self.service.pagamentos(g.id_usuario)), 200

    def painel(self):
        return jsonify(self.service.painel(g.id_usuario)), 200

    def gerar_pin(self, id_aula):
        return jsonify(self.service.gerar_pin(g.id_usuario, id_aula)), 200
