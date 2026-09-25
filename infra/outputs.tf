# ==============================================================================
# Terraform Outputs — Global Wall Inspector
# ==============================================================================

output "web_service_url" {
  description = "Public HTTPS URL of the deployed Global Wall Inspector service"
  value       = render_web_service.wall_inspector_app.url
}

output "postgres_instance_id" {
  description = "Managed PostgreSQL 15 database identifier"
  value       = render_postgres.wall_inspector_db.id
}
