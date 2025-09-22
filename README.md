# Sistema de Ordens de Serviço Telecom

Aplicação FastAPI para gestão de ordens de serviço de instalação telecom com controle de equipes, técnicos e períodos.

## Requisitos

- Python 3.11+
- pip

## Instalação

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Uso

```bash
uvicorn app.main:app --reload
```

A aplicação cria automaticamente:

- Usuário admin padrão `admin`/`admin` (altere a senha em produção).
- Equipes "Equipe 1" até "Equipe 4".

## Endpoints principais

Autenticação via OAuth2 Password (Bearer Token). Obtenha token em `/auth/token` informando usuário e senha.

### Usuários

- `POST /users` (admin): cria usuários com papéis `admin`, `support` ou `technician`.
- `GET /users` (admin/suporte): lista usuários cadastrados.

### Equipes

- `GET /teams` (admin/suporte): lista equipes.
- `POST /teams` (admin): cria novas equipes.

### Períodos

- `POST /periods` (admin/suporte): cadastra período personalizado.
- `GET /periods` (admin/suporte): lista períodos existentes.

### Ordens de serviço

- `POST /orders` (admin/suporte): cria ordem de serviço individual.
- `POST /orders/import` (admin/suporte): importa várias ordens via CSV com cabeçalhos `nome,endereco,id_instalacao,plano,data_agendamento` (data no formato `YYYY-MM-DD`).
- `GET /orders` (todos): lista ordens filtrando por período, intervalo de datas e equipe. Técnicos visualizam apenas as suas ordens.
- `GET /orders/{id}` (todos): detalhes da ordem (tecnicos apenas as próprias).
- `PATCH /orders/{id}` (todos): atualização de status, equipe, técnico e data. Técnicos só podem marcar como `in_progress` ou `completed`.
- `POST /orders/{id}/observations` (todos): adiciona observações à ordem.
- `POST /orders/{id}/photos` (todos): upload de fotos da instalação (salvas em `app/storage/order_{id}/`).
- `DELETE /orders/{id}` (admin/suporte): remove ordem.

## Testes rápidos

Com o servidor em execução, utilize o Swagger UI disponível em `http://localhost:8000/docs` para explorar e testar todos os recursos.
