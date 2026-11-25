# Microservicios de carga

Entorno local de desarrollo para tres servicios de dominio FastAPI y un coordinador de SAGA. Las integraciones de cobro y cargador son simuladas; este entorno no realiza cobros ni activa hardware real.

## Iniciar

Desde este directorio:

```sh
docker compose up --build
```

| Servicio | URL local | Persistencia |
|---|---|---|
| station-reservation-service | http://localhost:8001 | DynamoDB Local en memoria (`connector-locks-local`) |
| billing-wallet-service | http://localhost:8002 | SQLite (`wallet-data`) |
| energy-dispatch-service | http://localhost:8003 | Memoria del proceso (simulación) |
| saga-orchestrator-service | http://localhost:8004 | DynamoDB Local en memoria (`charging-sagas-local`) |
| GraphQL API Gateway | http://localhost:8005/graphql | Agrega reservas, telemetría y SAGA |

Cada servicio publica `/docs` y `/health`. El servicio de reservas devuelve el estado `RESERVED` o `AVAILABLE`; los bloqueos expiran según `expires_at` y no dependen de la eliminación eventual de TTL. La creación del bloqueo es condicional y evita que dos solicitudes reserven simultáneamente el mismo conector. DynamoDB Local se ejecuta en memoria para evitar problemas de permisos de volúmenes; sus bloqueos y SAGA se pierden al reiniciar ese contenedor.

Todos los servicios emiten logs JSON a stdout con `timestamp`, `level`, `message`, `environment`, `service` y `correlation_id`. Para ejecutar una auditoría Prefect local después de iniciar el stack, ejecuta `docker compose --profile observability run --rm saga-auditor-service`. En EKS la auditoría se ejecuta cada cinco minutos y reporta en CloudWatch las SAGA pendientes durante al menos diez minutos; no cambia estados ni dispara compensaciones.

## Flujo de prueba

1. Crear la billetera de la flota: `POST /wallets/{fleet_id}` con `{"currency":"USD"}`.
2. Cargar fondos de prueba: `POST /wallets/{fleet_id}/funds` con `{"amount_cents":5000}`.
3. Consultar disponibilidad: `GET /connectors/{connector_id}/availability`.
4. Reservar: `POST /connectors/{connector_id}/reservations` con `{"fleet_id":"fleet-1","duration_seconds":300}`.
5. Cobrar el estimado: `POST /charges` con `{"fleet_id":"fleet-1","reservation_id":"<id>","estimated_amount_cents":1200,"idempotency_key":"charge-<id>"}`.
6. Iniciar carga simulada: `POST /dispatches` con `{"reservation_id":"<id>","connector_id":"connector-1","duration_seconds":60}`.
7. Leer telemetría actual en `GET /dispatches/{dispatch_id}/telemetry/latest` o suscribirse a `GET /dispatches/{dispatch_id}/telemetry` (SSE).
8. Reembolsar el cargo: `POST /charges/{charge_id}/refunds` con `{"idempotency_key":"refund-<id>"}`. El reembolso es total.

Los importes se expresan como unidades menores enteras (por ejemplo, centavos); claves de idempotencia evitan duplicar cargos y reembolsos. La billetera se crea con saldo cero; el endpoint de fondos de prueba está deshabilitado por defecto y Compose lo habilita solo para el entorno local. En despliegue debe reemplazarse por la integración de pagos autorizada.

## SAGA «Reservar y activar carga»

El coordinador expone `POST /sagas/reserve-and-activate`. Envía `correlation_id` (UUID) y los datos de la flota, conector e importe:

```json
{
  "correlation_id": "f68c9e74-7f1e-49c5-bec3-f3c799948ea4",
  "fleet_id": "fleet-1",
  "connector_id": "connector-1",
  "estimated_amount_cents": 1200,
  "reservation_duration_seconds": 300,
  "charging_duration_seconds": 60
}
```

La secuencia es **reservar → cobrar → activar**. Si la activación falla, compensa en orden **reembolsar → liberar**. Un mismo `correlation_id` se propaga como cabecera `X-Correlation-ID` y clave idempotente en los participantes. Repetir la solicitud con el mismo ID reanuda pasos incompletos o devuelve el resultado previo; reutilizarlo con otro contenido responde `409`. Consulta el estado en `GET /sagas/{correlation_id}`. Estados `RETRYABLE` y `COMPENSATION_PENDING` responden `202`; vuelve a enviar la misma solicitud para reanudar la operación o su compensación. El estado se guarda en DynamoDB usando `correlation_id` como clave idempotente; las escrituras condicionales evitan que dos réplicas sobrescriban un avance concurrente. Los participantes de reservas y cobro también deduplican sus operaciones.

Para verificar la compensación automática, inicia el entorno con `SIMULATE_CHARGER_HARDWARE_FAULT=true docker compose up --build` (PowerShell: `$env:SIMULATE_CHARGER_HARDWARE_FAULT='true'; docker compose up --build`). La activación simula un error y el coordinador reembolsa el cargo antes de liberar el conector. En modo normal, establece la variable en `false` o elimínala.

## GraphQL API Gateway

El gateway sirve GraphQL en `/graphql` (HTTP y WebSocket para suscripciones) y `/health`. Es el punto de entrada para consultar conectores, sesiones y SAGA, y para iniciar la carga completa. La mutación inicia la SAGA; no ejecuta cobros ni reservas directamente.

Consultar el estado del conector y telemetría:

```graphql
query EstadoYCarga($connectorId: String!, $dispatchId: ID!) {
  stationStatus(connectorId: $connectorId)
  chargingSession(dispatchId: $dispatchId)
  latestTelemetry(dispatchId: $dispatchId)
}
```

Iniciar reserva, cobro y sesión de carga con una sola mutación:

```graphql
mutation IniciarCarga($input: StartChargingSessionInput!) {
  startChargingSession(input: $input)
}
```

Ejemplo de variables (el `correlation_id` debe ser un UUID y nuevo por operación):

```json
{
  "input": {
    "correlationId": "f68c9e74-7f1e-49c5-bec3-f3c799948ea4",
    "fleetId": "fleet-1",
    "connectorId": "connector-1",
    "estimatedAmountCents": 1200,
    "reservationDurationSeconds": 300,
    "chargingDurationSeconds": 60
  }
}
```

La respuesta incluye los resultados de reserva, cobro, despacho y el estado de la SAGA. Para reintentar una operación con estado `RETRYABLE` o `COMPENSATION_PENDING`, repite la mutación con el mismo `correlationId` y el mismo contenido. Los errores upstream se devuelven en `errors[].extensions` con `code`, servicio y, cuando aplica, `statusCode`.

La telemetría en vivo está disponible como suscripción GraphQL sobre WebSocket:

```graphql
subscription Telemetria($dispatchId: ID!) {
  telemetry(dispatchId: $dispatchId)
}
```

Las consultas y la suscripción agregan datos del servicio de reservas y despacho; `sagaStatus(correlationId: UUID!)` consulta el estado de la SAGA. El gateway no expone mutations que omitan el coordinador.

## Variables de entorno

- Reservas: `TABLE_NAME`, `DYNAMODB_ENDPOINT_URL`, `AWS_DEFAULT_REGION` y credenciales AWS estándar. Sin endpoint local, boto3 usa la configuración AWS del entorno.
- Billetera: `DATABASE_PATH`.
- Despacho: `TELEMETRY_INTERVAL_SECONDS`, `SIMULATE_CHARGER_HARDWARE_FAULT`.
- Coordinador: `DATABASE_PATH`, `STATION_RESERVATION_URL`, `BILLING_WALLET_URL`, `ENERGY_DISPATCH_URL`.
- GraphQL API Gateway: `STATION_RESERVATION_URL`, `ENERGY_DISPATCH_URL`, `SAGA_ORCHESTRATOR_URL`.

El despacho conserva sus registros solo en memoria: reiniciar el contenedor borra dispatches y telemetría. En producción, sustituir el controlador simulado, incorporar almacenamiento de telemetría y autenticar/autorizar las llamadas entre servicios. El coordinador persiste progreso en DynamoDB y reintenta de manera segura solo porque los participantes deduplican por correlación; un adaptador de hardware real también debe aceptar una clave idempotente o permitir consultar el estado de la orden.

## CI/CD y despliegue EKS

Los workflows están en `.github/workflows/` en la raíz del repositorio. Requieren ramas de destino y despliegue llamadas exactamente `dev`, `test` y `prod`.

- **Pull request:** linter Ruff, pruebas pytest, compilación Docker de los servicios, `terraform fmt`/`validate` y `terraform plan` en el workspace igual a la rama destino.
- **Push después del merge:** selecciona el workspace por la rama, ejecuta `terraform apply -auto-approve`, publica las imágenes en ECR y despliega el chart Helm.
- **Canary:** Kubernetes inicia pods estables y canary con sondas de salud; el ALB dirige 90%/10% del tráfico GraphQL. El workflow envía solicitudes de prueba, mide `HTTPCode_Target_5XX_Count / RequestCount` del target group canary en CloudWatch y solo promueve si la tasa es ≤5% con al menos 20 solicitudes observadas en cinco minutos. Si la comprobación falla, restaura el peso estable al 100%.

### Configuración requerida antes de habilitar los workflows

1. Crea en GitHub los Environments `dev`, `test` y `prod`. Para `prod`, activa aprobación manual y restringe las ramas desplegables. Configura en cada Environment:
   - Secret `AWS_ROLE_ARN`: rol de GitHub Actions con trust OIDC (audience `sts.amazonaws.com`) para este repositorio y Environment.
   - Variables `AWS_REGION` y `TF_STATE_BUCKET`. El bucket S3 remoto debe existir previamente, estar cifrado y con versionado; el rol necesita leer/escribir el estado y su lockfile S3.
   - Variable `EKS_API_ALLOWED_CIDRS`: lista JSON de CIDRs confiables para el endpoint EKS, por ejemplo `["203.0.113.12/32"]`. No uses `0.0.0.0/0` ni `::/0`. El runner de GitHub debe salir por una IP incluida; usa un runner self-hosted en la VPC o egress estático para no depender de rangos públicos que cambian.
   - Variable `INGRESS_ALLOWED_CIDRS`: lista JSON de CIDRs de clientes autorizados, por ejemplo `["198.51.100.0/24"]`. No uses `0.0.0.0/0` ni `::/0`; incluye la IP de salida del runner si el workflow debe ejecutar sus probes contra el ALB. Sin dominio propio, el ALB usa su hostname DNS asignado por AWS y sirve HTTP; el workflow muestra la URL al finalizar el despliegue. Un certificado TLS público válido requiere un dominio que controles y no puede emitirse para el hostname AWS del ALB.
2. El rol necesita permisos para planificar/aplicar la infraestructura (VPC/EKS/IAM/DynamoDB/ECR), publicar en ECR, autenticarse en EKS y consultar métricas de CloudWatch y target groups. Limita la trust policy OIDC a este repositorio y a los Environments `dev`, `test` y `prod`; no guardes claves AWS de larga duración en GitHub.
3. El workflow exige `EKS_API_ALLOWED_CIDRS` y Terraform rechaza rangos IPv4/IPv6 abiertos. El endpoint EKS sigue requiriendo autenticación IAM. Asegúrate de incluir la IP de salida del runner autorizado o usa un runner dentro de la VPC con acceso privado. Ajusta versión de Kubernetes, tamaño de nodos y CIDR según la cuenta y región.
4. El primer `terraform apply` puede crear VPC/NAT, EKS, roles IAM, DynamoDB y repositorios ECR; genera costes AWS. El estado Terraform S3 y el proveedor GitHub OIDC deben prepararse antes. No ejecuté `apply` contra una cuenta real.

### Observabilidad y auditoría SAGA

- Terraform crea una tabla DynamoDB por ambiente para el estado de SAGA, con el índice `status-updated-at-index` usado por la auditoría.
- El addon `amazon-cloudwatch-observability` envía logs de contenedores a `/aws/containerinsights/<cluster>/application`, con retención de 30 días. Los contenedores escriben JSON a stdout y cada servicio añade `correlation_id`, `environment` y `service`.
- El CronJob `charging-saga-auditor` ejecuta un Prefect Flow cada cinco minutos. Sus Tasks consultan en modo lectura las SAGA `STARTED`, `RETRYABLE`, `COMPENSATING` y `COMPENSATION_PENDING` cuya última actualización excede 10 minutos. Publica cada hallazgo como log estructurado con el `correlation_id`, estado, paso, antigüedad y tipo (`ORPHANED_PENDING_SAGA` o `PENDING_COMPENSATION`).
- La identidad IRSA del auditor solo puede consultar el índice de DynamoDB. La auditoría informa; no reintenta operaciones, reembolsa ni libera conectores. Los logs se pueden consultar en CloudWatch Logs Insights con `fields @timestamp, environment, service, correlation_id, saga_status, step, finding_kind, age_seconds | filter finding_kind != ""`.
- En local, usa `docker compose --profile observability run --rm saga-auditor-service`. DynamoDB Local es efímero; el estado no sobrevive al reinicio.

El plan con OIDC se omite para PRs provenientes de forks, porque GitHub no entrega secretos ni tokens OIDC a ese contexto. Los checks sin credenciales (lint, pruebas, build, Terraform validate) sí se ejecutan. El job de plan requiere que el Environment cuyo nombre coincide con la rama destino permita el acceso del rol configurado.

### Alcance y limitaciones del canary actual

El ALB divide el tráfico externo de GraphQL, y el gateway canary enruta reservas y despacho al stack canary. Si no se configura dominio y certificado, AWS entrega un hostname DNS para el ALB y el Ingress sirve HTTP limitado a los CIDRs configurados; el workflow imprime la URL. HTTP no cifra el tráfico, por lo que este modo es solo para pruebas y no debe transportar credenciales ni datos sensibles. Para habilitar HTTPS, configura un dominio propio y un certificado ACM válido; el chart admite `ingress.hostname` y `ingress.certificateArn`. La billetera usa SQLite local: su copia canary se despliega y pasa health checks, pero **no recibe tráfico de negocio**; la SAGA canary llama a la billetera estable para no operar sobre un saldo vacío/aislado. La base SQLite de billetera y el estado en memoria del cargador tampoco son almacenamiento durable para EKS. Antes de usar este scaffold con datos reales, migra billetera a almacenamiento compartido y durable (por ejemplo, RDS), añade autenticación/autorización y define alertas/umbrales de negocio. El estado SAGA ahora sí persiste en DynamoDB y se audita periódicamente. El endpoint público de EKS también queda limitado por CIDRs configurados. El workflow valida métricas de error HTTP del target group GraphQL; no sustituye pruebas de carga ni observabilidad funcional.
