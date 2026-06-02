# AI Dev Factory

**Dual-Gate Swarm Orchestrator for reliable AI software generation with human approval at the two highest-risk decision points.**

![Hackathon](https://img.shields.io/badge/Hackathon-Ready-success)
![Workflow](https://img.shields.io/badge/Workflow-Dual--Gate%20Human--in--the--Loop-blue)
![Frontend](https://img.shields.io/badge/Frontend-React%20%2B%20Vite%20%2B%20Tailwind-0ea5e9)
![Backend](https://img.shields.io/badge/Backend-FastAPI%20Swarm%20Orchestrator-10b981)
![Cloud](https://img.shields.io/badge/Cloud-Azure%20Web%20App%20%2B%20Container%20Apps-2563eb)

## Architecture Overview

AI Dev Factory runs as a **Dual-Gate Agentic Workflow**:

```text
[PM Agent]
	-> (Human Gate 1: PRD Approval)
[System Architect]
	-> (Human Gate 2: API Contract Approval)
[Backend Engine & Frontend Engine]
```

```mermaid
flowchart LR
	 A[PM Agent] --> B{Human Gate 1\nPRD Approval}
	 B -->|Approved| C[System Architect]
	 C --> D{Human Gate 2\nAPI Contract Approval}
	 D -->|Approved| E[Backend Engine]
	 D -->|Approved| F[Frontend Engine]
```

### Why the dual-gate state machine matters

- **Gate 1 (PRD Approval)** prevents requirement drift before architecture is generated.
- **Gate 2 (API Contract Approval)** locks integration boundaries before code synthesis begins.
- **State-driven execution** (idle -> running_pm -> review_prd -> running_architect -> review_contract -> running_downstream -> completed/failed) makes behavior auditable and deterministic.
- **Human-in-the-loop checkpoints** reduce hallucinations, enforce intent alignment, and produce outputs that are far closer to production-ready.

## Key Features

- **Resizable IDE-like Workspace** powered by `react-resizable-panels` for Control Center, Agent War Room, and Artifact Workspace panes.
- **Live Inter-Agent Communication Log** with real-time stream indicators (connecting/live/reconnecting/disconnected) and stage-tagged updates.
- **Real-time status polling + event streaming** so the UI stays responsive even during long-running generation jobs.
- **Artifact Viewer** for PRD, architecture contract, and generated code files, including per-file loading and download actions.
- **Human approval controls** for PRD and architecture before downstream generation is allowed.

## Tech Stack

### Frontend

- **React** (UI runtime)
- **Vite** (build and dev tooling)
- **Tailwind CSS** (utility-first styling)
- **Lucide React** (icon system)
- **react-resizable-panels** (multi-pane IDE workspace interactions)

### Backend

- **Python**
- **FastAPI**
- **Swarm Orchestrator** (multi-agent PM/Architect/Backend/Frontend/Dependency pipeline)
- **FastAPI BackgroundTasks** for asynchronous downstream execution after contract approval

### Deployment

- **Azure Web App** for the frontend static app hosting
- **Azure Container Apps** for the FastAPI orchestration backend

## Local Setup

### 1) Backend (FastAPI)

```bash
cd backend
python -m venv .venv
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# macOS/Linux:
# source .venv/bin/activate

pip install -r requirements.txt
uvicorn main:app --reload
```

Backend default URL:

```text
http://127.0.0.1:8000
```

### 2) Frontend (Vite)

```bash
cd dashboard-ui
npm install
npm run dev
```

Frontend default URL:

```text
http://localhost:5173
```

### 3) Environment Variables

Create a `.env` file in the repo root (or backend runtime context) with at least:

```env
# Required for backend CORS
FRONTEND_URL=http://localhost:5173

# Backend runtime
PORT=8000
DEBUG=true

# Azure + model configuration (required for full agent execution)
AZURE_OPENAI_ENDPOINT=
AZURE_OPENAI_DEPLOYMENT_NAME=
AZURE_SUBSCRIPTION_ID=
AZURE_RESOURCE_GROUP=
AZURE_STORAGE_ACCOUNT_URL=
AZURE_STORAGE_CONTAINER_NAME=
```

## Cloud Deployment Architecture

### Frontend on Azure Web App (Static SPA via PM2)

1. Build the frontend into a static output:

```bash
cd dashboard-ui
npm install
npm run build
```

2. Deploy the generated `dist` folder to Azure Web App (`/home/site/wwwroot`).
3. Start the Node BFF server on Azure Web App:

```bash
npm start
# or
node server/bff-server.js
```

This runs the dashboard BFF (`server/bff-server.js`) so `/api/*` requests are proxied correctly to the backend while still serving the SPA.

### Backend on Azure Container Apps

- Containerize FastAPI backend via Docker.
- Push image to Azure Container Registry.
- Deploy to Azure Container Apps with managed identity + RBAC for Azure OpenAI and Blob Storage.
- Expose secure HTTPS ingress for the orchestration API and event/status endpoints.

The provided PowerShell deployment flow in `infrastructure/deploy.ps1` automates image build/push, container app updates, and role assignments.

## Hackathon Value Proposition

Most AI code generators fail at reliability because they optimize for speed over control. **AI Dev Factory** flips that tradeoff:

- **Predictable outputs** through explicit, gated state transitions.
- **Higher quality delivery** by forcing human approval at PRD and contract boundaries.
- **Scalable architecture** where downstream code engines can run asynchronously and independently.
- **Production-readiness by design** with real-time observability, artifact traceability, and cloud-native deployment targets.

In short: this is not just an AI code generator, it is a **governed software generation pipeline** built for real teams.
