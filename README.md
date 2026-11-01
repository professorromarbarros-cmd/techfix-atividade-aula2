# TechFix Informática — Sistema de Ordens de Serviço

Atividade Aula 2 · Aplicações em Data Science · Pós-Graduação em Data Science (UNICAMP)
**Tecnologias:** Supabase (PostgreSQL) · Python + Gradio · Python + Streamlit

```
[Celular / Navegador]                 [Navegador do Gerente]
         |                                      |
 app_gradio.py (cadastro)          app_streamlit.py (gerenciamento)
         |        supabase-py (API REST)        |
         +------------->  SUPABASE  <-----------+
                     (PostgreSQL na nuvem)
```

## Estrutura

```
techfix/
├── sql/
│   ├── schema.sql              # script completo de criação do banco (obrigatório)
│   ├── seed_ficticio.sql       # dados fictícios para popular o painel (opcional)
│   └── testes_restricoes.sql   # 12 testes das restrições (roda e desfaz com ROLLBACK)
├── app_gradio.py               # interface de cadastro (balcão / celular)
├── app_streamlit.py            # painel do gerente (CRUD + indicadores + CSV)
├── requirements.txt            # dependências com versões testadas
├── .env.example                # nomes das variáveis, sem valores
├── .streamlit/secrets.toml.example
├── .gitignore                  # impede versionar .env e secrets.toml
├── README.md
└── evidencias/                 # prints e saídas dos testes
```

## 1. Banco de dados (Supabase)

1. Crie um projeto em [supabase.com](https://supabase.com) (anote a senha do banco).
2. Abra **SQL Editor**, cole todo o `sql/schema.sql` e clique em **Run**.
3. (Opcional) Rode `sql/seed_ficticio.sql` para ter dados de exemplo.
4. (Opcional) Rode `sql/testes_restricoes.sql`: todas as linhas devem mostrar `OK`.

O que o `schema.sql` implementa:

| Requisito | Implementação |
|---|---|
| Chave primária | `id bigint generated always as identity primary key` nas duas tabelas |
| Chave estrangeira + exclusão | `ordens_servico.cliente_id → clientes(id) ON DELETE CASCADE` |
| NOT NULL | todos os campos essenciais; nome, endereço, modelo e problema também não aceitam texto só com espaços |
| UNIQUE no e-mail | `uq_clientes_email`; o CHECK `email = lower(btrim(email))` faz o UNIQUE valer sem diferenciar maiúsculas |
| CHECK de status | `'Aberto','Em análise','Aguardando peça','Concluído','Entregue'` (padrão `'Aberto'`) |
| Validação de e-mail | regex `^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$` (case-insensitive) |
| Validação de celular | somente dígitos, 10 a 13 caracteres: `^[0-9]{10,13}$` |
| Datas | `data_cadastro` e `data_abertura` com `default now()`; `data_atualizacao` mantida por trigger em cada UPDATE |
| Índices | `cliente_id` (o PostgreSQL não indexa FK automaticamente) e `status` |
| Segurança | RLS habilitado + política "Acesso total" (padrão da Aula 2); função do trigger com `search_path` fixo; view com `security_invoker = true` (sem SECURITY DEFINER) |
| Comentários | todos os blocos comentados com `--` |

O script pode ser executado mais de uma vez sem apagar dados. Para recriar do zero, descomente o bloco 0 (RESET).

**Por que ON DELETE CASCADE:** o painel precisa excluir clientes; com CASCADE as OS do cliente saem junto. O painel mostra antes quantas OS serão removidas e exige confirmação. Se a loja preferir preservar o histórico, troque por `ON DELETE RESTRICT`; aí o banco recusa a exclusão de cliente que tenha OS.

> Os números de OS vêm de uma sequência. Uma tentativa de inserção que falha ou é desfeita consome o número, então podem aparecer lacunas (comportamento normal do PostgreSQL).

## 2. Configuração local

Use Python 3.10 ou mais recente.

```bash
python -m venv venv
venv\Scripts\activate            # Windows  (Linux/Mac: source venv/bin/activate)
pip install -r requirements.txt
```

Credenciais: no Supabase, a URL fica em **Project Settings → Data API** e a chave em **Project Settings → API Keys**. Use a chave **anon/public** (`eyJ...`) ou **publishable** (`sb_publishable_...`). **Não use a service_role/secret**: ela ignora o RLS, e o Gradio roda com link público.

- Gradio: copie `.env.example` para `.env` e preencha.
- Streamlit: copie `.streamlit/secrets.toml.example` para `.streamlit/secrets.toml` e preencha. Se esse arquivo não existir, o painel usa o `.env`.

Os dois arquivos reais estão no `.gitignore`.

## 3. Executar

```bash
python app_gradio.py             # imprime a URL local e o link público *.gradio.live (share=True)
streamlit run app_streamlit.py   # abre em http://localhost:8501
```

Abra o link `*.gradio.live` no celular para testar a versão mobile. Se a sua rede bloquear o túnel, use `GRADIO_SHARE=false` no `.env`.

### app_gradio.py (cadastro)
- Usa `gr.Blocks` com `gr.Row`/`gr.Column` (`min_width=280`). No celular, as colunas viram uma única coluna.
- Tem título, instrução de uso, rótulos e placeholders em todos os campos. O problema é um campo de várias linhas.
- Valida antes de enviar: campos obrigatórios, formato do e-mail, celular só com números e de 10 a 13 dígitos.
- Converte o e-mail para minúsculas. Se o e-mail já existir, **reaproveita o cliente** (os dados cadastrais existentes são mantidos). Se não existir, cria o cliente. Também trata o caso de dois atendentes cadastrarem o mesmo e-mail ao mesmo tempo.
- Abre a OS com status **Aberto**, mostra o **nº da OS** e limpa o formulário. Em caso de erro, os campos ficam preenchidos.
- O botão **Limpar** esvazia todos os campos.
- Todo acesso ao banco fica em `try/except`. Erros de restrição, permissão e conexão aparecem como mensagens amigáveis.

### app_streamlit.py (painel do gerente)
- **Sidebar:** filtros por nome (sem diferenciar acentos nem maiúsculas), e-mail e status, além do botão para recarregar os dados.
- **📋 Consultar:** `st.dataframe` com cada OS e os dados do cliente, lidos da view `vw_ordens_servico` com paginação de 1000 em 1000. Inclui a lista de clientes e o **bônus: exportar CSV dos dados filtrados** (`st.download_button`, separador `;` e UTF-8 com BOM para abrir direto no Excel).
- **➕ Cadastrar:** nova OS para um cliente existente ou para um cliente novo (reaproveitando o cadastro se o e-mail já existir).
- **✏️ Editar/Excluir:** altera o status, o modelo e o problema da OS, e o nome, endereço, e-mail e celular do cliente, com validação. A exclusão de OS ou de cliente exige marcar uma confirmação. Ao excluir um cliente, o painel avisa quantas OS serão removidas pela cascata.
- **📊 Indicadores:** `st.metric` com o total e a contagem de cada status, mais o total em andamento, e gráfico de barras por status na ordem do fluxo.
- Todo acesso ao banco fica em `try/except`, com mensagens amigáveis.

## 4. Testes realizados

Os testes rodaram num ambiente que reproduz o Supabase: **PostgreSQL 16** e **PostgREST 12**, o mesmo servidor da API REST (Data API) do Supabase. A API ficou exposta em `/rest/v1`, com os papéis `anon`/`authenticated` e chave JWT anon. Os apps usaram o `supabase-py` 2.33 sem nenhuma alteração.

- `schema.sql`: executado duas vezes sem erro, o que confirma que pode ser rodado de novo com segurança.
- `testes_restricoes.sql`: os 12 testes passaram usando o papel `anon`, o que valida também o RLS e as permissões. A saída está em `evidencias/teste_local_restricoes_sql.txt`.
- Gradio: cadastro com cliente novo, reaproveitamento por e-mail (inclusive digitado com maiúsculas), validações, falha de conexão e falta de credenciais.
- Streamlit: consultar, filtrar, exportar CSV, cadastrar, editar OS, editar cliente (validação e e-mail duplicado barrado pelo UNIQUE), excluir OS, excluir cliente com cascata e ver indicadores. Nenhuma exceção ocorreu. Também foram testadas a leitura por `secrets.toml` e a falta de credenciais.

Todos os dados são fictícios: nomes inventados, e-mails no domínio reservado `example.com` e celulares sem dono (LGPD).

## 5. Evidências

| Item exigido | Arquivo |
|---|---|
| (a) Gradio no celular | `a_gradio_celular_formulario.png` (tela de 390 px, viewport de iPhone 13) |
| (b) Cadastro realizado | `b_gradio_celular_cadastro_sucesso.png`, `b3_gradio_desktop_cliente_reaproveitado.png`, `b2_gradio_celular_validacao.png` |
| (c) Tabelas preenchidas | **capturar no Table Editor do Supabase** (`clientes` e `ordens_servico`); referência local em `teste_local_tabelas.txt` |
| (d) Streamlit: consulta, edição, indicadores | `d1`…`d11` (consulta, filtro, cadastro, edição, validação, exclusão, cascata, indicadores, celular) |
| Bônus CSV | `bonus_export_filtrado.csv` |
