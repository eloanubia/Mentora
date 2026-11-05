from flask import Flask, jsonify
from flask_cors import CORS
from werkzeug.exceptions import HTTPException

from admin import AdminController, AdminRepository, AdminService
from area_professor import AreaProfessorController, AreaProfessorRepository, AreaProfessorService
from aula import AulaController, AulaRepository, AulaService
from cadastro_professor import (Arquivos, CadastroProfessorController,
                                CadastroProfessorRepository, CadastroProfessorService)
from database import Database
from disciplina import DisciplinaController, DisciplinaRepository, DisciplinaService
from erros import ErroApi
from notificacao import NotificacaoController, NotificacaoRepository, NotificacaoService
from professor import ProfessorController, ProfessorRepository, ProfessorService
from seguranca import Autenticacao, Token
from usuario import UsuarioController, UsuarioRepository, UsuarioService


class Api:
    def __init__(self):
        self.app = Flask(__name__)
        CORS(self.app)  # em produção, restrinja: CORS(self.app, origins=["https://seu-front.com"])
        self._registrar_erros()
        self._registrar_rotas()

    def _registrar_rotas(self):
        db = Database()
        token = Token()                      # lê JWT_SECRET do .env
        autenticacao = Autenticacao(token, db)  # protege as rotas (admin é conferido no banco)
        arquivos = Arquivos()                # pasta de uploads (fotos e comprovantes)

        # conta (cadastro, login, /api/me)
        usuarios = UsuarioController(UsuarioService(UsuarioRepository(db), token), autenticacao)

        # público: disciplinas e professores (busca, perfil, horários)
        disciplinas = DisciplinaController(DisciplinaService(DisciplinaRepository(db)))
        servico_professores = ProfessorService(ProfessorRepository(db))
        professores = ProfessorController(servico_professores)

        # aluno (exige login): solicitar aula, minhas aulas, confirmar com PIN, avaliar
        aulas = AulaController(AulaService(AulaRepository(db), servico_professores), autenticacao)

        # professor (exige login): cadastro, perfil, disciplinas, disponibilidade, documentos
        cadastro_prof = CadastroProfessorController(
            CadastroProfessorService(CadastroProfessorRepository(db), arquivos), autenticacao, arquivos)

        # professor: pedidos, agenda, PIN, pagamentos, painel
        area_prof = AreaProfessorController(
            AreaProfessorService(AreaProfessorRepository(db)), autenticacao)

        # notificações (aluno e professor)
        notificacoes = NotificacaoController(NotificacaoService(NotificacaoRepository(db)), autenticacao)

        # admin (aprovar professores)
        admin = AdminController(AdminService(AdminRepository(db)), autenticacao, arquivos)

        for modulo in (usuarios, disciplinas, professores, aulas, cadastro_prof,
                       area_prof, notificacoes, admin):
            self.app.register_blueprint(modulo.bp)

        self.app.add_url_rule("/api/status", view_func=self.status)

    def _registrar_erros(self):
        @self.app.errorhandler(ErroApi)
        def tratar_erro_api(e):
            return jsonify(erro=e.mensagem), e.status

        @self.app.errorhandler(Exception)
        def erro_generico(e):
            if isinstance(e, HTTPException):
                return jsonify(erro=e.description), e.code
            self.app.logger.exception(e)
            return jsonify(erro="Erro interno do servidor."), 500

    def status(self):
        return jsonify({"status": "ok"})

    def run(self):
        self.app.run(debug=True, port=3000)


if __name__ == "__main__":
    Api().run()