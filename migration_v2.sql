-- =========================================================================
-- EXPANSÃO RELACIONAL: DEMANDA #2026-INV05 (Parte 2 - Vendas & RBAC)
-- =========================================================================

-- 1. TABELA DE USUÁRIOS (RBAC)
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome_completo TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    senha_hash TEXT NOT NULL,
    perfil_acesso TEXT NOT NULL CHECK (perfil_acesso IN ('OPERADOR', 'GERENTE')),
    status TEXT NOT NULL DEFAULT 'ATIVO' CHECK (status IN ('ATIVO', 'INATIVO'))
);

-- 2. TABELA DE VENDAS (CABEÇALHO TRANSACIONAL)
CREATE TABLE IF NOT EXISTS vendas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    numero_pedido TEXT NOT NULL UNIQUE,
    data_hora TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    cliente_nome TEXT NOT NULL,
    cliente_documento TEXT NOT NULL,
    forma_pagamento TEXT NOT NULL CHECK (forma_pagamento IN ('PIX', 'CARTAO_CREDITO', 'BOLETO_FATURADO')),
    valor_total REAL NOT NULL CHECK (valor_total > 0),
    status_venda TEXT NOT NULL DEFAULT 'CONCLUIDA' CHECK (status_venda IN ('CONCLUIDA', 'CANCELADA')),
    usuario_id INTEGER NOT NULL,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE RESTRICT
);

-- 3. TABELA DE ITENS DA VENDA (COMPOSIÇÃO DO CARRINHO)
CREATE TABLE IF NOT EXISTS itens_venda (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    venda_id INTEGER NOT NULL,
    produto_id INTEGER NOT NULL,
    quantidade_vendida INTEGER NOT NULL CHECK (quantidade_vendida > 0),
    preco_unitario_praticado REAL NOT NULL CHECK (preco_unitario_praticado > 0),
    subtotal_item REAL NOT NULL CHECK (subtotal_item > 0),
    FOREIGN KEY (venda_id) REFERENCES vendas(id) ON DELETE CASCADE,
    FOREIGN KEY (produto_id) REFERENCES produtos(id) ON DELETE RESTRICT
);

-- Inserção dos usuários de teste (senhas padrão: 'senha123')
INSERT OR IGNORE INTO usuarios (id, nome_completo, email, senha_hash, perfil_acesso, status) VALUES 
(1, 'Carlos Operador de Caixa', 'operador@techstore.com', 'scrypt:32768:8:1$xT5Z7K1NqF0P8M2L$a7f34032d847864f16a0487439589d71cbfb40bf24fa7521ebcf7aa0cf7169542a1f22ba546f140660424578b8719f9bbff4270258d4a6703554e223ae3bfb2a', 'OPERADOR', 'ATIVO'),
(2, 'Mariana Gerente de Operações', 'gerente@techstore.com', 'scrypt:32768:8:1$xT5Z7K1NqF0P8M2L$a7f34032d847864f16a0487439589d71cbfb40bf24fa7521ebcf7aa0cf7169542a1f22ba546f140660424578b8719f9bbff4270258d4a6703554e223ae3bfb2a', 'GERENTE', 'ATIVO');