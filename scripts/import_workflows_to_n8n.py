#!/usr/bin/env python3
"""
Script to import workflows into n8n via API.

Usage:
    python scripts/import_workflows_to_n8n.py

Note: Requires one of:
  - N8N_API_KEY environment variable (recommended)
  - N8N_USER + N8N_PASSWORD for Basic Auth (if enabled in n8n)
"""

import json
import os
import sys

try:
    import requests
except ImportError:
    print("requests not installed. Installing...")
    os.system(f"{sys.executable} -m pip install requests")
    import requests

N8N_URL = "https://n8n.sec-scanner.pro"
API_ENDPOINT = f"{N8N_URL}/api/v1/workflows"

WORKFLOW_FILES = [
    "n8n/workflows/agents/architect-agent.json",
    "n8n/workflows/agents/dev-agent.json",
    "n8n/workflows/agents/qa-agent.json",
    "n8n/workflows/agents/tech-writer-agent.json",
    "n8n/workflows/agents/support-agent.json",
    "n8n/workflows/agents/marketer-agent.json",
    "n8n/workflows/sales/telegram-content-publisher.json",
    # "n8n/workflows/agents/master-orchestrator.json",  # TODO: fix JSON in jsCode strings
]


def import_workflow(
    file_path: str,
    api_key: str | None = None,
    basic_auth: tuple | None = None,
) -> dict:
    """Import a single workflow file into n8n."""
    print(f"\n📄 Importing: {file_path}")

    if not os.path.exists(file_path):
        print(f"❌ File not found: {file_path}")
        return None

    with open(file_path, encoding="utf-8") as f:
        workflow_data = json.load(f)

    headers = {
        "Content-Type": "application/json",
    }
    auth = None

    if api_key:
        headers["X-N8N-API-KEY"] = api_key
    elif basic_auth:
        auth = basic_auth

    try:
        response = requests.post(
            API_ENDPOINT, headers=headers, json=workflow_data, auth=auth, timeout=30
        )

        if response.status_code == 200:
            result = response.json()
            print(f"✅ Successfully imported: {result.get('name', 'Unknown')}")
            print(f"   ID: {result.get('id', 'N/A')}")
            return result
        elif response.status_code == 401:
            print(f"❌ Authentication required. Status: {response.status_code}")
            print(f"   Response: {response.text}")
            return None
        else:
            print(f"❌ Failed to import. Status: {response.status_code}")
            print(f"   Response: {response.text}")
            return None

    except requests.exceptions.RequestException as e:
        print(f"❌ Request error: {e}")
        return None


def main():
    print("=" * 60)
    print("🔄 n8n Workflow Import Tool")
    print("=" * 60)
    print(f"\nTarget: {N8N_URL}")

    api_key = os.environ.get("N8N_API_KEY")

    if api_key:
        print("✅ Using API key from N8N_API_KEY environment variable")
    else:
        print("⚠️  No API key found (N8N_API_KEY not set)")
        print("   Trying without authentication (may fail)")

    success_count = 0
    failed_count = 0

    basic_auth = None
    if not api_key and os.environ.get("N8N_USER") and os.environ.get("N8N_PASSWORD"):
        basic_auth = (os.environ["N8N_USER"], os.environ["N8N_PASSWORD"])
        print("✅ Using Basic Auth (N8N_USER + N8N_PASSWORD)")

    for workflow_file in WORKFLOW_FILES:
        result = import_workflow(workflow_file, api_key, basic_auth)
        if result:
            success_count += 1
        else:
            failed_count += 1

    print("\n" + "=" * 60)
    print("📊 Import Summary")
    print("=" * 60)
    print(f"✅ Successful: {success_count}")
    print(f"❌ Failed: {failed_count}")
    print(f"📁 Total: {len(WORKFLOW_FILES)}")

    if failed_count > 0 and not api_key:
        print("\n💡 Tip: Set N8N_API_KEY environment variable for authentication")
        print("   You can get API key from n8n UI: Settings > API")

    return success_count == len(WORKFLOW_FILES)


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
