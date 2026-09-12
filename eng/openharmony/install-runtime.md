# .NET Runtime 10.0.12 LTS — HarmonyOS PC ARM64

本包运行 .NET 10 控制台应用，支持 CoreCLR JIT 和 ReadyToRun。
目标 RID 为 `openharmony-arm64`。ICU、OpenSSL 和 C++ 运行库已随包提供。

使用 `bin/dotnet-runtime` 入口；oheco 安装后可直接执行：

```sh
dotnet-runtime --info
dotnet-runtime path/to/application.dll
```

构建应用或进行 NativeAOT 发布请安装配套 `dotnet-sdk` 包，其命令为 `dotnet`。
本运行时包无需安装编译器或签名工具。解压迁移时保持包内目录结构及执行权限。

入口脚本为当前终端应用选择可创建 Unix socket 的私有临时目录。
其他终端应用应将 `DOTNET_OHOS_TMPDIR` 设置为自身较短的私有可写路径。
网络代理可通过标准 `HTTP_PROXY` / `HTTPS_PROXY` 环境变量配置。

验证环境为 HarmonyOS PC ARM64 API 26、7.0.0.105、内核 1.13。
验证涵盖 Unicode、文件、管道、内存映射、ICU、时区、线程、GC、进程、
互斥量、网络接口、Unix socket、加密和证书验证 TLS。
GUI、ASP.NET Core、Windows Desktop 和移动应用打包不在本包范围内；
Kerberos/GSSAPI 未启用。

源码：<https://github.com/oheco/dotnet-runtime/tree/ohos/10.0.12>。
许可证和第三方声明见本包的 LICENSE、ThirdPartyNotices 及 licenses 目录。
