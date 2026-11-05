#Aqui é feita a conexão com o bd Myqsl
import os
import pymysql

from pymysql.cursors import DictCursor
from dotenv import load_dotenv #Irá ler a arquivo .env

load_dotenv()

class Database:
    #Retorna conexão com o banco e guarda as configurações do banco.

    def __init__(self):
        self.host = os.getenv("DB_HOST", "localhost") 
        self.user = os.getenv("DB_USER")
        self.password  = os.getenv("DB_PASSWORD")
        self.nome = os.getenv("DB_NAME", "mentora")

    def conectar(self):
        return pymysql.connect(
            host=self.host,
            user=self.user,
            password=self.password,
            database=self.nome,
            charset="utf8mb4",
            cursorclass=DictCursor,
            autocommit=False,
        )
