using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Globalization;
using System.IO;
using System.Threading.Tasks;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

namespace MLogger.Desktop
{
    internal sealed class MainForm : Form
    {
        private static readonly Color Stone = Color.FromArgb(31, 36, 41);
        private static readonly Color Water = Color.FromArgb(99, 206, 224);
        private static readonly Color Ink = Color.FromArgb(211, 219, 225);
        private static readonly Color Muted = Color.FromArgb(139, 151, 161);

        private readonly ServerProcess server = new ServerProcess();
        private readonly WebView2 web = new WebView2();
        private readonly Panel status = new Panel();
        private readonly Label title = new Label();
        private readonly Label message = new Label();
        private readonly FlowLayoutPanel buttons = new FlowLayoutPanel();
        private readonly Button retry = new Button();
        private readonly Button extra = new Button();
        private readonly NotifyIcon tray = new NotifyIcon();
        private readonly string settingsPath = Path.Combine(ServerProcess.LocalDir, "desktop.ini");
        private readonly Dictionary<string, string> settings = new Dictionary<string, string>();

        private bool ready;
        private bool exiting;
        private bool starting;
        private string extraLink;

        public MainForm()
        {
            Text = "MLogger";
            Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
            BackColor = Stone;
            MinimumSize = new Size(880, 600);
            StartPosition = FormStartPosition.CenterScreen;
            ClientSize = new Size(1320, 840);
            AutoScaleMode = AutoScaleMode.Dpi;
            LoadSettings();
            ApplySavedBounds();

            web.Dock = DockStyle.Fill;
            web.Visible = false;
            web.DefaultBackgroundColor = Color.FromArgb(20, 23, 27);

            BuildStatusPanel();
            Controls.Add(web);
            Controls.Add(status);
            BuildTray();
        }

        private void BuildStatusPanel()
        {
            status.Dock = DockStyle.Fill;
            status.BackColor = Stone;
            status.Padding = new Padding(48);

            title.AutoSize = true;
            title.ForeColor = Color.White;
            title.Font = new Font("Segoe UI Semibold", 20f);
            title.Margin = new Padding(0, 0, 0, 10);

            message.AutoSize = true;
            message.ForeColor = Ink;
            message.Font = new Font("Segoe UI", 11f);
            message.MaximumSize = new Size(760, 0);
            message.Margin = new Padding(0, 0, 0, 22);

            StyleButton(retry, true);
            retry.Text = Strings.Retry;
            retry.Click += async (s, e) => await StartAsync();
            StyleButton(extra, false);
            extra.Click += (s, e) => OpenExternal(extraLink);

            buttons.AutoSize = true;
            buttons.FlowDirection = FlowDirection.LeftToRight;
            buttons.Controls.Add(retry);
            buttons.Controls.Add(extra);

            var column = new FlowLayoutPanel
            {
                Dock = DockStyle.Fill,
                FlowDirection = FlowDirection.TopDown,
                WrapContents = false,
                AutoScroll = true,
            };
            column.Controls.Add(title);
            column.Controls.Add(message);
            column.Controls.Add(buttons);
            status.Controls.Add(column);
        }

        private static void StyleButton(Button button, bool primary)
        {
            button.AutoSize = true;
            button.FlatStyle = FlatStyle.Flat;
            button.FlatAppearance.BorderSize = primary ? 0 : 1;
            button.FlatAppearance.BorderColor = Muted;
            button.BackColor = primary ? Water : Stone;
            button.ForeColor = primary ? Color.FromArgb(6, 36, 43) : Ink;
            button.Font = new Font("Segoe UI Semibold", 10.5f);
            button.Padding = new Padding(14, 6, 14, 6);
            button.Margin = new Padding(0, 0, 12, 0);
            button.Cursor = Cursors.Hand;
        }

        private void BuildTray()
        {
            var menu = new ContextMenuStrip();
            menu.Items.Add(Strings.Open, null, (s, e) => ShowFromTray());
            menu.Items.Add(Strings.OpenInBrowser, null, (s, e) => OpenExternal(ServerProcess.Url));
            menu.Items.Add(Strings.DataFolder, null, (s, e) => OpenDataFolder());
            menu.Items.Add(new ToolStripSeparator());
            menu.Items.Add(Strings.Exit, null, (s, e) => ExitApplication());
            tray.Icon = Icon;
            tray.Text = "MLogger";
            tray.ContextMenuStrip = menu;
            tray.Visible = true;
            tray.DoubleClick += (s, e) => ShowFromTray();
            tray.BalloonTipClicked += (s, e) => ShowFromTray();
        }

        protected override async void OnShown(EventArgs e)
        {
            base.OnShown(e);
            await StartAsync();
        }

        private async Task StartAsync()
        {
            if (starting) return;
            starting = true;
            ready = false;
            web.Visible = false;
            status.Visible = true;
            ShowStatus(Strings.Starting, Strings.StartingHint, false, null, null);
            try
            {
                await server.StartAsync();
                ready = true;
                await ShowInterfaceAsync();
            }
            catch (StartupException error)
            {
                ShowStatus(Strings.FailedTitle, error.Message, true,
                    error.PythonMissing ? Strings.GetPython : null,
                    error.PythonMissing ? "https://www.python.org/downloads/" : null);
            }
            catch (Exception error)
            {
                ShowStatus(Strings.FailedTitle, error.Message, true, null, null);
            }
            finally
            {
                starting = false;
            }
        }

        private async Task ShowInterfaceAsync()
        {
            try
            {
                if (web.CoreWebView2 == null)
                {
                    var options = new CoreWebView2EnvironmentOptions { Language = CultureInfo.CurrentUICulture.Name };
                    string profile = Path.Combine(ServerProcess.LocalDir, "WebView2");
                    CoreWebView2Environment environment = await CoreWebView2Environment.CreateAsync(null, profile, options);
                    await web.EnsureCoreWebView2Async(environment);
                    web.CoreWebView2.Settings.IsStatusBarEnabled = false;
                    web.CoreWebView2.Settings.AreDefaultContextMenusEnabled = true;
                    web.CoreWebView2.Settings.IsZoomControlEnabled = true;
                    web.CoreWebView2.NewWindowRequested += (s, e) =>
                    {
                        e.Handled = true;
                        OpenExternal(e.Uri);
                    };
                    web.CoreWebView2.NavigationStarting += (s, e) =>
                    {
                        if (e.Uri.StartsWith(ServerProcess.Url, StringComparison.OrdinalIgnoreCase)) return;
                        if (e.Uri.StartsWith("about:", StringComparison.OrdinalIgnoreCase)) return;
                        e.Cancel = true;
                        OpenExternal(e.Uri);
                    };
                    web.CoreWebView2.DocumentTitleChanged += (s, e) =>
                    {
                        string page = web.CoreWebView2.DocumentTitle;
                        Text = string.IsNullOrWhiteSpace(page) ? "MLogger" : page;
                    };
                }
                web.CoreWebView2.Navigate(ServerProcess.Url + "/");
                status.Visible = false;
                web.Visible = true;
                web.Focus();
            }
            catch (WebView2RuntimeNotFoundException)
            {
                OpenExternal(ServerProcess.Url);
                ShowStatus("MLogger", Strings.NoWebView, false, Strings.GetWebView, "https://developer.microsoft.com/microsoft-edge/webview2/");
                buttons.Visible = true;
            }
        }

        private void ShowStatus(string heading, string text, bool canRetry, string extraText, string link)
        {
            title.Text = heading;
            message.Text = text;
            retry.Visible = canRetry;
            extra.Visible = extraText != null;
            extra.Text = extraText ?? "";
            extraLink = link;
            buttons.Visible = canRetry || extraText != null;
            status.Visible = true;
            status.BringToFront();
        }

        public void ShowFromTray()
        {
            Show();
            if (WindowState == FormWindowState.Minimized) WindowState = FormWindowState.Normal;
            Activate();
        }

        private void OpenDataFolder()
        {
            string dir = server.DataDir;
            if (string.IsNullOrEmpty(dir)) return;
            try
            {
                Directory.CreateDirectory(dir);
                Process.Start(new ProcessStartInfo { FileName = dir, UseShellExecute = true });
            }
            catch (Exception)
            {
            }
        }

        private static void OpenExternal(string target)
        {
            if (string.IsNullOrEmpty(target)) return;
            if (!target.StartsWith("http://", StringComparison.OrdinalIgnoreCase) && !target.StartsWith("https://", StringComparison.OrdinalIgnoreCase)) return;
            try
            {
                Process.Start(new ProcessStartInfo { FileName = target, UseShellExecute = true });
            }
            catch (Exception)
            {
            }
        }

        private void ExitApplication()
        {
            exiting = true;
            Close();
        }

        protected override void OnFormClosing(FormClosingEventArgs e)
        {
            SaveBounds();
            if (!exiting && ready && server.Owned && e.CloseReason == CloseReason.UserClosing)
            {
                e.Cancel = true;
                Hide();
                if (!settings.ContainsKey("trayHint"))
                {
                    settings["trayHint"] = "shown";
                    tray.ShowBalloonTip(6000, Strings.TrayRunning, Strings.TrayHint, ToolTipIcon.Info);
                }
                SaveSettings();
                return;
            }
            SaveSettings();
            tray.Visible = false;
            server.Dispose();
            base.OnFormClosing(e);
        }

        protected override void Dispose(bool disposing)
        {
            if (disposing)
            {
                tray.Dispose();
                web.Dispose();
                server.Dispose();
            }
            base.Dispose(disposing);
        }

        private void LoadSettings()
        {
            try
            {
                if (!File.Exists(settingsPath)) return;
                foreach (string line in File.ReadAllLines(settingsPath))
                {
                    int split = line.IndexOf('=');
                    if (split > 0) settings[line.Substring(0, split).Trim()] = line.Substring(split + 1).Trim();
                }
            }
            catch (Exception)
            {
            }
        }

        private void SaveSettings()
        {
            try
            {
                var lines = new List<string>();
                foreach (KeyValuePair<string, string> pair in settings) lines.Add(pair.Key + "=" + pair.Value);
                File.WriteAllLines(settingsPath, lines);
            }
            catch (Exception)
            {
            }
        }

        private void ApplySavedBounds()
        {
            if (!settings.TryGetValue("bounds", out string saved)) return;
            string[] parts = saved.Split(',');
            if (parts.Length != 4) return;
            var numbers = new int[4];
            for (int i = 0; i < 4; i++)
            {
                if (!int.TryParse(parts[i], NumberStyles.Integer, CultureInfo.InvariantCulture, out numbers[i])) return;
            }
            var bounds = new Rectangle(numbers[0], numbers[1], numbers[2], numbers[3]);
            bool visible = false;
            foreach (Screen screen in Screen.AllScreens)
            {
                if (screen.WorkingArea.IntersectsWith(bounds)) visible = true;
            }
            if (!visible || bounds.Width < MinimumSize.Width || bounds.Height < MinimumSize.Height) return;
            StartPosition = FormStartPosition.Manual;
            Bounds = bounds;
            if (settings.TryGetValue("maximized", out string maximized) && maximized == "1") WindowState = FormWindowState.Maximized;
        }

        private void SaveBounds()
        {
            if (WindowState == FormWindowState.Minimized) return;
            Rectangle bounds = WindowState == FormWindowState.Normal ? Bounds : RestoreBounds;
            settings["bounds"] = string.Format(CultureInfo.InvariantCulture, "{0},{1},{2},{3}", bounds.X, bounds.Y, bounds.Width, bounds.Height);
            settings["maximized"] = WindowState == FormWindowState.Maximized ? "1" : "0";
        }
    }
}
