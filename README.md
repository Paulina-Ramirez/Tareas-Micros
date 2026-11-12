# Sistema de Gestión de Tareas Colaborativo (Microservicios)

Bienvenido al repositorio oficial del **Proyecto 4: Sistema de Gestión de Tareas**. Este sistema está diseñado bajo una **arquitectura de microservicios**, utilizando tecnologías modernas para garantizar escalabilidad, seguridad y comunicación en tiempo real.

## Arquitectura del Proyecto

El sistema está compuesto por 4 microservicios independientes, orquestados mediante **Docker Compose**, y utiliza **Redis** como caché y bus de eventos (Pub/Sub).

*   **API Gateway:** Punto único de entrada y validación de JWT *(En desarrollo)*.
*   **auth-service:** Registro, login y emisión de tokens JWT.
*   **task-service:** CRUD de proyectos y tareas (Patrón Cache-Aside con Redis).
*   **notification-service:** Envío de notificaciones en tiempo real (WebSockets + Redis Pub/Sub).
*   **presence-service:** Gestión del estado de usuarios en línea.

## Stack Tecnológico

*   **Backend:** Python 3.11 + FastAPI
*   **Base de Datos:** PostgreSQL 15
*   **Caché y Mensajería:** Redis 7
*   **Contenerización:** Docker & Docker Compose
*   **Seguridad:** JWT (JSON Web Tokens)

---

## Guía de Instalación Rápida

Sigue estos pasos para levantar el entorno completo en tu computadora.

### Requisitos Previos
1. Tener instalado **Git**.
2. Tener instalado y abierto **Docker Desktop** (debe decir "Engine running").

### Pasos

**1. Clonar el repositorio:**
```bash
git clone https://github.com/Paulina-Ramirez/Tareas-Micros.git
cd Tareas-Micros
```

**2. Levantar la infraestructura:**
```bash
docker-compose up --build
```
**3.Verificar que todo esté funcionando 
Abre tu navegador y visita los siguientes puertos. Deberías ver un mensaje {"status": "ok"} en cada uno:

http://localhost:8001 - Auth Service

http://localhost:8002 - Task Service

http://localhost:8003 - Notification Service

http://localhost:8004 - Presence Service

**4.Detener el entorno
Presiona Ctrl + C en la terminal o ejecuta: 
```bash
docker-compose down
```
