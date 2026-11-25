import io
import os
import sqlite3
import secrets
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from fpdf import FPDF

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "techstock.db")
SQL_PATH = os.path.join(BASE_DIR, "database.sql")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def registrar_auditoria(conn, usuario_id, acao, detalhes):
    ip = request.remote_addr or "127.0.0.1"
    conn.execute(
        "INSERT INTO auditoria_logs (usuario_id, acao, detalhes, ip_origem) VALUES (?, ?, ?, ?)",
        (usuario_id, acao, detalhes, ip),
    )


def init_db():
    conn = get_db()
    with open(SQL_PATH, "r", encoding="utf-8") as f:
        conn.executescript(f.read())

    existe = conn.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]
    if existe == 0:
        conn.execute(
            "INSERT INTO usuarios (nome, email, senha_hash, cargo) VALUES (?, ?, ?, ?)",
            ("Gerente TechStore", "gerente@techstore.com", generate_password_hash("senha123"), "gerente"),
        )
        conn.execute(
            "INSERT INTO usuarios (nome, email, senha_hash, cargo) VALUES (?, ?, ?, ?)",
            ("Carlos Operador", "operador@techstore.com", generate_password_hash("senha123"), "operador"),
        )
        conn.execute("INSERT INTO categorias (nome) VALUES ('Hardware'), ('Software B2B'), ('Perifericos')")
        conn.execute(
            "INSERT INTO fornecedores (nome, cnpj) VALUES ('Distribuidora Brasil TI', '12.345.678/0001-90'), ('Microsoft Partner', '98.765.432/0001-10')"
        )
        produtos_iniciais = [
            ("SSD-NVME-500G", "SSD NVMe 500GB Kingston", "fisico", 289.90, 2, 5, None, 1, 1),
            ("RAM-DDR4-16G", "Memoria RAM DDR4 16GB", "fisico", 249.00, 14, 5, None, 1, 1),
            ("WIN-11-PRO", "Licenca Windows 11 Pro OEM", "digital", 699.00, 999, 1, "W11P-8842-K99L-2026", 2, 2),
        ]
        conn.executemany(
            """INSERT INTO produtos 
               (sku, nome, tipo, preco, estoque_atual, estoque_minimo, chave_digital, categoria_id, fornecedor_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            produtos_iniciais,
        )
        conn.commit()
    conn.close()


# --- DECORATORS DE SEGURANCA (RBAC) ---
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "usuario_id" not in session:
            flash("Acesso restrito. Realize o login.", "erro")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def gerente_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get("cargo") != "gerente":
            flash("Acesso negado. Funcionalidade exclusiva da gerencia.", "erro")
            return redirect(url_for("dashboard"))
        return f(*args, **kwargs)
    return decorated


# --- AUTENTICACAO ---
@app.route("/login", methods=["GET", "POST"])
def login():
    if "usuario_id" in session:
        return redirect(url_for("home"))

    if request.method == "POST":
        email = request.form.get("email", "").strip()
        senha = request.form.get("senha", "")

        conn = get_db()
        user = conn.execute("SELECT * FROM usuarios WHERE email = ?", (email,)).fetchone()

        if user and check_password_hash(user["senha_hash"], senha):
            session.clear()
            session["usuario_id"] = user["id"]
            session["usuario_nome"] = user["nome"]
            session["cargo"] = user["cargo"]
            registrar_auditoria(conn, user["id"], "LOGIN", f"Acesso ao sistema como {user['cargo']}")
            conn.commit()
            conn.close()
            return redirect(url_for("home"))

        conn.close()
        flash("E-mail ou senha invalidos.", "erro")
    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    conn = get_db()
    registrar_auditoria(conn, session["usuario_id"], "LOGOUT", "Encerramento de sessao")
    conn.commit()
    conn.close()
    session.clear()
    return redirect(url_for("login"))


# --- PAGINA INICIAL (HOME - POS-LOGIN) ---
@app.route("/")
@login_required
def home():
    return render_template("home.html")


# --- DASHBOARD / PAINEL ---
@app.route("/painel")
@login_required
def dashboard():
    conn = get_db()
    produtos = conn.execute("""
        SELECT p.*, c.nome AS categoria_nome, f.nome AS fornecedor_nome
        FROM produtos p
        JOIN categorias c ON p.categoria_id = c.id
        JOIN fornecedores f ON p.fornecedor_id = f.id
        ORDER BY p.nome ASC
    """).fetchall()

    alertas_estoque = 0
    for p in produtos:
        if p["tipo"] == "fisico" and p["estoque_atual"] <= p["estoque_minimo"]:
            alertas_estoque += 1

    resumo_vendas = None
    prod_labels = []
    prod_valores = []
    diario_labels = []
    diario_valores = []
    mensal_labels = []
    mensal_valores = []
    anual_labels = []
    anual_valores = []

    if session.get("cargo") == "gerente":
        resumo_vendas = conn.execute(
            "SELECT COUNT(*) AS qtd, COALESCE(SUM(valor_total), 0) AS faturamento FROM vendas"
        ).fetchone()

        grafico_prod = conn.execute("""
            SELECT p.nome, COALESCE(SUM(iv.quantidade), 0) AS total_vendido
            FROM produtos p
            LEFT JOIN itens_venda iv ON p.id = iv.produto_id
            GROUP BY p.id, p.nome
            ORDER BY total_vendido DESC
        """).fetchall()
        prod_labels = [row["nome"] for row in grafico_prod]
        prod_valores = [row["total_vendido"] for row in grafico_prod]

        dados_diarios = conn.execute("""
            SELECT strftime('%d/%m/%Y', data_venda) AS periodo, COALESCE(SUM(valor_total), 0) AS total
            FROM vendas
            GROUP BY strftime('%Y-%m-%d', data_venda)
            ORDER BY strftime('%Y-%m-%d', data_venda) ASC
            LIMIT 14
        """).fetchall()
        diario_labels = [row["periodo"] for row in dados_diarios]
        diario_valores = [round(row["total"], 2) for row in dados_diarios]

        dados_mensais = conn.execute("""
            SELECT strftime('%m/%Y', data_venda) AS periodo, COALESCE(SUM(valor_total), 0) AS total
            FROM vendas
            GROUP BY strftime('%Y-%m', data_venda)
            ORDER BY strftime('%Y-%m', data_venda) ASC
            LIMIT 12
        """).fetchall()
        mensal_labels = [row["periodo"] for row in dados_mensais]
        mensal_valores = [round(row["total"], 2) for row in dados_mensais]

        dados_anuais = conn.execute("""
            SELECT strftime('%Y', data_venda) AS periodo, COALESCE(SUM(valor_total), 0) AS total
            FROM vendas
            GROUP BY strftime('%Y', data_venda)
            ORDER BY strftime('%Y', data_venda) ASC
        """).fetchall()
        anual_labels = [row["periodo"] for row in dados_anuais]
        anual_valores = [round(row["total"], 2) for row in dados_anuais]

    conn.close()
    return render_template(
        "dashboard.html",
        produtos=produtos,
        alertas_estoque=alertas_estoque,
        resumo_vendas=resumo_vendas,
        prod_labels=prod_labels,
        prod_valores=prod_valores,
        diario_labels=diario_labels,
        diario_valores=diario_valores,
        mensal_labels=mensal_labels,
        mensal_valores=mensal_valores,
        anual_labels=anual_labels,
        anual_valores=anual_valores,
    )


# --- NOVO PRODUTO ---
@app.route("/produto/novo", methods=["GET", "POST"])
@login_required
@gerente_required
def novo_produto():
    conn = get_db()
    if request.method == "POST":
        sku = request.form["sku"].strip().upper()
        nome = request.form["nome"].strip()
        tipo = request.form["tipo"]
        preco = float(request.form["preco"])
        estoque_atual = int(request.form.get("estoque_atual", 0)) if tipo == "fisico" else 999
        estoque_minimo = int(request.form.get("estoque_minimo", 5)) if tipo == "fisico" else 1
        chave_digital = request.form.get("chave_digital", "").strip() if tipo == "digital" else None
        categoria_id = int(request.form["categoria_id"])
        fornecedor_id = int(request.form["fornecedor_id"])

        try:
            cursor = conn.execute(
                """INSERT INTO produtos 
                   (sku, nome, tipo, preco, estoque_atual, estoque_minimo, chave_digital, categoria_id, fornecedor_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (sku, nome, tipo, preco, estoque_atual, estoque_minimo, chave_digital, categoria_id, fornecedor_id),
            )
            prod_id = cursor.lastrowid
            if tipo == "fisico" and estoque_atual > 0:
                conn.execute(
                    """INSERT INTO movimentacoes (produto_id, tipo, quantidade, motivo, usuario_id)
                       VALUES (?, 'ENTRADA', ?, 'Cadastro Inicial de Estoque', ?)""",
                    (prod_id, estoque_atual, session["usuario_id"]),
                )
            registrar_auditoria(
                conn,
                session["usuario_id"],
                "CADASTRO_PRODUTO",
                f"Produto {sku} ({nome}) cadastrado a R$ {preco:.2f}",
            )
            conn.commit()
            conn.close()
            flash("Produto cadastrado com sucesso.", "sucesso")
            return redirect(url_for("dashboard"))
        except sqlite3.IntegrityError:
            conn.rollback()
            flash("Erro: SKU ja existente no banco de dados.", "erro")

    categorias = conn.execute("SELECT * FROM categorias ORDER BY nome").fetchall()
    fornecedores = conn.execute("SELECT * FROM fornecedores ORDER BY nome").fetchall()
    conn.close()
    return render_template("novo_produto.html", categorias=categorias, fornecedores=fornecedores)


# --- EDITAR PRODUTO ---
@app.route("/produto/editar/<int:produto_id>", methods=["GET", "POST"])
@login_required
@gerente_required
def editar_produto(produto_id):
    conn = get_db()
    produto = conn.execute("SELECT * FROM produtos WHERE id = ?", (produto_id,)).fetchone()
    if not produto:
        conn.close()
        flash("Produto nao encontrado.", "erro")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        sku = request.form["sku"].strip().upper()
        nome = request.form["nome"].strip()
        tipo = request.form["tipo"]
        preco = float(request.form["preco"])
        estoque_atual = int(request.form.get("estoque_atual", 0)) if tipo == "fisico" else 999
        estoque_minimo = int(request.form.get("estoque_minimo", 5)) if tipo == "fisico" else 1
        chave_digital = request.form.get("chave_digital", "").strip() if tipo == "digital" else None
        categoria_id = int(request.form["categoria_id"])
        fornecedor_id = int(request.form["fornecedor_id"])

        try:
            if tipo == "fisico" and estoque_atual != produto["estoque_atual"]:
                diff = estoque_atual - produto["estoque_atual"]
                tipo_mov = "ENTRADA" if diff > 0 else "SAIDA"
                conn.execute(
                    """INSERT INTO movimentacoes (produto_id, tipo, quantidade, motivo, usuario_id)
                       VALUES (?, ?, ?, 'Ajuste Manual de Cadastro', ?)""",
                    (produto_id, tipo_mov, abs(diff), session["usuario_id"]),
                )

            conn.execute(
                """UPDATE produtos 
                   SET sku = ?, nome = ?, tipo = ?, preco = ?, estoque_atual = ?, 
                       estoque_minimo = ?, chave_digital = ?, categoria_id = ?, fornecedor_id = ?
                   WHERE id = ?""",
                (sku, nome, tipo, preco, estoque_atual, estoque_minimo, chave_digital, categoria_id, fornecedor_id, produto_id),
            )
            registrar_auditoria(
                conn,
                session["usuario_id"],
                "EDICAO_PRODUTO",
                f"Atualizado {sku} ({nome}) | Preco: R$ {produto['preco']:.2f} -> R$ {preco:.2f} | Estoque: {produto['estoque_atual']} -> {estoque_atual}",
            )
            conn.commit()
            conn.close()
            flash("Informacoes do produto atualizadas com sucesso.", "sucesso")
            return redirect(url_for("dashboard"))
        except sqlite3.IntegrityError:
            conn.rollback()
            flash("Erro: SKU ja utilizado por outro produto.", "erro")

    categorias = conn.execute("SELECT * FROM categorias ORDER BY nome").fetchall()
    fornecedores = conn.execute("SELECT * FROM fornecedores ORDER BY nome").fetchall()
    conn.close()
    return render_template("editar_produto.html", produto=produto, categorias=categorias, fornecedores=fornecedores)


@app.route("/produto/excluir/<int:produto_id>", methods=["POST"])
@login_required
@gerente_required
def excluir_produto(produto_id):
    conn = get_db()
    produto = conn.execute("SELECT sku, nome FROM produtos WHERE id = ?", (produto_id,)).fetchone()
    try:
        conn.execute("DELETE FROM produtos WHERE id = ?", (produto_id,))
        if produto:
            registrar_auditoria(conn, session["usuario_id"], "EXCLUSAO_PRODUTO", f"Produto {produto['sku']} removido")
        conn.commit()
        flash("Produto excluido com sucesso.", "sucesso")
    except sqlite3.IntegrityError:
        conn.rollback()
        flash("Bloqueio de integridade: produto vinculado a vendas/movimentacoes (ON DELETE RESTRICT).", "erro")
    finally:
        conn.close()
    return redirect(url_for("dashboard"))


# --- MOVIMENTACOES DE ESTOQUE ---
@app.route("/movimentacoes", methods=["GET", "POST"])
@login_required
def movimentacoes():
    conn = get_db()
    if request.method == "POST":
        produto_id = int(request.form["produto_id"])
        tipo = request.form["tipo"]
        quantidade = int(request.form["quantidade"])
        motivo = request.form["motivo"].strip()

        prod = conn.execute("SELECT * FROM produtos WHERE id = ?", (produto_id,)).fetchone()
        if not prod or prod["tipo"] == "digital":
            flash("Movimentacao valida apenas para produtos fisicos.", "erro")
        elif quantidade <= 0:
            flash("Quantidade deve ser maior que zero.", "erro")
        elif tipo == "SAIDA" and prod["estoque_atual"] < quantidade:
            flash("Saldo insuficiente para registrar saida manual.", "erro")
        else:
            novo_saldo = prod["estoque_atual"] + quantidade if tipo == "ENTRADA" else prod["estoque_atual"] - quantidade
            conn.execute("UPDATE produtos SET estoque_atual = ? WHERE id = ?", (novo_saldo, produto_id))
            conn.execute(
                """INSERT INTO movimentacoes (produto_id, tipo, quantidade, motivo, usuario_id)
                   VALUES (?, ?, ?, ?, ?)""",
                (produto_id, tipo, quantidade, motivo, session["usuario_id"]),
            )
            registrar_auditoria(
                conn,
                session["usuario_id"],
                f"MOVIMENTACAO_{tipo}",
                f"{prod['sku']}: {tipo} de {quantidade} un. ({motivo})",
            )
            conn.commit()
            flash("Movimentacao registrada no livro de estoque.", "sucesso")

    lista_movs = conn.execute("""
        SELECT m.*, p.sku, p.nome AS produto_nome, u.nome AS usuario_nome
        FROM movimentacoes m
        JOIN produtos p ON m.produto_id = p.id
        JOIN usuarios u ON m.usuario_id = u.id
        ORDER BY m.data_movimentacao DESC
    """).fetchall()
    produtos_fisicos = conn.execute("SELECT * FROM produtos WHERE tipo = 'fisico' ORDER BY nome").fetchall()
    conn.close()
    return render_template("movimentacoes.html", movimentacoes=lista_movs, produtos=produtos_fisicos)


# --- PDV / CHECKOUT + EMISSAO DE RECIBO ---
@app.route("/pdv", methods=["GET", "POST"])
@login_required
def pdv():
    conn = get_db()
    produtos = conn.execute("SELECT * FROM produtos ORDER BY nome ASC").fetchall()

    if request.method == "POST":
        cliente_nome = request.form["cliente_nome"].strip()
        cliente_cnpj = request.form["cliente_cnpj"].strip()
        forma_pagamento = request.form["forma_pagamento"]
        produtos_ids = request.form.getlist("produto_id[]")
        quantidades = request.form.getlist("quantidade[]")

        itens_validados = []
        valor_total = 0.0

        try:
            conn.execute("BEGIN IMMEDIATE;")

            for p_id_str, qtd_str in zip(produtos_ids, quantidades):
                if not p_id_str or not qtd_str:
                    continue
                p_id = int(p_id_str)
                qtd = int(qtd_str)
                if qtd <= 0:
                    continue

                prod = conn.execute("SELECT * FROM produtos WHERE id = ?", (p_id,)).fetchone()
                if not prod:
                    raise ValueError("Produto nao encontrado.")

                if prod["tipo"] == "fisico" and prod["estoque_atual"] < qtd:
                    raise ValueError(
                        f"Estoque insuficiente para {prod['nome']}. Disponivel: {prod['estoque_atual']}, Solicitado: {qtd}."
                    )

                subtotal = prod["preco"] * qtd
                valor_total += subtotal
                itens_validados.append((prod, qtd, subtotal))

            if not itens_validados:
                raise ValueError("Selecione pelo menos um produto valido.")

            cursor = conn.execute(
                """INSERT INTO vendas (cliente_nome, cliente_cnpj, forma_pagamento, valor_total, usuario_id)
                   VALUES (?, ?, ?, ?, ?)""",
                (cliente_nome, cliente_cnpj, forma_pagamento, valor_total, session["usuario_id"]),
            )
            venda_id = cursor.lastrowid

            for prod, qtd, subtotal in itens_validados:
                conn.execute(
                    """INSERT INTO itens_venda (venda_id, produto_id, quantidade, preco_unitario, subtotal)
                       VALUES (?, ?, ?, ?, ?)""",
                    (venda_id, prod["id"], qtd, prod["preco"], subtotal),
                )
                if prod["tipo"] == "fisico":
                    conn.execute(
                        "UPDATE produtos SET estoque_atual = estoque_atual - ? WHERE id = ?",
                        (qtd, prod["id"]),
                    )
                    conn.execute(
                        """INSERT INTO movimentacoes (produto_id, tipo, quantidade, motivo, usuario_id)
                           VALUES (?, 'SAIDA', ?, ?, ?)""",
                        (prod["id"], qtd, f"Baixa Automatica PDV #{venda_id}", session["usuario_id"]),
                    )

            registrar_auditoria(
                conn,
                session["usuario_id"],
                "VENDA_PDV",
                f"Venda #{venda_id} para {cliente_nome} - Total: R$ {valor_total:.2f}",
            )
            conn.commit()
            conn.close()
            flash(f"Venda #{venda_id} concluida com sucesso.", "sucesso")
            return redirect(url_for("recibo", venda_id=venda_id))

        except ValueError as e:
            conn.rollback()
            flash(f"Operacao cancelada (ROLLBACK): {str(e)}", "erro")
        except Exception as e:
            conn.rollback()
            flash(f"Erro interno (ROLLBACK): {str(e)}", "erro")

    conn.close()
    return render_template("pdv.html", produtos=produtos)


@app.route("/recibo/<int:venda_id>")
@login_required
def recibo(venda_id):
    conn = get_db()
    venda = conn.execute("""
        SELECT v.*, u.nome AS operador_nome
        FROM vendas v
        JOIN usuarios u ON v.usuario_id = u.id
        WHERE v.id = ?
    """, (venda_id,)).fetchone()

    if not venda:
        conn.close()
        flash("Recibo nao encontrado.", "erro")
        return redirect(url_for("dashboard"))

    itens = conn.execute("""
        SELECT iv.*, p.sku, p.nome AS produto_nome, p.tipo, p.chave_digital
        FROM itens_venda iv
        JOIN produtos p ON iv.produto_id = p.id
        WHERE iv.venda_id = ?
    """, (venda_id,)).fetchall()
    conn.close()
    return render_template("recibo.html", venda=venda, itens=itens)


@app.route("/recibo/<int:venda_id>/pdf")
@login_required
def recibo_pdf(venda_id):
    conn = get_db()
    venda = conn.execute("""
        SELECT v.*, u.nome AS operador_nome
        FROM vendas v
        JOIN usuarios u ON v.usuario_id = u.id
        WHERE v.id = ?
    """, (venda_id,)).fetchone()

    if not venda:
        conn.close()
        flash("Recibo nao encontrado.", "erro")
        return redirect(url_for("historico_vendas"))

    itens = conn.execute("""
        SELECT iv.*, p.sku, p.nome AS produto_nome, p.tipo, p.chave_digital
        FROM itens_venda iv
        JOIN produtos p ON iv.produto_id = p.id
        WHERE iv.venda_id = ?
    """, (venda_id,)).fetchall()
    conn.close()

    def limpar_texto(txt):
        return str(txt).encode("latin-1", "replace").decode("latin-1")

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, limpar_texto(f"TECHSTOCK MANAGER - RECIBO B2B #{venda['id']}"), ln=True)

    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, limpar_texto(f"Data da Operacao: {venda['data_venda']}"), ln=True)
    pdf.cell(0, 6, limpar_texto(f"Operador Responsavel: {venda['operador_nome']}"), ln=True)
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, limpar_texto("DADOS DO CLIENTE"), ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, limpar_texto(f"Razao Social: {venda['cliente_nome']}"), ln=True)
    pdf.cell(0, 6, limpar_texto(f"CNPJ: {venda['cliente_cnpj']}"), ln=True)
    pdf.cell(0, 6, limpar_texto(f"Forma de Pagamento: {venda['forma_pagamento']}"), ln=True)
    pdf.ln(6)

    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(32, 8, "SKU", border=1)
    pdf.cell(88, 8, "Produto", border=1)
    pdf.cell(16, 8, "Qtd", border=1, align="C")
    pdf.cell(27, 8, "Unitario", border=1, align="R")
    pdf.cell(27, 8, "Subtotal", border=1, align="R", ln=True)

    pdf.set_font("Helvetica", "", 9)
    for item in itens:
        pdf.cell(32, 8, limpar_texto(item["sku"]), border=1)
        pdf.cell(88, 8, limpar_texto(item["produto_nome"][:42]), border=1)
        pdf.cell(16, 8, str(item["quantidade"]), border=1, align="C")
        pdf.cell(27, 8, f"R$ {item['preco_unitario']:.2f}", border=1, align="R")
        pdf.cell(27, 8, f"R$ {item['subtotal']:.2f}", border=1, align="R", ln=True)

        if item["tipo"] == "digital" and item["chave_digital"]:
            pdf.set_font("Helvetica", "I", 8)
            pdf.cell(0, 6, limpar_texto(f"   Licenca Digital Liberada: {item['chave_digital']}"), ln=True)
            pdf.set_font("Helvetica", "", 9)

    pdf.ln(6)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 10, f"VALOR TOTAL: R$ {venda['valor_total']:.2f}", align="R", ln=True)

    buffer = io.BytesIO()
    pdf.output(buffer)
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=False,
        download_name=f"recibo_venda_{venda_id}.pdf",
        mimetype="application/pdf",
    )


@app.route("/vendas")
@login_required
def historico_vendas():
    conn = get_db()
    vendas = conn.execute("""
        SELECT v.*, u.nome AS operador_nome
        FROM vendas v
        JOIN usuarios u ON v.usuario_id = u.id
        ORDER BY v.data_venda DESC
    """).fetchall()
    conn.close()
    return render_template("vendas.html", vendas=vendas)


# --- GESTAO DE USUARIOS (CRIAR E EXCLUIR - GERENTE) ---
@app.route("/usuarios", methods=["GET", "POST"])
@login_required
@gerente_required
def usuarios():
    conn = get_db()
    if request.method == "POST":
        nome = request.form["nome"].strip()
        email = request.form["email"].strip().lower()
        senha = request.form["senha"]
        cargo = request.form["cargo"]

        if cargo not in ("gerente", "operador"):
            flash("Perfil de acesso invalido.", "erro")
        elif len(senha) < 6:
            flash("A senha deve ter no minimo 6 caracteres.", "erro")
        else:
            try:
                conn.execute(
                    "INSERT INTO usuarios (nome, email, senha_hash, cargo) VALUES (?, ?, ?, ?)",
                    (nome, email, generate_password_hash(senha), cargo),
                )
                registrar_auditoria(
                    conn,
                    session["usuario_id"],
                    "CRIACAO_USUARIO",
                    f"Criado acesso para {nome} ({email}) com perfil {cargo.upper()}",
                )
                conn.commit()
                flash(f"Usuario {nome} criado com perfil {cargo.upper()}.", "sucesso")
            except sqlite3.IntegrityError:
                conn.rollback()
                flash("Erro: ja existe um usuario cadastrado com este e-mail.", "erro")

    lista_usuarios = conn.execute("SELECT id, nome, email, cargo, criado_em FROM usuarios ORDER BY id ASC").fetchall()
    conn.close()
    return render_template("usuarios.html", usuarios=lista_usuarios)


@app.route("/usuarios/excluir/<int:usuario_id>", methods=["POST"])
@login_required
@gerente_required
def excluir_usuario(usuario_id):
    if usuario_id == session.get("usuario_id"):
        flash("Voce nao pode excluir seu proprio usuario enquanto esta logado.", "erro")
        return redirect(url_for("usuarios"))

    conn = get_db()
    alvo = conn.execute("SELECT nome, email, cargo FROM usuarios WHERE id = ?", (usuario_id,)).fetchone()
    if not alvo:
        conn.close()
        flash("Usuario nao encontrado.", "erro")
        return redirect(url_for("usuarios"))

    try:
        conn.execute("DELETE FROM usuarios WHERE id = ?", (usuario_id,))
        registrar_auditoria(
            conn,
            session["usuario_id"],
            "EXCLUSAO_USUARIO",
            f"Usuario {alvo['nome']} ({alvo['email']} - {alvo['cargo'].upper()}) removido do sistema",
        )
        conn.commit()
        flash(f"Usuario {alvo['nome']} excluido com sucesso.", "sucesso")
    except sqlite3.IntegrityError:
        conn.rollback()
        flash(
            "Bloqueio de integridade: usuario possui vendas ou movimentacoes vinculadas no historico (ON DELETE RESTRICT).",
            "erro",
        )
    finally:
        conn.close()

    return redirect(url_for("usuarios"))


# --- AUDITORIA (EXCLUSIVO GERENTE) ---
@app.route("/auditoria")
@login_required
@gerente_required
def auditoria():
    conn = get_db()
    logs = conn.execute("""
        SELECT a.*, u.nome AS usuario_nome, u.cargo
        FROM auditoria_logs a
        JOIN usuarios u ON a.usuario_id = u.id
        ORDER BY a.data_hora DESC
    """).fetchall()
    conn.close()
    return render_template("auditoria.html", logs=logs)


if __name__ == "__main__":
    init_db()
    app.run(debug=False)