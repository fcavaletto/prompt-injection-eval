"""Delete the pod this runs in when its paid lifetime is over. Standard library only.

Started in the background by the pod's own start command, so it does not depend on the
machine that rented the pod, on the agent, or on the experiment process. It uses the
pod-scoped key RunPod puts in the pod's environment (RUNPOD_API_KEY) and never prints it.

EXPIRES_AT is an absolute UNIX time set when the pod is created, so a container restart
does not restart the clock. At expiry it tries to delete (terminate) the pod, then to stop
it, every 30 seconds until one call is accepted. Every attempt is logged with its HTTP status.
"""

import json
import os
import time
import urllib.error
import urllib.request

POD = os.environ.get("RUNPOD_POD_ID", "")
KEY = os.environ.get("RUNPOD_API_KEY", "")
EXPIRES_AT = float(os.environ.get("EXPIRES_AT", "0") or 0)


def log(message: str) -> None:
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    print(f"[pod-expiry] {stamp} {message}", flush=True)


def call(method: str, url: str, body: dict | None = None) -> str:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        url,
        method=method,
        data=data,
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            text = response.read(400).decode(errors="replace")
            if "errors" in text and url.endswith("graphql"):
                return f"{response.status} graphql-error"
            return str(response.status)
    except urllib.error.HTTPError as error:
        return str(error.code)
    except Exception as error:  # noqa: BLE001 - logged and retried
        return type(error).__name__


def graphql(mutation: str) -> dict:
    return {"query": f'mutation {{ {mutation}(input: {{podId: "{POD}"}}) }}'}


ATTEMPTS = (
    ("DELETE", f"https://rest.runpod.io/v1/pods/{POD}", None),
    ("DELETE", f"https://api.runpod.io/v2/pods/{POD}", None),
    ("POST", "https://api.runpod.io/graphql", graphql("podTerminate")),
    ("POST", f"https://rest.runpod.io/v1/pods/{POD}/stop", None),
)
ACCEPTED = {"200", "202", "204"}


def main() -> None:
    log(f"pod id present: {bool(POD)}; key present: {bool(KEY)}; expires at {EXPIRES_AT:.0f}")
    if not POD or not KEY or not EXPIRES_AT:
        log("cannot enforce expiry: missing pod id, key or EXPIRES_AT")
        return
    for url in (f"https://rest.runpod.io/v1/pods/{POD}", f"https://api.runpod.io/v2/pods/{POD}"):
        log(f"probe GET {url.split('//')[1].split('/')[0]}: {call('GET', url)}")
    while (left := EXPIRES_AT - time.time()) > 0:
        log(f"{left / 60:.1f} min left")
        time.sleep(min(left, 300))
    while True:
        for method, url, body in ATTEMPTS:
            status = call(method, url, body)
            where = url.split("//")[1].split("/")[0] + ("/stop" if url.endswith("stop") else "")
            log(f"expired: {method} {where}: {status}")
            if status in ACCEPTED:
                log("accepted; waiting for the platform to end the pod")
                time.sleep(3600)
        time.sleep(30)


if __name__ == "__main__":
    main()
