"""Start, connect to and pause the SURF GPU workspace (Python version of surf_gpu.R).

Reads SRC_API_KEY from the environment (never printed).
"""
import os, time, json, subprocess, datetime
import requests

WS_ID = os.environ.get("SURF_GPU_WORKSPACE_ID", "")
HOST = os.environ.get("SURF_GPU_HOST", "")
USER = os.environ.get("SURF_GPU_USER", "")
HOME = os.environ.get("USERPROFILE", os.path.expanduser("~"))
KEY = os.path.join(HOME, ".ssh", "id_ed25519_surf")
KNOWN = os.path.join(HOME, ".ssh", "known_hosts_surf_gpu")
MODEL = "gpt-oss:20b-capped"
LOCAL_PORT = 11435
OLLAMA = f"http://localhost:{LOCAL_PORT}"
SSH = ["ssh", "-i", KEY, "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
       "-o", f"UserKnownHostsFile={KNOWN}", "-o", "StrictHostKeyChecking=accept-new"]

def _api(path, method="GET"):
    tok = os.environ.get("SRC_API_KEY", "").strip().strip('"')
    if not tok:
        raise SystemExit("SRC_API_KEY is not set")
    url = "https://gw.live.surfresearchcloud.nl/v1/" + path
    h = {"authorization": tok, "accept": "application/json"}
    r = requests.post(url, headers=h, json={}, timeout=60) if method == "POST" else requests.get(url, headers=h, timeout=60)
    if r.status_code >= 300:
        raise SystemExit(f"SURF answered {r.status_code} to {method} {path}: {r.text[:300]}")
    return r.json()

def workspace():
    return _api(f"workspace/workspaces/{WS_ID}/")

def ssh(cmd, timeout=40):
    try:
        p = subprocess.run(SSH + [f"{USER}@{HOST}", cmd], capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout.strip()
    except subprocess.TimeoutExpired:
        return 255, ""

def _action(action, target, timeout_min=30):
    ws = workspace()
    if ws["status"] == target:
        print("The workspace is already", target); return
    if action not in (ws.get("allowed_actions") or []):
        raise SystemExit(f"SURF does not allow '{action}' now (status {ws['status']}, "
                         f"allowed {ws.get('allowed_actions')}). Look in the SRC portal.")
    asked = datetime.datetime.now(datetime.timezone.utc)
    _api(f"workspace/workspaces/{WS_ID}/actions/{action}/", "POST")
    print(f"Asked SURF to {action}; waiting until '{target}'", flush=True)
    while True:
        time.sleep(15)
        ws = workspace()
        a = (ws.get("workspace_actions") or [{}])[0]
        try:
            t = datetime.datetime.fromisoformat(a.get("time_created", "").replace("Z", "+00:00"))
            if t.tzinfo is None:
                t = t.replace(tzinfo=datetime.timezone.utc)
        except ValueError:
            t = None
        if t and t >= asked - datetime.timedelta(minutes=2) and a.get("type") == action and a.get("status") == "failed":
            raise SystemExit(f"SURF reports that the {action} FAILED: {a.get('reason') or a.get('result')}. "
                             "The machine may still have started: check the SRC portal.")
        if ws["status"] == target:
            break
        if ws["status"] in ("failed", "unhealthy"):
            raise SystemExit(f"The workspace became '{ws['status']}'. Look in the SRC portal.")
        if (datetime.datetime.now(datetime.timezone.utc) - asked).total_seconds() > timeout_min * 60:
            raise SystemExit(f"Not '{target}' after {timeout_min} minutes (status {ws['status']}).")
    print(f"The workspace is {target} after {(datetime.datetime.now(datetime.timezone.utc) - asked).seconds} s", flush=True)

def start():
    _action("resume", "running")
    for _ in range(40):
        code, out = ssh("systemctl is-active ollama")
        if out.strip() == "active":
            print("Logins work and Ollama runs", flush=True); return
        time.sleep(15)
    raise SystemExit("The workspace runs, but SSH or Ollama did not answer within 10 minutes")

def has_model():
    try:
        tags = requests.get(OLLAMA + "/api/tags", timeout=5).json()
        return any(m["name"] == MODEL for m in tags.get("models", []))
    except Exception:
        return False

def connect():
    if has_model():
        return None
    # ssh's messages go to a log file: an unread pipe fills up and then blocks the tunnel
    log = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "tunnel_log.txt"), "a")
    tunnel = subprocess.Popen(SSH + ["-N", "-o", "ExitOnForwardFailure=yes", "-o", "ServerAliveInterval=30",
                                     "-L", f"{LOCAL_PORT}:127.0.0.1:11434", f"{USER}@{HOST}"],
                              stdout=subprocess.DEVNULL, stderr=log)
    for _ in range(30):
        if has_model() or tunnel.poll() is not None:
            break
        time.sleep(1)
    if not has_model():
        tunnel.kill()
        raise SystemExit("No Ollama with the model through the tunnel")
    print("Tunnel open: localhost:%d -> workspace Ollama" % LOCAL_PORT, flush=True)
    return tunnel

def stop(tunnel=None):
    if tunnel is not None and tunnel.poll() is None:
        tunnel.kill()
    _action("pause", "paused")
    code, _ = ssh("true", timeout=30)
    if code == 0:
        print("WARNING: SURF says 'paused' but SSH still answers: the GPU may still run. Check the SRC portal.")
    else:
        print("Paused, and SSH no longer answers", flush=True)

def status():
    ws = workspace()
    a = (ws.get("workspace_actions") or [{}])[0]
    print("Workspace", ws.get("name"), "status:", ws.get("status"), "| last action:", a.get("type"), a.get("status"),
          a.get("time_created"))
    return ws.get("status")

if __name__ == "__main__":
    import sys
    {"status": status, "start": start, "stop": stop}[sys.argv[1]]()
