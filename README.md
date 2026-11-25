# TechStock Manager + Módulo PDV/Checkout (PulseTech)

Solução web integrada de gestão de inventário, controle de acesso (RBAC) e frente de caixa transacional (ACID) desenvolvida pela **PulseTech Automação e Inteligência de Dados Ltda.** para a **TechStore Informática & Serviços Corporativos**.

## Arquitetura & Stack Tecnológica
- **Backend:** Python 3 + Flask 3.0.3
- **Banco de Dados:** SQLite3 com integridade referencial ativada (`PRAGMA foreign_keys = ON`)
- **Segurança:** Hash de senhas via `Werkzeug` e controle de sessão baseado em papéis (`OPERADOR` vs. `GERENTE`)
- **Frontend:** HTML5, Bootstrap 5.3 e JavaScript Vanilla

## Modelagem Relacional (7 Tabelas)
- **Núcleo de Inventário (`database.sql`):** `categorias`, `fornecedores`, `produtos`, `movimentacoes`
- **Núcleo Comercial & RBAC (`migration_v2.sql`):** `usuarios`, `vendas`, `itens_venda`

## Como Executar o Projeto
1. Clone o repositório e acesse a pasta do projeto:
   ```bash
   git clone [https://github.com/PulseTechEnterpriseGit/techstock-manager.git](https://github.com/PulseTechEnterpriseGit/techstock-manager.git)
   cd techstock-manager