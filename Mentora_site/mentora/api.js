// =====================================================================
// api.js — tudo que o site precisa para conversar com a API (Flask)
// Este arquivo vem ANTES do script.js em todas as páginas.
// =====================================================================

// Endereço da API. O app.py roda na porta 3000 (self.app.run(port=3000)).
// Quando publicar a API na internet, troque só esta linha.
const API_URL = "http://localhost:3000";

// Rotas de conta (ficam no usuario.py). Se no seu projeto o caminho for outro, mude AQUI:
const ROTA_LOGIN = "/api/login";
const ROTA_CADASTRO = "/api/cadastro";
const ROTA_ME = "/api/me";

// ---------- Sessão: o token (JWT) fica guardado no navegador ----------
function token() {
  return localStorage.getItem("token");
}

// Dados do usuário logado (gravados no login), usados no menu e nos cumprimentos
function usuario() {
  return {
    nome: localStorage.getItem("nome") || "",
    email: localStorage.getItem("email") || "",
    tipo: localStorage.getItem("tipo") || ""
  };
}

function sair() {
  ["token", "nome", "email", "tipo"].forEach(k => localStorage.removeItem(k));
  window.location.href = "index.html";
}

// Páginas que só funcionam com login mandam o visitante para a tela de entrada
function exigirLogin() {
  if (!token()) { window.location.href = "entrar.html"; return false; }
  return true;
}

// ---------- Função que fala com a API ----------
// api("/api/professores")                                  -> GET
// api("/api/solicitacoes", { metodo:"POST", corpo:{...} }) -> POST com JSON
// Se o corpo for FormData (upload de arquivo), é enviado como arquivo.
// Quando a API responde com erro, lança um Error com a mensagem dela (campo "erro").
async function api(caminho, opcoes = {}) {
  const cabecalhos = {};
  if (token() && !opcoes.semToken) cabecalhos["Authorization"] = "Bearer " + token();
  let corpo = opcoes.corpo;
  if (corpo && !(corpo instanceof FormData)) {
    cabecalhos["Content-Type"] = "application/json";
    corpo = JSON.stringify(corpo);
  }

  let resposta;
  try {
    resposta = await fetch(API_URL + caminho, { method: opcoes.metodo || "GET", headers: cabecalhos, body: corpo });
  } catch (e) {
    throw new Error("Não consegui falar com o servidor. A API está ligada?");
  }

  if (opcoes.blob && resposta.ok) return resposta.blob(); // usado para baixar o comprovante

  const dados = await resposta.json().catch(() => null);
  if (!resposta.ok) {
    const erro = new Error((dados && dados.erro) || "Erro " + resposta.status);
    erro.status = resposta.status;
    throw erro;
  }
  return dados;
}

// Mostra o erro para o usuário; se a sessão expirou (401), manda entrar de novo
function mostrarErro(e) {
  if (e.status === 401) {
    alert("Sua sessão expirou. Entre novamente.");
    window.location.href = "entrar.html";
  } else {
    alert(e.message);
  }
}

// ---------- Login ----------
async function fazerLogin(email, senha) {
  const r = await api(ROTA_LOGIN, { metodo: "POST", corpo: { email: email, senha: senha }, semToken: true });
  localStorage.setItem("token", r.token || r.access_token);
  // pega nome/tipo do usuário (a resposta do login ou, se não vier, a rota /api/me)
  let u = r.usuario || r.user;
  if (!u) { try { u = await api(ROTA_ME); } catch (e) { u = {}; } }
  localStorage.setItem("nome", u.nome || "");
  localStorage.setItem("email", u.email || email);
  localStorage.setItem("tipo", u.tipo || "");
  return u;
}
