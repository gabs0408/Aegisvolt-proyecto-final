# AegisVolt frontend

Con los microservicios iniciados en los puertos 8001–8005: `npm ci`, `npm run build`, `npm run dev`. Abrir http://localhost:5173. Node 24 recomendado.

Docker Desktop: `docker build -t aegisvolt-frontend .` y `docker run --rm -p 5173:80 aegisvolt-frontend`. Detener Vite antes. Nginx usa host.docker.internal para acceder a los puertos publicados del backend. No se modifica el compose existente.

Billetera: REST real, recargas únicamente de prueba. Historial: IDs y últimas respuestas en localStorage, no listado global. Dashboard: dos conectores configurados y saldo fleet-1. Observabilidad: health checks HTTP y enlace a Prefect local si está iniciado. Telemetría: muestras recogidas mientras el panel está montado; no historial remoto completo. Una sesión anterior se puede consultar en Transacciones usando su UUID sin cobrar de nuevo. No usar este proxy local como configuración de producción sin autenticación.
