#!/usr/bin/env python3
"""
One-time deployment script: deploys the newsletter curation agent to Vertex AI Agent Engine.

Usage:
    python3 src/newsletter/deploy_agent.py [--project kx-hub] [--region us-central1]

After deployment, saves the agent_engine_id to Secret Manager as 'newsletter-agent-engine-id'.
The Cloud Function reads this via NEWSLETTER_AGENT_ENGINE_ID env var.

Prerequisites:
    pip install google-adk google-cloud-aiplatform google-cloud-secret-manager
    gcloud auth application-default login
"""

import argparse
import sys

GCP_PROJECT_DEFAULT = "kx-hub"
GCP_REGION_DEFAULT = "us-central1"  # Agent Engine requires us-central1


def deploy(project: str, region: str) -> str:
    """Deploy ADK agent to Vertex AI Agent Engine and return resource_name."""
    import vertexai
    from google.adk.agents import LlmAgent
    from google.adk.tools import google_search
    from vertexai import agent_engines

    try:
        from curation_agent import AGENT_INSTRUCTION
    except ImportError:
        import os
        sys.path.insert(0, os.path.dirname(__file__))
        from curation_agent import AGENT_INSTRUCTION

    print(f"Initializing Vertex AI: project={project}, region={region}")
    vertexai.init(project=project, location=region)

    agent = LlmAgent(
        model="gemini-2.0-flash",
        name="newsletter-curator",
        description="Curates tech newsletter from personal knowledge sources + web search",
        instruction=AGENT_INSTRUCTION,
        tools=[google_search],
    )

    print("Deploying agent to Vertex AI Agent Engine...")
    app = agent_engines.AdkApp(agent=agent)
    remote_app = agent_engines.create(
        app,
        requirements=["google-adk>=0.3.0"],
        display_name="newsletter-curator",
        description="Newsletter curation agent for kx-hub",
    )

    resource_name = remote_app.resource_name
    print(f"Agent deployed: {resource_name}")
    return resource_name


def save_to_secret_manager(resource_name: str, project: str) -> None:
    """Save the agent resource_name to Secret Manager."""
    from google.cloud import secretmanager

    client = secretmanager.SecretManagerServiceClient()
    parent = f"projects/{project}"
    secret_id = "newsletter-agent-engine-id"

    # Try to create secret (ignore if already exists)
    try:
        client.create_secret(
            request={
                "parent": parent,
                "secret_id": secret_id,
                "secret": {"replication": {"automatic": {}}},
            }
        )
        print(f"Created secret: {secret_id}")
    except Exception:
        print(f"Secret {secret_id} already exists, adding new version")

    # Add secret version
    client.add_secret_version(
        request={
            "parent": f"{parent}/secrets/{secret_id}",
            "payload": {"data": resource_name.encode("UTF-8")},
        }
    )
    print(f"Saved agent engine ID to Secret Manager: {secret_id}")


def main():
    parser = argparse.ArgumentParser(description="Deploy newsletter curation agent")
    parser.add_argument("--project", default=GCP_PROJECT_DEFAULT)
    parser.add_argument("--region", default=GCP_REGION_DEFAULT)
    parser.add_argument("--dry-run", action="store_true", help="Skip actual deployment")
    args = parser.parse_args()

    if args.dry_run:
        print("Dry-run mode: skipping deployment")
        return

    resource_name = deploy(args.project, args.region)
    save_to_secret_manager(resource_name, args.project)
    print(f"\nDeployment complete!")
    print(f"Resource name: {resource_name}")
    print(f"\nNext: Add NEWSLETTER_AGENT_ENGINE_ID={resource_name} to Cloud Function env vars,")
    print("or it will be loaded from Secret Manager at runtime.")


if __name__ == "__main__":
    main()
