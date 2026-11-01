-- =====================================================================
-- Dados FICTÍCIOS para teste (LGPD): nomes inventados, e-mails no
-- domínio reservado example.com e celulares sem dono real.
-- Opcional — rode depois do schema.sql para popular o painel.
-- =====================================================================
insert into public.clientes (nome, endereco, email, celular_whatsapp) values
  ('Ana Ficticia Souza',      'Rua das Acácias, 100 - Centro',      'ana.ficticia@example.com',     '77900000001'),
  ('Bruno Teste Lima',        'Av. dos Ipês, 250 - Candeias',       'bruno.teste@example.com',      '77900000002'),
  ('Carla Exemplo Rocha',     'Rua Projetada A, 12 - Recreio',      'carla.exemplo@example.com',    '77900000003'),
  ('Diego Modelo Alves',      'Travessa Beta, 8 - Brasil',          'diego.modelo@example.com',     '77900000004'),
  ('Elisa Simulada Prado',    'Rua Gama, 45 - Patagônia',           'elisa.simulada@example.com',   '77900000005')
on conflict (email) do nothing;

insert into public.ordens_servico (cliente_id, modelo_computador, problema_relatado, status)
select c.id, v.modelo, v.problema, v.status
from (values
  ('ana.ficticia@example.com',   'Notebook Dell Inspiron 15',  'Não liga após queda de energia.',          'Aberto'),
  ('ana.ficticia@example.com',   'Impressora HP DeskJet',      'Atolando papel constantemente.',           'Entregue'),
  ('bruno.teste@example.com',    'Desktop montado i5',         'Reinicia sozinho durante jogos.',          'Em análise'),
  ('carla.exemplo@example.com',  'Notebook Lenovo IdeaPad 3',  'Tela com listras verticais.',              'Aguardando peça'),
  ('carla.exemplo@example.com',  'Mouse sem fio Logitech',     'Clique esquerdo falhando.',                'Concluído'),
  ('diego.modelo@example.com',   'MacBook Air M1',             'Bateria descarrega muito rápido.',         'Em análise'),
  ('elisa.simulada@example.com', 'Notebook Acer Aspire 5',     'Teclado com teclas sem resposta.',         'Aberto'),
  ('elisa.simulada@example.com', 'All-in-one Positivo',        'Lentidão extrema e possíveis vírus.',      'Concluído')
) as v(email, modelo, problema, status)
join public.clientes c on c.email = v.email;
