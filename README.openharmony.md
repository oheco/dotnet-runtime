# .NET 10 for HarmonyOS PC ARM64

The adaptation branch is `ohos/10.0.12`, based on upstream `v10.0.12`.
The companion SDK is [oheco/dotnet-sdk](https://github.com/oheco/dotnet-sdk),
branch `ohos/10.0.401`, based on upstream `v10.0.401`.

This port provides the CoreCLR JIT runtime, ReadyToRun support, NativeAOT
runtime/compiler packs and the command-line SDK. GUI applications, mobile
application packaging, workloads and ASP.NET Core are outside its scope.

See [platform behavior and limitations](eng/openharmony/PORTING.md) and the
[build and acceptance helpers](eng/openharmony/README.md). These notes currently
describe development validation. Release publication and formal package-index
installation have not yet completed.
