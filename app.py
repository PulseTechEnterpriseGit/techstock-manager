import sqlite3
import os
from flask import Flask, render_template, request, redirect, url_for, flash

app = Flask(__name__)
app.secret_key = "techstock_secret_key_2026"
DATABASE = "techstock.db"

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    # Ativação obrigatória de integridade de chaves estrangeiras no SQLite
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db():
    if not os.path.exists(DATABASE):
        conn = get_db_connection()
        with open("database.sql", "r", encoding="utf-8") as f:
            conn.executescript(f.read())
        conn.close()

# R1: Dashboard Consolidado e Alertas Operacionais (Read com JOIN)
@app.route("/")
def dashboard():
    conn = get_db_connection()
    query = """
        SELECT 
            p.id,
            p.sku,
            p.nome AS ativo,
            p.fabricante,
            c.nome AS categoria,
            f.razao_social AS fornecedor,
            p.preco_venda,
            p.estoque_atual,
            p.estoque_minimo,
            p.localizacao,
            p.classificacao,
            p.modalidade_licenca
        FROM produtos p
        INNER JOIN categorias c ON p.categoria_id = c.id
        INNER JOIN fornecedores f ON p.fornecedor_id = f.id
        ORDER BY p.nome ASC;
    """
    produtos = conn.execute(query).fetchall()
    conn.close()
    return render_template("dashboard.html", produtos=produtos)

# R2: Entrada de Novos Ativos no Catálogo (Create)
@app.route("/produtos/novo", methods=["GET", "POST"])
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
        except sqlite3.IntegrityError as e:
            conn.rollback()
            flash("Erro de integridade: SKU já cadastrado ou campos inválidos.", "danger")

    categorias = conn.execute("SELECT id, nome FROM categorias ORDER BY nome ASC;").fetchall()
    fornecedores = conn.execute("SELECT id, razao_social FROM fornecedores ORDER BY razao_social ASC;").fetchall()
    conn.close()
    return render_template("novo_produto.html", categorias=categorias, fornecedores=fornecedores)

# R3: Orquestração de Fluxo e Movimentação (Update de Saldo)
@app.route("/movimentacao", methods=["GET", "POST"])
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

        # Validação de Negócio Impeditiva
        if tipo == "Saida" and quantidade > produto["estoque_atual"]:
            flash(f"Operação cancelada: Saldo insuficiente para {produto['nome']}. Disponível: {produto['estoque_atual']}, Solicitado: {quantidade}.", "danger")
            conn.close()
            return redirect(url_for("movimentacao"))

        novo_estoque = produto["estoque_atual"] + quantidade if tipo == "Entrada" else produto["estoque_atual"] - quantidade

        try:
            # Transação atómica: atualiza produto e audita na tabela de movimentações
            conn.execute("UPDATE produtos SET estoque_atual = ? WHERE id = ?", (novo_estoque, produto_id))
            conn.execute("""
                INSERT INTO movimentacoes (tipo, quantidade, justificativa, produto_id)
                VALUES (?, ?, ?, ?)
            """, (tipo, quantidade, justificativa, produto_id))
            conn.commit()
            flash(f"Movimentação de {tipo} efetuada com sucesso! Saldo atualizado para {novo_estoque}.", "success")
            conn.close()
            return redirect(url_for("dashboard"))
        except Exception as e:
            conn.rollback()
            flash("Falha ao registrar a transação no banco de dados.", "danger")

    produtos = conn.execute("SELECT id, sku, nome, estoque_atual FROM produtos ORDER BY nome ASC;").fetchall()
    conn.close()
    return render_template("movimentacao.html", produtos=produtos)

# R4: Gestão de Descontinuação de Itens (Delete com Proteção Referencial)
@app.route("/produtos/remover/<int:produto_id>", methods=["POST"])
def remover_produto(produto_id):
    conn = get_db_connection()
    try:
        conn.execute("DELETE FROM produtos WHERE id = ?", (produto_id,))
        conn.commit()
        flash("Ativo removido do inventário com sucesso.", "info")
    except sqlite3.IntegrityError:
        conn.rollback()
        flash("Ação bloqueada: Não é possível excluir o item pois existem registros de auditoria ou dependências associadas.", "danger")
    finally:
        conn.close()
    return redirect(url_for("dashboard"))

if __name__ == "__main__":
    init_db()
    app.run(debug=True)