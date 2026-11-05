// =====================================================================
// script.js — telas do site. Os dados vêm da API (veja api.js).
// =====================================================================

// Protege o texto que vem da API/usuários antes de colocá-lo na página (evita código malicioso)
function esc(texto) {
  return String(texto == null ? "" : texto).replace(/[&<>"']/g, c => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" }[c]));
}

// ---------- Menu do topo (escrito uma vez e usado em todas as páginas) ----------
function montarMenu() {
  const logado = !!token();
  const inicial = (usuario().nome || "?")[0];
  const direita = logado
    ? `<a href="buscar.html"><span class="avatar">${esc(inicial)}</span> Meu perfil</a>`
    : `<a href="entrar.html">Entrar</a><a href="cadastro.html" class="btn">Cadastre-se</a>`;
  document.getElementById("menu").innerHTML = `
    <header class="topo">
      <a href="index.html" class="logo"><img src="Imagens/logo.png" alt="Logo Mentora"></a>
      <nav><a href="index.html">Home</a><a href="buscar.html">Buscar professor</a><a href="index.html#como">Como funciona</a></nav>
      <div>${direita}</div>
    </header>`;
}

// ---------- Conta: entrar e criar conta ----------
async function entrar(evento) {
  evento.preventDefault();
  const f = evento.target;
  try {
    const u = await fazerLogin(f.email.value, f.senha.value);
    window.location.href = u.tipo === "admin" ? "admin.html" : "escolha.html";
  } catch (e) { alert(e.message); }
}

async function criarConta(evento) {
  evento.preventDefault(); // impede a página de recarregar
  const f = evento.target;
  if (f.senha.value !== f.confirmar.value) { alert("As senhas não são iguais."); return; }
  try {
    await api(ROTA_CADASTRO, { metodo: "POST", semToken: true,
      corpo: { nome: f.nome.value, email: f.email.value, senha: f.senha.value } });
    await fazerLogin(f.email.value, f.senha.value); // já entra logado depois de criar a conta
    window.location.href = "escolha.html";
  } catch (e) { alert(e.message); }
}

// ---------- Professores (cards) ----------
function notaTexto(p) {
  return p.nota === null || p.nota === undefined ? "Novo" : p.nota; // sem avaliações ainda = "Novo"
}

function fotoOuInicial(p) {
  return p.foto ? `<img class="foto-prof" src="${esc(API_URL + p.foto)}" alt="">`
                : `<span class="avatar grande">${esc((p.nome || "?")[0])}</span>`;
}

function cardProfessor(p) {
  return `<div class="card">
    <div class="linha">
      ${fotoOuInicial(p)}
      <div class="cresce"><b>${esc(p.nome)}</b><br><small class="laranja">${esc(p.materia || "")}</small><br><small>⭐ ${notaTexto(p)} (${p.avaliacoes})</small></div>
      <div class="preco">${p.preco != null ? "R$ " + p.preco : "—"}<br><small>/hora</small></div>
    </div>
    <p><small>${esc(p.descricao || "")}</small></p>
    ${p.disciplinas.map(d => `<span class="tag">${esc(d.nome)}</span>`).join("")}
    <a href="perfil-professor.html?id=${p.id}" class="btn btn-largo">Ver perfil</a>
  </div>`;
}

function mostrarProfessores(lista) {
  document.getElementById("lista").innerHTML = lista.length
    ? lista.map(cardProfessor).join("")
    : '<div class="card centro"><small>Nenhum professor encontrado.</small></div>';
}

// Home: só os 4 primeiros professores (a API já devolve os mais bem avaliados primeiro)
async function carregarDestaques() {
  try { mostrarProfessores(await api("/api/professores?limit=4", { semToken: true })); }
  catch (e) { document.getElementById("lista").innerHTML = `<div class="card centro"><small>${esc(e.message)}</small></div>`; }
}

// ---------- Busca com filtro por disciplina (buscar.html) ----------
let categoria = "Todos";
let nomesCategorias = ["Todos"];
let temporizador;

async function montarCategorias() {
  try {
    const lista = await api("/api/disciplinas", { semToken: true });
    nomesCategorias = ["Todos"].concat(lista.map(d => d.nome));
  } catch (e) { /* sem disciplinas, só aparece o "Todos" */ }
  document.getElementById("categorias").innerHTML = nomesCategorias.map((n, i) =>
    `<button class="chip ${i === 0 ? "ativo" : ""}" onclick="escolherCategoria(this, ${i})">${esc(n)}</button>`).join("");
}

function escolherCategoria(botao, indice) {
  categoria = nomesCategorias[indice];
  document.querySelectorAll("#categorias .chip").forEach(c => c.classList.remove("ativo"));
  botao.classList.add("ativo");
  filtrar();
}

// espera o usuário parar de digitar antes de consultar a API
function filtrarDigitando() {
  clearTimeout(temporizador);
  temporizador = setTimeout(filtrar, 300);
}

async function filtrar() {
  const params = new URLSearchParams();
  const texto = document.getElementById("busca").value.trim();
  if (texto) params.set("busca", texto);
  if (categoria !== "Todos") params.set("disciplina", categoria);
  try {
    const lista = await api("/api/professores?" + params, { semToken: true });
    document.getElementById("total").textContent = lista.length + " professores encontrados";
    mostrarProfessores(lista);
  } catch (e) { document.getElementById("total").textContent = e.message; }
}

// ---------- Abas (mostra uma seção e esconde as outras) ----------
function trocarAba(nome) {
  document.querySelectorAll(".aba").forEach(a => a.classList.remove("ativa"));
  document.getElementById("aba-" + nome).classList.add("ativa");
  document.querySelectorAll(".abas button").forEach(b => b.classList.toggle("ativo", nome.startsWith(b.dataset.aba)));
}

// ---------- Cadastro do professor (3 etapas) ----------
let etapaAtual = 1;

function irEtapa(n) {
  etapaAtual = n;
  document.querySelectorAll(".etapa").forEach((e, i) => e.style.display = (i + 1 === n) ? "block" : "none");
  document.querySelectorAll(".barra span").forEach((b, i) => b.classList.toggle("feita", i < n));
  document.getElementById("passo").textContent = "Etapa " + n + " de 3";
}

function voltar() {
  if (etapaAtual === 1) window.location.href = "escolha.html";
  else irEtapa(etapaAtual - 1);
}

// As disciplinas vêm do banco (cada chip guarda o id da disciplina)
async function carregarDisciplinasCadastro() {
  try {
    const lista = await api("/api/disciplinas", { semToken: true });
    document.getElementById("pdisciplinas").innerHTML = lista.map(d =>
      `<button class="chip" data-id="${d.id}" onclick="this.classList.toggle('ativo')">${esc(d.nome)}</button>`).join("");
  } catch (e) { document.getElementById("pdisciplinas").innerHTML = "<small>" + esc(e.message) + "</small>"; }
}

// Quem já enviou o cadastro (com comprovante) vai direto para a área do professor
async function jaCadastrado() {
  try {
    const p = await api("/api/professor/perfil");
    if (p.tem_comprovante) window.location.href = "professor.html";
  } catch (e) { /* 403 = ainda não é professor: continua no formulário */ }
}

// Envia o cadastro (dados) e depois os documentos (foto + comprovante). O admin vai ver como "pendente".
async function enviarSolicitacao() {
  const valor = id => document.getElementById(id).value.trim();
  const marcados = caixa => [...document.querySelectorAll(caixa + " .chip.ativo")];

  const ids = marcados("#pdisciplinas").map(c => Number(c.dataset.id));
  const dias = marcados("#pdisp").map(c => c.textContent);
  const comprovante = document.getElementById("pcomprovante").files[0];
  const foto = document.getElementById("pfoto").files[0];

  if (!valor("pformacao") || !valor("pbio")) { alert("Preencha a formação e a apresentação."); irEtapa(1); return; }
  if (ids.length === 0) { alert("Escolha pelo menos uma disciplina."); irEtapa(2); return; }
  if (!(Number(valor("pvalor")) > 0)) { alert("Informe o valor da aula."); irEtapa(2); return; }
  if (dias.length === 0 || !valor("phini") || !valor("phfim")) { alert("Marque os dias e o horário disponível."); return; }
  if (!comprovante) { alert("Anexe o comprovante de formação."); return; }
  if (!document.getElementById("pautoriza").checked) { alert("Autorize a análise do perfil para continuar."); return; }

  const botao = document.getElementById("penviar");
  botao.disabled = true;
  try {
    // 1) dados do cadastro (o mesmo valor por hora vale para todas as disciplinas marcadas)
    try {
      await api("/api/professor/cadastro", { metodo: "POST", corpo: {
        formacao: valor("pformacao"), descricao: valor("pbio"),
        disciplinas: ids.map(id => ({ id: id, preco: Number(valor("pvalor")) })),
        disponibilidade: dias.map(d => ({ dia_semana: d, hora_inicio: valor("phini"), hora_fim: valor("phfim") }))
      }});
    } catch (e) {
      if (e.status !== 409) throw e; // 409 = já tinha cadastro; segue só para enviar os documentos
    }
    // 2) documentos (arquivos vão em FormData)
    const arquivos = new FormData();
    arquivos.append("comprovante", comprovante);
    if (foto) arquivos.append("foto", foto);
    await api("/api/professor/documentos", { metodo: "POST", corpo: arquivos });
    window.location.href = "aguardando.html";
  } catch (e) { mostrarErro(e); }
  botao.disabled = false;
}

// ---------- Aulas do aluno (buscar.html) ----------
const STATUS_AULA = { aguardando:"Aguardando professor", recusada:"Recusada", agendada:"Agendada",
  aguardando_confirmacao:"Aguardando confirmação", confirmada:"Confirmada", cancelada:"Cancelada" };

async function mostrarAulas() {
  const div = document.getElementById("aulas");
  try {
    const itens = await api("/api/aluno/aulas");
    div.innerHTML = itens.length === 0 ? '<div class="card centro"><small>Você ainda não tem aulas.</small></div>' : itens.map(a => `
      <div class="card linha">
        <span class="avatar">${esc((a.professor || "?")[0])}</span>
        <div class="cresce"><b>${esc(a.professor)}</b><br><small>${esc(a.disciplina)} · ${esc(a.rotulo || "")}</small></div>
        <span class="tag">${STATUS_AULA[a.status] || esc(a.status)}</span>
        ${a.pode_confirmar ? `<button class="btn" onclick="confirmarAula(${a.id})">Confirmar aula</button>` : ""}
        ${a.pode_avaliar ? `<button class="btn btn-claro" onclick="avaliarAula(${a.id})">Avaliar</button>` : ""}
      </div>`).join("");
  } catch (e) { div.innerHTML = `<div class="card centro"><small>${esc(e.message)}</small></div>`; }
}

// A aula só é confirmada com o PIN que o professor gera (libera o pagamento dele)
async function confirmarAula(id) {
  const pin = prompt("Digite o PIN (4 a 6 números) que o professor te passou:");
  if (!pin) return;
  try { await api("/api/aulas/" + id + "/confirmar", { metodo: "POST", corpo: { pin: pin } }); alert("Aula confirmada!"); mostrarAulas(); }
  catch (e) { mostrarErro(e); }
}

async function avaliarAula(id) {
  const nota = prompt("Qual nota você dá para esta aula? (1 a 5)");
  if (!nota) return;
  const comentario = prompt("Quer deixar um comentário? (opcional)") || "";
  try { await api("/api/aulas/" + id + "/avaliacao", { metodo: "POST", corpo: { nota: nota, comentario: comentario } }); alert("Obrigado pela avaliação!"); mostrarAulas(); }
  catch (e) { mostrarErro(e); }
}

// ---------- Perfil do aluno (buscar.html) ----------
function mostrarPerfilAluno() {
  const u = usuario();
  document.getElementById("ola").textContent = "Olá, " + (u.nome.split(" ")[0] || "") + "! 👋";
  document.getElementById("inicial").textContent = (u.nome || "?")[0];
  document.getElementById("nome").textContent = u.nome;
  document.getElementById("email").textContent = u.email;
}

// ---------- Perfil do professor visto pelo aluno (perfil-professor.html) ----------
let horariosLista = [];
let horarioEscolhido = null;
let disciplinaEscolhida = null;
let professorAtual = null;

async function mostrarPerfilDoProfessor() {
  const id = Number(new URLSearchParams(window.location.search).get("id"));
  const div = document.getElementById("conteudo");
  let p;
  try {
    p = await api("/api/professores/" + id, { semToken: true });
    horariosLista = await api("/api/professores/" + id + "/horarios?dias=14", { semToken: true });
  } catch (e) { div.innerHTML = "<p>Professor não encontrado.</p>"; return; }
  professorAtual = p;
  disciplinaEscolhida = p.disciplinas.length === 1 ? p.disciplinas[0].id : null;

  div.innerHTML = `
    <div class="card">
      <div class="linha">
        ${fotoOuInicial(p)}
        <div class="cresce"><h2 style="margin:0">${esc(p.nome)}</h2><small class="laranja">${esc(p.formacao || "")}</small><br><small>⭐ ${notaTexto(p)} (${p.avaliacoes} avaliações)</small></div>
      </div>
      <h3>Sobre</h3>
      <p><small>${esc(p.descricao || "")}</small></p>
      ${p.experiencia ? `<p><small><b>Experiência:</b> ${esc(p.experiencia)}</small></p>` : ""}
    </div>
    <div class="card">
      <h3>Disciplinas e valores</h3>
      ${p.disciplinas.map(d => `<button class="chip ${p.disciplinas.length === 1 ? "ativo" : ""}" data-disc="${d.id}" onclick="escolherDisciplina(this, ${d.id})">${esc(d.nome)} · R$ ${d.preco}/h</button>`).join("")}
    </div>
    <div class="card">
      <h3>Horários disponíveis</h3>
      ${horariosLista.length === 0 ? "<small>Nenhum horário livre nos próximos dias.</small>" :
        horariosLista.map((h, i) => `<button class="chip" data-hora="${i}" onclick="escolherHorario(this, ${i})">${esc(h.rotulo)}</button>`).join("")}
      <button class="btn btn-largo" style="width:100%" onclick="solicitarAula()">Solicitar aula</button>
    </div>`;
}

function escolherDisciplina(botao, id) {
  disciplinaEscolhida = id;
  document.querySelectorAll("[data-disc]").forEach(c => c.classList.remove("ativo"));
  botao.classList.add("ativo");
}

function escolherHorario(botao, indice) {
  horarioEscolhido = horariosLista[indice];
  document.querySelectorAll("[data-hora]").forEach(c => c.classList.remove("ativo"));
  botao.classList.add("ativo");
}

async function solicitarAula() {
  if (!exigirLogin()) return;
  if (!disciplinaEscolhida) { alert("Escolha a disciplina."); return; }
  if (!horarioEscolhido) { alert("Escolha um horário primeiro."); return; }
  try {
    const r = await api("/api/solicitacoes", { metodo: "POST", corpo: {
      id_professor: professorAtual.id, id_disciplina: disciplinaEscolhida, data_hora: horarioEscolhido.data_hora } });
    alert(r.mensagem);
    window.location.href = "buscar.html";
  } catch (e) { mostrarErro(e); }
}

// =====================================================================
// ÁREA DO PROFESSOR (professor.html)
// =====================================================================
const AVISO_STATUS = {
  pendente: "⏳ Seu perfil está em análise pela equipe Mentora (até 2 dias úteis). Você já pode editar seus dados.",
  recusado: "❌ Seu perfil não foi aprovado. Veja o motivo em Perfil › Notificações e corrija seus dados.",
  inativo: "⛔ Seu perfil está desativado e não aparece nas buscas."
};

async function mostrarPainel() {
  if (!exigirLogin()) return;
  let perfil;
  try { perfil = await api("/api/professor/perfil"); }
  catch (e) {
    if (e.status === 403) { alert("Você ainda não se cadastrou como professor."); window.location.href = "professor-cadastro.html"; }
    else mostrarErro(e);
    return;
  }
  document.querySelectorAll(".p-nome").forEach(e => e.textContent = perfil.nome);
  document.querySelectorAll(".p-materia").forEach(e => e.textContent = perfil.materia || "Sem disciplina");
  document.querySelectorAll(".p-inicial").forEach(e => e.textContent = perfil.nome[0]);
  document.getElementById("pe-nome").value = perfil.nome;
  document.getElementById("pe-formacao").value = perfil.formacao || "";
  document.getElementById("pe-bio").value = perfil.descricao || "";
  if (perfil.status !== "ativo") document.getElementById("aviso-status").innerHTML = `<div class="card">${AVISO_STATUS[perfil.status] || ""}</div>`;

  // cada parte carrega sozinha: se uma falhar, as outras continuam funcionando
  carregarResumo(); mostrarPedidos(); mostrarAgenda(); mostrarPagamentos(); mostrarDisciplinas(); mostrarNotificacoes();
}

function avisoNaDiv(id, e) {
  document.getElementById(id).innerHTML = `<div class="card centro"><small>${esc(e.message)}</small></div>`;
}

async function carregarResumo() {
  try {
    const r = await api("/api/professor/painel");
    document.getElementById("c-aulas").textContent = r.aulas_mes;
    document.getElementById("c-ganhos").textContent = "R$ " + r.ganhos_mes;
    document.getElementById("c-nota").textContent = (r.nota == null ? "—" : r.nota + " ⭐");
    document.getElementById("c-alunos").textContent = r.alunos_ativos;
  } catch (e) { /* perfil ainda não aprovado: os números ficam em "—" */ }
}

async function mostrarPedidos() {
  try {
    const pedidos = await api("/api/professor/pedidos");
    document.getElementById("pedidos").innerHTML = pedidos.length === 0 ? '<div class="card centro"><small>Nenhuma solicitação.</small></div>' : pedidos.map(p => `
      <div class="card">
        <div class="linha"><span class="avatar">${esc((p.aluno || "?")[0])}</span>
          <div><b>${esc(p.aluno)}</b><br><small>${esc(p.disciplina)} · ${esc(p.rotulo || "")}</small><br><b class="laranja">R$ ${p.valor}</b></div></div>
        ${p.status === "pendente"
          ? `<div class="linha" style="margin-top:12px">
               <button class="btn btn-claro cresce" onclick="responder(${p.id}, 'recusar')">✗ Recusar</button>
               <button class="btn cresce" onclick="responder(${p.id}, 'aceitar')">✓ Aceitar</button></div>`
          : `<span class="tag">${esc(p.status)}</span>`}
      </div>`).join("");
    const pendentes = pedidos.filter(p => p.status === "pendente").length;
    document.querySelectorAll(".contador").forEach(e => e.textContent = pendentes);
  } catch (e) { avisoNaDiv("pedidos", e); }
}

async function responder(id, acao) {
  try { await api("/api/professor/pedidos/" + id + "/" + acao, { metodo: "POST" }); mostrarPedidos(); mostrarAgenda(); carregarResumo(); }
  catch (e) { mostrarErro(e); }
}

async function mostrarAgenda() {
  try {
    const agenda = await api("/api/professor/agenda");
    // a mesma lista serve para "Próximas aulas" (Início) e para a Agenda
    const html = agenda.length === 0 ? '<div class="card centro"><small>Nenhuma aula agendada.</small></div>' : agenda.map(a => `
      <div class="card linha">
        <b class="laranja">${esc(a.hora)}</b>
        <div class="cresce"><b>${esc(a.aluno)}</b><br><small>${esc(a.disciplina)} · ${esc(a.dia)}</small></div>
        <a href="#" class="laranja" onclick="gerarPin(${a.id}); return false;">PIN →</a>
      </div>`).join("");
    document.getElementById("proximas").innerHTML = html;
    document.getElementById("agenda").innerHTML = html;
  } catch (e) { avisoNaDiv("proximas", e); avisoNaDiv("agenda", e); }
}

async function mostrarPagamentos() {
  try {
    const lista = await api("/api/professor/pagamentos");
    document.getElementById("pagamentos").innerHTML = lista.length === 0 ? '<div class="card centro"><small>Nenhum pagamento ainda.</small></div>' : lista.map(p => `
      <div class="card linha">
        <span class="avatar">${esc((p.aluno || "?")[0])}</span>
        <div class="cresce"><b>${esc(p.aluno)}</b><br><small>${esc(p.rotulo || "")} · R$ ${p.valor}</small></div>
        <span class="tag">${p.status === "liberado" ? "Liberado" : "Retido"}</span>
      </div>`).join("");
  } catch (e) { avisoNaDiv("pagamentos", e); }
}

// O PIN é mostrado ao professor, que o passa ao aluno; o aluno digita para confirmar a aula
async function gerarPin(idAula) {
  try {
    const r = await api("/api/aulas/" + idAula + "/pin", { metodo: "POST" });
    alert("PIN de confirmação: " + r.pin + "\nVálido por " + r.valido_por_minutos + " minutos.");
  } catch (e) { mostrarErro(e); }
}

// Editar perfil: a matéria vem das disciplinas (aba "Minhas disciplinas"), por isso não há campo de matéria
async function salvarPerfilProfessor(evento) {
  evento.preventDefault();
  try {
    const p = await api("/api/professor/perfil", { metodo: "PUT", corpo: {
      nome: document.getElementById("pe-nome").value, formacao: document.getElementById("pe-formacao").value,
      descricao: document.getElementById("pe-bio").value } });
    document.querySelectorAll(".p-nome").forEach(e => e.textContent = p.nome);
    localStorage.setItem("nome", p.nome);
    alert("Perfil atualizado!");
    trocarAba("perfil");
  } catch (e) { mostrarErro(e); }
}

// Minhas disciplinas: clicar marca/desmarca (salvo no banco)
let todasDisciplinas = [];
let minhasDisciplinas = [];

async function mostrarDisciplinas() {
  try {
    todasDisciplinas = await api("/api/disciplinas", { semToken: true });
    minhasDisciplinas = await api("/api/professor/disciplinas");
    desenharDisciplinas();
  } catch (e) { avisoNaDiv("disciplinas", e); }
}

function desenharDisciplinas() {
  const ids = minhasDisciplinas.map(d => d.id);
  document.getElementById("disciplinas").innerHTML = todasDisciplinas.map(d =>
    `<button class="chip ${ids.includes(d.id) ? "ativo" : ""}" onclick="alternarDisciplina(${d.id})">${esc(d.nome)}</button>`).join("");
}

async function alternarDisciplina(id) {
  let nova = minhasDisciplinas.map(d => ({ id: d.id, preco: d.preco }));
  if (nova.some(d => d.id === id)) nova = nova.filter(d => d.id !== id);        // tira
  else nova.push({ id: id, preco: nova.length ? nova[0].preco : 0 });           // coloca (mesmo preço da primeira)
  if (nova.length === 0) { alert("Você precisa ensinar pelo menos uma disciplina."); return; }
  try {
    minhasDisciplinas = await api("/api/professor/disciplinas", { metodo: "PUT", corpo: { disciplinas: nova } });
    desenharDisciplinas();
  } catch (e) { mostrarErro(e); }
}

// Notificações (inclusive o resultado da análise do admin, com o motivo se foi recusado)
async function mostrarNotificacoes() {
  try {
    const r = await api("/api/notificacoes");
    document.getElementById("qtdNotif").textContent = r.nao_lidas ? " (" + r.nao_lidas + ")" : "";
    document.getElementById("notificacoes").innerHTML = r.itens.length === 0
      ? '<div class="card centro"><small>Nenhuma notificação por enquanto.</small></div>'
      : `<button class="btn btn-claro" onclick="marcarLidas()">Marcar todas como lidas</button>` +
        r.itens.map(n => `<div class="card">🔔 ${n.lida ? esc(n.texto) : "<b>" + esc(n.texto) + "</b>"}<br><small>${esc(n.quando || "")}</small></div>`).join("");
  } catch (e) { avisoNaDiv("notificacoes", e); }
}

async function marcarLidas() {
  try { await api("/api/notificacoes/lidas", { metodo: "POST" }); mostrarNotificacoes(); }
  catch (e) { mostrarErro(e); }
}

// =====================================================================
// PAINEL DO ADMINISTRADOR (admin.html)
// Só entra quem tem conta com tipo = 'admin'; a API confere isso em cada pedido.
// =====================================================================
let candidatos = [];
let filtroAdmin = "pendente";
const STATUS_ADMIN = { pendente:"Pendente", ativo:"Aprovado", recusado:"Recusado", inativo:"Inativo" };

async function entrarAdmin(evento) {
  evento.preventDefault();
  const f = evento.target;
  try { await fazerLogin(f.email.value, f.senha.value); await mostrarAdmin(); }
  catch (e) { erroAdmin(e); }
}

// Se já estava logado, tenta abrir direto o painel
async function iniciarAdmin() {
  if (token()) { try { await mostrarAdmin(); } catch (e) { /* mostra o login */ } }
}

// 401 = sem login / sessão expirada, 403 = conta que não é de administrador
function erroAdmin(e) {
  if (e.status === 401 || e.status === 403) {
    ["token", "nome", "email", "tipo"].forEach(k => localStorage.removeItem(k));
    document.getElementById("login").style.display = "block";
    document.getElementById("painel").style.display = "none";
    alert(e.status === 403 ? "Esta conta não é de administrador." : "Entre novamente para continuar.");
  } else alert(e.message);
}

async function mostrarAdmin() {
  candidatos = await api("/api/admin/professores"); // lança erro 403 se a conta não for admin
  document.getElementById("login").style.display = "none";
  document.getElementById("painel").style.display = "block";
  voltarLista(false);
}

function sairAdmin() { sair(); }

// ---------- Lista de candidaturas ----------
function escolherFiltro(status) { filtroAdmin = status; desenharLista(); }

function desenharLista() {
  Object.keys(STATUS_ADMIN).forEach(s => {
    document.getElementById("qtd-" + s).textContent = candidatos.filter(c => c.status === s).length;
    document.querySelector(`[data-filtro="${s}"]`).classList.toggle("ativo", s === filtroAdmin);
  });
  const lista = candidatos.filter(c => c.status === filtroAdmin);
  document.getElementById("listaCandidatos").innerHTML = lista.length === 0
    ? '<div class="card centro"><small>Nenhuma candidatura nesta categoria.</small></div>'
    : lista.map(c => `
      <div class="card linha">
        <span class="avatar grande">${esc((c.nome || "?")[0])}</span>
        <div class="cresce"><b>${esc(c.nome)}</b><br><small>${esc(c.formacao)}</small><br>
          <small>${c.tem_comprovante ? "📎 comprovante enviado" : "⚠️ sem comprovante"}</small></div>
        <button class="btn" onclick="abrirCandidato(${c.id})">Analisar</button>
      </div>`).join("");
}

// volta para a lista; recarrega da API para mostrar o status atualizado
async function voltarLista(recarregar = true) {
  document.getElementById("detalhe").style.display = "none";
  document.getElementById("vistaLista").style.display = "block";
  if (recarregar) { try { candidatos = await api("/api/admin/professores"); } catch (e) { erroAdmin(e); return; } }
  desenharLista();
}

// ---------- Tela de análise de um candidato ----------
async function abrirCandidato(id) {
  let c;
  try { c = await api("/api/admin/professores/" + id); } catch (e) { erroAdmin(e); return; }

  const itens = ["Nome e dados conferem com o comprovante", "A formação é compatível com as disciplinas escolhidas",
                 "O comprovante é legível e parece autêntico", "A apresentação é adequada para a plataforma"];

  let decisao;
  if (c.status === "pendente") {
    decisao = `
      <h3>Checklist do administrador</h3>
      ${itens.map(t => `<p><label style="font-weight:normal;margin:6px 0"><input type="checkbox" class="conferido"> ${t}</label></p>`).join("")}
      <label>Motivo (obrigatório para recusar — o professor recebe por notificação)</label>
      <textarea rows="3" id="motivo" maxlength="200" placeholder="Explique ao candidato o que precisa ser corrigido..."></textarea>
      <div class="linha" style="margin-top:14px">
        <button class="btn btn-claro cresce" onclick="decidir(${c.id}, 'recusado')">✗ Recusar</button>
        <button class="btn cresce" onclick="decidir(${c.id}, 'ativo')">✓ Aprovar professor</button>
      </div>`;
  } else {
    decisao = `<h3>Decisão</h3><p><span class="tag">${STATUS_ADMIN[c.status]}</span></p>
      ${c.status === "recusado" ? "<p><small>O motivo da recusa foi enviado ao professor por notificação.</small></p>" : ""}
      <div class="linha">
        ${c.status === "ativo" ? `<button class="btn btn-claro" onclick="decidir(${c.id}, 'inativo')">Desativar professor</button>` : ""}
        ${c.status === "inativo" ? `<button class="btn" onclick="decidir(${c.id}, 'ativo')">Reativar professor</button>` : ""}
        <button class="btn btn-claro" onclick="decidir(${c.id}, 'pendente')">↩ Reabrir análise</button>
      </div>`;
  }

  document.getElementById("conteudoDetalhe").innerHTML = `
    <div class="card">
      <div class="linha">${c.foto ? `<img class="foto-prof" src="${esc(API_URL + c.foto)}" alt="">` : `<span class="avatar grande">${esc((c.nome || "?")[0])}</span>`}
        <div class="cresce"><h2 style="margin:0">${esc(c.nome)}</h2><small>${esc(c.email)}</small></div>
        <span class="tag">${STATUS_ADMIN[c.status]}</span></div>
    </div>
    <div class="card">
      <h3>Dados do cadastro</h3>
      <p><b>Formação:</b> ${esc(c.formacao)}</p>
      <p><b>Apresentação:</b><br><small>${esc(c.descricao) || "—"}</small></p>
      <p><b>Experiência:</b><br><small>${esc(c.experiencia) || "—"}</small></p>
      <p><b>Modalidade:</b> ${esc(c.modalidade)}</p>
      <p><b>Disciplinas e valores:</b><br>${c.disciplinas.map(d => `<span class="tag">${esc(d.nome)} · R$ ${d.preco}/h</span>`).join("") || "—"}</p>
      <p><b>Disponibilidade:</b><br>${c.disponibilidade.map(d => `<span class="tag">${esc(d.dia_semana)} ${esc(d.hora_inicio)}–${esc(d.hora_fim)}</span>`).join("") || "—"}</p>
    </div>
    <div class="card"><h3>Comprovante de formação / certificação</h3><div id="areaComprovante"><small>Carregando...</small></div></div>
    <div class="card">
      <h3>Verificação automática</h3>
      ${c.verificacoes.map(v => `<p class="${v.ok ? "ok" : "aviso"}">${v.ok ? "✅" : "⚠️"} ${esc(v.texto)}</p>`).join("")}
    </div>
    <div class="card">${decisao}</div>`;

  document.getElementById("vistaLista").style.display = "none";
  document.getElementById("detalhe").style.display = "block";
  if (c.tem_comprovante) mostrarComprovante(c.id);
  else document.getElementById("areaComprovante").innerHTML = "<small>⚠️ Nenhum comprovante anexado.</small>";
}

// O comprovante só abre com o token do admin, então é baixado pelo JavaScript e exibido a partir do arquivo em memória
async function mostrarComprovante(id) {
  const area = document.getElementById("areaComprovante");
  try {
    const arquivo = await api("/api/admin/professores/" + id + "/comprovante", { blob: true });
    const url = URL.createObjectURL(arquivo);
    area.innerHTML = arquivo.type.startsWith("image")
      ? `<img src="${url}" alt="Comprovante" style="max-width:100%;border:1px solid var(--borda);border-radius:8px">`
      : `<a class="btn btn-claro" href="${url}" target="_blank">📎 Abrir comprovante (PDF)</a>`;
  } catch (e) { area.innerHTML = "<small>" + esc(e.message) + "</small>"; }
}

// ---------- Aprovar, recusar, desativar ou reabrir ----------
async function decidir(id, status) {
  const campo = document.getElementById("motivo");
  const motivo = campo ? campo.value.trim() : "";
  const caixas = document.querySelectorAll(".conferido");
  if (status === "ativo" && caixas.length && document.querySelectorAll(".conferido:checked").length < caixas.length) {
    alert("Marque todos os itens do checklist antes de aprovar."); return;
  }
  if (status === "recusado" && !motivo) { alert("Escreva o motivo da recusa."); return; }
  try {
    await api("/api/admin/professores/" + id, { metodo: "PATCH", corpo: { status: status, motivo: motivo } });
    filtroAdmin = status;
    voltarLista();
  } catch (e) {
    erroAdmin(e);
    if (e.status === 409) voltarLista(); // alguém já mudou o status: recarrega a lista
  }
}
