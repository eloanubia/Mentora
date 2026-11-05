# Arquivos                      - salva uploads com segurança
# CadastroProfessorRepository   - acesso ao banco
# CadastroProfessorService      - regras e validações
# CadastroProfessorController   - endpoints HTTP
import os
import re
import secrets
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pymysql
from flask import Blueprint, g, jsonify, request, send_from_directory

from base import RepositorioBase
from erros import ErroApi
from professor import Horarios

NOMES_DIAS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
MODALIDADES = ("online", "presencial", "ambos")
NOME_FOTO = re.compile(r"^[0-9a-f]{32}\.(jpg|png)$")


def _float(valor):
    return float(valor) if valor is not None else None


# ---------- ARQUIVOS: upload seguro ----------
class Arquivos:
    # O tipo do arquivo é descoberto pelos primeiros bytes, nunca pelo nome ou pelo que o
    # navegador diz. O nome salvo é aleatório, então ninguém consegue sobrescrever ou adivinhar.
    ASSINATURAS = {"jpg": b"\xff\xd8\xff", "png": b"\x89PNG\r\n\x1a\n", "pdf": b"%PDF-"}

    def __init__(self):
        padrao = Path(__file__).resolve().parent / "uploads"
        self.base = Path(os.getenv("UPLOAD_DIR") or padrao)

    def pasta(self, subpasta):
        destino = self.base / subpasta
        destino.mkdir(parents=True, exist_ok=True)
        return destino

    def salvar(self, arquivo, permitidos, max_bytes, subpasta, nome_campo):
        dados = arquivo.stream.read(max_bytes + 1)
        if len(dados) > max_bytes:
            raise ErroApi(f"{nome_campo}: arquivo maior que {max_bytes // (1024 * 1024)} MB", 413)
        if not dados:
            raise ErroApi(f"{nome_campo}: arquivo vazio", 400)
        tipo = next((t for t, sig in self.ASSINATURAS.items() if dados.startswith(sig)), None)
        if tipo not in permitidos:
            aceitos = ", ".join(sorted(p.upper() for p in permitidos))
            raise ErroApi(f"{nome_campo}: formato não aceito (use {aceitos})", 400)
        nome = f"{secrets.token_hex(16)}.{tipo}"
        (self.pasta(subpasta) / nome).write_bytes(dados)
        return nome


# ---------- REPOSITÓRIO ----------
class CadastroProfessorRepository(RepositorioBase):
    def perfil(self, id_usuario):
        return self._consultar(
            """SELECT p.id_professor, p.descricao, p.formacao, p.experiencia, p.modalidade,
                      p.status, p.comprovante, u.nome, u.email, u.foto
               FROM perfil_professor p JOIN usuario u ON u.id_usuario = p.id_usuario
               WHERE p.id_usuario = %s""", (id_usuario,), um=True)

    def disciplinas(self, id_professor):
        return self._consultar(
            """SELECT d.id_disciplina, d.nome, pd.preco FROM professor_disciplina pd
               JOIN disciplina d ON d.id_disciplina = pd.id_disciplina
               WHERE pd.id_professor = %s ORDER BY d.nome""", (id_professor,))

    def disponibilidade(self, id_professor):
        return self._consultar(
            "SELECT dia_semana, hora_inicio, hora_fim FROM disponibilidade WHERE id_professor = %s",
            (id_professor,))

    def ids_de_disciplinas_existentes(self, ids):
        marcadores = ", ".join(["%s"] * len(ids))
        linhas = self._consultar(
            f"SELECT id_disciplina FROM disciplina WHERE id_disciplina IN ({marcadores})", tuple(ids))
        return {l["id_disciplina"] for l in linhas}

    @staticmethod
    def _gravar_disciplinas(cur, id_professor, disciplinas):
        cur.execute("DELETE FROM professor_disciplina WHERE id_professor = %s", (id_professor,))
        cur.executemany(
            "INSERT INTO professor_disciplina (id_professor, id_disciplina, preco) VALUES (%s, %s, %s)",
            [(id_professor, i, p) for i, p in disciplinas])

    @staticmethod
    def _gravar_faixas(cur, id_professor, faixas):
        cur.execute("DELETE FROM disponibilidade WHERE id_professor = %s", (id_professor,))
        cur.executemany(
            """INSERT INTO disponibilidade (id_professor, dia_semana, hora_inicio, hora_fim)
               VALUES (%s, %s, %s, %s)""",
            [(id_professor, dia, ini, fim) for dia, ini, fim in faixas])

    def _transacao(self, executar):
        conexao = self.db.conectar()
        try:
            with conexao.cursor() as cur:
                resultado = executar(cur)
            conexao.commit()
            return resultado
        except pymysql.err.IntegrityError as e:
            conexao.rollback()
            if e.args[0] == 1062:
                raise ErroApi("Você já tem um cadastro de professor", 409)
            raise
        except pymysql.MySQLError:
            conexao.rollback()
            raise
        finally:
            conexao.close()

    def criar(self, id_usuario, d, disciplinas, faixas):
        def executar(cur):
            cur.execute(
                """INSERT INTO perfil_professor (id_usuario, descricao, formacao, experiencia,
                       modalidade, status) VALUES (%s, %s, %s, %s, %s, 'pendente')""",
                (id_usuario, d["descricao"], d["formacao"], d["experiencia"], d["modalidade"]))
            id_professor = cur.lastrowid
            self._gravar_disciplinas(cur, id_professor, disciplinas)
            self._gravar_faixas(cur, id_professor, faixas)
            return id_professor
        return self._transacao(executar)

    def atualizar_perfil(self, id_usuario, id_professor, nome, d):
        def executar(cur):
            cur.execute("UPDATE usuario SET nome = %s WHERE id_usuario = %s", (nome, id_usuario))
            cur.execute(
                """UPDATE perfil_professor SET descricao = %s, formacao = %s, experiencia = %s,
                       modalidade = %s WHERE id_professor = %s""",
                (d["descricao"], d["formacao"], d["experiencia"], d["modalidade"], id_professor))
        self._transacao(executar)

    def substituir_disciplinas(self, id_professor, disciplinas):
        self._transacao(lambda cur: self._gravar_disciplinas(cur, id_professor, disciplinas))

    def substituir_faixas(self, id_professor, faixas):
        self._transacao(lambda cur: self._gravar_faixas(cur, id_professor, faixas))

    def salvar_foto(self, id_usuario, caminho):
        self._transacao(lambda cur: cur.execute(
            "UPDATE usuario SET foto = %s WHERE id_usuario = %s", (caminho, id_usuario)))

    def salvar_comprovante(self, id_professor, nome):
        self._transacao(lambda cur: cur.execute(
            "UPDATE perfil_professor SET comprovante = %s WHERE id_professor = %s", (nome, id_professor)))


# ---------- SERVIÇO ----------
class CadastroProfessorService:
    FOTO_MAX = 5 * 1024 * 1024
    COMPROVANTE_MAX = 10 * 1024 * 1024
    PRECO_MAX = Decimal("9999.99")

    def __init__(self, repositorio, arquivos):
        self.repositorio = repositorio
        self.arquivos = arquivos

    # --- validações ---
    @staticmethod
    def _texto(valor, nome, maximo, obrigatorio=True):
        texto = (valor or "").strip() if isinstance(valor, str) or valor is None else None
        if texto is None:
            raise ErroApi(f"{nome} deve ser um texto", 400)
        if obrigatorio and not texto:
            raise ErroApi(f"{nome} é obrigatório", 400)
        if len(texto) > maximo:
            raise ErroApi(f"{nome} deve ter no máximo {maximo} caracteres", 400)
        return texto or None

    def _preco(self, valor):
        try:
            preco = Decimal(str(valor)).quantize(Decimal("0.01"))
        except (InvalidOperation, ValueError, TypeError):
            raise ErroApi("preço inválido", 400)
        if not preco.is_finite() or preco <= 0 or preco > self.PRECO_MAX:
            raise ErroApi("O preço deve ser maior que zero e no máximo 9999,99", 400)
        return preco

    @staticmethod
    def _hora(valor, nome):
        for formato in ("%H:%M", "%H:%M:%S"):
            try:
                return datetime.strptime(str(valor).strip(), formato).time()
            except ValueError:
                pass
        raise ErroApi(f"{nome} inválido. Use o formato HH:MM (ex.: 18:00)", 400)

    def _validar_disciplinas(self, itens, preco_padrao=None):
        if not isinstance(itens, list) or not itens:
            raise ErroApi("Escolha ao menos uma disciplina", 400)
        if len(itens) > 30:
            raise ErroApi("Disciplinas demais", 400)
        pares = {}
        for item in itens:
            id_bruto, preco = (item.get("id"), item.get("preco", preco_padrao)) \
                if isinstance(item, dict) else (item, preco_padrao)
            if isinstance(id_bruto, bool) or not re.fullmatch(r"\d+", str(id_bruto)):
                raise ErroApi("id de disciplina inválido", 400)
            if preco is None:
                raise ErroApi("Informe o preço da aula", 400)
            pares[int(id_bruto)] = self._preco(preco)
        if set(pares) != self.repositorio.ids_de_disciplinas_existentes(list(pares)):
            raise ErroApi("Alguma disciplina escolhida não existe", 400)
        return list(pares.items())

    def _validar_faixas(self, lista):
        if not isinstance(lista, list):
            raise ErroApi("disponibilidade deve ser uma lista", 400)
        if len(lista) > 40:
            raise ErroApi("Faixas de horário demais", 400)
        faixas = []
        for item in lista:
            if not isinstance(item, dict):
                raise ErroApi("Cada faixa precisa de dia_semana, hora_inicio e hora_fim", 400)
            dia = Horarios.indice_do_dia(item.get("dia_semana"))
            if dia is None:
                raise ErroApi("dia_semana inválido (use Segunda, Terça, ... ou Seg, Ter, ...)", 400)
            ini = self._hora(item.get("hora_inicio"), "hora_inicio")
            fim = self._hora(item.get("hora_fim"), "hora_fim")
            minutos = (datetime.combine(date.min, fim) - datetime.combine(date.min, ini)) / timedelta(minutes=1)
            if minutos < 60:
                raise ErroApi("Cada faixa precisa terminar pelo menos 1 hora depois de começar", 400)
            faixas.append((dia, ini, fim))
        faixas.sort()
        for anterior, atual in zip(faixas, faixas[1:]):
            if anterior[0] == atual[0] and atual[1] < anterior[2]:
                raise ErroApi(f"Faixas sobrepostas na {NOMES_DIAS[atual[0]]}", 400)
        return [(NOMES_DIAS[d], i, f) for d, i, f in faixas]

    def _campos_do_perfil(self, dados, atual=None):
        def pegar(chave):
            return dados[chave] if chave in dados else (atual or {}).get(chave)
        modalidade = pegar("modalidade") or "ambos"
        if modalidade not in MODALIDADES:
            raise ErroApi("modalidade deve ser online, presencial ou ambos", 400)
        return {
            "descricao": self._texto(pegar("descricao"), "descricao", 2000),
            "formacao": self._texto(pegar("formacao"), "formacao", 255),
            "experiencia": self._texto(pegar("experiencia"), "experiencia", 2000, obrigatorio=False),
            "modalidade": modalidade,
        }

    def _perfil(self, id_usuario):
        perfil = self.repositorio.perfil(id_usuario)
        if not perfil:
            raise ErroApi("Você ainda não se cadastrou como professor", 403)
        return perfil

    # --- casos de uso ---
    def cadastrar(self, id_usuario, dados):
        if self.repositorio.perfil(id_usuario):
            raise ErroApi("Você já tem um cadastro de professor", 409)
        campos = self._campos_do_perfil(dados)
        disciplinas = self._validar_disciplinas(dados.get("disciplinas"), dados.get("preco"))
        faixas = self._validar_faixas(dados.get("disponibilidade") or [])
        id_professor = self.repositorio.criar(id_usuario, campos, disciplinas, faixas)
        return {"id_professor": id_professor, "status": "pendente"}

    def status(self, id_usuario):
        perfil = self.repositorio.perfil(id_usuario)
        if not perfil:
            return {"cadastrado": False}
        return {"cadastrado": True, "id_professor": perfil["id_professor"], "status": perfil["status"]}

    def obter_perfil(self, id_usuario):
        p = self._perfil(id_usuario)
        disciplinas = self.obter_disciplinas(id_usuario)
        return {
            "id_professor": p["id_professor"], "nome": p["nome"], "email": p["email"],
            "foto": p["foto"], "descricao": p["descricao"], "formacao": p["formacao"],
            "experiencia": p["experiencia"], "modalidade": p["modalidade"], "status": p["status"],
            "tem_comprovante": bool(p["comprovante"]),
            "materia": disciplinas[0]["nome"] if disciplinas else None,
            "disciplinas": disciplinas,
        }

    def atualizar_perfil(self, id_usuario, dados):
        p = self._perfil(id_usuario)
        nome = self._texto(dados.get("nome", p["nome"]), "nome", 100)
        campos = self._campos_do_perfil(dados, atual=p)
        self.repositorio.atualizar_perfil(id_usuario, p["id_professor"], nome, campos)
        return self.obter_perfil(id_usuario)

    def obter_disciplinas(self, id_usuario):
        p = self._perfil(id_usuario)
        return [{"id": d["id_disciplina"], "nome": d["nome"], "preco": _float(d["preco"])}
                for d in self.repositorio.disciplinas(p["id_professor"])]

    def atualizar_disciplinas(self, id_usuario, dados):
        p = self._perfil(id_usuario)
        disciplinas = self._validar_disciplinas(dados.get("disciplinas"), dados.get("preco"))
        self.repositorio.substituir_disciplinas(p["id_professor"], disciplinas)
        return self.obter_disciplinas(id_usuario)

    def obter_disponibilidade(self, id_usuario):
        p = self._perfil(id_usuario)
        faixas = []
        for f in self.repositorio.disponibilidade(p["id_professor"]):
            dia = Horarios.indice_do_dia(f["dia_semana"])
            ini, fim = Horarios._hora(f["hora_inicio"]), Horarios._hora(f["hora_fim"])
            if dia is not None and ini and fim:
                faixas.append((dia, ini, fim))
        faixas.sort()
        return [{"dia_semana": NOMES_DIAS[d], "hora_inicio": i.strftime("%H:%M"),
                 "hora_fim": f.strftime("%H:%M")} for d, i, f in faixas]

    def atualizar_disponibilidade(self, id_usuario, dados):
        p = self._perfil(id_usuario)
        faixas = self._validar_faixas(dados.get("disponibilidade"))
        self.repositorio.substituir_faixas(p["id_professor"], faixas)
        return self.obter_disponibilidade(id_usuario)

    def enviar_documentos(self, id_usuario, foto, comprovante):
        p = self._perfil(id_usuario)
        if not foto and not comprovante:
            raise ErroApi("Envie a foto e/ou o comprovante de formação", 400)
        # valida e grava os dois ANTES de mexer no banco
        nome_foto = nome_comprovante = None
        if foto:
            nome_foto = self.arquivos.salvar(foto, {"jpg", "png"}, self.FOTO_MAX, "fotos", "foto")
        if comprovante:
            nome_comprovante = self.arquivos.salvar(
                comprovante, {"pdf", "jpg", "png"}, self.COMPROVANTE_MAX, "comprovantes", "comprovante")
        if nome_foto:
            self.repositorio.salvar_foto(id_usuario, f"/api/arquivos/fotos/{nome_foto}")
        if nome_comprovante:
            self.repositorio.salvar_comprovante(p["id_professor"], nome_comprovante)
        return {"foto": f"/api/arquivos/fotos/{nome_foto}" if nome_foto else None,
                "comprovante_enviado": bool(nome_comprovante)}


# ---------- CONTROLLER ----------
class CadastroProfessorController:
    def __init__(self, service, autenticacao, arquivos):
        self.service = service
        self.arquivos = arquivos
        self.bp = Blueprint("cadastro_professor", __name__)
        protegida = autenticacao.requer_login
        regras = [
            ("/api/professor/cadastro", self.cadastrar, ["POST"]),
            ("/api/professor/status", self.status, ["GET"]),
            ("/api/professor/perfil", self.ver_perfil, ["GET"]),
            ("/api/professor/perfil", self.editar_perfil, ["PUT"]),
            ("/api/professor/disciplinas", self.ver_disciplinas, ["GET"]),
            ("/api/professor/disciplinas", self.editar_disciplinas, ["PUT"]),
            ("/api/professor/disponibilidade", self.ver_disponibilidade, ["GET"]),
            ("/api/professor/disponibilidade", self.editar_disponibilidade, ["PUT"]),
            ("/api/professor/documentos", self.documentos, ["POST"]),
        ]
        for caminho, funcao, metodos in regras:
            self.bp.add_url_rule(caminho, view_func=protegida(funcao), methods=metodos)
        # as fotos de perfil são públicas (aparecem na busca); o comprovante NÃO é servido aqui
        self.bp.add_url_rule("/api/arquivos/fotos/<nome>", view_func=self.foto, methods=["GET"])

    @staticmethod
    def _json():
        return request.get_json(silent=True) or {}

    def cadastrar(self):
        resultado = self.service.cadastrar(g.id_usuario, self._json())
        return jsonify({"mensagem": "Cadastro enviado para análise", **resultado}), 201

    def status(self):
        return jsonify(self.service.status(g.id_usuario)), 200

    def ver_perfil(self):
        return jsonify(self.service.obter_perfil(g.id_usuario)), 200

    def editar_perfil(self):
        return jsonify(self.service.atualizar_perfil(g.id_usuario, self._json())), 200

    def ver_disciplinas(self):
        return jsonify(self.service.obter_disciplinas(g.id_usuario)), 200

    def editar_disciplinas(self):
        return jsonify(self.service.atualizar_disciplinas(g.id_usuario, self._json())), 200

    def ver_disponibilidade(self):
        return jsonify(self.service.obter_disponibilidade(g.id_usuario)), 200

    def editar_disponibilidade(self):
        return jsonify(self.service.atualizar_disponibilidade(g.id_usuario, self._json())), 200

    def documentos(self):
        resultado = self.service.enviar_documentos(
            g.id_usuario, request.files.get("foto"), request.files.get("comprovante"))
        return jsonify({"mensagem": "Documentos recebidos", **resultado}), 200

    def foto(self, nome):
        if not NOME_FOTO.match(nome):
            raise ErroApi("Arquivo não encontrado", 404)
        return send_from_directory(self.arquivos.pasta("fotos"), nome)
