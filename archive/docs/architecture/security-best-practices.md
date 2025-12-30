# Security & Best Practices

## IAM Least-Privilege
- Each Cloud Function has a dedicated Service Account with minimal permissions.
- GCS: Bucket policies restrict access per Service Account.
- Secret Manager: Strict access control on secrets.

## Monitoring & Alerting
- Cloud Monitoring:
  - Function execution times
  - API Gateway latency
  - Vector Search query latency
  - Cost budgets
- Cloud Logging for all services.

## Infrastructure as Code (IaC)

Terraform has been selected as the exclusive tool for provisioning and managing all cloud infrastructure for this project.

- **Tool:** Terraform by HashiCorp
- **Reasoning:** As the industry standard, Terraform provides a mature, declarative, and safe way to manage infrastructure. Its large community, extensive documentation for Google Cloud, and multi-cloud capabilities make it the most pragmatic and lowest-risk choice.
- **Process:** All resources (Cloud Functions, Storage, Firestore, etc.) will be defined in `.tf` configuration files. Changes will be applied via the standard `terraform plan` and `terraform apply` workflow.

## Deployment

- **CI/CD:** Continuous Integration and Continuous Deployment will be managed via GitHub Actions.
- **Workflow:** The GitHub Actions workflow will be configured to automatically run `terraform plan` on pull requests and `terraform apply` on merges to the main branch, ensuring the deployed infrastructure always matches the configuration in the repository.

---