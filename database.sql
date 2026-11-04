-- 1. TABELA CATEGORIAS
CREATE TABLE IF NOT EXISTS categorias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL UNIQUE
);

-- 2. TABELA FORNECEDORES
CREATE TABLE IF NOT EXISTS fornecedores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    razao_social TEXT NOT NULL,
    cnpj TEXT NOT NULL UNIQUE,
    telefone TEXT,
    email TEXT
);

-- 3. TABELA PRODUTOS
CREATE TABLE IF NOT EXISTS produtos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sku TEXT NOT NULL UNIQUE,
    nome TEXT NOT NULL,
    fabricante TEXT NOT NULL,
    classificacao TEXT NOT NULL CHECK (classificacao IN ('Hardware', 'Software', 'Periférico')),
    especificacao_tecnica TEXT,
    modalidade_licenca TEXT,
    preco_venda REAL NOT NULL CHECK (preco_venda > 0),
    estoque_atual INTEGER NOT NULL DEFAULT 0 CHECK (estoque_atual >= 0),
    estoque_minimo INTEGER NOT NULL DEFAULT 0 CHECK (estoque_minimo >= 0),
    localizacao TEXT NOT NULL,
    categoria_id INTEGER NOT NULL,
    fornecedor_id INTEGER NOT NULL,
    FOREIGN KEY (categoria_id) REFERENCES categorias(id) ON DELETE RESTRICT,
    FOREIGN KEY (fornecedor_id) REFERENCES fornecedores(id) ON DELETE RESTRICT
);

-- 4. TABELA MOVIMENTAÇÕES (Auditoria)
CREATE TABLE IF NOT EXISTS movimentacoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo TEXT NOT NULL CHECK (tipo IN ('Entrada', 'Saida')),
    quantidade INTEGER NOT NULL CHECK (quantidade > 0),
    data_hora TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    justificativa TEXT NOT NULL,
    produto_id INTEGER NOT NULL,
    FOREIGN KEY (produto_id) REFERENCES produtos(id) ON DELETE CASCADE
);

-- =========================================================================
-- CARGA DE TESTES INICIAL
-- =========================================================================

-- Inserção de Categorias
INSERT OR IGNORE INTO categorias (nome) VALUES 
('Armazenamento'),
('Processamento'),
('Suítes de Escritório'),
('Sistemas Operacionais');

-- Inserção de Fornecedores
INSERT OR IGNORE INTO fornecedores (razao_social, cnpj, telefone, email) VALUES 
('Distribuidora Tech Brasil Ltda', '11.222.333/0001-44', '(11) 3333-1111', 'contato@techbrasil.com.br'),
('Global Cloud & Softwares S.A.', '22.333.444/0001-55', '(21) 2222-4444', 'vendas@globalcloud.com.br'),
('Hardware Express Componentes', '33.444.555/0001-66', '(62) 3456-7890', 'comercial@hwexpress.com.br');

-- Inserção de Produtos (Hardware e Software)
INSERT OR IGNORE INTO produtos (sku, nome, fabricante, classificacao, especificacao_tecnica, modalidade_licenca, preco_venda, estoque_atual, estoque_minimo, localizacao, categoria_id, fornecedor_id) VALUES 
('HW-SSD-1TB', 'SSD NVMe 1TB PCIe 4.0', 'Kingston', 'Hardware', 'Leitura 3500MB/s, Gravação 2100MB/s', NULL, 450.00, 2, 5, 'Prateleira A1', 1, 3),
('HW-RAM-16GB', 'Memória RAM 16GB DDR4 3200MHz', 'Corsair', 'Hardware', 'DDR4 CL16 Vengeance LPX', NULL, 280.00, 15, 4, 'Prateleira A2', 2, 3),
('SW-WIN11-PRO', 'Windows 11 Pro Corporativo', 'Microsoft', 'Software', 'Licença eletrónica x64 OEM', 'OEM / Perpétua', 890.00, 10, 3, 'Cofre Digital #01', 4, 2),
('SW-M365-BUS', 'Microsoft 365 Business Standard', 'Microsoft', 'Software', 'Subscrição anual para 1 utilizador', 'Assinatura Anual', 650.00, 1, 4, 'Cofre Digital #02', 3, 2),
('HW-CPU-R5', 'Processador AMD Ryzen 5 5600', 'AMD', 'Hardware', '6 núcleos, 12 threads, 3.5GHz', NULL, 820.00, 6, 2, 'Bancada B1', 2, 1),
('HW-MOUSE-LOG', 'Rato Sem Fios Ergonómico MX Master 3', 'Logitech', 'Periférico', 'Sensor 8000 DPI, Conexão Bluetooth', NULL, 550.00, 8, 3, 'Prateleira C3', 1, 1);