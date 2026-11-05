# Erro "esperado" da API: carrega a mensagem e o código HTTP que devem ir para o cliente
class ErroApi(Exception):
    def __init__(self, mensagem, status=400):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.status = status