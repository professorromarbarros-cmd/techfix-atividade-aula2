"""
TechFix Informática — Painel do Gerente (Streamlit)

CRUD completo das ordens de serviço e clientes no Supabase:
  • Consultar   — tabela de OS + dados do cliente, com exportação CSV (bônus)
  • Cadastrar   — nova OS para cliente existente ou novo
  • Editar/Excluir — status/dados da OS e dados do cliente; exclusão com confirmação
  • Indicadores — st.metric por status + gráfico de barras
Filtros (nome, e-mail, status) na barra lateral valem para todas as abas.

Credenciais: .streamlit/secrets.toml  OU  variáveis de ambiente/.env
(SUPABASE_URL e SUPABASE_KEY) — nunca escritas no código.

Executar:  streamlit run app_streamlit.py
"""

from __future__ import annotations

import os
import re
import unicodedata

import altair as alt
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from postgrest.exceptions import APIError
from supabase import Client, create_client

# ----------------------------------------------------------------------
# Configuração
# ----------------------------------------------------------------------
st.set_page_config(page_title="TechFix — Painel do Gerente", page_icon="🛠️", layout="wide")
load_dotenv()

STATUS = ["Aberto", "Em análise", "Aguardando peça", "Concluído", "Entregue"]
FUSO = "America/Bahia"
PAGINA = 1000  # o Supabase devolve no máximo 1000 linhas por requisição

# Mesmas regras dos CHECKs do schema.sql
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
CELULAR_RE = re.compile(r"^[0-9]{10,13}$")

MENSAGENS_RESTRICAO = {
    "uq_clientes_email": "Já existe um cliente com este e-mail.",
    "chk_clientes_email_formato": "E-mail em formato inválido.",
    "chk_clientes_email_normalizado": "E-mail deve estar em minúsculas e sem espaços.",
    "chk_clientes_celular_formato": "Celular deve ter apenas números (10 a 13 dígitos).",
    "chk_clientes_nome_preenchido": "Informe o nome do cliente.",
    "chk_clientes_endereco_preenchido": "Informe o endereço.",
    "chk_os_modelo_preenchido": "Informe o modelo do computador.",
    "chk_os_problema_preenchido": "Descreva o problema apresentado.",
    "chk_os_status": "Status inválido.",
    "fk_os_cliente": "Cliente não encontrado para esta OS.",
}


def ler_credencial(nome: str) -> str:
    """Busca primeiro em st.secrets; se não houver secrets.toml, usa o ambiente/.env."""
    try:
        valor = st.secrets[nome]
        if valor:
            return str(valor).strip()
    except Exception:  # noqa: BLE001 — secrets.toml ausente ou chave inexistente
        pass
    return os.getenv(nome, "").strip()


@st.cache_resource(show_spinner=False)
def get_supabase() -> Client:
    url, key = ler_credencial("SUPABASE_URL"), ler_credencial("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError(
            "Credenciais ausentes: defina SUPABASE_URL e SUPABASE_KEY em "
            ".streamlit/secrets.toml ou no arquivo .env."
        )
    return create_client(url, key)


def mensagem_erro(erro: Exception) -> str:
    """Converte exceções do banco/rede em mensagens amigáveis."""
    if isinstance(erro, APIError):
        texto = f"{erro.message or ''} {erro.details or ''}"
        for restricao, msg in MENSAGENS_RESTRICAO.items():
            if restricao in texto:
                return msg
        if erro.code == "42501":
            return "Permissão negada pelo banco (verifique o RLS/políticas e a chave usada)."
        if erro.code in ("PGRST205", "42P01"):
            return "Tabela/view não encontrada: execute o schema.sql no SQL Editor do Supabase."
        return f"Erro no banco de dados: {erro.message}"
    if isinstance(erro, RuntimeError):
        return str(erro)
    return f"Não foi possível conectar ao Supabase ({type(erro).__name__}). Verifique a internet e o SUPABASE_URL."


def avisar(tipo: str, texto: str) -> None:
    """Guarda uma mensagem para exibir após o st.rerun()."""
    st.session_state["aviso"] = (tipo, texto)


def apos_gravar(tipo: str, texto: str) -> None:
    """Invalida o cache, guarda a mensagem e recarrega a página."""
    st.cache_data.clear()
    avisar(tipo, texto)
    st.rerun()


def sem_acento(txt: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", str(txt)) if not unicodedata.combining(c)).lower()


def validar_cliente(nome, endereco, email, celular) -> list[str]:
    erros = []
    if not nome:
        erros.append("Informe o nome do cliente.")
    if not endereco:
        erros.append("Informe o endereço.")
    if not email:
        erros.append("Informe o e-mail.")
    elif not EMAIL_RE.match(email):
        erros.append("E-mail em formato inválido (ex.: nome@dominio.com).")
    if not celular:
        erros.append("Informe o celular/WhatsApp.")
    elif not celular.isdigit():
        erros.append("Celular deve conter apenas números (sem espaços, traços ou parênteses).")
    elif not CELULAR_RE.match(celular):
        erros.append("Celular deve ter de 10 a 13 dígitos (DDD + número).")
    return erros


# ----------------------------------------------------------------------
# Leitura (com cache curto)
# ----------------------------------------------------------------------
def buscar_tudo(tabela: str, colunas: str, ordem: str) -> list[dict]:
    """Lê todas as linhas paginando de 1000 em 1000."""
    sb = get_supabase()
    linhas, inicio = [], 0
    while True:
        lote = (
            sb.table(tabela).select(colunas).order(ordem)
            .range(inicio, inicio + PAGINA - 1).execute().data
        )
        linhas.extend(lote)
        if len(lote) < PAGINA:
            return linhas
        inicio += PAGINA


def para_data_local(serie: pd.Series) -> pd.Series:
    return pd.to_datetime(serie, utc=True, format="ISO8601").dt.tz_convert(FUSO).dt.tz_localize(None)


@st.cache_data(ttl=60, show_spinner="Carregando ordens de serviço…")
def carregar_os() -> pd.DataFrame:
    colunas = [
        "os_id", "status", "cliente_nome", "cliente_email", "cliente_celular",
        "cliente_endereco", "modelo_computador", "problema_relatado",
        "data_abertura", "data_atualizacao", "cliente_id",
    ]
    df = pd.DataFrame(buscar_tudo("vw_ordens_servico", ",".join(colunas), "os_id"), columns=colunas)
    for c in ("data_abertura", "data_atualizacao"):
        df[c] = para_data_local(df[c])
    return df.sort_values("os_id", ascending=False, ignore_index=True)


@st.cache_data(ttl=60, show_spinner="Carregando clientes…")
def carregar_clientes() -> pd.DataFrame:
    colunas = ["id", "nome", "email", "celular_whatsapp", "endereco", "data_cadastro"]
    df = pd.DataFrame(buscar_tudo("clientes", ",".join(colunas), "nome"), columns=colunas)
    df["data_cadastro"] = para_data_local(df["data_cadastro"])
    return df


# ----------------------------------------------------------------------
# Cabeçalho, aviso pendente e carga de dados
# ----------------------------------------------------------------------
st.title("🛠️ TechFix Informática — Painel do Gerente")
st.caption("Gerenciamento das ordens de serviço no Supabase · use apenas dados fictícios (LGPD)")

# Mensagem da última gravação: exibida como toast para não deslocar o layout
# (assim as abas não "pulam" de volta para a primeira após o st.rerun()).
if "aviso" in st.session_state:
    tipo, texto = st.session_state.pop("aviso")
    st.toast(texto, icon="✅" if tipo == "success" else "⚠️", duration="long")

try:
    df_os = carregar_os()
    df_cli = carregar_clientes()
except Exception as erro:  # noqa: BLE001
    st.error(f"❌ {mensagem_erro(erro)}")
    st.stop()

# ----------------------------------------------------------------------
# Sidebar: filtros
# ----------------------------------------------------------------------
with st.sidebar:
    st.header("🔎 Filtros")
    f_nome = st.text_input("Nome do cliente", placeholder="parte do nome")
    f_email = st.text_input("E-mail", placeholder="parte do e-mail")
    f_status = st.multiselect("Status", STATUS, default=STATUS)
    st.divider()
    if st.button("🔄 Recarregar dados do banco", width="stretch"):
        st.cache_data.clear()
        st.rerun()
    st.caption(f"{len(df_os)} OS e {len(df_cli)} clientes no banco.")

filtro = df_os["status"].isin(f_status)
if f_nome.strip():
    alvo = sem_acento(f_nome.strip())
    filtro &= df_os["cliente_nome"].map(sem_acento).str.contains(alvo, regex=False)
if f_email.strip():
    filtro &= df_os["cliente_email"].str.contains(f_email.strip().lower(), regex=False)
df_filtrado = df_os[filtro]

aba_consultar, aba_cadastrar, aba_editar, aba_indicadores = st.tabs(
    ["📋 Consultar", "➕ Cadastrar", "✏️ Editar/Excluir", "📊 Indicadores"],
    key="aba_ativa",      # mantém a aba aberta após salvar/excluir
    on_change="rerun",
)

# ----------------------------------------------------------------------
# Aba 1 — Consultar (READ) + exportação CSV (bônus)
# ----------------------------------------------------------------------
with aba_consultar:
    st.subheader("Ordens de serviço")
    st.caption(f"{len(df_filtrado)} de {len(df_os)} OS exibidas conforme os filtros da barra lateral.")
    st.dataframe(
        df_filtrado.drop(columns=["cliente_id"]),
        hide_index=True,
        width="stretch",
        column_config={
            "os_id": st.column_config.NumberColumn("Nº OS", format="%d"),
            "status": "Status",
            "cliente_nome": "Cliente",
            "cliente_email": "E-mail",
            "cliente_celular": "Celular/WhatsApp",
            "cliente_endereco": "Endereço",
            "modelo_computador": "Modelo",
            "problema_relatado": st.column_config.TextColumn("Problema", width="large"),
            "data_abertura": st.column_config.DatetimeColumn("Abertura", format="DD/MM/YYYY HH:mm"),
            "data_atualizacao": st.column_config.DatetimeColumn("Atualização", format="DD/MM/YYYY HH:mm"),
        },
    )

    # Bônus (+0,5): exporta exatamente o que está filtrado.
    # Separador ";" e UTF-8 com BOM para abrir corretamente no Excel em português.
    csv = df_filtrado.drop(columns=["cliente_id"]).to_csv(
        index=False, sep=";", date_format="%d/%m/%Y %H:%M"
    ).encode("utf-8-sig")
    st.download_button(
        "⬇️ Exportar dados filtrados (CSV)",
        data=csv,
        file_name="techfix_ordens_servico.csv",
        mime="text/csv",
        disabled=df_filtrado.empty,
    )

    with st.expander(f"👥 Clientes cadastrados ({len(df_cli)})"):
        st.dataframe(
            df_cli,
            hide_index=True,
            width="stretch",
            column_config={
                "id": st.column_config.NumberColumn("ID", format="%d"),
                "nome": "Nome", "email": "E-mail", "celular_whatsapp": "Celular/WhatsApp",
                "endereco": "Endereço",
                "data_cadastro": st.column_config.DatetimeColumn("Cadastro", format="DD/MM/YYYY HH:mm"),
            },
        )

# ----------------------------------------------------------------------
# Aba 2 — Cadastrar (CREATE)
# ----------------------------------------------------------------------
with aba_cadastrar:
    st.subheader("Nova ordem de serviço")
    tipo_cliente = st.radio(
        "Cliente", ["Cliente já cadastrado", "Novo cliente"], horizontal=True,
        disabled=df_cli.empty, index=1 if df_cli.empty else 0,
    )
    with st.form("form_nova_os", clear_on_submit=True):
        if tipo_cliente == "Cliente já cadastrado" and not df_cli.empty:
            rotulos = {r.id: f"{r.nome} — {r.email}" for r in df_cli.itertuples()}
            cli_id = st.selectbox("Selecione o cliente", list(rotulos), format_func=rotulos.get)
        else:
            c1, c2 = st.columns(2)
            n_nome = c1.text_input("Nome do Cliente *", placeholder="Ex.: Maria Fictícia")
            n_email = c1.text_input("E-mail *", placeholder="Ex.: maria@example.com")
            n_endereco = c2.text_input("Endereço *", placeholder="Ex.: Rua das Flores, 123")
            n_celular = c2.text_input("Celular/WhatsApp * (somente números)", placeholder="77999998888", max_chars=13)
        c3, c4 = st.columns(2)
        n_modelo = c3.text_input("Modelo do Computador *", placeholder="Ex.: Notebook Dell Inspiron 15")
        n_status = c3.selectbox("Status inicial", STATUS, index=0)
        n_problema = c4.text_area("Problema Apresentado *", placeholder="Descreva o defeito…", height=122)
        enviar = st.form_submit_button("Cadastrar OS", type="primary")

    if enviar:
        modelo, problema = n_modelo.strip(), n_problema.strip()
        erros = []
        novo_cliente = not (tipo_cliente == "Cliente já cadastrado" and not df_cli.empty)
        if novo_cliente:
            nome, endereco = n_nome.strip(), n_endereco.strip()
            email, celular = n_email.strip().lower(), n_celular.strip()
            erros += validar_cliente(nome, endereco, email, celular)
        if not modelo:
            erros.append("Informe o modelo do computador.")
        if not problema:
            erros.append("Descreva o problema apresentado.")

        if erros:
            st.error("❌ Corrija antes de enviar:\n\n" + "\n".join(f"- {e}" for e in erros))
        else:
            try:
                sb = get_supabase()
                info = ""
                if novo_cliente:
                    # Reaproveita pelo e-mail, como no app de balcão
                    achado = sb.table("clientes").select("id, nome").eq("email", email).limit(1).execute().data
                    if achado:
                        cli_id = achado[0]["id"]
                        info = f" O e-mail já existia: cliente {achado[0]['nome']} (ID {cli_id}) reaproveitado."
                    else:
                        cli_id = sb.table("clientes").insert(
                            {"nome": nome, "endereco": endereco, "email": email, "celular_whatsapp": celular}
                        ).execute().data[0]["id"]
                        info = f" Cliente novo cadastrado (ID {cli_id})."
                nova = sb.table("ordens_servico").insert(
                    {"cliente_id": int(cli_id), "modelo_computador": modelo,
                     "problema_relatado": problema, "status": n_status}
                ).execute().data[0]
                apos_gravar("success", f"OS nº {nova['id']} cadastrada com status '{nova['status']}'.{info}")
            except Exception as erro:  # noqa: BLE001
                st.error(f"❌ {mensagem_erro(erro)}")

# ----------------------------------------------------------------------
# Aba 3 — Editar/Excluir (UPDATE + DELETE)
# ----------------------------------------------------------------------
with aba_editar:
    col_os, col_cli = st.columns(2, gap="large")

    # ---------- Ordem de serviço ----------
    with col_os:
        st.subheader("Ordem de serviço")
        if df_filtrado.empty:
            st.info("Nenhuma OS para os filtros atuais.")
        else:
            rot_os = {
                r.os_id: f"OS {r.os_id} — {r.cliente_nome} — {r.status}"
                for r in df_filtrado.itertuples()
            }
            os_id = st.selectbox("Selecione a OS (respeita os filtros)", list(rot_os), format_func=rot_os.get)
            os_atual = df_filtrado.loc[df_filtrado["os_id"] == os_id].iloc[0]

            with st.form(f"form_os_{os_id}"):
                e_status = st.selectbox("Status", STATUS, index=STATUS.index(os_atual["status"]))
                e_modelo = st.text_input("Modelo do Computador", value=os_atual["modelo_computador"])
                e_problema = st.text_area("Problema Apresentado", value=os_atual["problema_relatado"])
                salvar_os = st.form_submit_button("💾 Salvar OS", type="primary")
            if salvar_os:
                if not e_modelo.strip() or not e_problema.strip():
                    st.error("❌ Modelo e problema não podem ficar em branco.")
                else:
                    try:
                        get_supabase().table("ordens_servico").update(
                            {"status": e_status, "modelo_computador": e_modelo.strip(),
                             "problema_relatado": e_problema.strip()}
                        ).eq("id", int(os_id)).execute()
                        apos_gravar("success", f"OS nº {os_id} atualizada (status: {e_status}).")
                    except Exception as erro:  # noqa: BLE001
                        st.error(f"❌ {mensagem_erro(erro)}")

            with st.container(border=True):
                st.markdown("**🗑️ Excluir esta OS**")
                conf_os = st.checkbox(f"Confirmo a exclusão definitiva da OS nº {os_id}.", key=f"conf_os_{os_id}")
                if st.button("Excluir OS", disabled=not conf_os, key=f"del_os_{os_id}"):
                    try:
                        get_supabase().table("ordens_servico").delete().eq("id", int(os_id)).execute()
                        apos_gravar("success", f"OS nº {os_id} excluída.")
                    except Exception as erro:  # noqa: BLE001
                        st.error(f"❌ {mensagem_erro(erro)}")

    # ---------- Cliente ----------
    with col_cli:
        st.subheader("Cliente")
        if df_cli.empty:
            st.info("Nenhum cliente cadastrado.")
        else:
            rot_cli = {r.id: f"{r.nome} — {r.email}" for r in df_cli.itertuples()}
            cli_id = st.selectbox("Selecione o cliente", list(rot_cli), format_func=rot_cli.get, key="sel_cli_edit")
            cli = df_cli.loc[df_cli["id"] == cli_id].iloc[0]

            with st.form(f"form_cli_{cli_id}"):
                c_nome = st.text_input("Nome", value=cli["nome"])
                c_endereco = st.text_input("Endereço", value=cli["endereco"])
                c_email = st.text_input("E-mail", value=cli["email"])
                c_celular = st.text_input("Celular/WhatsApp (somente números)", value=cli["celular_whatsapp"], max_chars=13)
                salvar_cli = st.form_submit_button("💾 Salvar cliente", type="primary")
            if salvar_cli:
                dados = {
                    "nome": c_nome.strip(), "endereco": c_endereco.strip(),
                    "email": c_email.strip().lower(), "celular_whatsapp": c_celular.strip(),
                }
                erros = validar_cliente(*dados.values())
                if erros:
                    st.error("❌ Corrija antes de salvar:\n\n" + "\n".join(f"- {e}" for e in erros))
                else:
                    try:
                        get_supabase().table("clientes").update(dados).eq("id", int(cli_id)).execute()
                        apos_gravar("success", f"Dados do cliente {dados['nome']} atualizados.")
                    except Exception as erro:  # noqa: BLE001
                        st.error(f"❌ {mensagem_erro(erro)}")

            qtd_os = int((df_os["cliente_id"] == cli_id).sum())
            with st.container(border=True):
                st.markdown("**🗑️ Excluir este cliente**")
                if qtd_os:
                    st.warning(
                        f"Este cliente possui **{qtd_os} OS**, que também serão excluídas "
                        "(regra ON DELETE CASCADE do banco)."
                    )
                conf_cli = st.checkbox(
                    f"Confirmo a exclusão definitiva de {cli['nome']}"
                    + (f" e das suas {qtd_os} OS." if qtd_os else "."),
                    key=f"conf_cli_{cli_id}",
                )
                if st.button("Excluir cliente", disabled=not conf_cli, key=f"del_cli_{cli_id}"):
                    try:
                        get_supabase().table("clientes").delete().eq("id", int(cli_id)).execute()
                        apos_gravar("success", f"Cliente {cli['nome']} excluído ({qtd_os} OS removidas junto).")
                    except Exception as erro:  # noqa: BLE001
                        st.error(f"❌ {mensagem_erro(erro)}")

# ----------------------------------------------------------------------
# Aba 4 — Indicadores
# ----------------------------------------------------------------------
with aba_indicadores:
    st.subheader("Indicadores por status")
    st.caption("Calculados sobre as OS que atendem aos filtros da barra lateral.")
    contagem = df_filtrado["status"].value_counts().reindex(STATUS, fill_value=0)

    cols = st.columns(len(STATUS) + 1)
    cols[0].metric("Total de OS", int(contagem.sum()))
    for col, status in zip(cols[1:], STATUS):
        col.metric(status, int(contagem[status]))

    pendentes = int(contagem[["Aberto", "Em análise", "Aguardando peça"]].sum())
    st.metric("Em andamento (Aberto + Em análise + Aguardando peça)", pendentes)

    dados_graf = contagem.rename_axis("Status").reset_index(name="Quantidade")
    grafico = (
        alt.Chart(dados_graf)
        .mark_bar()
        .encode(
            x=alt.X("Status:N", sort=STATUS, axis=alt.Axis(labelAngle=0)),  # ordem do fluxo
            y=alt.Y("Quantidade:Q", axis=alt.Axis(tickMinStep=1)),
            tooltip=["Status", "Quantidade"],
        )
        .properties(title="Ordens de serviço por status", height=340)
    )
    rotulos_barras = grafico.mark_text(dy=-8).encode(text="Quantidade:Q")
    st.altair_chart(grafico + rotulos_barras, width="stretch")
