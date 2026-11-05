# AulaRepository  - acesso ao banco (solicitações, aulas, PIN)
# AulaService     - regras de negócio do aluno
# AulaController  - endpoints HTTP (todos exigem login)
import hmac
import re
from datetime import datetime

import pymysql
from flask import Blueprint, g, jsonify, request

from erros import ErroApi
from professor import DIAS_CURTOS

FORMATO_ISO = "%Y-%m-%dT%H:%M:%S"
PIN_VALIDO = re.compile(r"^\d{4,6}$")


def _rotulo(data_hora):
    if not data_hora:
        return None
    return f"{DIAS_CURTOS[data_hora.weekday()]} {data_hora:%d/%m} · {data_hora:%H:%M}"


def _iso(data_hora):
    return data_hora.strftime(FORMATO_ISO) if data_hora else None


# ---------- REPOSITÓRIO ----------
class AulaRepository:
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

    def id_usuario_do_professor(self, id_professor):
        linha = self._consultar(
            "SELECT id_usuario FROM perfil_professor WHERE id_professor = %s",
            (id_professor,), um=True)
        return linha["id_usuario"] if linha else None

    def disciplinas_do_professor(self, id_professor):
        return self._consultar(
            """SELECT d.id_disciplina, d.nome, pd.preco
               FROM professor_disciplina pd
               JOIN disciplina d ON d.id_disciplina = pd.id_disciplina
               WHERE pd.id_professor = %s ORDER BY d.nome""",
            (id_professor,))

    def inserir_solicitacao(self, id_aluno, id_professor, id_disciplina, data_hora):
        # tudo na mesma transação: confere duplicada, grava e avisa o professor
        conexao = self.db.conectar()
        try:
            with conexao.cursor() as cursor:
                cursor.execute(
                    """SELECT 1 FROM solicitacao_aula
                       WHERE id_usuario_aluno = %s AND id_professor = %s
                         AND data_hora_solicitada = %s AND status = 'pendente' FOR UPDATE""",
                    (id_aluno, id_professor, data_hora))
                if cursor.fetchone():
                    raise ErroApi("Você já solicitou esse horário e está aguardando resposta", 409)
                cursor.execute(
                    """INSERT INTO solicitacao_aula
                       (id_usuario_aluno, id_professor, id_disciplina, data_hora_solicitada)
                       VALUES (%s, %s, %s, %s)""",
                    (id_aluno, id_professor, id_disciplina, data_hora))
                novo_id = cursor.lastrowid
                cursor.execute(
                    """INSERT INTO notificacao (id_usuario, texto)
                       SELECT pr.id_usuario, CONCAT(ua.nome, ' solicitou uma aula de ', d.nome)
                       FROM perfil_professor pr, usuario ua, disciplina d
                       WHERE pr.id_professor = %s AND ua.id_usuario = %s AND d.id_disciplina = %s""",
                    (id_professor, id_aluno, id_disciplina))
            conexao.commit()
            return novo_id
        except Exception:
            conexao.rollback()
            raise
        finally:
            conexao.close()

    def listar_solicitacoes(self, id_aluno):
        # só pendentes e recusadas: as aceitas já viram contrato + aula
        return self._consultar(
            """SELECT s.id_solicitacao, s.data_hora_solicitada, s.status,
                      u.nome AS professor, d.nome AS disciplina
               FROM solicitacao_aula s
               JOIN perfil_professor pr ON pr.id_professor = s.id_professor
               JOIN usuario u ON u.id_usuario = pr.id_usuario
               JOIN disciplina d ON d.id_disciplina = s.id_disciplina
               WHERE s.id_usuario_aluno = %s AND s.status IN ('pendente', 'recusada')""",
            (id_aluno,))

    def listar_aulas(self, id_aluno):
        return self._consultar(
            """SELECT a.id_aula, a.data_hora, a.duracao, a.status, a.confirmada_aluno,
                      u.nome AS professor, d.nome AS disciplina,
                      (SELECT p.status FROM pagamento p WHERE p.id_contrato = c.id_contrato
                       ORDER BY p.id_pagamento DESC LIMIT 1) AS pagamento,
                      (SELECT COUNT(*) FROM avaliacao av WHERE av.id_aula = a.id_aula) AS avaliada
               FROM aula a
               JOIN contrato c ON c.id_contrato = a.id_contrato
               JOIN perfil_professor pr ON pr.id_professor = c.id_professor
               JOIN usuario u ON u.id_usuario = pr.id_usuario
               JOIN disciplina d ON d.id_disciplina = c.id_disciplina
               WHERE c.id_usuario_aluno = %s""",
            (id_aluno,))

    @staticmethod
    def _liberar_pagamento(cursor, id_contrato):
        # O pagamento só é liberado quando TODAS as aulas do contrato foram confirmadas
        cursor.execute(
            """SELECT COUNT(*) AS faltam FROM aula
               WHERE id_contrato = %s AND confirmada_aluno = FALSE AND status <> 'cancelada'""",
            (id_contrato,))
        if cursor.fetchone()["faltam"] > 0:
            return
        cursor.execute(
            """UPDATE pagamento SET status = 'liberado', data_liberacao = NOW()
               WHERE id_contrato = %s AND status = 'retido'""", (id_contrato,))
        liberados = cursor.rowcount
        cursor.execute("UPDATE contrato SET status = 'concluido' WHERE id_contrato = %s", (id_contrato,))
        if liberados:
            cursor.execute(
                """INSERT INTO notificacao (id_usuario, texto)
                   SELECT pr.id_usuario, CONCAT('Pagamento de ', ua.nome, ' liberado')
                   FROM contrato c
                   JOIN perfil_professor pr ON pr.id_professor = c.id_professor
                   JOIN usuario ua ON ua.id_usuario = c.id_usuario_aluno
                   WHERE c.id_contrato = %s""", (id_contrato,))

    def avaliar(self, id_aula, id_aluno, nota, comentario):
        conexao = self.db.conectar()
        try:
            with conexao.cursor() as cursor:
                cursor.execute(
                    """SELECT a.confirmada_aluno, c.id_professor, pr.id_usuario AS id_usuario_professor
                       FROM aula a
                       JOIN contrato c ON c.id_contrato = a.id_contrato
                       JOIN perfil_professor pr ON pr.id_professor = c.id_professor
                       WHERE a.id_aula = %s AND c.id_usuario_aluno = %s FOR UPDATE""",
                    (id_aula, id_aluno))
                aula = cursor.fetchone()
                if not aula:
                    return "nao_encontrada"
                if not aula["confirmada_aluno"]:
                    return "nao_confirmada"
                cursor.execute("SELECT 1 FROM avaliacao WHERE id_aula = %s", (id_aula,))
                if cursor.fetchone():
                    return "ja_avaliada"
                cursor.execute(
                    """INSERT INTO avaliacao (id_aula, id_usuario_aluno, id_professor, nota, comentario)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (id_aula, id_aluno, aula["id_professor"], nota, comentario))
                cursor.execute(
                    "INSERT INTO notificacao (id_usuario, texto) VALUES (%s, %s)",
                    (aula["id_usuario_professor"], f"Você recebeu uma nova avaliação: {nota} ⭐"))
            conexao.commit()
            return "ok"
        except pymysql.MySQLError:
            conexao.rollback()
            raise
        finally:
            conexao.close()

    def confirmar_com_pin(self, id_aula, id_aluno, pin, agora, max_tentativas):
        # Devolve (codigo, tentativas_restantes). A linha da aula fica TRAVADA durante
        # a conferência: duas tentativas ao mesmo tempo não burlam o limite de erros.
        conexao = self.db.conectar()
        try:
            with conexao.cursor() as cursor:
                cursor.execute(
                    """SELECT a.id_contrato, a.status, a.confirmada_aluno, a.pin, a.pin_expira,
                              a.pin_tentativas
                       FROM aula a JOIN contrato c ON c.id_contrato = a.id_contrato
                       WHERE a.id_aula = %s AND c.id_usuario_aluno = %s FOR UPDATE""",
                    (id_aula, id_aluno))
                aula = cursor.fetchone()
                if not aula:
                    return "nao_encontrada", 0
                if aula["confirmada_aluno"]:
                    return "ja_confirmada", 0
                if aula["status"] not in ("agendada", "realizada"):
                    return "indisponivel", 0
                if not aula["pin"]:
                    return "sem_pin", 0
                if aula["pin_expira"] and aula["pin_expira"] < agora:
                    return "expirado", 0

                if hmac.compare_digest(str(aula["pin"]), pin):
                    cursor.execute(
                        """UPDATE aula SET confirmada_aluno = TRUE, status = 'realizada',
                           pin = NULL, pin_expira = NULL, pin_tentativas = 0
                           WHERE id_aula = %s""", (id_aula,))
                    cursor.execute(
                        """INSERT INTO notificacao (id_usuario, texto)
                           SELECT pr.id_usuario, CONCAT(ua.nome, ' confirmou a aula de ', d.nome)
                           FROM aula a
                           JOIN contrato c ON c.id_contrato = a.id_contrato
                           JOIN perfil_professor pr ON pr.id_professor = c.id_professor
                           JOIN usuario ua ON ua.id_usuario = c.id_usuario_aluno
                           JOIN disciplina d ON d.id_disciplina = c.id_disciplina
                           WHERE a.id_aula = %s""", (id_aula,))
                    self._liberar_pagamento(cursor, aula["id_contrato"])
                    conexao.commit()
                    return "ok", 0

                tentativas = aula["pin_tentativas"] + 1
                if tentativas >= max_tentativas:  # invalida o PIN: o professor gera outro
                    cursor.execute(
                        """UPDATE aula SET pin = NULL, pin_expira = NULL, pin_tentativas = 0
                           WHERE id_aula = %s""", (id_aula,))
                    conexao.commit()
                    return "bloqueado", 0
                cursor.execute("UPDATE aula SET pin_tentativas = %s WHERE id_aula = %s",
                               (tentativas, id_aula))
                conexao.commit()
                return "incorreto", max_tentativas - tentativas
        except pymysql.MySQLError:
            conexao.rollback()
            raise
        finally:
            conexao.close()


# ---------- SERVIÇO ----------
class AulaService:
    MAX_TENTATIVAS_PIN = 5
    DIAS_PARA_AGENDAR = 30

    def __init__(self, repositorio, professores):
        self.repositorio = repositorio
        self.professores = professores  # ProfessorService: reaproveita a lista de horários livres

    @staticmethod
    def _inteiro(valor, nome, obrigatorio=True):
        if valor in (None, ""):
            if obrigatorio:
                raise ErroApi(f"{nome} é obrigatório", 400)
            return None
        if isinstance(valor, bool) or not re.fullmatch(r"\d+", str(valor)):
            raise ErroApi(f"{nome} deve ser um número inteiro", 400)
        return int(valor)

    @staticmethod
    def _ler_data_hora(texto):
        if not isinstance(texto, str) or not texto.strip():
            raise ErroApi("data_hora é obrigatório (ex.: 2026-11-02T18:00:00)", 400)
        try:
            data = datetime.fromisoformat(texto.strip().replace(" ", "T"))
        except ValueError:
            raise ErroApi("data_hora inválida. Use o formato 2026-11-02T18:00:00", 400)
        if data.tzinfo is not None:
            raise ErroApi("data_hora deve ser sem fuso horário", 400)
        return data

    def solicitar(self, id_aluno, dados, agora=None):
        agora = agora or datetime.now()
        id_professor = self._inteiro(dados.get("id_professor"), "id_professor")
        id_disciplina = self._inteiro(dados.get("id_disciplina"), "id_disciplina", obrigatorio=False)
        data_hora = self._ler_data_hora(dados.get("data_hora"))

        # só aceita um horário que a própria API ofereceria (e já dá 404 se o professor não está ativo)
        livres = self.professores.horarios(id_professor, self.DIAS_PARA_AGENDAR, agora)
        if data_hora.strftime(FORMATO_ISO) not in {h["data_hora"] for h in livres}:
            raise ErroApi("Esse horário não está disponível. Escolha outro.", 400)

        if self.repositorio.id_usuario_do_professor(id_professor) == id_aluno:
            raise ErroApi("Você não pode solicitar aula para você mesmo", 400)

        ensinadas = self.repositorio.disciplinas_do_professor(id_professor)
        if id_disciplina is None:
            if len(ensinadas) != 1:
                raise ErroApi("Escolha a disciplina (id_disciplina)", 400)
            escolhida = ensinadas[0]
        else:
            escolhida = next((d for d in ensinadas if d["id_disciplina"] == id_disciplina), None)
            if not escolhida:
                raise ErroApi("Esse professor não ensina essa disciplina", 400)

        id_solicitacao = self.repositorio.inserir_solicitacao(
            id_aluno, id_professor, escolhida["id_disciplina"], data_hora)
        return {
            "id": id_solicitacao,
            "id_professor": id_professor,
            "disciplina": escolhida["nome"],
            "valor": float(escolhida["preco"]),
            "data_hora": _iso(data_hora),
            "rotulo": _rotulo(data_hora),
            "status": "aguardando",
        }

    @staticmethod
    def _status_da_aula(a):
        if a["status"] == "cancelada":
            return "cancelada"
        if a["confirmada_aluno"]:
            return "confirmada"
        return "agendada" if a["status"] == "agendada" else "aguardando_confirmacao"

    def minhas_aulas(self, id_aluno):
        itens = []
        for s in self.repositorio.listar_solicitacoes(id_aluno):
            itens.append({
                "tipo": "solicitacao", "id": s["id_solicitacao"],
                "professor": s["professor"], "disciplina": s["disciplina"],
                "data_hora": _iso(s["data_hora_solicitada"]),
                "rotulo": _rotulo(s["data_hora_solicitada"]),
                "status": "aguardando" if s["status"] == "pendente" else "recusada",
                "pode_confirmar": False, "pode_avaliar": False, "pagamento": None,
                "_ordem": s["data_hora_solicitada"],
            })
        for a in self.repositorio.listar_aulas(id_aluno):
            status = self._status_da_aula(a)
            itens.append({
                "tipo": "aula", "id": a["id_aula"],
                "professor": a["professor"], "disciplina": a["disciplina"],
                "data_hora": _iso(a["data_hora"]), "rotulo": _rotulo(a["data_hora"]),
                "status": status,
                "pode_confirmar": status in ("agendada", "aguardando_confirmacao"),
                "pode_avaliar": status == "confirmada" and not a["avaliada"],
                "pagamento": a["pagamento"],
                "_ordem": a["data_hora"],
            })
        # mais recentes primeiro; itens sem data (raros) vão para o fim
        itens.sort(key=lambda i: (i["_ordem"] is None, -(i["_ordem"].timestamp() if i["_ordem"] else 0)))
        for i in itens:
            del i["_ordem"]
        return itens

    def confirmar(self, id_aluno, id_aula, dados, agora=None):
        pin = str(dados.get("pin") or "").strip()
        if not PIN_VALIDO.match(pin):
            raise ErroApi("Informe o PIN (de 4 a 6 números)", 400)

        codigo, restantes = self.repositorio.confirmar_com_pin(
            id_aula, id_aluno, pin, agora or datetime.now(), self.MAX_TENTATIVAS_PIN)

        if codigo == "ok":
            return {"id": id_aula, "status": "confirmada"}
        erros = {
            "nao_encontrada": ("Aula não encontrada", 404),
            "ja_confirmada": ("Esta aula já foi confirmada", 409),
            "indisponivel": ("Esta aula não pode ser confirmada", 409),
            "sem_pin": ("O professor ainda não gerou o PIN desta aula", 400),
            "expirado": ("PIN expirado. Peça um novo ao professor", 400),
            "bloqueado": ("Muitas tentativas erradas. Peça um novo PIN ao professor", 429),
            "incorreto": (f"PIN incorreto. Restam {restantes} tentativa(s)", 400),
        }
        mensagem, status = erros[codigo]
        raise ErroApi(mensagem, status)

    def avaliar(self, id_aluno, id_aula, dados):
        nota = dados.get("nota")
        if isinstance(nota, bool) or not re.fullmatch(r"[1-5]", str(nota)):
            raise ErroApi("nota deve ser um número de 1 a 5", 400)
        comentario = dados.get("comentario")
        if comentario is not None:
            if not isinstance(comentario, str):
                raise ErroApi("comentario deve ser um texto", 400)
            comentario = comentario.strip() or None
            if comentario and len(comentario) > 1000:
                raise ErroApi("O comentário deve ter no máximo 1000 caracteres", 400)
        codigo = self.repositorio.avaliar(id_aula, id_aluno, int(nota), comentario)
        erros = {
            "nao_encontrada": ("Aula não encontrada", 404),
            "nao_confirmada": ("Confirme a aula antes de avaliar", 409),
            "ja_avaliada": ("Você já avaliou esta aula", 409),
        }
        if codigo != "ok":
            mensagem, status = erros[codigo]
            raise ErroApi(mensagem, status)
        return {"id": id_aula, "nota": int(nota)}


# ---------- CONTROLLER ----------
class AulaController:
    def __init__(self, service, autenticacao):
        self.service = service
        self.bp = Blueprint("aulas", __name__)
        protegida = autenticacao.requer_login
        self.bp.add_url_rule("/api/solicitacoes", view_func=protegida(self.solicitar),
                             methods=["POST"])
        self.bp.add_url_rule("/api/aluno/aulas", view_func=protegida(self.minhas_aulas),
                             methods=["GET"])
        self.bp.add_url_rule("/api/aulas/<int:id_aula>/confirmar",
                             view_func=protegida(self.confirmar), methods=["POST"])
        self.bp.add_url_rule("/api/aulas/<int:id_aula>/avaliacao",
                             view_func=protegida(self.avaliar), methods=["POST"])

    def solicitar(self):
        dados = request.get_json(silent=True) or {}
        solicitacao = self.service.solicitar(g.id_usuario, dados)
        return jsonify({"mensagem": "Solicitação enviada. Aguarde a resposta do professor.",
                        "solicitacao": solicitacao}), 201

    def minhas_aulas(self):
        return jsonify(self.service.minhas_aulas(g.id_usuario)), 200

    def confirmar(self, id_aula):
        dados = request.get_json(silent=True) or {}
        return jsonify({"mensagem": "Aula confirmada",
                        "aula": self.service.confirmar(g.id_usuario, id_aula, dados)}), 200

    def avaliar(self, id_aula):
        dados = request.get_json(silent=True) or {}
        return jsonify({"mensagem": "Avaliação enviada. Obrigado!",
                        "avaliacao": self.service.avaliar(g.id_usuario, id_aula, dados)}), 201
