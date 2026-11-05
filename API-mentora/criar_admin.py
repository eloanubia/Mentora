# Cria (ou promove) uma conta de administrador direto pelo terminal.
#   python criar_admin.py admin@mentora.com "Senha1234" "Administrador"
# Se o e-mail já existir, só vira admin (a senha não é alterada).
import sys

import bcrypt
from database import Database

if len(sys.argv) < 3:
    sys.exit('Uso: python criar_admin.py <email> <senha> ["Nome"]')

email = sys.argv[1].strip().lower()
senha = sys.argv[2]
nome = sys.argv[3] if len(sys.argv) > 3 else "Administrador"
if len(senha) < 8:
    sys.exit("A senha deve ter pelo menos 8 caracteres.")

conexao = Database().conectar()
try:
    with conexao.cursor() as cur:
        cur.execute("SELECT id_usuario FROM usuario WHERE email = %s", (email,))
        if cur.fetchone():
            cur.execute("UPDATE usuario SET tipo = 'admin' WHERE email = %s", (email,))
            print(f"Conta existente promovida a admin: {email}")
        else:
            hash_ = bcrypt.hashpw(senha.encode(), bcrypt.gensalt()).decode()
            cur.execute("INSERT INTO usuario (nome, email, senha, tipo) VALUES (%s, %s, %s, 'admin')",
                        (nome, email, hash_))
            print(f"Admin criado: {email}")
    conexao.commit()
finally:
    conexao.close()
