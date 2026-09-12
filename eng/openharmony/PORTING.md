# .NET 10 on HarmonyOS PC ARM64

This port targets command-line .NET development on the tested HarmonyOS PC
environment. Its public runtime identifier is `openharmony-arm64`.

The runtime baseline is `dotnet/runtime` v10.0.12
(`4271d88e0aebf3d04f188f1334c2220d80555ef6`); the SDK baseline is
`dotnet/sdk` v10.0.401 (`32593ca81f8aae7b0d41c1a7198529c3365106b8`).
Distribution revisions use `10.0.12-ohos.N` and `10.0.401-ohos.N` while
the framework and SDK retain their upstream .NET version numbers.

## Platform decisions

* The native runtime uses OpenHarmony SDK headers, libraries and CRT objects.
  CMake executes configuration probes on the actual host. Linux configuration
  results are not substituted for target probe results.
* CoreCLR, NativeAOT and the managed libraries use the existing Unix/Linux
  implementations where their APIs match. `OperatingSystem.IsOSPlatform`
  recognizes `OPENHARMONY`; `OperatingSystem.IsLinux()` also returns true for
  .NET libraries that use this check to select Unix behavior.
* The RID graph falls back to Unix assets, without advertising compatibility
  with glibc or generic Linux native packages. A third-party package containing
  only a Linux ELF library needs its own OpenHarmony port.
* CoreCLR disables its file-backed W^X allocation mode on this target. JIT uses
  anonymous executable memory supported by the tested host. Managed PE files
  cannot be mapped executable, so the runtime selects its existing loader that
  copies PE sections into anonymous memory. ReadyToRun code uses that loader.
  These behaviors require native acceptance on each supported host class.
* System timezone discovery reads the OpenHarmony parameter service and the
  indexed `/system/etc/zoneinfo/tzdata` file. OpenHarmony's index entries are
  48 bytes; Android's are 52 bytes. Explicit `TZ` remains authoritative.
* OpenSSL 3.5.8 and ICU 78.3 ship alongside the framework. OpenSSL uses its
  upstream `no-module` option to retain the embedded legacy provider for .NET
  DES/RC2 APIs. No module resolves through a temporary build prefix. ICU's data
  library retains the OpenHarmony CRT/platform note. Native ICU/OpenSSL shims
  resolve bundled libraries relative to their own module on OpenHarmony, and
  dependency ELF libraries carry an ORIGIN RUNPATH. This supports nested SDK
  and shared-framework layouts without LD_LIBRARY_PATH.
* Negotiate authentication uses the upstream managed NTLM implementation.
  GSSAPI/Kerberos and NUMA integration are not enabled in this port.

## Native tools and filesystem behavior

The shipping ILC and crossgen2 must be self-contained OpenHarmony publishes.
The Linux compilers built under the runtime's `arm64/` directory are build
inputs only. Compiler files are individually signed; their runtime is not
hidden inside a single-file bundle.

The host seals executed ELF inodes against later writes, including after a
process exits. The SDK prepares replacement inodes before its normal native
output copy steps and signs outputs after the last build/publish replacement.
Unchanged outputs retain the normal incremental copy behavior. Managed PE
assemblies, relocatable object files and detached symbols are not signed by
this task. Signing a detached debug file would invalidate its debuglink CRC.

`binary-sign-tool` from the native SDK toolchains must be on the host PATH for
SDK build/publish. NativeAOT also needs the host LLVM compiler, linker and
binary utilities. The standalone runtime has no compiler dependency.

Unix sockets need an application-private writable directory on the tested
host. The installed launcher supplies a private default for the host's known
unusable temporary-directory defaults. `DOTNET_OHOS_TMPDIR` overrides it;
other explicitly supplied `TMPDIR` values remain honored. Long temporary
paths can exceed the Unix domain socket path limit.

The shared filesystem exposes different mode bits to Linux and HarmonyOS.
Release archive modes are normalized explicitly, while signed bytes remain
unchanged. Native extraction, relocation and execution are required checks.

## Acceptance and limits

The full acceptance harness exercises Unicode and spaced paths, ordinary
file errors, file copying, memory-mapped files, asynchronous pipes, ICU,
timezone enumeration/DST, generics, threads, compacting GC, file watching,
child processes, named mutexes, network interfaces, Unix sockets, RSA,
legacy symmetric algorithms, validated TLS and proxied HTTPS to NuGet.
It runs under both CoreCLR and NativeAOT.

On Unix, upstream NativeAOT named mutexes are process-local. The harness
checks that behavior separately from CoreCLR cross-process mutexes.
NativeAOT retains upstream restrictions on dynamic code generation and
reflection; successful compilation of arbitrary .NET packages is not implied.

`accept-sdk.zsh` additionally checks project creation, restore, build/run,
execution of apphosts followed by source edits and rebuilds, repeated
self-contained/AOT publish after execution, and ReadyToRun publish.
It uses isolated CLI, NuGet and temporary directories.

GUI applications, workloads, ASP.NET Core and Windows Desktop runtime packs
are outside this delivery. Mobile application sandbox support is not inferred
from HarmonyOS PC validation.

## Current validation status

The development host is HarmonyOS PC ARM64, API 26, build 7.0.0.105,
kernel 1.13. Signed native JIT, NativeAOT and ReadyToRun probes pass, including
the specific timezone and memory-mapping adaptations. Complete CoreCLR framework acceptance and native ILC/linker execution also
pass. The development SDK also passed complete native acceptance, including
parallel MSBuild, repeated self-contained/AOT publication, JIT/R2R/AOT platform
behavior and a real proxied NuGet restore/build/run. MSBuild's target-only pipe
fix uses the configured private temporary directory. NativeAOT publishes carry
their ICU/OpenSSL dependencies and use uncompressed symbols with host LLVM.
Clean offline reproduction, release publication and formal catalogue
installation remain pending. This document is not a release
acceptance report; consult the final release's recorded checks and hashes.
