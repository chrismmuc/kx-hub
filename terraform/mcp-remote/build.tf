# Cloud Build trigger for MCP server Docker image
#
# This configuration creates a null_resource that triggers Cloud Build
# to build and push the Docker image before Cloud Run deployment

# Null resource to trigger Cloud Build when code changes
resource "null_resource" "build_mcp_image" {
  # Trigger rebuild when source code changes
  triggers = {
    # Hash of all Python files in src/mcp_server
    code_hash = md5(join("", [for f in fileset("${path.root}/../../src/mcp_server", "**/*.py") : filemd5("${path.root}/../../src/mcp_server/${f}")]))
    # Hash of Dockerfile
    dockerfile_hash = filemd5("${path.root}/../../Dockerfile.mcp-server")
  }

  # Build and push Docker image using Cloud Build
  provisioner "local-exec" {
    working_dir = "${path.root}/../.."
    command     = <<-EOT
      gcloud builds submit \
        --config=cloudbuild.mcp-server.yaml \
        --project=${var.project_id}
    EOT
  }
}

# Update Cloud Run service to depend on the build
resource "null_resource" "force_cloud_run_dependency" {
  depends_on = [null_resource.build_mcp_image]

  # This ensures Cloud Run service is updated after build completes
  triggers = {
    build_trigger = null_resource.build_mcp_image.id
  }
}
