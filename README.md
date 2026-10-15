# Vehicle Sales Service

Microsserviço de vendas do Tech Challenge SOAT - Fase 4. Este repositório concentra as
listagens e a compra de veículos e usa um banco próprio, separado do serviço principal.

## Responsabilidades

- receber por HTTP a projeção versionada dos veículos cadastrados no Core;
- listar veículos disponíveis e vendidos por preço crescente;
- reservar um veículo e gerar o código de pagamento;
- validar e armazenar o CPF do comprador sem devolvê-lo integralmente na API;
- processar confirmações e cancelamentos de pagamento de forma idempotente;
- sincronizar com o Core os estados `RESERVED`, `SOLD` e `AVAILABLE`.

Não existe acesso ao banco do Core. Toda comunicação entre os serviços usa HTTP e o header
`X-Service-Token`.

## Tecnologias

Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 assíncrono, `aiomysql`, MySQL 8.4,
Alembic, HTTPX, Pytest, Ruff e Docker. JWT e Argon2 ficam no Core, que é o responsável pela
identidade e pelas operações administrativas.

## Endpoints

| Método | Rota | Descrição |
| --- | --- | --- |
| `GET` | `/api/v1/vehicles/available` | Disponíveis por preço crescente. |
| `GET` | `/api/v1/vehicles/sold` | Vendidos pelo preço registrado na compra. |
| `POST` | `/api/v1/purchases` | Reserva o veículo e cria o código de pagamento. |
| `GET` | `/api/v1/purchases/{payment_code}` | Consulta a compra com CPF mascarado. |
| `PUT` | `/internal/v1/vehicles/{id}` | Upsert versionado da projeção; requer token interno. |
| `POST` | `/internal/v1/payments` | Confirma/cancela pagamento; requer token interno. |
| `POST` | `/internal/v1/purchases/{id}/sync` | Repete a sincronização com o Core. |
| `GET` | `/health/live` | Liveness. |
| `GET` | `/health/ready` | Readiness com verificação do banco. |

O header opcional `Idempotency-Key` torna a criação da compra repetível com segurança. O CPF
é normalizado e validado pelos dígitos verificadores. A reserva usa `SELECT ... FOR UPDATE`
para impedir duas compras simultâneas do mesmo veículo.

## Execução local

Requisitos: Python 3.12 e MySQL 8.4.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload --port 8001
```

No PowerShell, ative com `.venv\Scripts\Activate.ps1` e copie o ambiente com
`Copy-Item .env.example .env`. A documentação fica em `http://localhost:8001/docs`.

Para executar a plataforma completa, use o `docker-compose.yml` da raiz do pacote entregue.
Ele inicia duas APIs e duas instâncias MySQL 8.4 totalmente separadas.

## Testes e qualidade

Os testes usam SQLite assíncrono em memória e um cliente falso para o Core. Não é necessário
subir Docker ou MySQL.

```bash
ruff check .
ruff format --check .
pytest
```

O Pytest falha automaticamente se a cobertura ficar abaixo de 80%. A opção
`concurrency = ["greenlet"]` mantém a medição correta através das chamadas assíncronas do
SQLAlchemy.

## Docker

```bash
docker build -t vehicle-sales-service:local .
docker run --rm --env-file .env -p 8001:8000 vehicle-sales-service:local
```

A imagem usa Python 3.12 e usuário não-root. O entrypoint executa as migrations antes do
Uvicorn.

## CI/CD

O workflow em `.github/workflows/ci-cd.yml` valida Pull Requests com Ruff, testes e cobertura.
Após merge na `main`, ele publica uma imagem com a tag do commit no GHCR, executa a migration
como Job Kubernetes e atualiza o container `api` do Deployment `vehicle-sales-service`.

Para habilitar o deploy, configure `ENABLE_K8S_DEPLOY=true`, o secret `KUBE_CONFIG_B64` com
o kubeconfig em Base64 e, opcionalmente, `KUBE_NAMESPACE` (padrão `vehicle-sales`). Sem a
variável, testes e publicação no GHCR continuam funcionando e o deploy é apenas ignorado.
Proteja a branch `main` para que a implantação seja originada por merge de Pull Request.
