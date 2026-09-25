# ==============================================================================
# Terraform Input Variables — Global Wall Inspector
# ==============================================================================

variable "project_name" {
  description = "Base name for cloud infrastructure resources"
  type        = string
  default     = "global-wall-inspector"
}

variable "region" {
  description = "Cloud deployment region (e.g., frankfurt, oregon, ohio)"
  type        = string
  default     = "frankfurt"
}

variable "github_repo_url" {
  description = "GitHub repository URL containing the application and Dockerfile"
  type        = string
  default     = "https://github.com/BBSISK/wall_inspector"
}

variable "git_branch" {
  description = "Production deployment branch"
  type        = string
  default     = "main"
}

variable "web_service_plan" {
  description = "Render web service compute tier (free, starter, standard)"
  type        = string
  default     = "starter"
}

variable "postgres_plan" {
  description = "Render managed PostgreSQL plan tier (free, basic_256mb, standard)"
  type        = string
  default     = "free"
}

variable "render_api_key" {
  description = "Render API key for automated provisioning"
  type        = string
  sensitive   = true
  default     = ""
}

variable "render_owner_id" {
  description = "Render Workspace / Owner ID"
  type        = string
  default     = ""
}

variable "cloudinary_url" {
  description = "Cloudinary CDN connection string for 500+ uncompressed masonry images"
  type        = string
  sensitive   = true
  default     = ""
}

variable "gemini_api_key" {
  description = "Google Gemini Vision API key for AI defect pin suggestions"
  type        = string
  sensitive   = true
  default     = ""
}

variable "flask_secret_key" {
  description = "Cryptographic signing secret for student and mobile sessions"
  type        = string
  sensitive   = true
  default     = "masonry-inspector-prod-secret-2026"
}
