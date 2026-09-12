#!/usr/bin/env bash
# Compose a fresh, release-stamped SDK from a verified runtime/MSBuild feed.
set -euo pipefail
release_source=${1:?Usage: build-sdk-release.sh source-directory prepared-feed new-log-file}
release_feed=${2:?Missing prepared feed}
release_log=${3:?Missing log file}
release_source=$(cd -- "$release_source" && pwd)
release_kit=$(cd -- "$(dirname -- "$0")" && pwd)
[[ ! -e "$release_source/artifacts" ]] || { echo 'Use a fresh SDK source checkout' >&2; exit 2; }
[[ ! -e "$release_log" ]] || { echo 'Use a new log file' >&2; exit 2; }
: "${DOTNET_INSTALL_DIR:?Set the fixed Linux SDK 10.0.302 directory}"
: "${NUGET_PACKAGES:?Set an isolated cache seeded from the verified feed}"
: "${DOTNET_CLI_HOME:?Set an isolated CLI home}"
[[ -d "$DOTNET_INSTALL_DIR/sdk/10.0.302" ]] || { echo 'Missing fixed SDK 10.0.302' >&2; exit 2; }
release_commit=$(git -C "$release_source" rev-parse HEAD)
release_stamp=${DOTNET_OHOS_BUILD_ID:-20260912.1}
mkdir -p -- "$(dirname -- "$release_log")"
exec bash "$release_kit/build-sdk-target.sh" "$release_source" "$release_feed" \
    /p:DotNetUseShippingVersions=true "/p:OfficialBuildId=$release_stamp" \
    /p:OfficialBuild=false /p:DotNetFinalVersionKind=release \
    "/p:SourceRevisionId=$release_commit" "/p:RepositoryCommit=$release_commit" \
    > "$release_log" 2>&1
