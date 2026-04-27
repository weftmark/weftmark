import urllib.request, json, subprocess

token = subprocess.check_output(
    "grep ^GITEA_TOKEN= .env.local | cut -d= -f2 | tr -d '[:space:]'",
    shell=True, cwd="d:/repos/weaving_site"
).decode().strip()

# Create the test issue
payload = json.dumps({
    "title": "Webhook server integration test",
    "body": "This issue is used to test the weaving_site webhook server.\n\nComment on this issue and the webhook server will receive the event and respond via `claude -p`.",
    "assignees": ["claude_vscode"],
}).encode()

req = urllib.request.Request(
    "http://10.10.10.90:3000/api/v1/repos/gx1400/weaving_site/issues",
    data=payload,
    headers={"Authorization": f"token {token}", "Content-Type": "application/json"},
    method="POST"
)
with urllib.request.urlopen(req) as resp:
    issue = json.loads(resp.read())
    print("Issue created:", issue["html_url"])
    print("Issue number:", issue["number"])

# Register the webhook
webhook_payload = json.dumps({
    "active": True,
    "branch_filter": "*",
    "config": {
        "content_type": "json",
        "secret": "weaving-test-secret",
        "url": "http://10.10.10.90:3001/webhook",
    },
    "events": ["issue_comment"],
    "type": "gitea",
}).encode()

req2 = urllib.request.Request(
    "http://10.10.10.90:3000/api/v1/repos/gx1400/weaving_site/hooks",
    data=webhook_payload,
    headers={"Authorization": f"token {token}", "Content-Type": "application/json"},
    method="POST"
)
with urllib.request.urlopen(req2) as resp:
    hook = json.loads(resp.read())
    print("Webhook registered, id:", hook["id"])
    print("Target URL:", hook["config"]["url"])
