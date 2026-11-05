# Mentora — API + site (com tela de administrador)

## Como rodar (passo a passo no terminal)
1. Banco: `mysql -u root -p < mentora.sql`  (ATENÇÃO: apaga e recria o banco "mentora")
2. API:
   ```
   cd API-mentora
   python -m venv venv && source venv/bin/activate      # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   cp .env.example .env                                  # edite DB_PASSWORD e JWT_SECRET
   python criar_admin.py admin@mentora.com "Senha1234" "Administrador"
   python app.py                                         # porta 3000
   ```
3. Site (outro terminal): `cd Mentora_site/mentora && python -m http.server 5500` e abra http://localhost:5500
   Painel do admin: http://localhost:5500/admin.html  (se a API mudar de endereço, troque só `API_URL` no `api.js`)

## Teste rápido pelo terminal (curl)
```
curl http://localhost:3000/api/status
curl -X POST http://localhost:3000/api/cadastro -H "Content-Type: application/json" -d @cadastro.json
curl -X POST http://localhost:3000/api/login -H "Content-Type: application/json" -d '{"email":"admin@mentora.com","senha":"Senha1234"}'
# copie o "token" da resposta e use:
curl http://localhost:3000/api/admin/professores -H "Authorization: Bearer SEU_TOKEN"
curl http://localhost:3000/api/admin/professores/3 -H "Authorization: Bearer SEU_TOKEN"
curl -X PATCH http://localhost:3000/api/admin/professores/3 -H "Authorization: Bearer SEU_TOKEN" -H "Content-Type: application/json" -d '{"status":"ativo"}'
```
Sem token → 401. Token de conta comum → 403. Mudança de status repetida/inválida → 409.

## O que foi adicionado nesta versão
- `seguranca.py` (novo): JWT (12 h), `requer_login` e `requer_admin`. O `tipo` é conferido no banco a cada pedido.
- `usuario.py` (novo): `POST /api/cadastro` (também `/api/usuarios`), `POST /api/login`, `GET/PUT /api/me`. Senhas com bcrypt, e-mail em minúsculas, senha de 8 a 72 caracteres.
- `app.py`: `Autenticacao(token, db)`.
- `criar_admin.py`, `.env.example`, `requirements.txt` e `mentora.sql` incluídos na pasta.
- Atenção: os usuários de exemplo do `mentora.sql` têm hash fictício; não dá para entrar com eles. Crie contas novas pelo site/cadastro.

## Rotas que a tela de admin usa
GET /api/admin/professores · GET /api/admin/professores/<id> · PATCH /api/admin/professores/<id> · GET /api/admin/professores/<id>/comprovante
