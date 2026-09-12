#!/usr/bin/zsh
# Run only after the immutable Releases and official Pages index are deployed.
set -eu
if (( $# != 1 )); then
    print -u2 'Usage: accept-index.zsh <new-app-private-run-directory>'
    exit 2
fi
index_root=${1:A}
[[ ! -e $index_root ]] || { print -u2 'Use a new isolated directory'; exit 2; }
index_oo=$(command -v oo)
command -v binary-sign-tool >/dev/null
command -v clang >/dev/null
mkdir -p -- "$index_root/t" "$index_root/cli" "$index_root/packages"
export OHECO_ROOT="$index_root/installation with spaces"
export OHECO_INDEX_URL=${DOTNET_OHOS_INDEX_URL:-https://oheco.github.io/oheco-packages/index/v3/index.json}
export OHECO_NO_AUTO_UPDATE=1
export DOTNET_OHOS_TMPDIR="$index_root/t" TMPDIR="$index_root/t"
export DOTNET_CLI_HOME="$index_root/cli" NUGET_PACKAGES="$index_root/packages"
export DOTNET_CLI_TELEMETRY_OPTOUT=1 DOTNET_NOLOGO=1
export HTTP_PROXY=${DOTNET_OHOS_PROXY:-socks5://172.16.105.2:10808}
export HTTPS_PROXY=$HTTP_PROXY
export PATH="$OHECO_ROOT/bin:$PATH"
unset LD_LIBRARY_PATH DOTNET_ROOT DOTNET_ROOT_ARM64
index_sdk_version=10.0.401-ohos.1
index_runtime_version=10.0.12-ohos.1
index_run() {
    local index_label=$1
    shift
    print -r -- "RUN $index_label"
    if "$@" > "$index_root/$index_label.log" 2>&1; then
        print -r -- "PASS $index_label"
    else
        local index_rc=$?
        cat -- "$index_root/$index_label.log"
        return $index_rc
    fi
}
index_shutdown() {
    if [[ -x "$OHECO_ROOT/bin/dotnet" ]]; then
        "$OHECO_ROOT/bin/dotnet" build-server shutdown > "$index_root/server-shutdown.log" 2>&1 || true
    fi
}
trap index_shutdown EXIT
index_run update "$index_oo" update
index_run runtime-install "$index_oo" install dotnet-runtime
index_run sdk-install "$index_oo" install dotnet-sdk
index_run installed-list "$index_oo" list
[[ -d "$OHECO_ROOT/packages/dotnet-runtime/$index_runtime_version" ]]
[[ -d "$OHECO_ROOT/packages/dotnet-sdk/$index_sdk_version" ]]
index_run runtime-info "$OHECO_ROOT/bin/dotnet-runtime" --info
index_run runtime-version-entry "$OHECO_ROOT/bin/dotnet-runtime@$index_runtime_version" --info
index_run sdk-info "$OHECO_ROOT/bin/dotnet" --info
index_run sdk-version-entry "$OHECO_ROOT/bin/dotnet@$index_sdk_version" --version
[[ $(< "$index_root/sdk-version-entry.log") == 10.0.401 ]]

mkdir -- "$index_root/project with spaces"
cd -- "$index_root/project with spaces"
index_run new dotnet new console --name IndexProbe --output . --no-restore
cat > NuGet.Config <<'EOF'
<?xml version="1.0" encoding="utf-8"?>
<configuration><packageSources><clear /></packageSources></configuration>
EOF
print -r -- 'System.Console.WriteLine("formal index .NET 10 verified");' > Program.cs
index_run build dotnet build -c Release -p:RestoreConfigFile="$PWD/NuGet.Config" -p:NuGetAudit=false
index_run runtime-app dotnet-runtime bin/Release/net10.0/IndexProbe.dll
[[ $(< "$index_root/runtime-app.log") == 'formal index .NET 10 verified' ]]
index_run runtime-version-app "$OHECO_ROOT/bin/dotnet-runtime@$index_runtime_version" bin/Release/net10.0/IndexProbe.dll
[[ $(< "$index_root/runtime-version-app.log") == 'formal index .NET 10 verified' ]]
for index_mode in jit r2r aot; do
    index_options=(--self-contained true)
    [[ $index_mode != r2r ]] || index_options+=(-p:PublishReadyToRun=true)
    [[ $index_mode != aot ]] || index_options+=(-p:PublishAot=true)
    index_run "$index_mode-publish" "$OHECO_ROOT/bin/dotnet@$index_sdk_version" publish \
        -c Release -r openharmony-arm64 "${index_options[@]}" -o "$index_root/$index_mode output" \
        -p:RestoreConfigFile="$PWD/NuGet.Config" -p:NuGetAudit=false
    index_run "$index_mode-run" "$index_root/$index_mode output/IndexProbe"
    [[ $(< "$index_root/$index_mode-run.log") == 'formal index .NET 10 verified' ]]
done
index_shutdown
index_run sdk-remove "$index_oo" remove "dotnet-sdk@$index_sdk_version"
index_run runtime-remove "$index_oo" remove "dotnet-runtime@$index_runtime_version"
for index_command in dotnet "dotnet@$index_sdk_version" dotnet-runtime "dotnet-runtime@$index_runtime_version"; do
    [[ ! -e "$OHECO_ROOT/bin/$index_command" && ! -L "$OHECO_ROOT/bin/$index_command" ]]
done
[[ ! -d "$OHECO_ROOT/packages/dotnet-sdk/$index_sdk_version" ]]
[[ ! -d "$OHECO_ROOT/packages/dotnet-runtime/$index_runtime_version" ]]
index_run removed-list "$index_oo" list
print -r -- 'ALL OFFICIAL INDEX INSTALLATION CHECKS PASSED'
print -r -- "Logs: $index_root"
