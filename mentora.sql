-- ============================================================
-- MENTORA  (versão 2: já inclui as colunas de tipo, comprovante, PIN e a tabela notificacao)
-- ATENÇÃO: o DROP DATABASE abaixo apaga tudo. Use este arquivo só para criar o banco do zero.
-- Conteúdo: 1) Estrutura  2) Índices  3) Dados de exemplo
--           4) View  5) Consultas / operações de demonstração
-- ============================================================

DROP DATABASE IF EXISTS mentora;
CREATE DATABASE mentora CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci; -- faz acentos e emojis serem salvos de maneira correta
USE mentora;

-- ============================================================
-- 1) ESTRUTURA
-- ============================================================

-- BLOCO 1: IDENTIDADE E PERFIL
CREATE TABLE usuario (
    id_usuario INT AUTO_INCREMENT PRIMARY KEY,
    nome VARCHAR(100) NOT NULL,
    email VARCHAR(150) NOT NULL UNIQUE,
    senha VARCHAR(255) NOT NULL,              -- armazenar HASH (ex.: bcrypt), nunca texto puro
    telefone VARCHAR(20),
    data_nascimento DATE,
    foto VARCHAR(255),
    tipo VARCHAR(10) NOT NULL DEFAULT 'comum', -- comum | admin
    data_cadastro DATETIME DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_usuario_tipo CHECK (tipo IN ('comum', 'admin'))
);

CREATE TABLE perfil_professor (
    id_professor INT AUTO_INCREMENT PRIMARY KEY,
    id_usuario INT NOT NULL UNIQUE,           -- (1,1):(0,1) com usuario
    descricao TEXT,
    formacao VARCHAR(255),
    experiencia TEXT,
    comprovante VARCHAR(255),                 -- arquivo do comprovante de formação
    modalidade VARCHAR(50),                   -- online - presencial - ambos
    status VARCHAR(30) NOT NULL DEFAULT 'pendente',  -- pendente - ativo - recusado - inativo
    FOREIGN KEY (id_usuario) REFERENCES usuario(id_usuario)
);

CREATE TABLE endereco (
    id_endereco INT AUTO_INCREMENT PRIMARY KEY,
    id_usuario INT NOT NULL,
    cep VARCHAR(10),
    estado VARCHAR(50),
    cidade VARCHAR(100),
    bairro VARCHAR(100),
    logradouro VARCHAR(150),
    numero VARCHAR(10),
    FOREIGN KEY (id_usuario) REFERENCES usuario(id_usuario)
);

-- BLOCO 2: ENSINO
CREATE TABLE disciplina (
    id_disciplina INT AUTO_INCREMENT PRIMARY KEY,
    nome VARCHAR(100) NOT NULL,
    descricao TEXT
);

CREATE TABLE professor_disciplina (
    id_professor INT NOT NULL,
    id_disciplina INT NOT NULL,
    preco DECIMAL(10,2) NOT NULL,
    PRIMARY KEY (id_professor, id_disciplina),
    FOREIGN KEY (id_professor) REFERENCES perfil_professor(id_professor),
    FOREIGN KEY (id_disciplina) REFERENCES disciplina(id_disciplina)
);

CREATE TABLE disponibilidade (
    id_disponibilidade INT AUTO_INCREMENT PRIMARY KEY,
    id_professor INT NOT NULL,
    dia_semana VARCHAR(20) NOT NULL,
    hora_inicio TIME NOT NULL,
    hora_fim TIME NOT NULL,
    FOREIGN KEY (id_professor) REFERENCES perfil_professor(id_professor)
);

-- BLOCO 3: SOLICITAÇÃO
CREATE TABLE solicitacao_aula (
    id_solicitacao INT AUTO_INCREMENT PRIMARY KEY,
    id_usuario_aluno INT NOT NULL,
    id_professor INT NOT NULL,
    id_disciplina INT NOT NULL,
    data_hora_solicitada DATETIME,            -- horário escolhido pelo aluno
    data_solicitacao DATETIME DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(30) DEFAULT 'pendente',    -- pendente | aceita | recusada
    FOREIGN KEY (id_usuario_aluno) REFERENCES usuario(id_usuario),
    FOREIGN KEY (id_professor) REFERENCES perfil_professor(id_professor),
    FOREIGN KEY (id_disciplina) REFERENCES disciplina(id_disciplina)
);

-- BLOCO 4: CONTRATO
CREATE TABLE contrato (
    id_contrato INT AUTO_INCREMENT PRIMARY KEY,
    id_usuario_aluno INT NOT NULL,
    id_professor INT NOT NULL,
    id_disciplina INT NOT NULL,
    quantidade_aulas INT NOT NULL,
    valor_total DECIMAL(10,2) NOT NULL,
    data_inicio DATE,
    data_fim DATE,
    status VARCHAR(30) DEFAULT 'ativo',       -- ativo - concluido - cancelado
    FOREIGN KEY (id_usuario_aluno) REFERENCES usuario(id_usuario),
    FOREIGN KEY (id_professor) REFERENCES perfil_professor(id_professor),
    FOREIGN KEY (id_disciplina) REFERENCES disciplina(id_disciplina)
);

-- BLOCO 5: EXECUÇÃO
CREATE TABLE aula (
    id_aula INT AUTO_INCREMENT PRIMARY KEY,
    id_contrato INT NOT NULL,
    data_hora DATETIME NOT NULL,
    duracao INT,                              -- em minutos
    status VARCHAR(30) DEFAULT 'agendada',    -- agendada - realizada -cancelada
    confirmada_aluno BOOLEAN DEFAULT FALSE,
    pin VARCHAR(6),                           -- PIN gerado pelo professor
    pin_expira DATETIME,
    pin_tentativas INT NOT NULL DEFAULT 0,    -- erros de PIN seguidos (5 = PIN invalidado)
    FOREIGN KEY (id_contrato) REFERENCES contrato(id_contrato)
);

CREATE TABLE pagamento (
    id_pagamento INT AUTO_INCREMENT PRIMARY KEY,
    id_contrato INT NOT NULL,
    valor DECIMAL(10,2) NOT NULL,
    metodo VARCHAR(30),                       -- pix - cartao - boleto
    status VARCHAR(30) DEFAULT 'retido',      -- retido - liberado - reembolsado - em_disputa
    data_pagamento DATETIME DEFAULT CURRENT_TIMESTAMP,
    data_liberacao DATETIME,
    FOREIGN KEY (id_contrato) REFERENCES contrato(id_contrato)
);

-- BLOCO 6: AVALIAÇÃO
CREATE TABLE avaliacao (
    id_avaliacao INT AUTO_INCREMENT PRIMARY KEY,
    id_aula INT NOT NULL,
    id_usuario_aluno INT NOT NULL,
    id_professor INT NOT NULL,
    nota INT NOT NULL CHECK (nota BETWEEN 1 AND 5),
    comentario TEXT,
    data_avaliacao DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (id_aula) REFERENCES aula(id_aula),
    FOREIGN KEY (id_usuario_aluno) REFERENCES usuario(id_usuario),
    FOREIGN KEY (id_professor) REFERENCES perfil_professor(id_professor)
);

-- BLOCO 7: DISPUTA
CREATE TABLE disputa (
    id_disputa INT AUTO_INCREMENT PRIMARY KEY,
    id_pagamento INT NOT NULL,
    id_usuario INT NOT NULL,
    motivo VARCHAR(100),
    descricao TEXT,
    data_abertura DATETIME DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(30) DEFAULT 'aberta',      -- aberta - em_analise - encerrada
    resultado VARCHAR(50),
    FOREIGN KEY (id_pagamento) REFERENCES pagamento(id_pagamento),
    FOREIGN KEY (id_usuario) REFERENCES usuario(id_usuario)
);

-- BLOCO 8: MENSAGENS
CREATE TABLE conversa (
    id_conversa INT AUTO_INCREMENT PRIMARY KEY,
    data_criacao DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE participante_conversa (
    id_conversa INT NOT NULL,
    id_usuario INT NOT NULL,
    PRIMARY KEY (id_conversa, id_usuario),
    FOREIGN KEY (id_conversa) REFERENCES conversa(id_conversa),
    FOREIGN KEY (id_usuario) REFERENCES usuario(id_usuario)
);

CREATE TABLE mensagem (
    id_mensagem INT AUTO_INCREMENT PRIMARY KEY,
    id_conversa INT NOT NULL,
    id_usuario_remetente INT NOT NULL,
    mensagem TEXT NOT NULL,
    data_envio DATETIME DEFAULT CURRENT_TIMESTAMP,
    lida BOOLEAN DEFAULT FALSE,
    FOREIGN KEY (id_conversa) REFERENCES conversa(id_conversa),
    FOREIGN KEY (id_usuario_remetente) REFERENCES usuario(id_usuario)
);

-- BLOCO 9: NOTIFICAÇÕES
CREATE TABLE notificacao (
    id_notificacao INT AUTO_INCREMENT PRIMARY KEY,
    id_usuario INT NOT NULL,
    texto VARCHAR(255) NOT NULL,
    lida BOOLEAN NOT NULL DEFAULT FALSE,
    data_criacao DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (id_usuario) REFERENCES usuario(id_usuario)
);

-- ============================================================
-- 2) ÍNDICES (melhoram as buscas mais frequentes do back-end)
-- ============================================================
CREATE INDEX idx_solicitacao_professor ON solicitacao_aula(id_professor, status);
CREATE INDEX idx_solicitacao_aluno     ON solicitacao_aula(id_usuario_aluno);
CREATE INDEX idx_contrato_aluno        ON contrato(id_usuario_aluno);
CREATE INDEX idx_contrato_professor    ON contrato(id_professor);
CREATE INDEX idx_aula_contrato_data    ON aula(id_contrato, data_hora);
CREATE INDEX idx_pagamento_contrato    ON pagamento(id_contrato);
CREATE INDEX idx_avaliacao_professor   ON avaliacao(id_professor);
CREATE INDEX idx_mensagem_conversa     ON mensagem(id_conversa, data_envio);
CREATE INDEX idx_disponib_professor    ON disponibilidade(id_professor);
CREATE INDEX idx_notificacao_usuario   ON notificacao(id_usuario, lida);

-- ============================================================
-- 3) DADOS DE EXEMPLO (para a demonstração)
-- Senhas de exemplo: hash fictício. No back-end real, usar bcrypt.
-- ============================================================

INSERT INTO usuario (nome, email, senha, telefone, data_nascimento) VALUES
('Ana Souza',      'ana.souza@email.com',      '$2b$10$hashfficticio_ana',      '(19) 99111-1111', '2003-04-12'),
('Bruno Lima',     'bruno.lima@email.com',     '$2b$10$hashfficticio_bruno',    '(19) 99222-2222', '2001-09-30'),
('Carla Mendes',   'carla.mendes@email.com',   '$2b$10$hashfficticio_carla',    '(19) 99333-3333', '2004-01-25'),
('Prof. Daniel Rocha',   'daniel.rocha@email.com',   '$2b$10$hashfficticio_daniel',   '(19) 99444-4444', '1988-06-18'),
('Profa. Elisa Martins', 'elisa.martins@email.com',  '$2b$10$hashfficticio_elisa',    '(19) 99555-5555', '1990-11-02'),
('Prof. Felipe Nunes',   'felipe.nunes@email.com',   '$2b$10$hashfficticio_felipe',   '(11) 99666-6666', '1985-03-07');

INSERT INTO perfil_professor (id_usuario, descricao, formacao, experiencia, modalidade, status) VALUES
(4, 'Professor de exatas com didática prática.',          'Licenciatura em Matemática - PUC-Campinas', '8 anos de reforço escolar e pré-vestibular', 'ambos',      'ativo'),
(5, 'Professora de idiomas e redação.',                   'Letras - UNICAMP',                          '6 anos ensinando inglês e redação',            'online',     'ativo'),
(6, 'Engenheiro e professor de programação e física.',    'Engenharia de Computação - USP',            '10 anos de experiência em tecnologia e ensino','presencial', 'pendente');

INSERT INTO endereco (id_usuario, cep, estado, cidade, bairro, logradouro, numero) VALUES
(1, '13010-000', 'SP', 'Campinas', 'Centro',        'Rua Barão de Jaguara', '100'),
(2, '13020-000', 'SP', 'Campinas', 'Cambuí',        'Av. Norte-Sul',        '250'),
(3, '18200-000', 'SP', 'Itapetininga', 'Centro',    'Rua Quinze de Novembro','45'),
(4, '13015-000', 'SP', 'Campinas', 'Bosque',        'Rua Sales de Oliveira','320'),
(6, '01310-000', 'SP', 'São Paulo','Bela Vista',    'Av. Paulista',         '1500');

INSERT INTO disciplina (nome, descricao) VALUES
('Matemática',   'Álgebra, geometria, funções e preparação para vestibular'),
('Inglês',       'Conversação, gramática e preparação para exames'),
('Programação',  'Lógica de programação, Python e desenvolvimento web'),
('Física',       'Mecânica, termologia, eletricidade e ondas'),
('Redação',      'Estrutura dissertativa e preparação para o ENEM'),
('Português',    'Gramática, interpretação de texto e literatura'),
('Química',      'Química geral, orgânica e físico-química'),
('Biologia',     'Citologia, genética, ecologia e fisiologia'),
('História',     'História do Brasil e geral, com foco em vestibular');

INSERT INTO professor_disciplina (id_professor, id_disciplina, preco) VALUES
(1, 1, 80.00),
(1, 4, 90.00),
(2, 2, 70.00),
(2, 5, 75.00),
(3, 3, 100.00),
(3, 4, 95.00);

INSERT INTO disponibilidade (id_professor, dia_semana, hora_inicio, hora_fim) VALUES
(1, 'Segunda', '18:00:00', '21:00:00'),
(1, 'Quarta',  '18:00:00', '21:00:00'),
(2, 'Terça',   '14:00:00', '18:00:00'),
(2, 'Quinta',  '14:00:00', '18:00:00'),
(3, 'Sábado',  '09:00:00', '13:00:00');

INSERT INTO solicitacao_aula (id_usuario_aluno, id_professor, id_disciplina, status) VALUES
(1, 1, 1, 'aceita'),
(2, 2, 2, 'aceita'),
(3, 1, 4, 'pendente'),
(1, 3, 3, 'recusada');

INSERT INTO contrato (id_usuario_aluno, id_professor, id_disciplina, quantidade_aulas, valor_total, data_inicio, data_fim, status) VALUES
(1, 1, 1, 4, 320.00, '2026-10-05', '2026-11-02', 'ativo'),
(2, 2, 2, 2, 140.00, '2026-10-06', '2026-10-20', 'concluido');

INSERT INTO aula (id_contrato, data_hora, duracao, status, confirmada_aluno) VALUES
(1, '2026-10-05 18:30:00', 60, 'realizada', TRUE),
(1, '2026-10-12 18:30:00', 60, 'realizada', TRUE),
(1, '2026-10-19 18:30:00', 60, 'realizada', FALSE),
(1, '2026-10-26 18:30:00', 60, 'agendada',  FALSE),
(2, '2026-10-06 15:00:00', 60, 'realizada', TRUE),
(2, '2026-10-13 15:00:00', 60, 'realizada', TRUE);

INSERT INTO pagamento (id_contrato, valor, metodo, status, data_liberacao) VALUES
(1, 320.00, 'pix',    'retido',   NULL),
(2, 140.00, 'cartao', 'liberado', '2026-10-21 10:00:00');

INSERT INTO avaliacao (id_aula, id_usuario_aluno, id_professor, nota, comentario) VALUES
(1, 1, 1, 5, 'Explicação muito clara, super recomendo!'),
(2, 1, 1, 4, 'Ótima aula, só passamos um pouco do horário.'),
(5, 2, 2, 5, 'Professora excelente, aula dinâmica.'),
(6, 2, 2, 5, 'Aprendi muito sobre conversação.');

INSERT INTO disputa (id_pagamento, id_usuario, motivo, descricao, status, resultado) VALUES
(1, 1, 'Aula não confirmada', 'A aula do dia 19/10 consta como realizada, mas não houve confirmação do aluno.', 'em_analise', NULL);

INSERT INTO conversa () VALUES (), ();
INSERT INTO participante_conversa (id_conversa, id_usuario) VALUES
(1, 1), (1, 4),
(2, 2), (2, 5);

INSERT INTO mensagem (id_conversa, id_usuario_remetente, mensagem, lida) VALUES
(1, 1, 'Olá, professor! Posso agendar a primeira aula para segunda?', TRUE),
(1, 4, 'Claro, Ana! Segunda às 18h30 está ótimo.',                    TRUE),
(2, 2, 'Professora, podemos focar em conversação?',                   TRUE),
(2, 5, 'Com certeza, Bruno! Vamos montar um plano.',                  FALSE);

-- ============================================================
-- 4) VIEW: ranking de professores (usada na tela de busca)
-- ============================================================
CREATE VIEW vw_professores_avaliacao AS
SELECT  p.id_professor,
        u.nome AS professor,
        p.modalidade,
        COUNT(a.id_avaliacao)        AS total_avaliacoes,
        ROUND(AVG(a.nota), 2)        AS nota_media
FROM perfil_professor p
JOIN usuario u            ON u.id_usuario = p.id_usuario
LEFT JOIN avaliacao a     ON a.id_professor = p.id_professor
WHERE p.status = 'ativo'
GROUP BY p.id_professor, u.nome, p.modalidade;

-- ============================================================
-- 5) CONSULTAS E OPERAÇÕES DE DEMONSTRAÇÃO
-- (são as mesmas que o back-end executa nas rotas/endpoints)
-- ============================================================

-- LISTAR PROFESSORES POR DISCIPLINA (tela de busca)
SELECT u.nome AS professor, d.nome AS disciplina, pd.preco, p.modalidade
FROM professor_disciplina pd
JOIN perfil_professor p ON p.id_professor = pd.id_professor
JOIN usuario u          ON u.id_usuario   = p.id_usuario
JOIN disciplina d       ON d.id_disciplina = pd.id_disciplina
WHERE d.nome = 'Matemática' AND p.status = 'ativo'
ORDER BY pd.preco;

-- RANKING DE PROFESSORES (usa a view)
SELECT * FROM vw_professores_avaliacao ORDER BY nota_media DESC;

-- SOLICITAÇÕES PENDENTES DE UM PROFESSOR (painel do professor)
SELECT s.id_solicitacao, a.nome AS aluno, d.nome AS disciplina, s.data_solicitacao
FROM solicitacao_aula s
JOIN usuario a    ON a.id_usuario = s.id_usuario_aluno
JOIN disciplina d ON d.id_disciplina = s.id_disciplina
WHERE s.id_professor = 1 AND s.status = 'pendente';

-- AULAS DE UM ALUNO COM PROFESSOR E DISCIPLINA (agenda)
SELECT au.data_hora, au.status, d.nome AS disciplina, up.nome AS professor
FROM aula au
JOIN contrato c          ON c.id_contrato = au.id_contrato
JOIN disciplina d        ON d.id_disciplina = c.id_disciplina
JOIN perfil_professor pp ON pp.id_professor = c.id_professor
JOIN usuario up          ON up.id_usuario = pp.id_usuario
WHERE c.id_usuario_aluno = 1
ORDER BY au.data_hora;

-- HISTÓRICO DE UMA CONVERSA
SELECT m.data_envio, u.nome AS remetente, m.mensagem, m.lida
FROM mensagem m
JOIN usuario u ON u.id_usuario = m.id_usuario_remetente
WHERE m.id_conversa = 1
ORDER BY m.data_envio;

-- FATURAMENTO POR PROFESSOR (pagamentos liberados)
SELECT u.nome AS professor, SUM(pg.valor) AS total_liberado
FROM pagamento pg
JOIN contrato c          ON c.id_contrato = pg.id_contrato
JOIN perfil_professor pp ON pp.id_professor = c.id_professor
JOIN usuario u           ON u.id_usuario = pp.id_usuario
WHERE pg.status = 'liberado'
GROUP BY u.nome;

-- ---------- Operações de manipulação (INSERT / UPDATE / DELETE) ----------

-- Cadastro de novo aluno (rota POST /usuarios)
INSERT INTO usuario (nome, email, senha, telefone)
VALUES ('Diego Alves', 'diego.alves@email.com', '$2b$10$hashfficticio_diego', '(19) 99777-7777');

-- Professor aceita solicitação (rota PUT /solicitacoes/:id/aceitar)
UPDATE solicitacao_aula SET status = 'aceita' WHERE id_solicitacao = 3;

-- Aluno confirma aula realizada (rota PUT /aulas/:id/confirmar)
UPDATE aula SET confirmada_aluno = TRUE WHERE id_aula = 3;

-- Liberação do pagamento após confirmação (rota PUT /pagamentos/:id/liberar)
UPDATE pagamento SET status = 'liberado', data_liberacao = NOW() WHERE id_pagamento = 1;

-- Remoção de um horário de disponibilidade (rota DELETE /disponibilidades/:id)
DELETE FROM disponibilidade WHERE id_disponibilidade = 5;

-- ---------- Verificação final: contagem de registros por tabela ----------
SELECT 'usuario' AS tabela, COUNT(*) AS registros FROM usuario
UNION ALL SELECT 'perfil_professor', COUNT(*) FROM perfil_professor
UNION ALL SELECT 'endereco', COUNT(*) FROM endereco
UNION ALL SELECT 'disciplina', COUNT(*) FROM disciplina
UNION ALL SELECT 'professor_disciplina', COUNT(*) FROM professor_disciplina
UNION ALL SELECT 'disponibilidade', COUNT(*) FROM disponibilidade
UNION ALL SELECT 'solicitacao_aula', COUNT(*) FROM solicitacao_aula
UNION ALL SELECT 'contrato', COUNT(*) FROM contrato
UNION ALL SELECT 'aula', COUNT(*) FROM aula
UNION ALL SELECT 'pagamento', COUNT(*) FROM pagamento
UNION ALL SELECT 'avaliacao', COUNT(*) FROM avaliacao
UNION ALL SELECT 'disputa', COUNT(*) FROM disputa
UNION ALL SELECT 'conversa', COUNT(*) FROM conversa
UNION ALL SELECT 'participante_conversa', COUNT(*) FROM participante_conversa
UNION ALL SELECT 'mensagem', COUNT(*) FROM mensagem;