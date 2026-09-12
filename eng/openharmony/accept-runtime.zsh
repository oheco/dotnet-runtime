#!/usr/bin/zsh
# The acceptance DLL directory is produced by building acceptance/Acceptance.csproj.
set -eu
if (( $# != 3 )); then
    print -u2 'Usage: accept-runtime.zsh <signed-runtime-root> <acceptance-dll-directory> <new-app-private-run-directory>'
    exit 2
fi
runtime_root=${1:A}
runtime_harness=${2:A}
runtime_run=${3:A}
[[ ! -e $runtime_run ]] || { print -u2 'Use a new isolated run directory'; exit 2; }
[[ -x "$runtime_root/bin/dotnet-runtime" && -f "$runtime_harness/Acceptance.dll" ]]
mkdir -p -- "$runtime_run/t" "$runtime_run/cli" "$runtime_run/app"
cp -- "$runtime_harness/Acceptance.dll" "$runtime_harness/Acceptance.deps.json" \
    "$runtime_harness/Acceptance.runtimeconfig.json" "$runtime_run/app/"
export DOTNET_OHOS_TMPDIR="$runtime_run/t" TMPDIR="$runtime_run/t"
export DOTNET_CLI_HOME="$runtime_run/cli" DOTNET_CLI_TELEMETRY_OPTOUT=1 DOTNET_NOLOGO=1
export HTTP_PROXY=${DOTNET_OHOS_PROXY:-socks5://172.16.105.2:10808}
export HTTPS_PROXY=$HTTP_PROXY
unset LD_LIBRARY_PATH DOTNET_ROOT DOTNET_ROOT_ARM64
"$runtime_root/bin/dotnet-runtime" --info > "$runtime_run/info.log" 2>&1
if "$runtime_root/bin/dotnet-runtime" "$runtime_run/app/Acceptance.dll" --expect-ohos --network \
    > "$runtime_run/acceptance.log" 2>&1; then
    cat -- "$runtime_run/info.log" "$runtime_run/acceptance.log"
    print -r -- 'ALL INSTALLED RUNTIME ACCEPTANCE CHECKS PASSED'
else
    runtime_rc=$?
    cat -- "$runtime_run/acceptance.log"
    exit $runtime_rc
fi
