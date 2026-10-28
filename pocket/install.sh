#!/usr/bin/env bash
# Stage beside the running v1 phone platform. Preserve every existing database.
set -euo pipefail
umask 077
if command -v pkg >/dev/null 2>&1; then
  pkg install -y python git cloudflared curl
fi
command -v python3 >/dev/null || { echo 'Python 3 is required.'; exit 1; }
phone_root="$HOME/xi-phone-home"
data_dir="$phone_root/pocket-data"
mkdir -p "$phone_root/pocket-releases" "$data_dir"
script_path="${BASH_SOURCE[0]:-}"
source_dir=''
if [[ -n "$script_path" && -f "$script_path" ]]; then
  candidate_dir="$(cd "$(dirname "$script_path")" && pwd)"
  if [[ -f "$candidate_dir/server.py" && -f "$candidate_dir/app.js" ]]; then source_dir="$candidate_dir"; fi
fi
if [[ -z "$source_dir" ]]; then
  ref="${1:-}"
  [[ "$ref" =~ ^[0-9a-f]{40}$ ]] || { echo 'Pass the exact published 40-character commit SHA.'; exit 1; }
  checkout_dir="$phone_root/pocket-releases/$ref"
  if [[ ! -d "$checkout_dir/.git" ]]; then
    mkdir -p "$checkout_dir"
    git -C "$checkout_dir" init -q
    git -C "$checkout_dir" remote add origin https://github.com/rookslackie/plex-atlas.git
    git -C "$checkout_dir" fetch --depth 1 origin "$ref"
    git -C "$checkout_dir" checkout --detach FETCH_HEAD
  fi
  [[ "$(git -C "$checkout_dir" rev-parse HEAD)" == "$ref" ]] || { echo 'Commit mismatch.'; exit 1; }
  source_dir="$checkout_dir/pocket"
fi
python3 -m unittest discover -s "$source_dir" -p 'test_pocket.py' -q
carry_exports="${XI_POCKET_CARRY_EXPORTS:-$source_dir/../exports}"
if [[ -d "$carry_exports" ]]; then
  python3 - "$source_dir" "$data_dir" "$carry_exports" <<'PY'
import hashlib,pathlib,shutil,sys
sys.path.insert(0,sys.argv[1]);from server import COLLECTIONS
source=pathlib.Path(sys.argv[3]);target=pathlib.Path(sys.argv[2])/'exports';target.mkdir(exist_ok=True)
for name,(_,expected) in COLLECTIONS.items():
 src=source/(name+'.xi');raw=src.read_bytes()
 if hashlib.sha256(raw).hexdigest()!=expected:raise SystemExit('Carried export pin mismatch: '+name)
 dest=target/src.name
 if dest.exists() and dest.read_bytes()!=raw:raise SystemExit('Existing export differs; preserved without overwrite: '+name)
 if not dest.exists():shutil.copyfile(src,dest);dest.chmod(0o600)
print('Five actual carried collection files installed for owner-only access.')
PY
fi
if [[ -f "$phone_root/xi_phone_platform.db" ]]; then
  python3 - "$source_dir" "$data_dir" "$phone_root/xi_phone_platform.db" <<'PY'
from datetime import datetime,timezone
import os,pathlib,secrets,sqlite3,sys
sys.path.insert(0,sys.argv[1]);from server import Store
source=pathlib.Path(sys.argv[3]).resolve();directory=pathlib.Path(sys.argv[2]);backups=directory/'legacy-backups';backups.mkdir(mode=0o700,exist_ok=True)
target=backups/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+secrets.token_hex(3)+'.sqlite3')
old=sqlite3.connect(source.as_uri()+'?mode=ro',uri=True);copy=sqlite3.connect(target)
try:
 old.backup(copy)
 if copy.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise SystemExit('Legacy backup did not verify; existing platform preserved.')
finally:copy.close();old.close()
os.chmod(target,0o600)
store=Store(directory)
try:print('Preserved previous phone Room:',store.import_legacy(source))
finally:store.db.close()
PY
fi
if command -v termux-wake-lock >/dev/null 2>&1; then termux-wake-lock; fi
if ! python3 - <<'PY'
import json,urllib.request
try:
 with urllib.request.urlopen('http://127.0.0.1:7474/api/status',timeout=1) as r:
  assert json.load(r)['schema']=='xi.pocket.status.v1'
except Exception: raise SystemExit(1)
PY
then
  nohup python3 "$source_dir/service.py" --data "$data_dir" --port 7474 --tunnel quick > "$data_dir/supervisor.log" 2>&1 < /dev/null &
fi
python3 - <<'PY'
import json,time,urllib.request
for _ in range(15):
 try:
  with urllib.request.urlopen('http://127.0.0.1:7474/api/status',timeout=1) as r:
   assert json.load(r)['schema']=='xi.pocket.status.v1'
  print('Pocket server verified: http://127.0.0.1:7474');break
 except Exception: time.sleep(1)
else: raise SystemExit('Pocket did not become healthy. Existing platform left unchanged. Inspect pocket-data/server.log.')
PY
mkdir -p "$HOME/.termux/boot"
boot_file="$HOME/.termux/boot/xi-pocket"
{
  printf '#!/data/data/com.termux/files/usr/bin/bash\n'
  printf 'command -v termux-wake-lock >/dev/null && termux-wake-lock\n'
  printf 'exec python3 %q --data %q --port 7474 --tunnel quick >> %q 2>&1\n' "$source_dir/service.py" "$data_dir" "$data_dir/supervisor.log"
} > "$boot_file"
chmod 700 "$boot_file"
printf '\nOpen http://127.0.0.1:7474 and use the private credential in:\n%s\n' "$data_dir/owner-token"
printf '\nThe new authenticated tunnel address appears in:\n%s\n' "$data_dir/tunnel.log"
printf '\nYour previous :7472 platform and its database have not been changed.\n'
printf 'Termux:Boot must be installed and opened once for reboot startup.\n'
printf 'Set Termux battery use to Unrestricted in Android settings; a wake lock cannot guarantee survival.\n'
