using System;
using System.Threading;
using System.Windows.Forms;

namespace MLogger.Desktop
{
    internal static class Program
    {
        private const string InstanceName = "MLogger.Desktop.Instance";
        private const string ShowName = "MLogger.Desktop.Show";

        [STAThread]
        private static void Main()
        {
            using (var instance = new Mutex(true, InstanceName, out bool first))
            {
                if (!first)
                {
                    try
                    {
                        using (var running = EventWaitHandle.OpenExisting(ShowName)) running.Set();
                    }
                    catch (Exception)
                    {
                    }
                    return;
                }

                Application.EnableVisualStyles();
                Application.SetCompatibleTextRenderingDefault(false);

                using (var show = new EventWaitHandle(false, EventResetMode.AutoReset, ShowName))
                using (var form = new MainForm())
                {
                    var listener = new Thread(() =>
                    {
                        while (show.WaitOne())
                        {
                            if (form.IsDisposed) return;
                            try
                            {
                                form.BeginInvoke((Action)form.ShowFromTray);
                            }
                            catch (InvalidOperationException)
                            {
                            }
                        }
                    });
                    listener.IsBackground = true;
                    listener.Start();
                    Application.Run(form);
                }
                GC.KeepAlive(instance);
            }
        }
    }
}
