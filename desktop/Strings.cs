using System.Globalization;

namespace MLogger.Desktop
{
    internal static class Strings
    {
        public static readonly bool Russian = CultureInfo.CurrentUICulture.TwoLetterISOLanguageName == "ru";
        public static readonly string Language = Russian ? "ru" : "en";

        private static string Pick(string ru, string en) => Russian ? ru : en;

        public static string Starting => Pick("Запускаю MLogger…", "Starting MLogger…");
        public static string StartingHint => Pick("Поднимаю локальный сервер и открываю интерфейс.", "Starting the local server and opening the interface.");
        public static string Retry => Pick("Попробовать снова", "Try again");
        public static string OpenInBrowser => Pick("Открыть в браузере", "Open in browser");
        public static string Open => Pick("Открыть MLogger", "Open MLogger");
        public static string DataFolder => Pick("Папка с данными", "Data folder");
        public static string Exit => Pick("Выход", "Exit");
        public static string GetPython => Pick("Скачать Python", "Download Python");
        public static string GetWebView => Pick("Установить WebView2", "Install WebView2");

        public static string FailedTitle => Pick("Не получилось запустить MLogger", "MLogger could not start");
        public static string NoPython => Pick(
            "Не найден Python 3.9 или новее. Установите его с python.org (при установке отметьте «Add python.exe to PATH») и нажмите «Попробовать снова».",
            "Python 3.9 or newer was not found. Install it from python.org (tick “Add python.exe to PATH” during setup) and press “Try again”.");
        public static string NoAppFiles => Pick(
            "Рядом с программой нет файлов MLogger (папки app со start.py). Распакуйте архив целиком и запустите MLogger.exe из него.",
            "The MLogger files (the app folder with start.py) are missing next to the program. Unpack the whole archive and run MLogger.exe from it.");
        public static string ServerExited => Pick("Сервер MLogger завершился при запуске:", "The MLogger server exited during startup:");
        public static string ServerTimeout => Pick(
            "Сервер MLogger не ответил за отведённое время.",
            "The MLogger server did not respond in time.");
        public static string NoWebView => Pick(
            "На этом компьютере нет компонента Microsoft Edge WebView2, поэтому интерфейс открыт в обычном браузере. Сервер продолжает работать, пока открыто это окно.",
            "Microsoft Edge WebView2 is not installed on this computer, so the interface was opened in your regular browser. The server keeps running while this window is open.");

        public static string TrayRunning => Pick("MLogger работает", "MLogger is running");
        public static string TrayHint => Pick(
            "MLogger продолжает собирать метрики в фоне. Чтобы закрыть его совсем, выберите «Выход» в меню значка.",
            "MLogger keeps collecting metrics in the background. To quit completely, choose “Exit” in the icon menu.");
    }
}
