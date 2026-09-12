#!/usr/bin/env bash
# Build a new runtime source checkout from prepared, fixed offline inputs.
set -euo pipefail
release_source=${1:?Usage: build-runtime-release.sh new-source-checkout new-log-directory}
release_logs=${2:?Missing log directory}
release_source=$(cd -- "$release_source" && pwd)
release_kit=$(cd -- "$(dirname -- "$0")" && pwd)
[[ ! -e "$release_source/artifacts" ]] || { echo 'Release source must have no artifacts directory' >&2; exit 2; }
[[ ! -e "$release_logs" ]] || { echo 'Release log directory must be new' >&2; exit 2; }
for release_env in OHOS_CROSS_NDK OHOS_DEP_PREFIX OHOS_HOST_PROBE_LOG_ROOT \
    DOTNET_INSTALL_DIR NUGET_PACKAGES DOTNET_CLI_HOME DOTNET_OHOS_OFFLINE_FEED; do
    [[ -n ${!release_env:-} ]] || { echo "Set $release_env to a prepared input/output directory" >&2; exit 2; }
done
mkdir -p -- "$release_logs"
release_logs=$(cd -- "$release_logs" && pwd)
export OHOS_CMAKE_TOOLCHAIN="$release_kit/ohos-toolchain.cmake"
export DOTNET_CLI_TELEMETRY_OPTOUT=1 DOTNET_NOLOGO=1
export HTTP_PROXY=${DOTNET_OHOS_PROXY:-socks5://127.0.0.1:10808}
export HTTPS_PROXY=$HTTP_PROXY
release_stamp=${DOTNET_OHOS_BUILD_ID:-20260912.1}
release_options=(/p:DotNetUseShippingVersions=true "/p:OfficialBuildId=$release_stamp"
    /p:OfficialBuild=false /p:DotNetFinalVersionKind=release /p:PackageVersion=10.0.12)
release_run() {
    local release_label=$1
    shift
    printf 'START %s\n' "$release_label"
    printf '%q ' "$@" > "$release_logs/$release_label.command"
    printf '\n' >> "$release_logs/$release_label.command"
    if "$@" > "$release_logs/$release_label.log" 2>&1; then
        printf 'PASS %s\n' "$release_label"
    else
        local release_rc=$?
        printf 'FAIL %s (exit %s); see %s\n' "$release_label" "$release_rc" "$release_logs/$release_label.log" >&2
        return "$release_rc"
    fi
}
release_subset() {
    local release_name=$1
    shift
    release_run "$release_name" bash "$release_kit/build-runtime-target.sh" \
        "$release_source" "$release_name" "${release_options[@]}" "$@"
}
release_subset bootstrap
release_subset clr.nativeaotruntime
release_subset clr.nativeaotlibs
release_subset clr.crossarchtools

# Build the projects required by the shipping compilers, without unrelated test
# or diagnostic tool projects. Each publish builds its normal project references.
cd -- "$release_source"
release_managed_options=(-c Release /p:TargetOS=openharmony /p:TargetArchitecture=arm64
    /p:BuildArchitecture=arm64 /p:CrossBuild=true /p:UseBootstrap=true
    /p:UseSharedCompilation=false /p:NuGetAudit=false /m:2 /nr:false
    "/p:RestoreConfigFile=$DOTNET_OHOS_OFFLINE_FEED/NuGet.Config" "${release_options[@]}")
for release_project in \
    src/coreclr/nativeaot/BuildIntegration/BuildIntegration.proj \
    src/coreclr/tools/aot/ILCompiler.Build.Tasks/ILCompiler.Build.Tasks.csproj; do
    release_label=$(basename -- "$release_project")
    release_run "$release_label" "$DOTNET_INSTALL_DIR/dotnet" build "$release_project" "${release_managed_options[@]}"
done
for release_project in \
    src/coreclr/tools/aot/ILCompiler/ILCompiler_inbuild.csproj \
    src/coreclr/tools/aot/crossgen2/crossgen2_inbuild.csproj \
    src/coreclr/tools/aot/ILCompiler/ILCompiler_publish.csproj \
    src/coreclr/tools/aot/crossgen2/crossgen2_publish.csproj; do
    release_label=$(basename -- "$release_project")
    release_run "$release_label" "$DOTNET_INSTALL_DIR/dotnet" publish "$release_project" "${release_managed_options[@]}"
done
release_subset clr.nativecorelib /p:UseBootstrap=true
release_subset packs.product -pack /p:UseBootstrap=true
printf 'Runtime packages built. SDK composition, native signing and acceptance remain required.\n'
