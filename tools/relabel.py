import urllib.request, json, subprocess

token = subprocess.check_output(
    "grep ^GITEA_TOKEN= .env.local | cut -d= -f2 | tr -d '[:space:]'",
    shell=True
).decode().strip()

base = "http://10.10.10.90:3000/api/v1/repos/gx1400/weaving_site/issues"
headers = {"Authorization": f"token {token}", "Content-Type": "application/json"}

def add_labels(issue, label_ids):
    req = urllib.request.Request(
        f"{base}/{issue}/labels",
        data=json.dumps({"labels": label_ids}).encode(),
        headers=headers, method="POST"
    )
    urllib.request.urlopen(req).read()
    print(f"  +labels {label_ids} on #{issue}")

def remove_label(issue, label_id):
    req = urllib.request.Request(
        f"{base}/{issue}/labels/{label_id}",
        headers=headers, method="DELETE"
    )
    urllib.request.urlopen(req).read()
    print(f"  -label {label_id} on #{issue}")

def set_assignee(issue, login):
    req = urllib.request.Request(
        f"{base}/{issue}",
        data=json.dumps({"assignees": [login]}).encode(),
        headers=headers, method="PATCH"
    )
    urllib.request.urlopen(req).read()
    print(f"  assignee={login} on #{issue}")

# Label IDs: P1=1 P2=2 P3=3 P4=4 feature=5 process=14

print("#11 feedback button: P2→P3")
remove_label(11, 2)
add_labels(11, [3])

print("#13 session tracking: P2→P3")
remove_label(13, 2)
add_labels(13, [3])

print("#27 demo user: add P4")
add_labels(27, [4])

print("#34 photos in active activity: P2→P1, assign claude_vscode")
remove_label(34, 2)
add_labels(34, [1])
set_assignee(34, "claude_vscode")

print("#35 admin console: remove process label")
remove_label(35, 14)

print("Done.")
