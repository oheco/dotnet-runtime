#!/usr/bin/env bash
# Cross-build the .NET 10 sources; CMake run probes execute on the OHOS host.
set -euo pipefail
port_work=$(cd -- "$(dirname -- "$0")" && pwd)
port_source=${1:?Usage: build-runtime-target.sh source-directory [subset] [MSBuild options...]}
port_subset=${2:-bootstrap}
if (($# >= 2)); then shift 2; else shift; fi

export OHOS_CROSS_NDK=${OHOS_CROSS_NDK:-/tmp/oheco-dotnet-ndk-verified}
export OHOS_DEP_PREFIX=${OHOS_DEP_PREFIX:-/tmp/oheco-dotnet-deps-verified/install}
export OHOS_CMAKE_TOOLCHAIN="$port_work/ohos-toolchain.cmake"
export DOTNET_INSTALL_DIR=${DOTNET_INSTALL_DIR:-/tmp/oheco-dotnet-linux-10.0.110}
export NUGET_PACKAGES=${NUGET_PACKAGES:-/tmp/oheco-dotnet-nuget}
export DOTNET_CLI_HOME=${DOTNET_CLI_HOME:-/tmp/oheco-dotnet-cli-home}
export DOTNET_CLI_TELEMETRY_OPTOUT=1
export HTTP_PROXY=${DOTNET_OHOS_PROXY:-socks5://127.0.0.1:10808}
export HTTPS_PROXY=$HTTP_PROXY

port_restore_options=()
if [[ -n ${DOTNET_OHOS_OFFLINE_FEED:-} ]]; then
    if [[ ! -f "$DOTNET_OHOS_OFFLINE_FEED/NuGet.Config" ]]; then
        printf 'Missing fixed local feed configuration: %s\n' "$DOTNET_OHOS_OFFLINE_FEED/NuGet.Config" >&2
        exit 1
    fi
    # Security advisory access needs a network; archive integrity and the input
    # inventory are verified separately before an offline build.
    port_restore_options+=("/p:RestoreConfigFile=$DOTNET_OHOS_OFFLINE_FEED/NuGet.Config" /p:NuGetAudit=false)
fi

for port_required in "$OHOS_CROSS_NDK/sysroot/usr/include/stdlib.h" \
    "$OHOS_DEP_PREFIX/lib/libcrypto.so.3" "$OHOS_DEP_PREFIX/lib/libicudata.so.78" \
    "$DOTNET_INSTALL_DIR/dotnet"; do
    if [[ ! -f "$port_required" ]]; then
        printf 'Missing prepared input: %s\n' "$port_required" >&2
        exit 1
    fi
done

cd -- "$port_source"
exec bash ./build.sh "$port_subset" -os openharmony -arch arm64 -cross \
    -c Release -ninja /p:StabilizePackageVersion=true \
    /p:BuildInParallel=true /m:2 /p:UseSharedCompilation=false \
    /p:WarningsNotAsErrors=NU1903 "${port_restore_options[@]}" "$@"
