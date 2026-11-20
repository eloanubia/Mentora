from flask import Blueprint, g, jsonify, request

from base import RepositorioBase, iso
from erros import ErroApi


# ---------- REPOSITÓRIO ----------
# Faz a comunicação com o banco de dados.
class ChatRepository(RepositorioBase):

    def professor(self, id_professor):
        return self._consultar(
            """SELECT id_professor, id_usuario
               FROM perfil_professor
               WHERE id_professor = %s AND status = 'ativo'""",
            (id_professor,), um=True
        )

    def participante(self, id_conversa, id_usuario):
        return self._consultar(
            """SELECT 1 FROM participante_conversa
               WHERE id_conversa = %s AND id_usuario = %s""",
            (id_conversa, id_usuario), um=True
        ) is not None

    def criar_conversa(self, id_aluno, id_professor):
        conexao = self.db.conectar()

        try:
            with conexao.cursor() as cur:
                cur.execute(
                    """SELECT c.id_conversa
                       FROM conversa c
                       JOIN participante_conversa p
                         ON p.id_conversa = c.id_conversa
                       WHERE p.id_usuario IN (%s, %s)
                       GROUP BY c.id_conversa
                       HAVING COUNT(DISTINCT p.id_usuario) = 2
                       LIMIT 1""",
                    (id_aluno, id_professor)
                )

                existente = cur.fetchone()

                if existente:
                    return existente["id_conversa"]

                cur.execute("INSERT INTO conversa () VALUES ()")
                id_conversa = cur.lastrowid

                cur.execute(
                    """INSERT INTO participante_conversa
                       (id_conversa, id_usuario)
                       VALUES (%s, %s), (%s, %s)""",
                    (id_conversa, id_aluno, id_conversa, id_professor)
                )

            conexao.commit()
            return id_conversa

        except Exception:
            conexao.rollback()
            raise

        finally:
            conexao.close()

    def listar_conversas(self, id_usuario):
        return self._consultar(
            """SELECT c.id_conversa,
                      outro.id_usuario AS id_outro_usuario,
                      outro.nome AS nome_participante,
                      ultima.mensagem AS ultima_mensagem,
                      ultima.data_envio AS data_ultima_mensagem
               FROM conversa c
               JOIN participante_conversa meu
                 ON meu.id_conversa = c.id_conversa
               JOIN participante_conversa outro_part
                 ON outro_part.id_conversa = c.id_conversa
                AND outro_part.id_usuario <> meu.id_usuario
               JOIN usuario outro
                 ON outro.id_usuario = outro_part.id_usuario
               LEFT JOIN (
                   SELECT m1.id_conversa, m1.mensagem, m1.data_envio
                   FROM mensagem m1
                   JOIN (
                       SELECT id_conversa, MAX(id_mensagem) AS ultima_id
                       FROM mensagem
                       GROUP BY id_conversa
                   ) m2 ON m2.ultima_id = m1.id_mensagem
               ) ultima ON ultima.id_conversa = c.id_conversa
               WHERE meu.id_usuario = %s
               ORDER BY ultima.data_envio DESC, c.data_criacao DESC""",
            (id_usuario,)
        )

    def listar_mensagens(self, id_conversa):
        return self._consultar(
            """SELECT m.id_mensagem, m.id_usuario_remetente,
                      u.nome AS nome_remetente, m.mensagem, m.data_envio
               FROM mensagem m
               JOIN usuario u ON u.id_usuario = m.id_usuario_remetente
               WHERE m.id_conversa = %s
               ORDER BY m.data_envio, m.id_mensagem""",
            (id_conversa,)
        )

    def marcar_lidas(self, id_conversa, id_usuario):
        conexao = self.db.conectar()

        try:
            with conexao.cursor() as cur:
                cur.execute(
                    """UPDATE mensagem
                       SET lida = TRUE
                       WHERE id_conversa = %s
                         AND id_usuario_remetente <> %s""",
                    (id_conversa, id_usuario)
                )
            conexao.commit()
        finally:
            conexao.close()

    def enviar_mensagem(self, id_conversa, id_usuario, mensagem):
        conexao = self.db.conectar()

        try:
            with conexao.cursor() as cur:
                cur.execute(
                    """INSERT INTO mensagem
                       (id_conversa, id_usuario_remetente, mensagem)
                       VALUES (%s, %s, %s)""",
                    (id_conversa, id_usuario, mensagem)
                )
                id_mensagem = cur.lastrowid

            conexao.commit()
            return id_mensagem

        except Exception:
            conexao.rollback()
            raise

        finally:
            conexao.close()


# ---------- SERVIÇO ----------
# Contém as regras de funcionamento do chat.
class ChatService:

    def __init__(self, repositorio):
        self.repositorio = repositorio

    def criar_conversa(self, id_usuario, dados):
        try:
            id_professor = int(dados.get("id_professor"))
        except (TypeError, ValueError):
            raise ErroApi("Informe um professor válido.", 400)

        professor = self.repositorio.professor(id_professor)

        if not professor:
            raise ErroApi("Professor não encontrado ou indisponível.", 404)

        if professor["id_usuario"] == id_usuario:
            raise ErroApi("Você não pode conversar consigo mesmo.", 400)

        id_conversa = self.repositorio.criar_conversa(
            id_usuario, professor["id_usuario"]
        )

        return {"id_conversa": id_conversa}

    def listar_conversas(self, id_usuario):
        conversas = self.repositorio.listar_conversas(id_usuario)

        return [
            {
                "id_conversa": c["id_conversa"],
                "id_outro_usuario": c["id_outro_usuario"],
                "nome_participante": c["nome_participante"],
                "ultima_mensagem": c["ultima_mensagem"],
                "data_ultima_mensagem": iso(c["data_ultima_mensagem"])
            }
            for c in conversas
        ]

    def listar_mensagens(self, id_usuario, id_conversa):
        if not self.repositorio.participante(id_conversa, id_usuario):
            raise ErroApi("Conversa não encontrada.", 404)

        self.repositorio.marcar_lidas(id_conversa, id_usuario)

        mensagens = self.repositorio.listar_mensagens(id_conversa)

        return [
            {
                "id": m["id_mensagem"],
                "id_remetente": m["id_usuario_remetente"],
                "nome_remetente": m["nome_remetente"],
                "mensagem": m["mensagem"],
                "data_envio": iso(m["data_envio"])
            }
            for m in mensagens
        ]

    def enviar_mensagem(self, id_usuario, id_conversa, dados):
        if not self.repositorio.participante(id_conversa, id_usuario):
            raise ErroApi("Conversa não encontrada.", 404)

        mensagem = dados.get("mensagem")

        if not isinstance(mensagem, str) or not mensagem.strip():
            raise ErroApi("Digite uma mensagem.", 400)

        mensagem = mensagem.strip()

        if len(mensagem) > 5000:
            raise ErroApi("A mensagem deve ter no máximo 5000 caracteres.", 400)

        id_mensagem = self.repositorio.enviar_mensagem(
            id_conversa, id_usuario, mensagem
        )

        return {"id_mensagem": id_mensagem, "mensagem": mensagem}


# ---------- CONTROLLER ----------
# Define os endereços que o site utilizará para acessar o chat.
class ChatController:

    def __init__(self, service, autenticacao):
        self.service = service
        self.bp = Blueprint("chat", __name__)

        protegida = autenticacao.requer_login

        self.bp.add_url_rule(
            "/api/conversas",
            view_func=protegida(self.listar_conversas),
            methods=["GET"]
        )

        self.bp.add_url_rule(
            "/api/conversas",
            view_func=protegida(self.criar_conversa),
            methods=["POST"]
        )

        self.bp.add_url_rule(
            "/api/conversas/<int:id_conversa>/mensagens",
            view_func=protegida(self.listar_mensagens),
            methods=["GET"]
        )

        self.bp.add_url_rule(
            "/api/conversas/<int:id_conversa>/mensagens",
            view_func=protegida(self.enviar_mensagem),
            methods=["POST"]
        )

    def listar_conversas(self):
        return jsonify(
            self.service.listar_conversas(g.id_usuario)
        ), 200

    def criar_conversa(self):
        resultado = self.service.criar_conversa(
            g.id_usuario, request.get_json(silent=True) or {}
        )
        return jsonify(resultado), 201

    def listar_mensagens(self, id_conversa):
        return jsonify(
            self.service.listar_mensagens(g.id_usuario, id_conversa)
        ), 200

    def enviar_mensagem(self, id_conversa):
        resultado = self.service.enviar_mensagem(
            g.id_usuario,
            id_conversa,
            request.get_json(silent=True) or {}
        )
        return jsonify(resultado), 201
