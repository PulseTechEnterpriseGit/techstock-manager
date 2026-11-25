def listar_catalogo():
    conn = get_connection()
    # Usa LEFT JOIN para nunca sumir com produtos da tela
    query = """
        SELECT 
            p.id, p.sku, p.nome, p.classificacao, p.preco_venda, 
            p.estoque_atual, p.estoque_minimo,
            COALESCE(c.nome, 'Sem Categoria') AS categoria, 
            COALESCE(f.razao_social, 'Sem Fornecedor') AS fornecedor
        FROM produtos p
        LEFT JOIN categorias c ON p.categoria_id = c.id
        LEFT JOIN fornecedores f ON p.fornecedor_id = f.id
        ORDER BY p.id ASC;
    """
    produtos = conn.execute(query).fetchall()
    conn.close()

    if not produtos:
        print("\n[AVISO] A tabela de produtos está vazia no banco de dados!")
        return

    print("\n" + "-" * 95)
    print(f"{'ID':<4} | {'SKU':<14} | {'ATIVO':<30} | {'TIPO':<10} | {'PREÇO':<10} | {'SALDO':<6} | {'STATUS'}")
    print("-" * 95)
    for p in produtos:
        alerta = "[ALERTA RUPTURA]" if p["estoque_atual"] <= p["estoque_minimo"] else "REGULAR"
        nome_curto = (p["nome"][:28] + "..") if len(p["nome"]) > 30 else p["nome"]
        tipo = p["classificacao"] if p["classificacao"] else "Geral"
        print(f"{p['id']:<4} | {p['sku']:<14} | {nome_curto:<30} | {tipo:<10} | R$ {p['preco_venda']:<7.2f} | {p['estoque_atual']:<6} | {alerta}")
    print("-" * 95)