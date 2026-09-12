using System.Diagnostics;
using System.Globalization;
using System.IO.MemoryMappedFiles;
using System.IO.Pipes;
using System.Net;
using System.Net.Http;
using System.Net.NetworkInformation;
using System.Net.Security;
using System.Net.Sockets;
using System.Runtime;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using System.Security.Authentication;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using System.Text;

if (args.Length == 2 && args[0] == "--mutex-child")
{
    try
    {
        using var mutex = Mutex.OpenExisting(args[1]);
        if (mutex.WaitOne(200))
        {
            mutex.ReleaseMutex();
            return 2;
        }
        Console.WriteLine("mutex blocked");
    }
    catch (WaitHandleCannotBeOpenedException) when (!RuntimeFeature.IsDynamicCodeSupported)
    {
        // Upstream .NET 10 Unix NativeAOT has a process-local named object table.
        Console.WriteLine("process-local mutex");
    }
    return 0;
}

bool expectAot = args.Contains("--expect-aot");
Check(RuntimeFeature.IsDynamicCodeSupported != expectAot, "JIT/AOT execution mode");
Console.WriteLine($"{RuntimeInformation.FrameworkDescription}; {RuntimeInformation.RuntimeIdentifier}; {RuntimeInformation.OSDescription}");
if (args.Contains("--expect-ohos"))
{
    Check(RuntimeInformation.RuntimeIdentifier == "openharmony-arm64", "independent OpenHarmony RID");
#pragma warning disable CA1418 // This port adds OpenHarmony to the runtime platform names.
    Check(OperatingSystem.IsOSPlatform("OPENHARMONY") && OperatingSystem.IsLinux(), "OpenHarmony platform and Unix compatibility");
#pragma warning restore CA1418
}
int localZoneArgument = Array.IndexOf(args, "--expect-local-timezone");
if (localZoneArgument >= 0)
{
    Check(localZoneArgument + 1 < args.Length && TimeZoneInfo.Local.Id == args[localZoneArgument + 1], "local timezone selection");
}
Console.WriteLine("鸿蒙 .NET 10 验收 — Unicode ✓");
string root = Path.Combine(Path.GetTempPath(), "dn-" + Guid.NewGuid().ToString("N")[..8]);
Directory.CreateDirectory(root);
try
{
    string spaced = Directory.CreateDirectory(Path.Combine(root, "目录 with spaces")).FullName;
    string path = Path.Combine(spaced, "text.txt");
    await File.WriteAllTextAsync(path, "你好 HarmonyOS");
    Check(await File.ReadAllTextAsync(path) == "你好 HarmonyOS", "Unicode and space paths");
    string copiedPath = Path.Combine(spaced, "copied.txt");
    File.Copy(path, copiedPath);
    Check(await File.ReadAllTextAsync(copiedPath) == "你好 HarmonyOS", "file copying");
    try
    {
        File.ReadAllText(Path.Combine(root, "missing"));
        throw new Exception("Missing file did not fail");
    }
    catch (FileNotFoundException) { Console.WriteLine("PASS missing-file error"); }

    string mappedPath = Path.Combine(spaced, "mapped.bin");
    using (var mapping = MemoryMappedFile.CreateFromFile(mappedPath, FileMode.Create, null, 4096))
    using (var view = mapping.CreateViewAccessor())
    {
        view.Write(128, 0x12345678);
        view.Flush();
        Check(view.ReadInt32(128) == 0x12345678, "file-backed memory mapping");
    }
    byte[] mappedBytes = File.ReadAllBytes(mappedPath);
    Check(BitConverter.ToInt32(mappedBytes, 128) == 0x12345678, "memory mapping persistence");
    using (var mapping = MemoryMappedFile.CreateNew(null, 4096))
    using (var view = mapping.CreateViewAccessor())
    {
        view.Write(0, 42);
        Check(view.ReadInt32(0) == 42, "anonymous memory mapping");
    }

    // Keep below Unix socket path limits even with a long app-private TMPDIR.
    string pipeName = "dn-" + Guid.NewGuid().ToString("N")[..16];
    using (var pipeServer = new NamedPipeServerStream(pipeName, PipeDirection.InOut, 1,
        PipeTransmissionMode.Byte, PipeOptions.Asynchronous))
    using (var pipeClient = new NamedPipeClientStream(".", pipeName, PipeDirection.InOut, PipeOptions.Asynchronous))
    using (var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(15)))
    {
        Task connected = pipeServer.WaitForConnectionAsync(timeout.Token);
        await pipeClient.ConnectAsync(timeout.Token);
        await connected;
        await pipeClient.WriteAsync(new byte[] { 42 }, timeout.Token);
        byte[] data = new byte[1];
        await pipeServer.ReadExactlyAsync(data, timeout.Token);
        Check(data[0] == 42, "asynchronous named pipe");
    }

    var chinese = CultureInfo.GetCultureInfo("zh-CN");
    Check(!string.IsNullOrWhiteSpace(chinese.DateTimeFormat.GetMonthName(1)), "ICU Chinese culture");
    Check("istanbul".ToUpper(CultureInfo.GetCultureInfo("tr-TR")) == "İSTANBUL", "ICU Turkish casing");
    Check(TimeZoneInfo.FindSystemTimeZoneById("Asia/Shanghai").BaseUtcOffset == TimeSpan.FromHours(8), "timezone data");
    var paris = TimeZoneInfo.FindSystemTimeZoneById("Europe/Paris");
    Check(paris.GetUtcOffset(new DateTime(2026, 1, 15, 0, 0, 0, DateTimeKind.Utc)) == TimeSpan.FromHours(1) &&
        paris.GetUtcOffset(new DateTime(2026, 7, 15, 0, 0, 0, DateTimeKind.Utc)) == TimeSpan.FromHours(2), "timezone daylight saving transitions");
    Check(TimeZoneInfo.GetSystemTimeZones().Count > 400, "system timezone enumeration");

    long sum = 0;
    Parallel.For(0, 128, i =>
    {
        var values = Enumerable.Range(0, 4096).Select(x => (long)x + i).ToArray();
        Interlocked.Add(ref sum, values.Sum());
    });
    long expected = Enumerable.Range(0, 128).Sum(i => 4096L * 4095 / 2 + 4096L * i);
    GC.Collect(2, GCCollectionMode.Forced, blocking: true, compacting: true);
    Check(sum == expected, "generics, thread pool and GC");

    using (var watcher = new FileSystemWatcher(spaced))
    {
        var changed = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        watcher.Created += (_, e) => { if (e.Name == "watch.txt") changed.TrySetResult(); };
        watcher.EnableRaisingEvents = true;
        await File.WriteAllTextAsync(Path.Combine(spaced, "watch.txt"), "watch");
        await changed.Task.WaitAsync(TimeSpan.FromSeconds(10));
        Console.WriteLine("PASS file watcher");
    }

    string mutexName = "oheco-dotnet-" + Guid.NewGuid().ToString("N");
    using (var mutex = new Mutex(initiallyOwned: true, mutexName))
    {
        try
        {
            using (var sameProcess = Mutex.OpenExisting(mutexName))
            {
                Check(sameProcess.WaitOne(0), "same-process named mutex");
                sameProcess.ReleaseMutex();
            }
            var info = new ProcessStartInfo(Environment.ProcessPath!)
            {
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                UseShellExecute = false
            };
            // Apphosts also report the managed DLL as argv[0]. Only the dotnet
            // muxer and corerun need that DLL passed again to start a child.
            string executableName = Path.GetFileNameWithoutExtension(Environment.ProcessPath!);
            if (executableName is "dotnet" or "corerun")
                info.ArgumentList.Add(Environment.GetCommandLineArgs()[0]);
            info.ArgumentList.Add("--mutex-child");
            info.ArgumentList.Add(mutexName);
            using Process child = Process.Start(info)!;
            // Stay on the owning thread until ReleaseMutex: named mutex ownership is thread-affine.
            if (!child.WaitForExit(15000))
            {
                child.Kill(entireProcessTree: true);
                child.WaitForExit();
                throw new TimeoutException("Child process did not exit");
            }
            string expectedOutput = expectAot ? "process-local mutex" : "mutex blocked";
            Check(child.ExitCode == 0 && child.StandardOutput.ReadToEnd().Contains(expectedOutput),
                (expectAot ? "NativeAOT process-local mutex behavior" : "cross-process named mutex") + ": " + child.StandardError.ReadToEnd());
        }
        finally { mutex.ReleaseMutex(); }
    }

    NetworkInterface[] interfaces = NetworkInterface.GetAllNetworkInterfaces();
    Check(interfaces.Length > 0, "network interface enumeration");
    foreach (NetworkInterface networkInterface in interfaces)
    {
        Check(networkInterface.Speed >= -1, "network interface link speed");
    }

    using (var listener = new Socket(AddressFamily.Unix, SocketType.Stream, ProtocolType.Unspecified))
    using (var client = new Socket(AddressFamily.Unix, SocketType.Stream, ProtocolType.Unspecified))
    {
        var endpoint = new UnixDomainSocketEndPoint(Path.Combine(root, "socket"));
        listener.Bind(endpoint);
        listener.Listen(1);
        await client.ConnectAsync(endpoint);
        using Socket server = await listener.AcceptAsync();
        await client.SendAsync(new byte[] { 42 });
        byte[] bytes = new byte[1];
        Check(await server.ReceiveAsync(bytes) == 1 && bytes[0] == 42, "Unix socket");
    }

    // Exercise .NET compatibility APIs backed by OpenSSL's legacy provider.
#pragma warning disable CA5350, CA5351
    foreach (Func<SymmetricAlgorithm> factory in new Func<SymmetricAlgorithm>[] { DES.Create, RC2.Create })
#pragma warning restore CA5350, CA5351
    {
        using SymmetricAlgorithm algorithm = factory();
        algorithm.GenerateKey();
        algorithm.GenerateIV();
        byte[] plaintext = [1, 2, 3, 4, 5];
        byte[] encrypted = algorithm.EncryptCbc(plaintext, algorithm.IV);
        Check(algorithm.DecryptCbc(encrypted, algorithm.IV).SequenceEqual(plaintext),
            algorithm.GetType().Name + " legacy provider roundtrip");
    }

    using RSA rsa = RSA.Create(2048);
    var request = new CertificateRequest("CN=localhost", rsa, HashAlgorithmName.SHA256, RSASignaturePadding.Pkcs1);
    request.CertificateExtensions.Add(new X509BasicConstraintsExtension(true, false, 0, true));
    var san = new SubjectAlternativeNameBuilder();
    san.AddDnsName("localhost");
    request.CertificateExtensions.Add(san.Build());
    using X509Certificate2 certificate = request.CreateSelfSigned(DateTimeOffset.UtcNow.AddMinutes(-1), DateTimeOffset.UtcNow.AddDays(1));
    byte[] payload = Encoding.UTF8.GetBytes("signed content");
    byte[] signature = rsa.SignData(payload, HashAlgorithmName.SHA256, RSASignaturePadding.Pkcs1);
    Check(rsa.VerifyData(payload, signature, HashAlgorithmName.SHA256, RSASignaturePadding.Pkcs1), "RSA signing");
    using var tcpListener = new TcpListener(IPAddress.Loopback, 0);
    tcpListener.Start();
    int port = ((IPEndPoint)tcpListener.LocalEndpoint).Port;
    Task serverTask = Task.Run(async () =>
    {
        using TcpClient accepted = await tcpListener.AcceptTcpClientAsync();
        using var ssl = new SslStream(accepted.GetStream());
        await ssl.AuthenticateAsServerAsync(certificate, false, SslProtocols.Tls12 | SslProtocols.Tls13, false);
        await ssl.WriteAsync(payload);
    });
    using (var client = new TcpClient())
    {
        await client.ConnectAsync(IPAddress.Loopback, port);
        using var ssl = new SslStream(client.GetStream());
        var policy = new X509ChainPolicy { TrustMode = X509ChainTrustMode.CustomRootTrust, RevocationMode = X509RevocationMode.NoCheck };
        policy.CustomTrustStore.Add(certificate);
        await ssl.AuthenticateAsClientAsync(new SslClientAuthenticationOptions { TargetHost = "localhost", CertificateChainPolicy = policy });
        byte[] data = new byte[payload.Length];
        await ssl.ReadExactlyAsync(data);
        Check(data.SequenceEqual(payload), "TLS with certificate validation");
    }
    await serverTask.WaitAsync(TimeSpan.FromSeconds(15));

    if (args.Contains("--expect-ohos"))
    {
        // Only create a local protocol token; these fixture credentials are
        // never sent to a server. OHOS has no GSSAPI/Kerberos native shim.
        using var ntlm = new NegotiateAuthentication(new NegotiateAuthenticationClientOptions
        {
            Package = "NTLM",
            Credential = new NetworkCredential("fixture-user", "fixture-password", "WORKGROUP"),
            TargetName = "HTTP/localhost"
        });
        byte[]? token = ntlm.GetOutgoingBlob(ReadOnlySpan<byte>.Empty, out var ntlmStatus);
        Check(ntlmStatus == NegotiateAuthenticationStatusCode.ContinueNeeded &&
            token is not null && token.AsSpan().StartsWith("NTLMSSP\0"u8), "managed NTLM client token");
        using var kerberos = new NegotiateAuthentication(new NegotiateAuthenticationClientOptions
        {
            Package = "Kerberos",
            Credential = new NetworkCredential("fixture-user", "fixture-password"),
            TargetName = "HTTP/localhost"
        });
        kerberos.GetOutgoingBlob(ReadOnlySpan<byte>.Empty, out var kerberosStatus);
        Check(kerberosStatus == NegotiateAuthenticationStatusCode.Unsupported, "Kerberos explicitly unsupported");
    }

    if (args.Contains("--network"))
    {
        using var http = new HttpClient { Timeout = TimeSpan.FromSeconds(60) };
        string index = await http.GetStringAsync("https://api.nuget.org/v3/index.json");
        Check(index.Contains("resources"), "HTTPS NuGet via configured proxy");
    }

    Console.WriteLine("ALL ACCEPTANCE CHECKS PASSED");
    return 0;
}
finally { Directory.Delete(root, recursive: true); }

static void Check(bool condition, string message)
{
    if (!condition) throw new Exception(message);
    Console.WriteLine("PASS " + message);
}
