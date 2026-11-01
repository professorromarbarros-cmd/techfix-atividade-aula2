-- =====================================================================
-- Testes das restrições do schema.sql (executar no SQL Editor DEPOIS do
-- schema.sql). Tudo roda dentro de uma transação desfeita no final
-- (ROLLBACK): nenhum dado permanece no banco.
-- Cada teste imprime "OK" (comportamento esperado) ou "FALHOU".
-- No Supabase, as mensagens aparecem na aba de resultados/notices.
-- =====================================================================
begin;

do $$
declare
    v_cli  bigint;
    v_os   bigint;
    v_n    int;
    v_upd  timestamptz;
    v_abr  timestamptz;
begin
    -- ---------- Caso válido ----------
    insert into public.clientes (nome, endereco, email, celular_whatsapp)
    values ('Cliente Teste', 'Rua Fictícia, 1', 'teste@example.com', '77999990000')
    returning id into v_cli;

    insert into public.ordens_servico (cliente_id, modelo_computador, problema_relatado)
    values (v_cli, 'Notebook Teste X1', 'Não liga')
    returning id, data_abertura into v_os, v_abr;

    select count(*) into v_n from public.ordens_servico where id = v_os and status = 'Aberto';
    raise notice '% T01 status padrão = Aberto', case when v_n = 1 then 'OK     ' else 'FALHOU ' end;

    -- ---------- UNIQUE no e-mail ----------
    begin
        insert into public.clientes (nome, endereco, email, celular_whatsapp)
        values ('Outro', 'Rua B', 'teste@example.com', '77999990001');
        raise notice 'FALHOU  T02 e-mail duplicado foi aceito';
    exception when unique_violation then
        raise notice 'OK      T02 e-mail duplicado rejeitado (UNIQUE)';
    end;

    -- ---------- E-mail com maiúsculas (normalização) ----------
    begin
        insert into public.clientes (nome, endereco, email, celular_whatsapp)
        values ('Outro', 'Rua B', 'Teste@Example.com', '77999990001');
        raise notice 'FALHOU  T03 e-mail com maiúsculas foi aceito';
    exception when check_violation then
        raise notice 'OK      T03 e-mail com maiúsculas rejeitado (CHECK normalizado)';
    end;

    -- ---------- Formato de e-mail ----------
    begin
        insert into public.clientes (nome, endereco, email, celular_whatsapp)
        values ('Outro', 'Rua B', 'sem-arroba.com', '77999990001');
        raise notice 'FALHOU  T04 e-mail inválido foi aceito';
    exception when check_violation then
        raise notice 'OK      T04 e-mail sem @ rejeitado (CHECK formato)';
    end;

    -- ---------- Celular: letras / máscara ----------
    begin
        insert into public.clientes (nome, endereco, email, celular_whatsapp)
        values ('Outro', 'Rua B', 'b@example.com', '(77) 99999-0001');
        raise notice 'FALHOU  T05 celular com máscara foi aceito';
    exception when check_violation then
        raise notice 'OK      T05 celular com máscara rejeitado (somente dígitos)';
    end;

    -- ---------- Celular: tamanho ----------
    begin
        insert into public.clientes (nome, endereco, email, celular_whatsapp)
        values ('Outro', 'Rua B', 'c@example.com', '999990');
        raise notice 'FALHOU  T06 celular com 6 dígitos foi aceito';
    exception when check_violation then
        raise notice 'OK      T06 celular com menos de 10 dígitos rejeitado';
    end;

    -- ---------- NOT NULL ----------
    begin
        insert into public.clientes (nome, endereco, email, celular_whatsapp)
        values (null, 'Rua B', 'd@example.com', '77999990001');
        raise notice 'FALHOU  T07 nome nulo foi aceito';
    exception when not_null_violation then
        raise notice 'OK      T07 nome nulo rejeitado (NOT NULL)';
    end;

    -- ---------- Nome em branco ----------
    begin
        insert into public.clientes (nome, endereco, email, celular_whatsapp)
        values ('   ', 'Rua B', 'e@example.com', '77999990001');
        raise notice 'FALHOU  T08 nome em branco foi aceito';
    exception when check_violation then
        raise notice 'OK      T08 nome só com espaços rejeitado';
    end;

    -- ---------- CHECK de status ----------
    begin
        update public.ordens_servico set status = 'Cancelado' where id = v_os;
        raise notice 'FALHOU  T09 status inválido foi aceito';
    exception when check_violation then
        raise notice 'OK      T09 status fora da lista rejeitado (CHECK status)';
    end;

    -- ---------- FK inexistente ----------
    begin
        insert into public.ordens_servico (cliente_id, modelo_computador, problema_relatado)
        values (-1, 'PC', 'Teste');
        raise notice 'FALHOU  T10 OS com cliente inexistente foi aceita';
    exception when foreign_key_violation then
        raise notice 'OK      T10 OS com cliente inexistente rejeitada (FK)';
    end;

    -- ---------- Trigger data_atualizacao ----------
    -- Tenta gravar uma data antiga; o trigger deve sobrescrevê-la com now()
    update public.ordens_servico
       set status = 'Em análise', data_atualizacao = '2000-01-01'
     where id = v_os
    returning data_atualizacao into v_upd;
    raise notice '% T11 trigger atualizou data_atualizacao (valor gravado: %)',
        case when v_upd > '2000-01-01' then 'OK     ' else 'FALHOU ' end, v_upd;

    -- ---------- ON DELETE CASCADE ----------
    delete from public.clientes where id = v_cli;
    select count(*) into v_n from public.ordens_servico where id = v_os;
    raise notice '% T12 excluir cliente remove suas OS (ON DELETE CASCADE)',
        case when v_n = 0 then 'OK     ' else 'FALHOU ' end;
end;
$$;

rollback;
