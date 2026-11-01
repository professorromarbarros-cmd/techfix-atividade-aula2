-- =====================================================================
-- TechFix Informática — Sistema de Ordens de Serviço
-- Script DDL para Supabase (PostgreSQL 15+)
-- Executar inteiro no SQL Editor do Supabase.
--
-- O script é idempotente e NÃO destrutivo: pode ser executado mais de
-- uma vez sem apagar dados (usa IF NOT EXISTS / CREATE OR REPLACE /
-- DROP ... IF EXISTS apenas em políticas, triggers e views).
-- =====================================================================


-- ---------------------------------------------------------------------
-- 0. RESET (OPCIONAL) — descomente apenas se quiser recriar tudo do zero.
--    ATENÇÃO: apaga as tabelas e TODOS os dados.
-- ---------------------------------------------------------------------
-- drop view  if exists public.vw_ordens_servico;
-- drop table if exists public.ordens_servico cascade;
-- drop table if exists public.clientes cascade;
-- drop function if exists public.fn_set_data_atualizacao();


-- ---------------------------------------------------------------------
-- 1. Tabela CLIENTES
--    Um cliente pode trazer vários equipamentos ao longo do tempo
--    (relação 1:N com ordens_servico).
-- ---------------------------------------------------------------------
create table if not exists public.clientes (
    -- Chave primária substituta, gerada pelo banco
    id               bigint generated always as identity primary key,

    -- Campos essenciais: NOT NULL + proibição de texto em branco
    nome             text        not null,
    endereco         text        not null,
    email            text        not null,
    celular_whatsapp text        not null,

    -- Data de cadastro com padrão "agora"
    data_cadastro    timestamptz not null default now(),

    -- E-mail único: o mesmo e-mail identifica o mesmo cliente
    constraint uq_clientes_email unique (email),

    -- Nome e endereço não podem ser só espaços
    constraint chk_clientes_nome_preenchido     check (btrim(nome) <> ''),
    constraint chk_clientes_endereco_preenchido check (btrim(endereco) <> ''),

    -- Formato simples de e-mail: algo@dominio.tld (sem espaços)
    constraint chk_clientes_email_formato
        check (email ~* '^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$'),

    -- E-mail sempre minúsculo e sem espaços nas pontas: garante que
    -- "Ana@X.com" e "ana@x.com" não virem dois clientes (o UNIQUE acima
    -- passa a valer, na prática, sem diferenciar maiúsculas)
    constraint chk_clientes_email_normalizado
        check (email = lower(btrim(email))),

    -- Celular/WhatsApp: somente dígitos, de 10 a 13 caracteres
    -- (ex.: 7733334444, 77999998888, 5577999998888)
    constraint chk_clientes_celular_formato
        check (celular_whatsapp ~ '^[0-9]{10,13}$')
);

comment on table  public.clientes                  is 'Clientes da TechFix Informática (somente dados fictícios em testes — LGPD).';
comment on column public.clientes.email            is 'E-mail único, minúsculo; usado para reaproveitar o cliente no cadastro.';
comment on column public.clientes.celular_whatsapp is 'Somente dígitos, 10 a 13 caracteres (DDD + número, opcionalmente com DDI 55).';


-- ---------------------------------------------------------------------
-- 2. Tabela ORDENS_SERVICO
--    Cada OS pertence a exatamente um cliente (FK obrigatória).
-- ---------------------------------------------------------------------
create table if not exists public.ordens_servico (
    -- Chave primária; o "id" é o número da OS informado ao cliente
    id                 bigint generated always as identity primary key,

    -- Chave estrangeira para clientes.
    -- Comportamento na exclusão: ON DELETE CASCADE — ao excluir um
    -- cliente, as OS dele também são excluídas (o painel Streamlit avisa
    -- quantas OS serão removidas e pede confirmação antes).
    cliente_id         bigint      not null
        constraint fk_os_cliente
        references public.clientes (id)
        on delete cascade,

    modelo_computador  text        not null,
    problema_relatado  text        not null,

    -- Status: começa em 'Aberto' e só aceita os 5 valores do fluxo
    status             text        not null default 'Aberto',

    data_abertura      timestamptz not null default now(),
    -- Mantida automaticamente pelo trigger da seção 3
    data_atualizacao   timestamptz not null default now(),

    constraint chk_os_modelo_preenchido   check (btrim(modelo_computador) <> ''),
    constraint chk_os_problema_preenchido check (btrim(problema_relatado) <> ''),

    -- Fluxo: Aberto → Em análise → Aguardando peça → Concluído → Entregue
    constraint chk_os_status check (
        status in ('Aberto', 'Em análise', 'Aguardando peça', 'Concluído', 'Entregue')
    )
);

comment on table  public.ordens_servico        is 'Ordens de serviço (OS) abertas no balcão; id = número da OS.';
comment on column public.ordens_servico.status is 'Aberto | Em análise | Aguardando peça | Concluído | Entregue';

-- Índices: o PostgreSQL NÃO cria índice automático para FK.
-- Índice em cliente_id acelera o JOIN e o ON DELETE CASCADE;
-- índice em status acelera os filtros e indicadores do painel.
create index if not exists idx_os_cliente_id on public.ordens_servico (cliente_id);
create index if not exists idx_os_status     on public.ordens_servico (status);


-- ---------------------------------------------------------------------
-- 3. Trigger: atualiza data_atualizacao em todo UPDATE de uma OS
--    (search_path fixo evita o alerta "function_search_path_mutable"
--    do Security Advisor do Supabase).
-- ---------------------------------------------------------------------
create or replace function public.fn_set_data_atualizacao()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
    new.data_atualizacao := now();
    return new;
end;
$$;

drop trigger if exists trg_os_data_atualizacao on public.ordens_servico;
create trigger trg_os_data_atualizacao
    before update on public.ordens_servico
    for each row
    execute function public.fn_set_data_atualizacao();


-- ---------------------------------------------------------------------
-- 4. Segurança: RLS (Row Level Security) + política aberta
--    Padrão da Aula 2: habilitar RLS logo após criar a tabela e criar
--    uma política aberta, para o Security Advisor não emitir alertas.
--    Observação: a política aberta libera leitura/escrita a quem tiver a
--    chave anon/publishable. Serve para esta atividade acadêmica; em
--    produção, restrinja por usuário autenticado (auth.uid()).
-- ---------------------------------------------------------------------
alter table public.clientes       enable row level security;
alter table public.ordens_servico enable row level security;

drop policy if exists "Acesso total" on public.clientes;
create policy "Acesso total" on public.clientes
    for all
    to anon, authenticated
    using (true)
    with check (true);

drop policy if exists "Acesso total" on public.ordens_servico;
create policy "Acesso total" on public.ordens_servico
    for all
    to anon, authenticated
    using (true)
    with check (true);

-- Privilégios explícitos para os papéis da API REST do Supabase
-- (o Supabase já os concede por padrão no schema public; repetir aqui
-- garante o funcionamento mesmo se esse padrão estiver desativado).
grant select, insert, update, delete on public.clientes       to anon, authenticated;
grant select, insert, update, delete on public.ordens_servico to anon, authenticated;


-- ---------------------------------------------------------------------
-- 5. View de consulta: OS + dados do cliente (usada pelo painel)
--    security_invoker = true → a view respeita o RLS de quem consulta
--    (equivale a NÃO usar SECURITY DEFINER, como pede a Aula 2).
-- ---------------------------------------------------------------------
drop view if exists public.vw_ordens_servico;
create view public.vw_ordens_servico
with (security_invoker = true) as
select
    os.id                as os_id,
    os.status,
    os.modelo_computador,
    os.problema_relatado,
    os.data_abertura,
    os.data_atualizacao,
    c.id                 as cliente_id,
    c.nome               as cliente_nome,
    c.email              as cliente_email,
    c.celular_whatsapp   as cliente_celular,
    c.endereco           as cliente_endereco
from public.ordens_servico os
join public.clientes       c on c.id = os.cliente_id;

grant select on public.vw_ordens_servico to anon, authenticated;


-- ---------------------------------------------------------------------
-- 6. Conferência rápida (opcional): rode depois de executar o script
-- ---------------------------------------------------------------------
-- select conname, pg_get_constraintdef(oid)
--   from pg_constraint
--  where conrelid in ('public.clientes'::regclass, 'public.ordens_servico'::regclass)
--  order by conrelid::regclass::text, conname;
