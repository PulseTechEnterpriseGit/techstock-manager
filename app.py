import sqlite3
import os
import uuid
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "techstock_secure_enterprise_key_2026"
DATABASE = "techstock.db"

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if os.path.exists("database.sql"):
        with open("database.sql", "r", encoding="utf-8") as f:
            cursor.executescript(f.read())
    if os.path.exists("migration_v2.sql"):
        with open("migration_v2.sql", "r", encoding="utf-8") as f:
            cursor.executescript(f.read())
            
    # Garante carga base de usuários e produtos caso o banco esteja vazio
    senha_padrao = generate_password_hash("senha123")
    cursor.execute("""
        INSERT OR IGNORE INTO usuarios (id, nome_completo, email, senha_hash, perfil_acesso, status) VALUES 
        (1, 'Carlos Operador de Caixa', 'operador@techstore.com', ?, 'OPERADOR', 'ATIVO'),
        (2, 'Mariana Gerente de Operações', 'gerente@techstore.com', ?, 'GERENTE', 'ATIVO');
    """, (senha_padrao, senha_padrao))
    cursor.execute("UPDATE usuarios SET senha_hash = ? WHERE email IN ('operador@techstore.com', 'gerente@techstore.com')", (senha_padrao,))

    cursor.execute("INSERT OR IGNORE INTO categorias (id, nome) VALUES (1, 'Hardware'), (2, 'Software'), (3, 'Periféricos')")
    cursor.execute("INSERT OR IGNORE INTO fornecedores (id, razao_social, cnpj) VALUES (1, 'Tech Distribuidora', '12345678000190'), (2, 'Global Hardware', '98765432000110')")

    produtos_base = [
        (1, 'MEM-DDR4-8GB', 'Memoria RAM DDR4 8GB 2666MHz', 'Kingston', 'Hardware', 150.0, 15, 5, 'Prateleira A1', 1, 1),
        (2, 'MEM-DDR4-16GB', 'Memoria RAM DDR4 16GB 3200MHz', 'Corsair', 'Hardware', 280.0, 8, 3, 'Prateleira A2', 1, 1),
        (3, 'LIC-WIN11-PRO', 'Windows 11 Professional OEM', 'Microsoft', 'Software', 880.0, 20, 5, 'Vault Cloud', 2, 1),
        (4, 'LIC-OFF365-BS', 'Microsoft 365 Business Standard', 'Microsoft', 'Software', 650.0, 12, 4, 'Vault Cloud', 2, 1),
        (5, 'SSD-NVME-500G', 'SSD NVMe M.2 500GB Gen3', 'Crucial', 'Hardware', 240.0, 2, 5, 'Prateleira B3', 1, 2),
        (6, 'SW-GIGA-08P', 'Switch Gigabit Ethernet 8 Portas', 'TP-Link', 'Periférico', 180.0, 6, 2, 'Prateleira C1', 3, 1)
    ]
    for p in produtos_base:
        cursor.execute("""
            INSERT OR IGNORE INTO produtos (
                id, sku, nome, fabricante, classificacao, preco_venda, 
                estoque_atual, estoque_minimo, localizacao, categoria_id, fornecedor_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, p)

    conn.commit()
    conn.close()

# -------------------------------------------------------------
# CONTROLE DE ACESSO (RBAC)
# -------------------------------------------------------------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "usuario_id" not in session:
            flash("Faça login para acessar o sistema.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

def gerente_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "usuario_id" not in session or session.get("perfil_acesso") != "GERENTE":
            flash("Acesso restrito: Requer permissões de nível GERENTE.", "danger")
            return redirect(url_for("dashboard"))
        return f(*args, **kwargs)
    return decorated_function

# -------------------------------------------------------------
# LOGIN E LOGOUT
# -------------------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        senha = request.form["senha"]

        conn = get_db_connection()
        usuario = conn.execute("SELECT * FROM usuarios WHERE email = ? AND status = 'ATIVO'", (email,)).fetchone()
        conn.close()

        if usuario and check_password_hash(usuario["senha_hash"], senha):
            session["usuario_id"] = usuario["id"]
            session["usuario_nome"] = usuario["nome_completo"]
            session["perfil_acesso"] = usuario["perfil_acesso"]
            flash(f"Bem-vindo(a), {usuario['nome_completo']} ({usuario['perfil_acesso']})!", "success")
            return redirect(url_for("dashboard"))
        else:
            flash("Credenciais inválidas ou usuário inativo. Tente novamente.", "danger")

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("Sessão finalizada com sucesso.", "info")
    return redirect(url_for("login"))

# -------------------------------------------------------------
# DASHBOARD PRINCIPAL
# -------------------------------------------------------------
@app.route("/")
@login_required
def dashboard():
    conn = get_db_connection()
    query = """
        SELECT 
            p.id, p.sku, p.nome AS ativo, p.fabricante,
            COALESCE(c.nome, 'Geral') AS categoria, 
            COALESCE(f.razao_social, 'Fornecedor Padrão') AS fornecedor,
            p.preco_venda, p.estoque_atual, p.estoque_minimo,
            p.localizacao, p.classificacao, p.modalidade_licenca
        FROM produtos p
        LEFT JOIN categorias c ON p.categoria_id = c.id
        LEFT JOIN fornecedores f ON p.fornecedor_id = f.id
        ORDER BY p.nome ASC;
    """
    produtos = conn.execute(query).fetchall()
    conn.close()
    return render_template("dashboard.html", produtos=produtos)

# -------------------------------------------------------------
# PROVISIONAMENTO E EXCLUSÃO (APENAS GERENTE)
# -------------------------------------------------------------
@app.route("/produtos/novo", methods=["GET", "POST"])
@login_required
@gerente_required
def novo_produto():
    conn = get_db_connection()
    if request.method == "POST":
        sku = request.form["sku"].strip()
        nome = request.form["nome"].strip()
        fabricante = request.form["fabricante"].strip()
        classificacao = request.form["classificacao"]
        especificacao = request.form["especificacao_tecnica"].strip()
        modalidade = request.form.get("modalidade_licenca", "").strip() or None
        preco = float(request.form["preco_venda"])
        estoque_atual = int(request.form["estoque_atual"])
        estoque_minimo = int(request.form["estoque_minimo"])
        localizacao = request.form["localizacao"].strip()
        categoria_id = int(request.form["categoria_id"])
        fornecedor_id = int(request.form["fornecedor_id"])

        try:
            conn.execute("""
                INSERT INTO produtos (
                    sku, nome, fabricante, classificacao, especificacao_tecnica,
                    modalidade_licenca, preco_venda, estoque_atual, estoque_minimo,
                    localizacao, categoria_id, fornecedor_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                sku, nome, fabricante, classificacao, especificacao,
                modalidade, preco, estoque_atual, estoque_minimo,
                localizacao, categoria_id, fornecedor_id
            ))
            conn.commit()
            flash("Ativo cadastrado com sucesso no catálogo!", "success")
            conn.close()
            return redirect(url_for("dashboard"))
        except sqlite3.IntegrityError:
            conn.rollback()
            flash("Erro de integridade: SKU duplicado ou campos obrigatórios inválidos.", "danger")

    categorias = conn.execute("SELECT id, nome FROM categorias ORDER BY nome ASC;").fetchall()
    fornecedores = conn.execute("SELECT id, razao_social FROM fornecedores ORDER BY razao_social ASC;").fetchall()
    conn.close()
    return render_template("novo_produto.html", categorias=categorias, fornecedores=fornecedores)

@app.route("/produtos/remover/<int:produto_id>", methods=["POST"])
@login_required
@gerente_required
def remover_produto(produto_id):
    conn = get_db_connection()
    try:
        conn.execute("DELETE FROM produtos WHERE id = ?", (produto_id,))
        conn.commit()
        flash("Ativo removido do inventário com sucesso.", "info")
    except sqlite3.IntegrityError:
        conn.rollback()
        flash("Ação bloqueada: Não é possível excluir o item pois existem registros de vendas ou auditoria associados.", "danger")
    finally:
        conn.close()
    return redirect(url_for("dashboard"))

# -------------------------------------------------------------
# MOVIMENTAÇÕES MANUAIS
# -------------------------------------------------------------
@app.route("/movimentacao", methods=["GET", "POST"])
@login_required
def movimentacao():
    conn = get_db_connection()
    if request.method == "POST":
        produto_id = int(request.form["produto_id"])
        tipo = request.form["tipo"]
        quantidade = int(request.form["quantidade"])
        justificativa = request.form["justificativa"].strip()

        produto = conn.execute("SELECT nome, estoque_atual FROM produtos WHERE id = ?", (produto_id,)).fetchone()
        if not produto:
            flash("Ativo selecionado não encontrado.", "danger")
            conn.close()
            return redirect(url_for("movimentacao"))

        if quantidade <= 0:
            flash("A quantidade movimentada deve ser maior que zero.", "warning")
            conn.close()
            return redirect(url_for("movimentacao"))

        if tipo == "Saida" and quantidade > produto["estoque_atual"]:
            flash(f"Operação cancelada: Saldo insuficiente para {produto['nome']}. Disponível: {produto['estoque_atual']}, Solicitado: {quantidade}.", "danger")
            conn.close()
            return redirect(url_for("movimentacao"))

        novo_estoque = produto["estoque_atual"] + quantidade if tipo == "Entrada" else produto["estoque_atual"] - quantidade

        try:
            conn.execute("UPDATE produtos SET estoque_atual = ? WHERE id = ?", (novo_estoque, produto_id))
            conn.execute("""
                INSERT INTO movimentacoes (tipo, quantidade, justificativa, produto_id)
                VALUES (?, ?, ?, ?)
            """, (tipo, quantidade, justificativa, produto_id))
            conn.commit()
            flash(f"Movimentação de {tipo} registrada com sucesso! Novo saldo: {novo_estoque}.", "success")
            conn.close()
            return redirect(url_for("dashboard"))
        except Exception:
            conn.rollback()
            flash("Falha ao registrar a transação no banco de dados.", "danger")

    produtos = conn.execute("SELECT id, sku, nome, estoque_atual FROM produtos ORDER BY nome ASC;").fetchall()
    conn.close()
    return render_template("movimentacao.html", produtos=produtos)

# -------------------------------------------------------------
# CHECKOUT TRANSACIONAL (ACID)
# -------------------------------------------------------------
@app.route("/vendas/checkout", methods=["GET", "POST"])
@login_required
def checkout():
    conn = get_db_connection()
    if request.method == "POST":
        cliente_nome = request.form["cliente_nome"].strip()
        cliente_documento = request.form["cliente_documento"].strip()
        forma_pagamento = request.form["forma_pagamento"]
        
        produtos_selecionados = request.form.getlist("produto_id[]")
        quantidades_selecionadas = request.form.getlist("quantidade[]")

        if not produtos_selecionados:
            flash("Selecione pelo menos um item para compor a venda.", "warning")
            conn.close()
            return redirect(url_for("checkout"))

        numero_pedido = f"PED-2026-{uuid.uuid4().hex[:6].upper()}"
        
        try:
            conn.execute("BEGIN TRANSACTION;")
            valor_total_venda = 0.0
            itens_a_processar = []

            for prod_id_str, qtd_str in zip(produtos_selecionados, quantidades_selecionadas):
                if not prod_id_str or not qtd_str:
                    continue
                prod_id = int(prod_id_str)
                qtd = int(qtd_str)

                if qtd <= 0:
                    raise ValueError(f"Quantidade informada inválida para o item ID {prod_id}.")

                prod = conn.execute("SELECT id, sku, nome, preco_venda, estoque_atual FROM produtos WHERE id = ?", (prod_id,)).fetchone()
                if not prod:
                    raise ValueError(f"Ativo ID {prod_id} não encontrado no catálogo.")

                if qtd > prod["estoque_atual"]:
                    raise ValueError(f"Ruptura de estoque para '{prod['nome']}'. Saldo em estoque: {prod['estoque_atual']}, solicitado: {qtd}.")

                subtotal = prod["preco_venda"] * qtd
                valor_total_venda += subtotal
                itens_a_processar.append({
                    "produto_id": prod["id"],
                    "nome": prod["nome"],
                    "preco_unitario": prod["preco_venda"],
                    "quantidade": qtd,
                    "subtotal": subtotal,
                    "novo_estoque": prod["estoque_atual"] - qtd
                })

            if not itens_a_processar:
                raise ValueError("Nenhum item válido foi processado no carrinho.")

            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO vendas (numero_pedido, cliente_nome, cliente_documento, forma_pagamento, valor_total, status_venda, usuario_id)
                VALUES (?, ?, ?, ?, ?, 'CONCLUIDA', ?)
            """, (numero_pedido, cliente_nome, cliente_documento, forma_pagamento, valor_total_venda, session["usuario_id"]))
            venda_id = cursor.lastrowid

            for item in itens_a_processar:
                cursor.execute("""
                    INSERT INTO itens_venda (venda_id, produto_id, quantidade_vendida, preco_unitario_praticado, subtotal_item)
                    VALUES (?, ?, ?, ?, ?)
                """, (venda_id, item["produto_id"], item["quantidade"], item["preco_unitario"], item["subtotal"]))

                cursor.execute("""
                    UPDATE produtos SET estoque_atual = ? WHERE id = ?
                """, (item["novo_estoque"], item["produto_id"]))

                cursor.execute("""
                    INSERT INTO movimentacoes (tipo, quantidade, justificativa, produto_id)
                    VALUES ('Saida', ?, ?, ?)
                """, (item["quantidade"], f"Venda PDV {numero_pedido} - Cliente: {cliente_nome}", item["produto_id"]))

            conn.commit()
            flash(f"Venda {numero_pedido} concluída com sucesso com garantia ACID!", "success")
            conn.close()
            return redirect(url_for("recibo_venda", numero_pedido=numero_pedido))

        except Exception as e:
            conn.rollback()
            conn.close()
            flash(f"Transação abortada (ROLLBACK acionado): {str(e)}", "danger")
            return redirect(url_for("checkout"))

    produtos = conn.execute("""
        SELECT p.id, p.sku, p.nome, p.preco_venda, p.estoque_atual, p.classificacao, COALESCE(c.nome, 'Geral') AS categoria
        FROM produtos p
        LEFT JOIN categorias c ON p.categoria_id = c.id
        WHERE p.estoque_atual > 0
        ORDER BY p.nome ASC;
    """).fetchall()
    conn.close()
    return render_template("checkout.html", produtos=produtos)

# -------------------------------------------------------------
# RECIBO E HISTÓRICO DE VENDAS
# -------------------------------------------------------------
@app.route("/vendas/recibo/<numero_pedido>")
@login_required
def recibo_venda(numero_pedido):
    conn = get_db_connection()
    venda = conn.execute("""
        SELECT v.*, u.nome_completo AS operador_nome
        FROM vendas v
        INNER JOIN usuarios u ON v.usuario_id = u.id
        WHERE v.numero_pedido = ?;
    """, (numero_pedido,)).fetchone()

    if not venda:
        conn.close()
        flash("Comprovante de venda não localizado.", "warning")
        return redirect(url_for("dashboard"))

    itens = conn.execute("""
        SELECT iv.*, p.sku, p.nome AS produto_nome, p.classificacao, p.modalidade_licenca
        FROM itens_venda iv
        INNER JOIN produtos p ON iv.produto_id = p.id
        WHERE iv.venda_id = ?;
    """, (venda["id"],)).fetchall()
    conn.close()
    return render_template("recibo.html", venda=venda, itens=itens)

@app.route("/vendas")
@login_required
def listar_vendas():
    conn = get_db_connection()
    vendas = conn.execute("""
        SELECT v.*, u.nome_completo AS operador_nome
        FROM vendas v
        INNER JOIN usuarios u ON v.usuario_id = u.id
        ORDER BY v.data_hora DESC;
    """).fetchall()
    conn.close()
    return render_template("vendas.html", vendas=vendas)

if __name__ == "__main__":
    init_db()
    app.run(debug=True)