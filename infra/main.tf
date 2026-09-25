# ==============================================================================
# Global Wall Inspector — Terraform Infrastructure as Code (IaC)
# Declaratively provisions the Render Cloud Web Service, Managed PostgreSQL 15,
# and Environment Secret Bindings (Cloudinary CDN + Gemini Vision AI).
# ==============================================================================

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    render = {
      source  = "render-oss/render"
      version = "~> 1.3.0"
    }
  }
}

provider "render" {
  api_key  = var.render_api_key
  owner_id = var.render_owner_id
}

# 1. Managed PostgreSQL 15 Database Instance
resource "render_postgres" "wall_inspector_db" {
  name          = "${var.project_name}-postgres"
  plan          = var.postgres_plan
  region        = var.region
  version       = "15"
  database_name = "wall_inspector"
  database_user = "wall_inspector_admin"
}

# 2. Dockerized Production Web Service
resource "render_web_service" "wall_inspector_app" {
  name               = var.project_name
  plan               = var.web_service_plan
  region             = var.region
  health_check_path  = "/api/health"

  runtime_source = {
    docker = {
      repo_url        = var.github_repo_url
      branch          = var.git_branch
      dockerfile_path = "./Dockerfile"
      auto_deploy     = true
    }
  }

  env_vars = {
    "DATABASE_URL" = {
      value = render_postgres.wall_inspector_db.connection_info.internal_connection_string
    }
    "CLOUDINARY_URL" = {
      value = var.cloudinary_url
    }
    "GEMINI_API_KEY" = {
      value = var.gemini_api_key
    }
    "SECRET_KEY" = {
      value = var.flask_secret_key
    }
    "PYTHON_VERSION" = {
      value = "3.11.8"
    }
  }
}
