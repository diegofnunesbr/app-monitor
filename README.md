# App Monitor

Monitora endpoints `/manage/health` (Spring Boot Admin) e envia alertas no Microsoft Teams quando instâncias ficam DOWN ou voltam UP.

As URLs monitoradas definem-se em **`instances.yaml`**: em desenvolvimento o programa lê esse ficheiro diretamente; no Docker, monta o mesmo ficheiro em **`/app/instances.yaml`**. Podes usar uma URL `https://` por linha ou um YAML com `services:` ou `urls:`.

## Estrutura do repositório

```text
app-monitor/
├── app/
│   ├── app_monitor.py
│   ├── config_loader.py
│   └── health_checker.py
├── instances.yaml   # local / volume (não versionado)
├── Dockerfile
├── requirements.txt
└── README.md
```

## Como rodar localmente

```bash
pip install -r requirements.txt
python app/app_monitor.py
```

## Tecnologias

- Python
- asyncio
- aiohttp
- PyYAML
- Docker (opcional)

## Observações

- Compatível com o JSON de health do Spring Boot Admin.
- O arquivo com URLs reais `instances.yaml` (raiz) está no `.gitignore`.
- **Prod vs não-prod:** o hostname é partido por `.` em rótulos. Se algum rótulo for `qa`, `stg` ou `dev` → não-prod. Se não, há uma lista extra que só olha para o primeiro rótulo (instâncias e nomes compostos).

## Variáveis de ambiente

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `TEAMS_WEBHOOK` | — | URL do webhook do Microsoft Teams |
| `TEAMS_WEBHOOK_MAX_RETRIES` | 3 | Tentativas ao Teams (backoff) |
| `TEAMS_WEBHOOK_TIMEOUT_SECONDS` | 10 | Timeout por pedido ao webhook (s) |
| `TEAMS_WEBHOOK_RETRY_BACKOFF_SECONDS` | 1 | Atraso base entre tentativas |
| `MAX_CONCURRENT_CHECKS` | 100 | Máximo de checks em paralelo |
| `DOWN_THRESHOLD` | 2 | Passagens seguidas em DOWN antes de alertar |
| `HEALTH_CHECK_ATTEMPTS` | 3 | Tentativas por URL antes de marcar DOWN |
| `HEALTH_CHECK_ATTEMPT_INTERVAL` | 15 | Segundos entre tentativas na mesma verificação |
| `NON_PROD_ALERT_THRESHOLD` | 5 | Mínimo de instâncias não prod em DOWN/UP para alertar |

## Como rodar com Docker

```bash
docker build -t app-monitor .
docker run -d \
  --restart unless-stopped \
  --name app-monitor \
  -e TEAMS_WEBHOOK="https://webhook.office.com/..." \
  -v "$(pwd)/instances.yaml:/app/instances.yaml" \
  app-monitor
```

## Consultar os logs

```bash
docker logs -f app-monitor
```

## Parar e remover o container

```bash
docker rm -f app-monitor
```
