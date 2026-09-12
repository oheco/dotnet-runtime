# OpenHarmony build and acceptance kit

The source already contains the platform adaptation. These helpers use the
normal runtime/SDK build graphs and record the extra target inputs. Release build inputs are pinned by archive hashes and source commits.
Consult each Release for its build provenance and native acceptance records.

## Build environment and inputs

The current build machine is Linux ARM64 with Bash, Python 3.11+, Git,
Clang/LLD/LLVM tools 17, CMake 3.27+, Ninja, Make, Perl, tar and curl.
The HarmonyOS PC host needs zsh, its LLVM tools and `binary-sign-tool` on PATH.
Configuration executables are signed and run on that real host, using `zshc`.
`run-on-host.py` requires a shared log directory and these settings when the
default workspace mapping does not apply:

```sh
export OHOS_ZSHC=/path/to/zshc
export OHOS_LINUX_SHARED_ROOT=/mnt/linux_share
export OHOS_HOST_SHARED_ROOT=/storage/Users/currentUser/dev
export OHOS_HOST_PROBE_LOG_ROOT=/mnt/linux_share/ohos/build-logs/dotnet-probes
```

`base-inputs.json` fixes SDK/dependency archive URLs, versions, sizes, hashes
and licenses. Downloading is an explicit preparation phase:

```sh
export DOTNET_OHOS_DOWNLOADS=/path/to/fixed-downloads
export DOTNET_OHOS_PROXY=socks5h://127.0.0.1:10808
python3 fetch-inputs.py
python3 verify-inputs.py
python3 prepare-ndk.py /path/to/new-ohos-ndk
```

`fetch-inputs.py` never falls back to a direct connection. Build tools that use
.NET's proxy support take `socks5://` instead of curl's `socks5h://` spelling.
Set `DOTNET_OHOS_PROXY` accordingly before using the build shell helpers.

Extract the fixed Linux .NET SDK archives to separate bootstrap directories.
Runtime builds use 10.0.110; SDK builds use 10.0.302. Run
`prepare-tool-runtimes.py <sdk-bootstrap-root>` to install the pinned 6–9
frameworks needed by upstream SDK build/test tooling. They are build inputs
and are excluded from the target product.
The SDK's vendored MSBuild dependency uses the separately fixed 10.0.300 SDK.

`nuget-inputs-current.json` records the 699 captured upstream NuGet inputs
and their licenses. Fetch them as a separate preparation step through the configured proxy, then
verify and stage the cache without network access:

```sh
python3 fetch-nuget-inputs.py nuget-inputs-current.json /path/to/prepared-nuget-cache
python3 nuget-inputs.py stage /path/to/prepared-nuget-cache \
  nuget-inputs-current.json --destination /path/to/local-feed
```

The manifest is an inventory of build dependencies, not an inventory of files
shipped in the SDK. Keep the bootstrap input feed separate from target-built
packages. NuGet caches containing an earlier locally built package of the same
version must also be kept separate from a new build's cache.

Before the first source build, populate the isolated `NUGET_PACKAGES` cache
with `seed-nuget-cache.py <bootstrap-dotnet> <input-manifest> <verified-feed>
<new-restore-project-directory> <new-log-file>`. Set `DOTNET_CLI_HOME` too.
This verifies package archives again and restores only from the local feed,
including the Arcade SDK that MSBuild resolves before normal project restore.

## Build order

1. Set `OHOS_CROSS_NDK`, `OHOS_DEP_PREFIX` and `DOTNET_OHOS_DEPS_BUILD` to new
   prepared/build directories. Run `build-deps.sh openssl` and
   `build-deps.sh icu`. Both dependency libraries retain adjacent-library
   RUNPATHs; ICU data retains the target CRT platform note.
2. Set `DOTNET_INSTALL_DIR`, `NUGET_PACKAGES`, `DOTNET_CLI_HOME` and
   `DOTNET_OHOS_OFFLINE_FEED`. `build-runtime-target.sh <runtime-source> <subset>`
   invokes the target build with the real-host CMake probe runner.
3. Build `bootstrap`, target NativeAOT runtime/libraries and Linux-host cross
   tools. Build the in-build compilers and target compiler publishes using
   `UseBootstrap=true`, then generate the ReadyToRun CoreLib and `packs.product`.
4. After any native runtime change, refresh `libs.pretest`, then
   `Build.proj /t:SetupBootstrapLayout /p:Subset=bootstrap`, then the target ILC
   and crossgen2 publishes. Recreate compiler archives before assembling a new
   SDK feed. Incremental pack timestamps can otherwise retain an old archive.
5. `prepare-sdk-feed.py --bootstrap-feed <feed> --runtime-packages
   <runtime-artifacts/packages/Release> --runtime-archive <combined-runtime-tar>
   --output <new-sdk-feed>` verifies the runtime/compiler CoreCLR hashes and
   combines the nine source-built target packs with fixed build inputs.
6. Build the SDK fork's vendored MSBuild dependency using its separate fixed
   manifest/feed and `eng/openharmony/build-msbuild.sh`. Its
   `merge-msbuild-feed.py` creates a new SDK feed containing the six patched
   MSBuild packages. See the SDK fork's README for commands and provenance.
7. With the SDK bootstrap selected and the merged feed prepared, run
   `build-sdk-target.sh <sdk-source> <new-sdk-feed>`. The completed layout is
   `artifacts/bin/redist/Release/dotnet-installer` in the SDK source tree.

For a new runtime checkout, `build-runtime-release.sh <source> <new-log-directory>`
executes the complete release sequence, including separate ILLink and RID graph
packing. For a fresh SDK checkout and merged feed, use
`build-sdk-release.sh <source> <feed> <new-log-file>`. The wrappers pin the build
stamp and shipping versions; the SDK wrapper records its actual Git commit.
Both require explicit bootstrap/cache/CLI-home settings and prepared inputs.
The SDK fork's MSBuild input manifest can also be fetched using
`fetch-nuget-inputs.py` before its separate offline dependency build.

For the first released SDK, runtime/compiler binaries come from runtime commit
`033589b2981f30e657b283f54a3697c5d124fc3b`. The generic NativeAOT MSBuild package
also includes the library-path quoting fix from
`8b7bf48c679f9e24078a693b84ce8f820f3c7da5`. To reproduce those inputs, build the
baseline first, advance that checkout to the integration-fix commit, then run
`repack-aot-build-integration.sh <built-runtime-source> <new-log-file>` with the
same fixed runtime bootstrap/cache/feed settings. It refreshes the integration
files and generic package while retaining the already built native binaries.
Prepare a new SDK feed and empty cache afterward. BUILDINFO records the binary
and build-integration commits separately. New ports may build all components
from one later source commit instead.

## Native acceptance and packaging

`stage-install.py <layout> <new-shared-directory> --kind sdk` copies a complete
SDK layout, adds its launcher and verifies/copies dependency notices. Use
`--kind runtime` for an extracted combined runtime archive. Wait for this
operation to finish before signing.

On the host, run `zsh sign-tree.zsh <staged-tree> <new-sign-log-directory>`,
then `chmod +x <staged-tree>/bin/dotnet`. For the runtime-only package the
launcher name is `dotnet-runtime`.

`zsh accept-sdk.zsh <signed-sdk> <new-app-private-directory>` checks native
project creation, restore/build/run, repeated apphost replacement,
self-contained/ReadyToRun/NativeAOT publish and broad runtime behavior. Its
network checks use the host proxy (`socks5://172.16.105.2:10808` by default).

`verify-elf-layout.py <tree>` audits signatures, architecture and accidental
foreign native binaries. Before signing, use `--allow-unsigned`.
`package-tree.py --help` describes archive creation: execution modes are
normalized while signed bytes and contained links are preserved. GNU tar
long-link records are used because the validated host tar truncates PAX
`linkpath` metadata. The extracted
archive must also be tested from a relocated path on the native host.

`accept-runtime.zsh <signed-runtime> <built-acceptance-dll-directory>
<new-app-private-directory>` validates the standalone runtime using the same
managed acceptance application. The package itself does not contain test files.

After immutable Release publication and Pages deployment, run
`accept-index.zsh <new-app-private-directory>` on the host with oo 0.5.0 or
later. It uses the official v3 index; `DOTNET_OHOS_INDEX_URL` can select the
official v2 compatibility index for older clients. It downloads both
packages through the official index, tests ordinary and versioned command links,
JIT/R2R/AOT publication, a path containing spaces, and uninstallation.

The SDK owns the `dotnet` command; the standalone runtime owns `dotnet-runtime`.
Both launch their own root muxer and establish a usable application-private
temporary directory. Set `DOTNET_OHOS_TMPDIR` when the host's application layout
differs. Consult [PORTING.md](PORTING.md) for the tested host and API limits.
