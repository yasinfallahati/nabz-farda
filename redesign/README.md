# Calm redesign: APPLIED and deployed 2026-10-04 16:40 Tehran
The live design source is now public/ + scripts/sitegen.py (nightly/stories routines rebuild from them).
redesign/new-design.tgz = snapshot of the approved redesign (pre-OG restyle); redesign/backup/pre-redesign.tgz = old design.
Rollback (only if asked):
    tar xzf redesign/backup/pre-redesign.tgz public/index.html public/assets scripts/sitegen.py
    .venv/bin/python scripts/build.py --pages-only && bash scripts/deploy_cli.sh
