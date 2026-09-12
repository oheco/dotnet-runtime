#!/usr/bin/env bash
# Refresh the generic NativeAOT build-integration package after a targets-only fix.
# Existing native compiler/runtime outputs keep their own recorded source provenance.
set -euo pipefail
integration_source=${1:?Usage: repack-aot-build-integration.sh built-source-directory new-log-file}
integration_log=${2:?Missing new log file}
integration_source=$(cd -- "$integration_source" && pwd)
[[ -d "$integration_source/artifacts/bin/coreclr" ]] || { echo 'Build the baseline runtime first' >&2; exit 2; }
[[ ! -e "$integration_log" ]] || { echo 'Use a new log file' >&2; exit 2; }
for integration_env in DOTNET_INSTALL_DIR NUGET_PACKAGES DOTNET_CLI_HOME DOTNET_OHOS_OFFLINE_FEED; do
    [[ -n ${!integration_env:-} ]] || { echo "Set $integration_env" >&2; exit 2; }
done
[[ -f "$DOTNET_OHOS_OFFLINE_FEED/NuGet.Config" ]] || { echo 'Missing fixed local feed' >&2; exit 2; }
mkdir -p -- "$(dirname -- "$integration_log")"
integration_log="$(cd -- "$(dirname -- "$integration_log")" && pwd)/$(basename -- "$integration_log")"
exec > "$integration_log" 2>&1
export DOTNET_CLI_TELEMETRY_OPTOUT=1 DOTNET_NOLOGO=1
export HTTP_PROXY=${DOTNET_OHOS_PROXY:-socks5://127.0.0.1:10808} HTTPS_PROXY=${DOTNET_OHOS_PROXY:-socks5://127.0.0.1:10808}
cd -- "$integration_source"
integration_stamp=${DOTNET_OHOS_BUILD_ID:-20260912.1}
integration_options=(-c Release /p:TargetOS=openharmony /p:TargetArchitecture=arm64
    /p:BuildArchitecture=arm64 /p:CrossBuild=true /p:UseBootstrap=true
    /p:UseSharedCompilation=false /p:NuGetAudit=false /m:2 /nr:false
    "/p:RestoreConfigFile=$DOTNET_OHOS_OFFLINE_FEED/NuGet.Config"
    /p:DotNetUseShippingVersions=true "/p:OfficialBuildId=$integration_stamp"
    /p:OfficialBuild=false /p:DotNetFinalVersionKind=release /p:PackageVersion=10.0.12)
printf 'Build integration source: '
git rev-parse HEAD
"$DOTNET_INSTALL_DIR/dotnet" build src/coreclr/nativeaot/BuildIntegration/BuildIntegration.proj "${integration_options[@]}"
# Preserve old archives alongside the log so incremental packing cannot retain them.
mkdir -- "$integration_log.previous-packages"
for integration_name in Microsoft.DotNet.ILCompiler.10.0.12.nupkg Microsoft.DotNet.ILCompiler.10.0.12.symbols.nupkg; do
    integration_archive="artifacts/packages/Release/Shipping/$integration_name"
    [[ ! -f $integration_archive ]] || mv -- "$integration_archive" "$integration_log.previous-packages/"
done
"$DOTNET_INSTALL_DIR/dotnet" pack src/installer/pkg/projects/Microsoft.DotNet.ILCompiler/Microsoft.DotNet.ILCompiler.pkgproj "${integration_options[@]}"
