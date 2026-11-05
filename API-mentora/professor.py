# Horarios - gera os horários livres a partir da disponibilidade
# ProfessorRepository - acesso ao banco
# ProfessorService - regras de negócio
# ProfessorController - endpoints HTTP (públicos: só professores com status 'ativo')
import unicodedata
from datetime import datetime, time, timedelta

from flask import Blueprint, jsonify, request

from erros import ErroApi

DIAS_CURTOS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]  # índice = weekday() do Python
PREFIXOS = ["seg", "ter", "qua", "qui", "sex", "sab", "dom"]


def _para_float(valor):
    return float(valor) if valor is not None else None


# ---------- HORÁRIOS: transforma faixas (Segunda 18h-21h) em datas reais ----------
class Horarios:
    DURACAO_MIN = 60          # cada aula ocupa 1 hora
    ANTECEDENCIA_MIN = 60     # não oferece horário que começa em menos de 1 hora

    @staticmethod
    def indice_do_dia(texto):
        # "Segunda", "terça", "Terca-feira" -> 0, 1, 1...  (None se não reconhecer)
        base = unicodedata.normalize("NFD", (texto or "").strip().lower())
        base = "".join(c for c in base if unicodedata.category(c) != "Mn")
        return PREFIXOS.index(base[:3]) if base[:3] in PREFIXOS else None

    @staticmethod
    def _hora(valor):
        # o MySQL devolve TIME como timedelta; aceita também time
        if isinstance(valor, timedelta):
            return (datetime.min + valor).time()
        return valor if isinstance(valor, time) else None

    @classmethod
    def gerar(cls, disponibilidades, ocupadas, agora, dias):
        # disponibilidades: linhas com dia_semana, hora_inicio, hora_fim
        # ocupadas: linhas com data_hora e duracao (aulas já marcadas)
        duracao = timedelta(minutes=cls.DURACAO_MIN)
        limite = agora + timedelta(minutes=cls.ANTECEDENCIA_MIN)
        bloqueios = [
            (o["data_hora"], o["data_hora"] + timedelta(minutes=o["duracao"] or cls.DURACAO_MIN))
            for o in ocupadas
        ]

        horarios = []
        for desloc in range(dias + 1):
            dia = (agora + timedelta(days=desloc)).date()
            for d in disponibilidades:
                if cls.indice_do_dia(d["dia_semana"]) != dia.weekday():
                    continue
                inicio, fim = cls._hora(d["hora_inicio"]), cls._hora(d["hora_fim"])
                if not inicio or not fim:
                    continue
                atual = datetime.combine(dia, inicio)
                fim_faixa = datetime.combine(dia, fim)
                while atual + duracao <= fim_faixa:
                    livre = atual >= limite and not any(
                        atual < b_fim and b_ini < atual + duracao for b_ini, b_fim in bloqueios
                    )
                    if livre:
                        horarios.append({
                            "data_hora": atual.strftime("%Y-%m-%dT%H:%M:%S"),
                            "data": atual.strftime("%Y-%m-%d"),
                            "dia": DIAS_CURTOS[dia.weekday()],
                            "hora": atual.strftime("%H:%M"),
                            "rotulo": f"{DIAS_CURTOS[dia.weekday()]} {atual:%d/%m} {atual:%H:%M}",
                        })
                    atual += duracao
        horarios.sort(key=lambda h: h["data_hora"])
        return horarios


# ---------- REPOSITÓRIO ----------
class ProfessorRepository:
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

    # trecho comum do SELECT (professor + nota da view)
    _BASE = """
        SELECT p.id_professor, u.nome, u.foto, p.descricao, p.formacao, p.experiencia,
               p.modalidade, v.nota_media, COALESCE(v.total_avaliacoes, 0) AS total_avaliacoes
        FROM perfil_professor p
        JOIN usuario u ON u.id_usuario = p.id_usuario
        LEFT JOIN vw_professores_avaliacao v ON v.id_professor = p.id_professor
        WHERE p.status = 'ativo'
    """

    def listar(self, busca, disciplina, limite):
        sql, params = self._BASE, []
        if disciplina is not None:
            sql += """ AND EXISTS (SELECT 1 FROM professor_disciplina pd
                                   JOIN disciplina d ON d.id_disciplina = pd.id_disciplina
                                   WHERE pd.id_professor = p.id_professor
                                     AND (d.nome = %s OR d.id_disciplina = %s))"""
            params += [disciplina, int(disciplina) if disciplina.isdigit() else -1]
        if busca:
            padrao = "%" + busca.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            sql += """ AND (u.nome LIKE %s OR EXISTS (SELECT 1 FROM professor_disciplina pd
                                   JOIN disciplina d ON d.id_disciplina = pd.id_disciplina
                                   WHERE pd.id_professor = p.id_professor AND d.nome LIKE %s))"""
            params += [padrao, padrao]
        sql += " ORDER BY v.nota_media IS NULL, v.nota_media DESC, v.total_avaliacoes DESC, u.nome LIMIT %s"
        params.append(limite)
        return self._consultar(sql, params)

    def buscar_ativo(self, id_professor):
        return self._consultar(self._BASE + " AND p.id_professor = %s", (id_professor,), um=True)

    def disciplinas_de(self, ids):
        if not ids:
            return []
        marcadores = ", ".join(["%s"] * len(ids))
        return self._consultar(
            f"""SELECT pd.id_professor, d.id_disciplina, d.nome, pd.preco
                FROM professor_disciplina pd
                JOIN disciplina d ON d.id_disciplina = pd.id_disciplina
                WHERE pd.id_professor IN ({marcadores})
                ORDER BY d.nome""",
            tuple(ids),
        )

    def avaliacoes_recentes(self, id_professor, limite=5):
        return self._consultar(
            """SELECT a.nota, a.comentario, a.data_avaliacao, u.nome
               FROM avaliacao a JOIN usuario u ON u.id_usuario = a.id_usuario_aluno
               WHERE a.id_professor = %s ORDER BY a.data_avaliacao DESC LIMIT %s""",
            (id_professor, limite),
        )

    def disponibilidades(self, id_professor):
        return self._consultar(
            "SELECT dia_semana, hora_inicio, hora_fim FROM disponibilidade WHERE id_professor = %s",
            (id_professor,),
        )

    def aulas_ocupadas(self, id_professor, inicio, fim):
        return self._consultar(
            """SELECT a.data_hora, a.duracao
               FROM aula a JOIN contrato c ON c.id_contrato = a.id_contrato
               WHERE c.id_professor = %s AND a.status <> 'cancelada'
                 AND a.data_hora >= %s AND a.data_hora < %s""",
            (id_professor, inicio, fim),
        )


# ---------- SERVIÇO ----------
class ProfessorService:
    LIMITE_PADRAO = 50
    LIMITE_MAX = 100
    DIAS_PADRAO = 14
    DIAS_MAX = 30

    def __init__(self, repositorio):
        self.repositorio = repositorio

    @staticmethod
    def _inteiro(texto, padrao, minimo, maximo, nome):
        if texto in (None, ""):
            return padrao
        try:
            valor = int(texto)
        except ValueError:
            raise ErroApi(f"{nome} deve ser um número inteiro", 400)
        return max(minimo, min(valor, maximo))

    def _montar(self, linha, disciplinas):
        # formato que o front usa no card (materia, preco, nota, avaliacoes, descricao...)
        precos = [_para_float(d["preco"]) for d in disciplinas]
        # matéria exibida no card = a do menor preço, para materia e preco combinarem
        principal = min(disciplinas, key=lambda d: d["preco"]) if disciplinas else None
        return {
            "id": linha["id_professor"],
            "nome": linha["nome"],
            "foto": linha["foto"],
            "materia": principal["nome"] if principal else None,
            "preco": min(precos) if precos else None,  # "a partir de"
            "nota": _para_float(linha["nota_media"]),  # None = ainda sem avaliações
            "avaliacoes": linha["total_avaliacoes"],
            "descricao": linha["descricao"],
            "formacao": linha["formacao"],
            "modalidade": linha["modalidade"],
            "disciplinas": [
                {"id": d["id_disciplina"], "nome": d["nome"], "preco": _para_float(d["preco"])}
                for d in disciplinas
            ],
        }

    def listar(self, busca, disciplina, limite):
        busca = (busca or "").strip()[:100]
        disciplina = (disciplina or "").strip() or None
        limite = self._inteiro(limite, self.LIMITE_PADRAO, 1, self.LIMITE_MAX, "limit")
        linhas = self.repositorio.listar(busca, disciplina, limite)

        por_professor = {}
        for d in self.repositorio.disciplinas_de([l["id_professor"] for l in linhas]):
            por_professor.setdefault(d["id_professor"], []).append(d)
        return [self._montar(l, por_professor.get(l["id_professor"], [])) for l in linhas]

    def _obter_ativo(self, id_professor):
        linha = self.repositorio.buscar_ativo(id_professor)
        if not linha:
            raise ErroApi("Professor não encontrado", 404)
        return linha

    def obter(self, id_professor):
        linha = self._obter_ativo(id_professor)
        dados = self._montar(linha, self.repositorio.disciplinas_de([id_professor]))
        dados["experiencia"] = linha["experiencia"]
        dados["avaliacoes_recentes"] = [
            {
                "nota": a["nota"],
                "comentario": a["comentario"],
                "aluno": (a["nome"] or "").split(" ")[0],  # só o primeiro nome
                "data": a["data_avaliacao"].strftime("%Y-%m-%d") if a["data_avaliacao"] else None,
            }
            for a in self.repositorio.avaliacoes_recentes(id_professor)
        ]
        return dados

    def horarios(self, id_professor, dias, agora=None):
        self._obter_ativo(id_professor)
        dias = self._inteiro(dias, self.DIAS_PADRAO, 1, self.DIAS_MAX, "dias")
        agora = agora or datetime.now()
        ocupadas = self.repositorio.aulas_ocupadas(
            id_professor, agora, agora + timedelta(days=dias + 2)
        )
        return Horarios.gerar(self.repositorio.disponibilidades(id_professor), ocupadas, agora, dias)


# ---------- CONTROLLER ----------
class ProfessorController:
    def __init__(self, service):
        self.service = service
        self.bp = Blueprint("professores", __name__)
        self.bp.add_url_rule("/api/professores", view_func=self.listar, methods=["GET"])
        self.bp.add_url_rule("/api/professores/<int:id_professor>", view_func=self.obter,
                             methods=["GET"])
        self.bp.add_url_rule("/api/professores/<int:id_professor>/horarios",
                             view_func=self.horarios, methods=["GET"])

    def listar(self):
        lista = self.service.listar(
            request.args.get("busca"), request.args.get("disciplina"), request.args.get("limit")
        )
        return jsonify(lista), 200

    def obter(self, id_professor):
        return jsonify(self.service.obter(id_professor)), 200

    def horarios(self, id_professor):
        return jsonify(self.service.horarios(id_professor, request.args.get("dias"))), 200
