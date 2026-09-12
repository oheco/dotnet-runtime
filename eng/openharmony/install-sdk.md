# .NET SDK 10.0.401 — HarmonyOS PC ARM64

本包包含 .NET 10 LTS runtime 10.0.12、SDK 10.0.401，以及本机
ReadyToRun 和 NativeAOT 编译器。目标 RID 为 `openharmony-arm64`。

构建时需要 PATH 中的 `binary-sign-tool`；NativeAOT 还需要鸿蒙 LLVM
工具链中的 Clang、LLD 和 llvm-objcopy。可通过 oheco 安装：

```sh
oo install ohos-sdk-toolchains
oo install ohos-sdk-native
```

使用本包的 `bin/dotnet` 入口；oheco 安装后可直接执行 `dotnet`：

```sh
dotnet --info
dotnet new console -o hello
cd hello
dotnet build
dotnet run
dotnet publish -c Release -r openharmony-arm64 --self-contained true -o out-jit
./out-jit/hello
dotnet publish -c Release -r openharmony-arm64 --self-contained true -p:PublishReadyToRun=true -o out-r2r
./out-r2r/hello
dotnet publish -c Release -r openharmony-arm64 -p:PublishAot=true -o out-aot
./out-aot/hello
```

依赖共享运行时的程序可用 `dotnet path/to/application.dll` 运行。若直接执行
其 apphost，需设置 `DOTNET_ROOT`（或 `DOTNET_ROOT_ARM64`）为本 SDK 的
安装根目录；自包含和 NativeAOT 发布目录无需该变量。

生成的本机文件自动签名。发布目录中的依赖库应与程序一起分发；随包提供
ICU、OpenSSL 和 C++ 运行库。NativeAOT 调试符号默认不压缩，以兼容当前宿主
LLVM；更换支持压缩的链接器后可显式设置 `CompressSymbols=true`。

入口脚本为当前终端应用选择可创建 Unix socket 的私有临时目录。
其他终端应用应将 `DOTNET_OHOS_TMPDIR` 设置为自身较短的私有可写路径。
NuGet 网络访问使用标准 `HTTP_PROXY` / `HTTPS_PROXY` 环境变量；包管理器
不会自动配置代理或安装上述工具依赖。

验证环境为 HarmonyOS PC ARM64 API 26、7.0.0.105、内核 1.13。
验收覆盖 C# 本机构建、运行、增量构建、并行 MSBuild、JIT、ReadyToRun、
NativeAOT 和 NuGet 包还原。GUI、workloads、ASP.NET Core 和移动应用打包
不在本包范围内。Kerberos/GSSAPI 未启用；NativeAOT 沿用上游动态代码、
反射及 Unix 命名互斥量的限制。

源码：<https://github.com/oheco/dotnet-sdk/tree/ohos/10.0.401>
及 <https://github.com/oheco/dotnet-runtime/tree/ohos/10.0.12>。
许可证和第三方声明见本包的 LICENSE、ThirdPartyNotices 及 licenses 目录。
