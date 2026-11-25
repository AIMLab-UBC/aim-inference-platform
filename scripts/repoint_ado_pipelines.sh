#!/usr/bin/env bash
# Repoint the AI model pipelines in Azure DevOps (aimlabdev/cpathportal) from
# one GitHub owner to another, using a given GitHub service connection.
#
#   scripts/repoint_ado_pipelines.sh <service-connection-name> [--apply]
#
# Without --apply it only prints what would change. Defaults: FROM=pouya-codes,
# TO=AIMLab-UBC, RENAMES="extract_areas=aim-inference-platform" (space-separated
# old=new repo names; override any of them in the environment).
set -euo pipefail

CONN_NAME="${1:?usage: $0 <service-connection-name> [--apply]}"
APPLY="${2:-}"
FROM="${FROM:-pouya-codes}"
TO="${TO:-AIMLab-UBC}"
RENAMES="${RENAMES-extract_areas=aim-inference-platform}"
PROJECT="${ADO_PROJECT:-cpathportal}"
PIPELINES=(worker-base worker-pdac worker-hovernet worker-ec worker-deepliif tissue-api)

CONN_ID=$(az devops service-endpoint list --project "$PROJECT" \
  --query "[?name=='${CONN_NAME}'].id | [0]" -o tsv 2>/dev/null)
[[ -n "$CONN_ID" ]] || { echo "no service connection named ${CONN_NAME}" >&2; exit 1; }
echo "connection ${CONN_NAME} = ${CONN_ID}"

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

for name in "${PIPELINES[@]}"; do
  id=$(az pipelines show --project "$PROJECT" --name "$name" --query id -o tsv 2>/dev/null)
  az devops invoke --area build --resource definitions \
    --route-parameters project="$PROJECT" definitionId="$id" \
    --api-version 7.1 -o json >"$work/$name.json" 2>/dev/null

  FROM="$FROM" TO="$TO" RENAMES="$RENAMES" CONN_ID="$CONN_ID" python3 - "$work/$name.json" <<'PY'
import json, os, sys
path = sys.argv[1]
d = json.load(open(path))
src, dst, conn = os.environ["FROM"], os.environ["TO"], os.environ["CONN_ID"]
r = d["repository"]
renames = [pair.split("=", 1) for pair in os.environ.get("RENAMES", "").split()]

def swap(s):
    if not isinstance(s, str):
        return s
    s = s.replace(f"/{src}/", f"/{dst}/").replace(f"{src}/", f"{dst}/", 1)
    for old, new in renames:
        for tail in (".git", "/", ""):
            if f"{dst}/{old}{tail}" in s and (tail or s.endswith(f"{dst}/{old}")):
                s = s.replace(f"{dst}/{old}{tail}", f"{dst}/{new}{tail}")
                break
    return s
before = r["name"]
for k in ("id", "name", "url"):
    r[k] = swap(r[k])
for k, v in list(r["properties"].items()):
    r["properties"][k] = swap(v)
r["properties"]["connectedServiceId"] = conn
r["properties"]["manageWebhook"] = "true"
json.dump(d, open(path, "w"))
print(f"  {d['name']:<16} {before}  ->  {r['name']}")
PY

  if [[ "$APPLY" == "--apply" ]]; then
    az devops invoke --area build --resource definitions --http-method PUT \
      --route-parameters project="$PROJECT" definitionId="$id" \
      --in-file "$work/$name.json" --api-version 7.1 \
      --query "repository.{repo:name,conn:properties.connectedServiceId}" -o tsv 2>/dev/null
  fi
done
[[ "$APPLY" == "--apply" ]] || echo "(dry run; add --apply to save)"
