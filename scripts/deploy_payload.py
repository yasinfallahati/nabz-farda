#!/usr/bin/env python3
"""Step 4 — DEPLOY helper: produce the exact `requestBody` for the Vercel MCP tool create_deployment.

  deploy_payload.py            -> writes deploy/payload.json and prints it.
        Files whose SHA1 is already on Vercel (recorded in deploy/state.json) are referenced by {file, sha, size};
        new/changed files are inlined as utf-8 text. Pass the printed JSON verbatim as `requestBody`.
  deploy_payload.py --all      -> inline every file (use if Vercel answers "missing_files").
  deploy_payload.py --mark-deployed https://nabz-farda.vercel.app
                               -> after a READY deployment, download every file from the live URL and record the
                                  SHAs that match local files (so next night they are referenced, not re-sent).
"""
import hashlib, json, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUB = ROOT / "public"
STATE = ROOT / "deploy/state.json"
PROJECT = "nabz-farda"


def files():
    for p in sorted(PUB.rglob("*")):
        if p.is_file() and ".vercel" not in p.relative_to(PUB).parts:
            b = p.read_bytes()
            yield p.relative_to(PUB).as_posix(), b, hashlib.sha1(b).hexdigest()


def main():
    STATE.parent.mkdir(exist_ok=True)
    st = json.loads(STATE.read_text()) if STATE.exists() else {"uploaded": [], "deployments": []}
    if "--mark-deployed" in sys.argv:
        import urllib.request
        base = sys.argv[sys.argv.index("--mark-deployed") + 1].rstrip("/")
        ok, bad = set(st["uploaded"]), []
        for path, b, sha in files():
            if sha in ok or path in (".gitignore", "vercel.json"):   # already verified / config files are not served
                continue
            try:
                live = urllib.request.urlopen(urllib.request.Request(f"{base}/{path}", headers={"Cache-Control": "no-cache"}), timeout=20).read()
            except Exception as ex:
                bad.append(f"{path}: {ex}"); continue
            if hashlib.sha1(live).hexdigest() == sha:
                ok.add(sha)
            else:
                bad.append(f"{path}: live content differs from local")
        st["uploaded"] = sorted(ok)
        st["deployments"].append({"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "url": base})
        STATE.write_text(json.dumps(st, indent=1))
        print("verified & recorded", len(ok), "shas")
        for x in bad:
            print("  WARN", x)
        sys.exit(1 if bad else 0)
    inline_all = "--all" in sys.argv
    up = set(st["uploaded"])
    out = []
    for path, b, sha in files():
        if not inline_all and sha in up:
            out.append({"file": path, "sha": sha, "size": len(b)})
        else:
            try:
                out.append({"file": path, "data": b.decode("utf-8"), "encoding": "utf-8"})
            except UnicodeDecodeError:  # binary (OG images, PNG logos)
                import base64
                out.append({"file": path, "data": base64.b64encode(b).decode(), "encoding": "base64"})
    body = {
        "name": PROJECT, "project": PROJECT, "target": "production",
        "projectSettings": {"framework": None, "buildCommand": None, "installCommand": None, "outputDirectory": None},
        "files": out,
    }
    (ROOT / "deploy/payload.json").write_text(json.dumps(body, ensure_ascii=False))
    n_inline = sum(1 for f in out if "data" in f)
    print(json.dumps(body, ensure_ascii=False))
    print(f"\n# {len(out)} files, {n_inline} inlined, {len(out) - n_inline} by sha -> deploy/payload.json", file=sys.stderr)


if __name__ == "__main__":
    main()
