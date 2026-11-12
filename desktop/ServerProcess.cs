using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Net.Http;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading.Tasks;

namespace MLogger.Desktop
{
    internal sealed class StartupException : Exception
    {
        public bool PythonMissing { get; }

        public StartupException(string message, bool pythonMissing = false) : base(message)
        {
            PythonMissing = pythonMissing;
        }
    }

    internal sealed class ServerProcess : IDisposable
    {
        public const int Port = 8765;
        public static readonly string Url = "http://127.0.0.1:" + Port;

        private static readonly HttpClient Http = new HttpClient { Timeout = TimeSpan.FromSeconds(2) };
        private static readonly Regex PingPattern = new Regex("\"app\"\\s*:\\s*\"mlogger\"", RegexOptions.Compiled);

        private readonly Queue<string> output = new Queue<string>();
        private Process process;
        private IntPtr job = IntPtr.Zero;

        public bool Owned { get; private set; }
        public string DataDir { get; private set; }

        public static string LocalDir
        {
            get
            {
                string dir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "MLogger");
                Directory.CreateDirectory(dir);
                return dir;
            }
        }

        public async Task StartAsync()
        {
            string root = FindRoot(out bool packaged);
            DataDir = ResolveDataDir(root, packaged);

            if (await PingAsync())
            {
                Owned = false;
                return;
            }
            if (root == null) throw new StartupException(Strings.NoAppFiles);

            string python = await Task.Run(() => FindPython());
            if (python == null) throw new StartupException(Strings.NoPython, true);

            Directory.CreateDirectory(DataDir);
            var info = new ProcessStartInfo
            {
                FileName = python,
                Arguments = "\"" + Path.Combine(root, "start.py") + "\" --no-browser --port " + Port + " --data \"" + DataDir + "\"",
                WorkingDirectory = root,
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                StandardOutputEncoding = Encoding.UTF8,
                StandardErrorEncoding = Encoding.UTF8,
            };
            info.EnvironmentVariables["PYTHONUTF8"] = "1";
            info.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8";
            info.EnvironmentVariables["PYTHONUNBUFFERED"] = "1";
            info.EnvironmentVariables["MLOGGER_LANG"] = Strings.Language;

            lock (output) output.Clear();
            process = new Process { StartInfo = info };
            process.OutputDataReceived += (s, e) => Remember(e.Data);
            process.ErrorDataReceived += (s, e) => Remember(e.Data);
            process.Start();
            Owned = true;
            AttachToJob(process);
            process.BeginOutputReadLine();
            process.BeginErrorReadLine();

            var watch = Stopwatch.StartNew();
            while (watch.Elapsed < TimeSpan.FromSeconds(30))
            {
                if (process.HasExited)
                {
                    await Task.Delay(150);
                    throw new StartupException(Strings.ServerExited + Environment.NewLine + Environment.NewLine + Tail());
                }
                if (await PingAsync()) return;
                await Task.Delay(200);
            }
            Stop();
            throw new StartupException(Strings.ServerTimeout + Environment.NewLine + Environment.NewLine + Tail());
        }

        public static async Task<bool> PingAsync()
        {
            try
            {
                string body = await Http.GetStringAsync(Url + "/api/v1/ping");
                return PingPattern.IsMatch(body);
            }
            catch (Exception)
            {
                return false;
            }
        }

        private void Remember(string line)
        {
            if (string.IsNullOrWhiteSpace(line)) return;
            lock (output)
            {
                output.Enqueue(line.TrimEnd());
                while (output.Count > 12) output.Dequeue();
            }
        }

        private string Tail()
        {
            lock (output) return string.Join(Environment.NewLine, output);
        }

        private static string FindRoot(out bool packaged)
        {
            string exeDir = AppDomain.CurrentDomain.BaseDirectory;
            string bundled = Path.Combine(exeDir, "app");
            if (File.Exists(Path.Combine(bundled, "start.py")))
            {
                packaged = true;
                return bundled;
            }
            packaged = false;
            var dir = new DirectoryInfo(exeDir);
            for (int depth = 0; dir != null && depth < 7; depth++, dir = dir.Parent)
            {
                if (File.Exists(Path.Combine(dir.FullName, "start.py")) && Directory.Exists(Path.Combine(dir.FullName, "server")))
                    return dir.FullName;
            }
            return null;
        }

        private static string ResolveDataDir(string root, bool packaged)
        {
            string forced = Environment.GetEnvironmentVariable("MLOGGER_DATA");
            if (!string.IsNullOrWhiteSpace(forced)) return forced;
            if (root != null && !packaged) return Path.Combine(root, "data");
            return Path.Combine(LocalDir, "data");
        }

        private static string FindPython()
        {
            string bundled = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "python", "python.exe");
            if (File.Exists(bundled)) return bundled;
            return Probe("py", "-3") ?? Probe("python", "") ?? Probe("python3", "");
        }

        private static string Probe(string command, string prefix)
        {
            const string code = "import sys; print(sys.executable if sys.version_info >= (3, 9) else '')";
            try
            {
                var info = new ProcessStartInfo
                {
                    FileName = command,
                    Arguments = (prefix + " -c \"" + code + "\"").Trim(),
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true,
                    StandardOutputEncoding = Encoding.UTF8,
                };
                info.EnvironmentVariables["PYTHONUTF8"] = "1";
                using (var probe = Process.Start(info))
                {
                    Task<string> reading = probe.StandardOutput.ReadToEndAsync();
                    probe.ErrorDataReceived += (s, e) => { };
                    probe.BeginErrorReadLine();
                    if (!probe.WaitForExit(8000))
                    {
                        try { probe.Kill(); } catch (Exception) { }
                        return null;
                    }
                    string path = reading.Result.Trim();
                    return probe.ExitCode == 0 && path.Length > 0 && File.Exists(path) ? path : null;
                }
            }
            catch (Exception)
            {
                return null;
            }
        }

        public void Stop()
        {
            if (!Owned) return;
            Owned = false;
            if (job != IntPtr.Zero)
            {
                TerminateJobObject(job, 0);
                CloseHandle(job);
                job = IntPtr.Zero;
            }
            try
            {
                if (process != null && !process.HasExited) process.Kill();
            }
            catch (Exception)
            {
            }
            process?.Dispose();
            process = null;
        }

        public void Dispose()
        {
            Stop();
        }

        private void AttachToJob(Process child)
        {
            job = CreateJobObject(IntPtr.Zero, null);
            if (job == IntPtr.Zero) return;
            var limits = new JOBOBJECT_EXTENDED_LIMIT_INFORMATION();
            limits.BasicLimitInformation.LimitFlags = KillOnJobClose;
            int size = Marshal.SizeOf(typeof(JOBOBJECT_EXTENDED_LIMIT_INFORMATION));
            IntPtr buffer = Marshal.AllocHGlobal(size);
            try
            {
                Marshal.StructureToPtr(limits, buffer, false);
                if (!SetInformationJobObject(job, ExtendedLimitInformation, buffer, (uint)size) || !AssignProcessToJobObject(job, child.Handle))
                {
                    CloseHandle(job);
                    job = IntPtr.Zero;
                }
            }
            finally
            {
                Marshal.FreeHGlobal(buffer);
            }
        }

        private const int ExtendedLimitInformation = 9;
        private const uint KillOnJobClose = 0x2000;

        [StructLayout(LayoutKind.Sequential)]
        private struct JOBOBJECT_BASIC_LIMIT_INFORMATION
        {
            public long PerProcessUserTimeLimit;
            public long PerJobUserTimeLimit;
            public uint LimitFlags;
            public UIntPtr MinimumWorkingSetSize;
            public UIntPtr MaximumWorkingSetSize;
            public uint ActiveProcessLimit;
            public UIntPtr Affinity;
            public uint PriorityClass;
            public uint SchedulingClass;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct IO_COUNTERS
        {
            public ulong ReadOperationCount;
            public ulong WriteOperationCount;
            public ulong OtherOperationCount;
            public ulong ReadTransferCount;
            public ulong WriteTransferCount;
            public ulong OtherTransferCount;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct JOBOBJECT_EXTENDED_LIMIT_INFORMATION
        {
            public JOBOBJECT_BASIC_LIMIT_INFORMATION BasicLimitInformation;
            public IO_COUNTERS IoInfo;
            public UIntPtr ProcessMemoryLimit;
            public UIntPtr JobMemoryLimit;
            public UIntPtr PeakProcessMemoryUsed;
            public UIntPtr PeakJobMemoryUsed;
        }

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern IntPtr CreateJobObject(IntPtr attributes, string name);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool SetInformationJobObject(IntPtr job, int infoClass, IntPtr info, uint length);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool AssignProcessToJobObject(IntPtr job, IntPtr process);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool TerminateJobObject(IntPtr job, uint exitCode);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool CloseHandle(IntPtr handle);
    }
}
