# 🏆 Global Wall Inspector — Master Interview & System Architecture Guide

This guide breaks down the **5-Pillar Modern AI & Cloud Engineering Stack** implemented in this repository so you can speak to every layer with hands-on authority in technical, product, or leadership interviews.

---

## 🗺️ High-Level System Architecture

```mermaid
flowchart TB
    subgraph CI_IaC["🏗️ Pillar 2 & 3: CI/CD & Infrastructure as Code"]
        GHA["⚡ GitHub Actions (.github/workflows/ci.yml)\nRuns 61 Unit & Agent Tests on every git push"]
        TF["📐 Terraform (infra/main.tf)\nProvisions Render Web Service, PostgreSQL 15 & Secrets"]
    end

    subgraph Runtime["🐳 Pillar 1: Dockerized Cloud Runtime (Dockerfile & docker-compose.yml)"]
        Web["🐍 Flask + Gunicorn WSGI Server\nUnified Student Portal (/portal) & Assessor Admin"]
        Sentinel["🛡️ Agent 1: Intake Sentinel (sentinel_agent.py)\nPillow Optical Audit + Gemini Photogrammetry"]
        Director["🎯 Agent 2: Curriculum Director (app.py)\nBattery Sizing, Side-by-Side Shuffle & Dry-Run"]
        Health["🩺 Observability (/api/health & openapi.yaml)"]
    end

    subgraph Data_MLOps["📦 Pillar 4 & 5: Storage, MCP & MLOps Flywheel"]
        PG[("🐘 PostgreSQL 15\nRelational Metadata & Scores")]
        CDN[("☁️ Cloudinary CDN\n500+ Uncompressed Masonry Photos")]
        COCO["📊 MLOps Exporter (/api/skill-assessment/export-coco)\nExports COCO 1.0 JSON for CVAT & YOLOv8"]
        MCP["🔌 MCP Server (mcp_server.py)\nJSON-RPC 2.0 Tool Interface for External LLMs"]
    end

    GHA --> Runtime
    TF --> Runtime
    Web --> Sentinel
    Web --> Director
    Web --> Health
    Web --> PG
    Web --> CDN
    PG --> COCO
    CDN --> COCO
    Runtime --> MCP
```

---

## 🎤 The 5 Pillars: Interview Questions & Your "Gold Standard" Answers

### Pillar 1: Docker & Containerization ([`Dockerfile`](Dockerfile), [`docker-compose.yml`](docker-compose.yml))

* **Why We Used It**:
  Earlier in development, our **Intake Sentinel Agent** worked on macOS (which already had `Pillow` installed) but failed when deployed to a Linux cloud server (`ModuleNotFoundError: No module named 'PIL'`). Docker eliminates the *"Works on My Machine"* problem by sealing the exact OS (`python:3.11-slim`), native C image libraries (`libjpeg62-turbo`), Python packages, and `Gunicorn` server inside an immutable container.
* **Key Engineering Best Practices in Our `Dockerfile` you can mention**:
  1. **Layer Caching**: We copy and install `requirements.txt` *before* copying `app.py`, so Docker caches the libraries and rebuilds in 2 seconds when code changes.
  2. **Non-Root Security (`appuser`)**: We run the container as a dedicated non-root user (`UID 1001`) so even if a web request is compromised, it has no root access.
  3. **Stateless Compute + Externalized State**: Because containers are ephemeral (wiped on restart), we store all 500 uncompressed masonry images in **Cloudinary CDN** and relational data in **PostgreSQL 15**.
  4. **Built-in `HEALTHCHECK`**: Docker automatically pings `http://localhost:8000/api/health` every 30 seconds to verify the app and database are alive.

---

### Pillar 2: Terraform — Infrastructure as Code ([`infra/main.tf`](infra/main.tf), [`infra/variables.tf`](infra/variables.tf))

* **Why We Used It**:
  Setting up cloud servers by clicking buttons in a web dashboard ("ClickOps") is slow, unrepeatable, and prone to human error. Terraform codifies our cloud infrastructure into declarative `.tf` files.
* **What Our `infra/main.tf` Does**:
  1. Provisions a managed **PostgreSQL 15** database (`render_postgres.wall_inspector_db`).
  2. Provisions the **Dockerized Web Service** (`render_web_service.wall_inspector_app`) pointing to `BBSISK/wall_inspector`.
  3. Automatically injects the database's internal connection string into the web service's `DATABASE_URL` environment variable, alongside sensitive secrets (`CLOUDINARY_URL`, `GEMINI_API_KEY`).
* **Interview Soundbite**:
  > *"While Docker defines what runs **inside** the container, Terraform defines the **cloud infrastructure** around it—provisioning the managed PostgreSQL 15 instance, networking, and secret bindings so we can spin up a staging or client environment in one command (`terraform apply`)."*

---

### Pillar 3: GitHub Actions CI/CD ([`ci/github-actions-ci.yml`](ci/github-actions-ci.yml))

* **Why We Used It**:
  To prevent broken code from ever reaching production.
* **What Happens on Every `git push`**:
  1. GitHub automatically boots a fresh Ubuntu Linux cloud machine.
  2. Installs Python 3.11 and `requirements.txt`.
  3. Runs all **60+ automated unit tests** covering the Unified Student Portal (`/portal`), the **Intake Sentinel Agent**, the **Curriculum Director Agent** (anti-collusion randomization & dry-run mode), and the **COCO MLOps Exporter**.
  4. Runs `python mcp_server.py --self-test` to verify all 4 MCP agent tools respond accurately.

---

### Pillar 4: Model Context Protocol — MCP Server ([`mcp_server.py`](mcp_server.py))

* **Why We Used It**:
  **MCP (Model Context Protocol)** is the universal open standard in 2026 for connecting AI assistants (Claude, Gemini, Cursor) to domain-specific tools and databases over JSON-RPC 2.0.
* **What Our `mcp_server.py` Exposes**:
  1. `sentinel_evaluate_image` — Lets any external AI agent run optical quality and sharpness checks on a wall photo.
  2. `curriculum_cohort_intelligence` — Lets an AI assistant query live student pass rates and identify which masonry defect categories the class is struggling with.
  3. `list_skill_specimens` — Queries the active masonry catalog by difficulty tier.
  4. `export_coco_dataset_stats` — Reports MLOps training dataset readiness.

---

### Pillar 5: MLOps Data Flywheel & CVAT / YOLOv8 Bridge ([`app.py`](app.py))

* **Why We Used It**:
  As assessors upload **500 uncompressed masonry images** to Cloudinary and students drop thousands of diagnostic pins in `/portal`, the platform naturally builds a massive labeled Computer Vision dataset.
* **How It Works**:
  - Clicking **`[ 📦 Export COCO / CVAT ]`** in `/skill-assessment/admin` hits `/api/skill-assessment/export-coco?download=1&include_student_consensus=1`.
  - It exports a standard **Microsoft COCO 1.0 JSON** dataset containing all Cloudinary image URLs, defect categories, expert ground-truth bounding boxes (`[x, y, width, height]`), and crowdsourced student consensus pins.
  - This JSON file can be imported directly into **CVAT** or used to fine-tune a custom **YOLOv8-Seg** masonry defect detector.

---

### Pillar 6: Dual Admin Architecture & Unified Multi-Provider OAuth ([`auth_manager.py`](auth_manager.py), [`models.py`](models.py))

* **Why We Used It**:
  In multi-organization civil engineering and conservation education, platform governance must be cleanly partitioned between:
  1. **Class Administration (`/admin/class`)**: Focused strictly on student rosters, cohort analytics, 4-digit PIN provisioning, and examination batteries.
  2. **System Administration (`/admin/system`)**: Focused on global master specimen curation, school tenant onboarding, Intake Sentinel quality audits, and assessor authorization control.
* **Unified OAuth & Email Fallback Implementation**:
  - **Google OAuth 2.0 & Microsoft 365 / Entra ID**: Single sign-on for students, instructors, and system administrators via OpenID Connect.
  - **Zero-Crash Interactive Sandbox Simulator (`/auth/simulate/<provider>`)**: When cloud API credentials are not yet injected into `.env`, the system provides an interactive simulation mode with pre-configured personas (Dr. Jane Doe for Class Admin, Prof. Barry Sisk for System Admin, Alex Mason for Student). This allows interviewers and evaluators to test the entire authentication and session lifecycle without cloud secrets.
  - **Email Passcode Fallback & Approval Gate (`/auth/email/request`)**: Users without OAuth can authenticate via a time-limited 6-digit cryptographic OTP. Newly registered instructors are held in a pending verification queue (`is_approved = False`) until authorized by the System Administrator in 1-click.

---

### Pillar 7: Automated Notification Sentinel & Transactional Alerts ([`notification_service.py`](notification_service.py))

* **Why We Used It**:
  Administrative security demands instant visibility when new instructors or assessors request access. The notification service uses a non-blocking daemon thread pool to dispatch rich HTML emails (supporting Resend, SendGrid, and SMTP/Gmail) without injecting any latency into user web requests.

---

## 🧭 Architectural Roadmap & Backlog

- 📌 **Pinned for Future Review**: **Class Admin Student Application Queue** — Enable approval gates on `/admin/class` so student self-registrations via school OAuth can be vetted and assigned to specific cohorts by their local instructor before accessing exam batteries.
- 🚀 **Next Phase (Phase 3)**: **Multimodal RAG on Human-Graded Masonry Database** — Using expert human-annotated specimens, calibrated tolerance radii, and remedial defect rationale as a retrieval-augmented generation (RAG) vector ground-truth to continually elevate Gemini's automated grading precision.

---

## 🛠️ Quick Reference Commands

```bash
# 1. Run all 85 Unit, Agent, OAuth, Notification & DevOps Tests
python3 -m unittest discover -s . -p "test_*.py" -v

# 2. Run the Model Context Protocol (MCP) Server Self-Test
python3 mcp_server.py --self-test

# 3. Start the Full Stack Locally in Docker (Web + PostgreSQL 15)
docker compose up --build

# 4. Validate Terraform Infrastructure Configuration
cd infra && terraform init && terraform validate
```
