# .NET 10 for HarmonyOS PC ARM64

The adaptation branch is `ohos/10.0.12`, based on upstream `v10.0.12`.
It provides the CoreCLR JIT runtime, ReadyToRun support and NativeAOT
runtime/compiler packs. The companion [SDK](https://github.com/oheco/dotnet-sdk)
uses branch `ohos/10.0.401`.

The immutable [Runtime 10.0.12-ohos.1 release](https://github.com/oheco/dotnet-runtime/releases/tag/v10.0.12-ohos.1)
remains the base of both distributions. [SDK 10.0.401-ohos.2](https://github.com/oheco/dotnet-sdk/releases/tag/v10.0.401-ohos.2)
also includes ASP.NET Core 10.0.12; a standalone [ASP.NET Core runtime](https://github.com/oheco/dotnet-aspnetcore/releases/tag/v10.0.12-ohos.1)
is available from `oheco/dotnet-aspnetcore`, branch `ohos/10.0.12`.
The original SDK ohos.1 archive remains available and does not include ASP.NET.

Use `oo install dotnet-sdk` for development, `oo install aspnetcore-runtime`
for framework-dependent Web applications, or `oo install dotnet-runtime`
for ordinary framework-dependent managed applications. Each distribution
includes its required runtime libraries. Commands are `dotnet`,
`aspnetcore-runtime` and `dotnet-runtime`, respectively.

See [platform behavior and limitations](eng/openharmony/PORTING.md) and the
[build and acceptance helpers](eng/openharmony/README.md). Web-specific
build recipes, native acceptance and feature limits are maintained in the
[ASP.NET adaptation](https://github.com/oheco/dotnet-aspnetcore/tree/ohos/10.0.12/eng/openharmony).
GUI applications, mobile application packaging and workloads are outside this
port's scope. NativeAOT Web applications follow upstream Minimal API limits;
HTTP/3 needs a compatible MsQuic dependency, which is not bundled.
