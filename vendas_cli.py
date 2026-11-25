import os
import sqlite3
from werkzeug.security import check_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "techstock.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def executar_venda_cli():
    conn = get_db()
    print("\n=== TECHSTOCK MANAGER - TERMINAL PDV (TESTE ACID) ===")

    email = input("E-mail do operador/gerente: ").strip()
    senha = input("Senha: ").strip()

    user = conn.execute("SELECT * FROM usuarios WHERE email = ?", (email,)).fetchone()
    if not user or not check_password_hash(user["senha_hash"], senha):
        print("[ERRO] Credenciais invalidas.")
        conn.close()
        return

    print(f"\nAutenticado como: {user['nome']} ({user['cargo'].upper()})")
    cliente_nome = input("Razao Social do Cliente B2B: ").strip()
    cliente_cnpj = input("CNPJ do Cliente: ").strip()
    forma_pagamento = input("Forma de Pagamento (PIX / Boleto / Cartao): ").strip()

    produtos = conn.execute("SELECT id, sku, nome, tipo, preco, estoque_atual FROM produtos").fetchall()
    print("\n--- CATALOGO DISPONIVEL ---")
    for p in produtos:
        saldo = "Ilimitado" if p["tipo"] == "digital" else f"{p['estoque_atual']} un."
        print(f"ID {p['id']} | {p['sku']} - {p['nome']} | R$ {p['preco']:.2f} | Saldo: {saldo}")

    try:
        prod_id = int(input("\nDigite o ID do produto: "))
        qtd = int(input("Digite a quantidade: "))

        # Inicia transação atômica ACID
        conn.execute("BEGIN IMMEDIATE;")

        prod = conn.execute("SELECT * FROM produtos WHERE id = ?", (prod_id,)).fetchone()
        if not prod:
            raise ValueError("Produto nao encontrado.")

        if prod["tipo"] == "fisico" and prod["estoque_atual"] < qtd:
            raise ValueError(
                f"Estoque insuficiente para {prod['nome']}. Disponivel: {prod['estoque_atual']}, Solicitado: {qtd}."
            )

        total = prod["preco"] * qtd
        cursor = conn.execute(
            """INSERT INTO vendas (cliente_nome, cliente_cnpj, forma_pagamento, valor_total, usuario_id)
               VALUES (?, ?, ?, ?, ?)""",
            (cliente_nome, cliente_cnpj, forma_pagamento, total, user["id"]),
        )
        venda_id = cursor.lastrowid

        conn.execute(
            """INSERT INTO itens_venda (venda_id, produto_id, quantidade, preco_unitario, subtotal)
               VALUES (?, ?, ?, ?, ?)""",
            (venda_id, prod["id"], qtd, prod["preco"], total),
        )

        if prod["tipo"] == "fisico":
            conn.execute(
                "UPDATE produtos SET estoque_atual = estoque_atual - ? WHERE id = ?",
                (qtd, prod["id"]),
            )
            conn.execute(
                """INSERT INTO movimentacoes (produto_id, tipo, quantidade, motivo, usuario_id)
                   VALUES (?, 'SAIDA', ?, ?, ?)""",
                (prod["id"], qtd, f"Baixa Automatica CLI #{venda_id}", user["id"]),
            )

        conn.execute(
            "INSERT INTO auditoria_logs (usuario_id, acao, detalhes, ip_origem) VALUES (?, ?, ?, ?)",
            (user["id"], "VENDA_CLI", f"Venda CLI #{venda_id} para {cliente_nome} - R$ {total:.2f}", "127.0.0.1"),
        )

        conn.commit()
        print(f"\n[COMMIT] Venda #{venda_id} concluida com sucesso! Baixa automatica efetuada.")

    except Exception as e:
        conn.rollback()
        print(f"\n[ROLLBACK] Transacao desfeita por seguranca: {e}")
    finally:
        conn.close()


if __name__ == "__main__":
    executar_venda_cli()