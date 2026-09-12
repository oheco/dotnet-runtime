#!/usr/bin/zsh
# Native end-to-end acceptance. Run against a signed, extracted SDK tree.
set -eu
if (( $# != 2 )); then
    print -u2 'Usage: accept-sdk.zsh <sdk-root> <new-app-private-run-directory>'
    exit 2
fi
accept_sdk=${1:A}
accept_root=${2:A}
accept_sources=${0:A:h}/acceptance
[[ ! -e $accept_root ]] || { print -u2 'Acceptance directory must be new'; exit 2; }
[[ -x $accept_sdk/bin/dotnet ]] || { print -u2 'Missing installed SDK launcher'; exit 2; }
command -v binary-sign-tool >/dev/null
command -v clang >/dev/null
command -v llvm-objcopy >/dev/null
mkdir -p -- "$accept_root/t" "$accept_root/cli" "$accept_root/packages"
export DOTNET_CLI_HOME="$accept_root/cli"
export NUGET_PACKAGES="$accept_root/packages"
export DOTNET_OHOS_TMPDIR="$accept_root/t"
export TMPDIR=$DOTNET_OHOS_TMPDIR
export DOTNET_ROOT=$accept_sdk DOTNET_ROOT_ARM64=$accept_sdk
export DOTNET_CLI_TELEMETRY_OPTOUT=1 DOTNET_NOLOGO=1
export HTTP_PROXY=${DOTNET_OHOS_PROXY:-socks5://172.16.105.2:10808}
export HTTPS_PROXY=$HTTP_PROXY
unset LD_LIBRARY_PATH
# The server uses the isolated TMPDIR, so shutdown affects this acceptance run.
trap '"$accept_sdk/bin/dotnet" build-server shutdown > "$accept_root/server-shutdown.log" 2>&1 || true' EXIT

accept_run() {
    local accept_label=$1
    shift
    print -r -- "RUN $accept_label"
    if "$@" > "$accept_root/$accept_label.log" 2>&1; then
        print -r -- "PASS $accept_label"
    else
        local accept_rc=$?
        cat -- "$accept_root/$accept_label.log"
        return $accept_rc
    fi
}

cat > "$accept_root/NuGet.Config" <<'EOF'
<?xml version="1.0" encoding="utf-8"?>
<configuration><packageSources><clear /></packageSources></configuration>
EOF
accept_run sdk-info "$accept_sdk/bin/dotnet" --info
[[ $("$accept_sdk/bin/dotnet" --version) == 10.0.401 ]]

# User workflow, including replacement of an ELF already executed by the host.
mkdir -- "$accept_root/project with spaces"
cd -- "$accept_root/project with spaces"
accept_run new "$accept_sdk/bin/dotnet" new console --name Incremental --output . --no-restore
print -r -- 'Console.WriteLine("incremental version 1");' > Program.cs
accept_run restore "$accept_sdk/bin/dotnet" restore --configfile "$accept_root/NuGet.Config" -p:NuGetAudit=false
accept_run build-1 "$accept_sdk/bin/dotnet" build --no-restore -c Release
accept_run run-1 "$accept_sdk/bin/dotnet" run --no-build -c Release
accept_run apphost-1 ./bin/Release/net10.0/Incremental
[[ $(< "$accept_root/apphost-1.log") == 'incremental version 1' ]]
print -r -- 'Console.WriteLine("incremental version 2");' > Program.cs
accept_run build-2 "$accept_sdk/bin/dotnet" build --no-restore -c Release
accept_run apphost-2 ./bin/Release/net10.0/Incremental
[[ $(< "$accept_root/apphost-2.log") == 'incremental version 2' ]]

for accept_revision in 1 2; do
    print -r -- "Console.WriteLine(\"publish version $accept_revision\");" > Program.cs
    accept_run "self-contained-publish-$accept_revision" "$accept_sdk/bin/dotnet" publish \
        -c Release -r openharmony-arm64 --self-contained true -o "$accept_root/self contained" \
        -p:RestoreConfigFile="$accept_root/NuGet.Config" -p:NuGetAudit=false
    accept_run "self-contained-run-$accept_revision" "$accept_root/self contained/Incremental"
    [[ $(< "$accept_root/self-contained-run-$accept_revision.log") == "publish version $accept_revision" ]]
    accept_run "aot-publish-$accept_revision" "$accept_sdk/bin/dotnet" publish \
        -c Release -r openharmony-arm64 -p:PublishAot=true -o "$accept_root/aot output" \
        -p:RestoreConfigFile="$accept_root/NuGet.Config" -p:NuGetAudit=false
    accept_run "aot-run-$accept_revision" "$accept_root/aot output/Incremental"
    [[ $(< "$accept_root/aot-run-$accept_revision.log") == "publish version $accept_revision" ]]
done

# Broad platform behavior under both CoreCLR and NativeAOT, using identical source.
mkdir -- "$accept_root/acceptance"
cp -- "$accept_sources/Acceptance.csproj" "$accept_sources/Program.cs" "$accept_root/acceptance/"
cd -- "$accept_root/acceptance"
accept_run acceptance-build "$accept_sdk/bin/dotnet" build -c Release \
    -p:RestoreConfigFile="$accept_root/NuGet.Config" -p:NuGetAudit=false
accept_run acceptance-jit "$accept_sdk/bin/dotnet" bin/Release/net10.0/Acceptance.dll --expect-ohos --network
accept_run acceptance-r2r-publish "$accept_sdk/bin/dotnet" publish -c Release \
    -r openharmony-arm64 --self-contained true -p:PublishReadyToRun=true -o "$accept_root/r2r" \
    -p:RestoreConfigFile="$accept_root/NuGet.Config" -p:NuGetAudit=false
accept_run acceptance-r2r "$accept_root/r2r/Acceptance" --expect-ohos
accept_run acceptance-aot-publish "$accept_sdk/bin/dotnet" publish -c Release \
    -r openharmony-arm64 -p:PublishAot=true -o "$accept_root/full aot" \
    -p:RestoreConfigFile="$accept_root/NuGet.Config" -p:NuGetAudit=false
accept_run acceptance-aot "$accept_root/full aot/Acceptance" --expect-ohos --expect-aot --network

# Exercise NuGet itself over the configured proxy, including extraction and use
# of a fixed managed package in a project independent of the AOT acceptance.
mkdir -- "$accept_root/nuget project"
cd -- "$accept_root/nuget project"
cat > NuGet.Config <<'EOF'
<?xml version="1.0" encoding="utf-8"?>
<configuration><packageSources><clear /><add key="nuget.org" value="https://api.nuget.org/v3/index.json" /></packageSources></configuration>
EOF
cat > NuGetProbe.csproj <<'EOF'
<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework></PropertyGroup><ItemGroup><PackageReference Include="Newtonsoft.Json" Version="13.0.3" /></ItemGroup></Project>
EOF
print -r -- 'if (Newtonsoft.Json.JsonConvert.SerializeObject(new[] { 1, 2, 3 }) != "[1,2,3]") throw new System.Exception("NuGet package failed"); System.Console.WriteLine("NuGet package ran successfully");' > Program.cs
accept_run nuget-restore "$accept_sdk/bin/dotnet" restore --configfile NuGet.Config -p:NuGetAudit=false
accept_run nuget-build "$accept_sdk/bin/dotnet" build --no-restore -c Release
accept_run nuget-run "$accept_sdk/bin/dotnet" run --no-build -c Release
print -r -- 'ALL NATIVE SDK ACCEPTANCE CHECKS PASSED'
print -r -- "Logs and isolated outputs: $accept_root"
