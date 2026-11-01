"""
TechFix Informática — Aplicação de Atendimento (Gradio)

Formulário de balcão (PC e celular) que:
  1. valida os campos (obrigatórios, e-mail e celular);
  2. reaproveita o cliente se o e-mail já existir (senão, cria um novo);
  3. abre a ordem de serviço com status 'Aberto';
  4. informa o número da OS gerada (ou o erro ocorrido).

Credenciais: lidas de variáveis de ambiente / arquivo .env
(SUPABASE_URL e SUPABASE_KEY) — nunca escritas no código.

Executar:  python app_gradio.py
"""

from __future__ import annotations

import os
import re

import gradio as gr
from dotenv import load_dotenv
from postgrest.exceptions import APIError
from supabase import Client, create_client

load_dotenv()  # carrega o .env (se existir) para os.environ

# Mesmas regras dos CHECKs do schema.sql (validação dupla: app + banco)
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
CELULAR_RE = re.compile(r"^[0-9]{10,13}$")

# Tradução das restrições do banco para mensagens amigáveis
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

_cliente_supabase: Client | None = None


def get_supabase() -> Client:
    """Cria (uma única vez) o cliente Supabase a partir do ambiente."""
    global _cliente_supabase
    if _cliente_supabase is None:
        url = os.getenv("SUPABASE_URL", "").strip()
        key = os.getenv("SUPABASE_KEY", "").strip()
        if not url or not key:
            raise RuntimeError(
                "Credenciais ausentes: defina SUPABASE_URL e SUPABASE_KEY no arquivo .env."
            )
        _cliente_supabase = create_client(url, key)
    return _cliente_supabase


def mensagem_erro_banco(erro: Exception) -> str:
    """Converte exceções do banco/rede em mensagens amigáveis."""
    if isinstance(erro, APIError):
        texto = f"{erro.message or ''} {erro.details or ''}"
        for restricao, msg in MENSAGENS_RESTRICAO.items():
            if restricao in texto:
                return msg
        if erro.code == "42501":
            return "Permissão negada pelo banco (verifique o RLS/políticas e a chave usada)."
        if erro.code in ("PGRST205", "42P01"):
            return "Tabela não encontrada: execute o schema.sql no SQL Editor do Supabase."
        return f"Erro no banco de dados: {erro.message}"
    if isinstance(erro, RuntimeError):
        return str(erro)
    return (
        "Não foi possível conectar ao Supabase. Verifique a internet e o SUPABASE_URL "
        f"({type(erro).__name__})."
    )


def validar(nome, endereco, email, celular, modelo, problema) -> list[str]:
    """Validação antes do envio. Retorna a lista de problemas encontrados."""
    erros = []
    obrigatorios = {
        "Nome do Cliente": nome,
        "Endereço": endereco,
        "E-mail": email,
        "Celular/WhatsApp": celular,
        "Modelo do Computador": modelo,
        "Problema Apresentado": problema,
    }
    vazios = [rotulo for rotulo, valor in obrigatorios.items() if not valor]
    if vazios:
        erros.append("Campos obrigatórios não preenchidos: " + ", ".join(vazios) + ".")
    if email and not EMAIL_RE.match(email):
        erros.append("E-mail em formato inválido (ex.: nome@dominio.com).")
    if celular and not celular.isdigit():
        erros.append("Celular/WhatsApp deve conter apenas números (sem espaços, traços ou parênteses).")
    elif celular and not CELULAR_RE.match(celular):
        erros.append("Celular/WhatsApp deve ter de 10 a 13 dígitos (DDD + número).")
    return erros


def obter_ou_criar_cliente(sb: Client, nome, endereco, email, celular) -> tuple[dict, bool]:
    """Reaproveita o cliente pelo e-mail; se não existir, cria. Retorna (cliente, novo?)."""
    existente = (
        sb.table("clientes").select("id, nome").eq("email", email).limit(1).execute()
    )
    if existente.data:
        return existente.data[0], False
    try:
        criado = (
            sb.table("clientes")
            .insert(
                {
                    "nome": nome,
                    "endereco": endereco,
                    "email": email,
                    "celular_whatsapp": celular,
                }
            )
            .execute()
        )
        return criado.data[0], True
    except APIError as erro:
        # Corrida: outro atendente cadastrou o mesmo e-mail entre a busca e o insert
        if erro.code == "23505":
            de_novo = sb.table("clientes").select("id, nome").eq("email", email).limit(1).execute()
            if de_novo.data:
                return de_novo.data[0], False
        raise


def cadastrar(nome, endereco, email, celular, modelo, problema):
    """Ação do botão Cadastrar. Retorna a mensagem + os valores dos 6 campos."""
    # Normalização: tira espaços das pontas; e-mail sempre minúsculo
    nome = (nome or "").strip()
    endereco = (endereco or "").strip()
    email = (email or "").strip().lower()
    celular = (celular or "").strip()
    modelo = (modelo or "").strip()
    problema = (problema or "").strip()
    campos = (nome, endereco, email, celular, modelo, problema)

    erros = validar(*campos)
    if erros:
        msg = "### ❌ Corrija antes de enviar\n" + "\n".join(f"- {e}" for e in erros)
        return (msg, *campos)  # mantém o que foi digitado

    try:
        sb = get_supabase()
        cliente, novo = obter_ou_criar_cliente(sb, nome, endereco, email, celular)
        os_criada = (
            sb.table("ordens_servico")
            .insert(
                {
                    "cliente_id": cliente["id"],
                    "modelo_computador": modelo,
                    "problema_relatado": problema,
                    "status": "Aberto",
                }
            )
            .execute()
        )
        numero_os = os_criada.data[0]["id"]
    except Exception as erro:  # noqa: BLE001 — qualquer falha vira mensagem amigável
        return (f"### ❌ Não foi possível cadastrar\n{mensagem_erro_banco(erro)}", *campos)

    if novo:
        origem = f"Cliente **novo** cadastrado (ID {cliente['id']})."
    else:
        origem = (
            f"Cliente **já cadastrado** reaproveitado pelo e-mail: "
            f"{cliente['nome']} (ID {cliente['id']}). Os dados cadastrais existentes "
            "foram mantidos; para alterá-los, use o painel do gerente."
        )
    msg = (
        f"### ✅ Ordem de Serviço nº {numero_os} aberta com sucesso\n"
        f"- Status: **Aberto**\n- Equipamento: {modelo}\n- {origem}\n\n"
        f"Informe ao cliente o número da OS: **{numero_os}**."
    )
    return (msg, "", "", "", "", "", "")  # sucesso: limpa o formulário


def limpar():
    """Ação do botão Limpar: esvazia todos os campos e a mensagem."""
    return ("", "", "", "", "", "", "")


CSS = """
.gradio-container {max-width: 900px !important; margin: 0 auto !important;}
#titulo h1 {margin-bottom: 0.2rem;}
"""

with gr.Blocks(title="TechFix — Abertura de OS") as demo:
    gr.Markdown(
        "# 🛠️ TechFix Informática — Abertura de Ordem de Serviço\n"
        "**Como usar:** preencha os dados do cliente e do equipamento e toque em "
        "**Cadastrar**. Se o e-mail já estiver cadastrado, o cliente é reaproveitado. "
        "A OS é aberta com status *Aberto* e o número gerado aparece abaixo.  \n"
        "*Use apenas dados fictícios em testes (LGPD).*",
        elem_id="titulo",
    )

    gr.Markdown("### 👤 Dados do cliente")
    with gr.Row():
        with gr.Column(min_width=280):
            in_nome = gr.Textbox(label="Nome do Cliente *", placeholder="Ex.: Maria Fictícia da Silva", max_length=120)
            in_email = gr.Textbox(label="E-mail *", placeholder="Ex.: maria@example.com", type="email", max_length=120)
        with gr.Column(min_width=280):
            in_endereco = gr.Textbox(label="Endereço *", placeholder="Ex.: Rua das Flores, 123 - Centro", max_length=200)
            in_celular = gr.Textbox(
                label="Celular/WhatsApp * (somente números)",
                placeholder="Ex.: 77999998888 (DDD + número)",
                max_length=13,
            )

    gr.Markdown("### 💻 Equipamento")
    with gr.Row():
        with gr.Column(min_width=280):
            in_modelo = gr.Textbox(label="Modelo do Computador *", placeholder="Ex.: Notebook Dell Inspiron 15", max_length=120)
        with gr.Column(min_width=280):
            in_problema = gr.Textbox(
                label="Problema Apresentado *",
                placeholder="Descreva o defeito relatado pelo cliente…",
                lines=4,
                max_lines=10,
            )

    with gr.Row():
        btn_cadastrar = gr.Button("✅ Cadastrar", variant="primary", min_width=140)
        btn_limpar = gr.Button("🧹 Limpar", variant="secondary", min_width=140)

    out_msg = gr.Markdown()

    campos = [in_nome, in_endereco, in_email, in_celular, in_modelo, in_problema]
    btn_cadastrar.click(cadastrar, inputs=campos, outputs=[out_msg, *campos])
    btn_limpar.click(limpar, inputs=None, outputs=[out_msg, *campos])


if __name__ == "__main__":
    # share=True gera o link público temporário (*.gradio.live) para testar no celular.
    # Para desligar (ex.: rede sem acesso ao túnel), defina GRADIO_SHARE=false no .env.
    compartilhar = os.getenv("GRADIO_SHARE", "true").strip().lower() in ("1", "true", "sim", "yes")
    # GRADIO_SERVER_NAME=0.0.0.0 permite abrir pelo IP do PC na mesma rede Wi-Fi
    # (alternativa quando a rede bloqueia o link público). Lido aqui, após o
    # load_dotenv(), porque o Gradio só consulta essa variável ao ser importado.
    servidor = os.getenv("GRADIO_SERVER_NAME", "").strip() or "127.0.0.1"
    demo.launch(share=compartilhar, server_name=servidor, theme=gr.themes.Soft(), css=CSS)
