import sqlite3
import os
import uuid
from werkzeug.security import generate_password_hash, check_password_hash

DATABASE = "techstock.db"

def get_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def inicializar_banco():
    conn = get_connection()
    if os.path.exists("database.sql"):
        with open("database.sql", "r", encoding="utf-8") as f:
            conn.executescript(f.read())
    if os.path.exists("migration_v2.sql"):
        with open("migration_v2.sql", "r", encoding="utf-8") as f:
            conn.executescript(f.read())
            
    # Garante hashes válidos para teste
    senha_hash = generate_password_hash("senha123")
    conn.execute("UPDATE usuarios SET senha_hash = ? WHERE email IN ('operador@techstore.com', 'gerente@techstore.com')", (senha_hash,))
    conn.commit()
    conn.close()

# -------------------------------------------------------------
# REQ-02: AUTENTICAÇÃO E SESSÃO VIA TERMINAL (RBAC)
# -------------------------------------------------------------
def autenticar_usuario():
    print("\n" + "=" * 60)
    print("      TECHSTORE INFORMÁTICA - TERMINAL DE ACESSO (RBAC)")
    print("=" * 60)
    print("Credenciais de homologação:")
    print("  Operador: operador@techstore.com | Senha: senha123")
    print("  Gerente:  gerente@techstore.com  | Senha: senha123\n")

    conn = get_connection()
    while True:
        email = input("E-mail corporativo: ").strip().lower()
        senha = input("Senha de acesso: ").strip()

        usuario = conn.execute("SELECT * FROM usuarios WHERE email = ? AND status = 'ATIVO'", (email,)).fetchone()

        if usuario and check_password_hash(usuario["senha_hash"], senha):
            print(f"\n[OK] Sessão iniciada: {usuario['nome_completo']} | Perfil: {usuario['perfil_acesso']}")
            conn.close()
            return dict(usuario)
        else:
            print("[ERRO] Credenciais inválidas ou conta inativa. Tente novamente.\n")

# -------------------------------------------------------------
# CONSULTAS DE CATÁLOGO E HISTÓRICO
# -------------------------------------------------------------
def listar_catalogo():
    conn = get_connection()
    query = """
        SELECT p.id, p.sku, p.nome, p.classificacao, p.preco_venda, p.estoque_atual, p.estoque_minimo,
               c.nome AS categoria, f.razao_social AS fornecedor
        FROM produtos p
        INNER JOIN categorias c ON p.categoria_id = c.id
        INNER JOIN fornecedores f ON p.fornecedor_id = f.id
        ORDER BY p.id ASC;
    """
    produtos = conn.execute(query).fetchall()
    conn.close()

    print("\n" + "-" * 95)
    print(f"{'ID':<4} | {'SKU':<14} | {'ATIVO':<30} | {'TIPO':<10} | {'PREÇO':<10} | {'SALDO':<6} | {'STATUS'}")
    print("-" * 95)
    for p in produtos:
        alerta = "[ALERTA RUPTURA]" if p["estoque_atual"] <= p["estoque_minimo"] else "REGULAR"
        print(f"{p['id']:<4} | {p['sku']:<14} | {p['nome'][:30]:<30} | {p['classificacao']:<10} | R$ {p['preco_venda']:<7.2f} | {p['estoque_atual']:<6} | {alerta}")
    print("-" * 95)

def listar_vendas():
    conn = get_connection()
    query = """
        SELECT v.numero_pedido, v.data_hora, v.cliente_nome, v.forma_pagamento, v.valor_total, u.nome_completo AS operador
        FROM vendas v
        INNER JOIN usuarios u ON v.usuario_id = u.id
        ORDER BY v.id DESC;
    """
    vendas = conn.execute(query).fetchall()
    conn.close()

    print("\n" + "=" * 90)
    print("                    LIVRO-RAZÃO DE VENDAS CONSOLIDADAS")
    print("=" * 90)
    for v in vendas:
        print(f"Pedido: {v['numero_pedido']} | Data: {v['data_hora']} | Total: R$ {v['valor_total']:.2f}")
        print(f"Cliente: {v['cliente_nome']} | Pagamento: {v['forma_pagamento']} | Operador: {v['operador']}")
        print("-" * 90)

# -------------------------------------------------------------
# REQ-03, REQ-04 & REQ-05: CHECKOUT MULTI-ITENS, ACID & RECIBO
# -------------------------------------------------------------
def realizar_venda(usuario):
    conn = get_connection()
    carrinho = []

    print("\n" + "=" * 60)
    print("             NOVA OPERAÇÃO DE VENDA (FRENTE DE CAIXA)")
    print("=" * 60)

    cliente_nome = input("Razão Social / Nome do Cliente: ").strip()
    cliente_doc = input("CPF ou CNPJ: ").strip()

    print("\nFormas de Pagamento disponíveis:")
    print("  1. PIX")
    print("  2. CARTAO_CREDITO")
    print("  3. BOLETO_FATURADO")
    opcao_pag = input("Escolha a opção (1-3): ").strip()
    formas = {"1": "PIX", "2": "CARTAO_CREDITO", "3": "BOLETO_FATURADO"}
    forma_pagamento = formas.get(opcao_pag, "PIX")

    # Montagem do Carrinho Multi-Itens
    while True:
        listar_catalogo()
        prod_input = input("\nDigite o ID do produto para adicionar ao carrinho (ou 'F' para fechar pedido): ").strip().upper()
        if prod_input == 'F':
            if not carrinho:
                print("[AVISO] Carrinho vazio. Operação cancelada.")
                conn.close()
                return
            break

        try:
            prod_id = int(prod_input)
            prod = conn.execute("SELECT * FROM produtos WHERE id = ?", (prod_id,)).fetchone()
            if not prod:
                print("[ERRO] Produto não encontrado no catálogo.")
                continue

            qtd = int(input(f"Quantidade desejada de '{prod['nome']}' (Disponível em estoque: {prod['estoque_atual']}): "))
            if qtd <= 0:
                print("[ERRO] A quantidade deve ser maior que zero.")
                continue

            carrinho.append({
                "produto_id": prod["id"],
                "sku": prod["sku"],
                "nome": prod["nome"],
                "classificacao": prod["classificacao"],
                "preco_unitario": prod["preco_venda"],
                "quantidade": qtd,
                "subtotal": prod["preco_venda"] * qtd
            })
            print(f"[OK] Adicionado: {qtd}x {prod['nome']} - Subtotal: R$ {prod['preco_venda'] * qtd:.2f}")

        except ValueError:
            print("[ERRO] Entrada inválida. Digite um número válido.")

    # Execução da Transação ACID
    numero_pedido = f"PED-2026-{uuid.uuid4().hex[:6].upper()}"
    valor_total = sum(item["subtotal"] for item in carrinho)

    print("\nExecutando transação atômica no banco de dados (ACID)...")
    try:
        conn.execute("BEGIN TRANSACTION;")

        # 1. Validação estrita de saldo de todos os itens antes de gravar
        for item in carrinho:
            atual = conn.execute("SELECT estoque_atual, nome FROM produtos WHERE id = ?", (item["produto_id"],)).fetchone()
            if item["quantidade"] > atual["estoque_atual"]:
                # Aborto mandatório se faltar estoque
                raise ValueError(f"Estoque insuficiente para '{atual['nome']}'. Solicitado: {item['quantidade']}, Disponível: {atual['estoque_atual']}.")

        # 2. Inserção do Cabeçalho da Venda
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO vendas (numero_pedido, cliente_nome, cliente_documento, forma_pagamento, valor_total, status_venda, usuario_id)
            VALUES (?, ?, ?, ?, ?, 'CONCLUIDA', ?)
        """, (numero_pedido, cliente_nome, cliente_doc if cliente_doc else "NÃO INFORMADO", forma_pagamento, valor_total, usuario["id"]))
        venda_id = cursor.lastrowid

        # 3. Inserção dos Itens, Débito e Auditoria de Estoque
        for item in carrinho:
            cursor.execute("""
                INSERT INTO itens_venda (venda_id, produto_id, quantidade_vendida, preco_unitario_praticado, subtotal_item)
                VALUES (?, ?, ?, ?, ?)
            """, (venda_id, item["produto_id"], item["quantidade"], item["preco_unitario"], item["subtotal"]))

            cursor.execute("UPDATE produtos SET estoque_atual = estoque_atual - ? WHERE id = ?", (item["quantidade"], item["produto_id"]))

            cursor.execute("""
                INSERT INTO movimentacoes (tipo, quantidade, justificativa, produto_id)
                VALUES ('Saida', ?, ?, ?)
            """, (item["quantidade"], f"Venda PDV {numero_pedido} - Cliente: {cliente_nome}", item["produto_id"]))

        # Confirmação atômica
        conn.commit()
        print("\n[TRANSAÇÃO FINALIZADA COM SUCESSO - COMMIT CONCLUÍDO!]\n")

        # Emissão do Recibo
        imprimir_recibo(numero_pedido, cliente_nome, cliente_doc, forma_pagamento, usuario["nome_completo"], carrinho, valor_total)

    except Exception as e:
        conn.rollback()
        print(f"\n[FALHA NA OPERAÇÃO - ROLLBACK EXECUTADO]: {e}")
        print("[AVISO] Toda a operação foi abortada e nenhum dado foi alterado no banco.\n")
    finally:
        conn.close()

# -------------------------------------------------------------
# EMISSÃO FORMATADA DO RECIBO (REQ-05)
# -------------------------------------------------------------
def imprimir_recibo(pedido, cliente, doc, pagamento, operador, itens, total):
    print("=" * 70)
    print("                    TECHSTORE INFORMÁTICA")
    print("          COMPROVANTE DE VENDA & ORDEM DE FATURAMENTO")
    print("=" * 70)
    print(f"Número do Pedido: {pedido:<20} Data/Hora: (Agora)")
    print(f"Cliente:          {cliente}")
    print(f"Documento:        {doc}")
    print(f"Operador Caixa:   {operador}")
    print(f"Forma Pagamento:  {pagamento}")
    print("-" * 70)
    print(f"{'ITEM / SKU':<32} | {'TIPO':<12} | {'QTD':<4} | {'UNIT.':<10} | {'SUBTOTAL'}")
    print("-" * 70)
    for it in itens:
        tipo_badge = f"[{it['classificacao']}]"
        print(f"{it['nome'][:30]:<32} | {tipo_badge:<12} | {it['quantidade']:<4} | R$ {it['preco_unitario']:<7.2f} | R$ {it['subtotal']:.2f}")
    print("-" * 70)
    print(f"{'VALOR TOTAL CONSOLIDADO:':<55} R$ {total:.2f}")
    print("=" * 70)
    print(f"Autenticação Digital: {pedido}-ACID-VERIFIED\n")

# -------------------------------------------------------------
# MENU PRINCIPAL CLI
# -------------------------------------------------------------
def menu():
    inicializar_banco()
    usuario = autenticar_usuario()

    while True:
        print("\n" + "=" * 45)
        print(f" TECHSTOCK - TERMINAL OPERACIONAL ({usuario['perfil_acesso']})")
        print("=" * 45)
        print("1. Consultar Catálogo de Produtos")
        print("2. Abrir Frente de Caixa (Realizar Venda - ACID)")
        print("3. Consultar Histórico de Vendas")
        print("0. Encerrar Sessão / Sair")
        print("-" * 45)

        opcao = input("Selecione uma opção: ").strip()

        if opcao == "1":
            listar_catalogo()
        elif opcao == "2":
            realizar_venda(usuario)
        elif opcao == "3":
            listar_vendas()
        elif opcao == "0":
            print(f"\nSessão de {usuario['nome_completo']} encerrada. Até logo!")
            break
        else:
            print("\n[ERRO] Opção inválida.")

if __name__ == "__main__":
    menu()