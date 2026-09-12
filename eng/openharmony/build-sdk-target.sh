#!/usr/bin/env bash
# Build the SDK layout using fixed local packages and the source-built runtime.
set -euo pipefail
port_source=${1:?Usage: build-sdk-target.sh source-directory prepared-feed [MSBuild options...]}
port_feed=${2:?Missing prepared feed}
shift 2
port_feed=$(cd -- "$port_feed" && pwd)
port_source=$(cd -- "$port_source" && pwd)

python3 - "$port_feed" <<'PY'
import hashlib
import json
from pathlib import Path
import sys
root = Path(sys.argv[1])
records = json.loads((root / "manifest.json").read_text())
for item in records:
    archive = (root / item["path"]).resolve()
    if not archive.is_relative_to(root) or archive.stat().st_size != item["size"]:
        raise SystemExit("Invalid input path/size: " + item["path"])
    with archive.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest != item["sha256"]:
        raise SystemExit("Input hash mismatch: " + item["path"])
print(f"Verified {len(records)} fixed SDK inputs.")
PY

export DOTNET_INSTALL_DIR=${DOTNET_INSTALL_DIR:-/tmp/oheco-dotnet-linux-10.0.302}
export NUGET_PACKAGES=${NUGET_PACKAGES:-/tmp/oheco-dotnet-sdk-target-nuget}
export DOTNET_CLI_HOME=${DOTNET_CLI_HOME:-/tmp/oheco-dotnet-cli-home}
export DOTNET_CLI_TELEMETRY_OPTOUT=1
export HTTP_PROXY=${DOTNET_OHOS_PROXY:-socks5://127.0.0.1:10808}
export HTTPS_PROXY=$HTTP_PROXY

port_options=(/p:Configuration=Release /p:TargetRid=openharmony-arm64 /p:PortableTargetRid=openharmony-arm64
    /p:TargetArchitecture=arm64 /p:VersionSDKMinorPatch=1 /p:StabilizePackageVersion=true
    /p:MicrosoftNETCoreAppRefPackageVersion=10.0.12
    /p:MicrosoftNETCorePlatformsPackageVersion=10.0.12
    /p:MicrosoftNETILLinkTasksPackageVersion=10.0.12
    "/p:RestoreConfigFile=$port_feed/NuGet.Config" "/p:DownloadsFolder=$port_feed/downloads/"
    /p:NuGetAudit=false /p:BuildTestPackages=false /p:UseSharedCompilation=false /m:1 /nr:false)
cd -- "$port_source"
# Some layout projects are invoked dynamically and need the solution restore.
"$DOTNET_INSTALL_DIR/dotnet" restore sdk.slnx "${port_options[@]}" "$@"
# Upstream redist consumes these layouts produced by the solution build but
# does not reference their task projects. Build them before composing redist.
for port_project in \
    src/BlazorWasmSdk/Tasks/Microsoft.NET.Sdk.BlazorWebAssembly.Tasks.csproj \
    src/RazorSdk/Tasks/Microsoft.NET.Sdk.Razor.Tasks.csproj \
    src/StaticWebAssetsSdk/Tasks/Microsoft.NET.Sdk.StaticWebAssets.Tasks.csproj \
    src/WasmSdk/Tasks/Microsoft.NET.Sdk.WebAssembly.Tasks.csproj; do
    "$DOTNET_INSTALL_DIR/dotnet" build "$port_project" --no-restore "${port_options[@]}" "$@"
done
exec "$DOTNET_INSTALL_DIR/dotnet" build src/Layout/redist/redist.csproj --no-restore \
    -c Release "${port_options[@]}" "$@"
