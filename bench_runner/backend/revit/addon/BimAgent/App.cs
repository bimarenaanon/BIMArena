using Autodesk.Revit.UI;

namespace BimAgent
{
    /// Revit add-in entry point. On startup it creates the main-thread dispatcher (an ExternalEvent
    /// handler) and starts a local HTTP server that serves the bim-agent routes the Python backend
    /// (bench_runner/backend/revit/client.py) calls. Every request is marshalled onto Revit's
    /// API thread via the dispatcher, because the Revit API must NOT be touched from the HTTP thread.
    public class App : IExternalApplication
    {
        private HttpServer _server;
        private RevitDispatcher _dispatcher;

        public Result OnStartup(UIControlledApplication application)
        {
            _dispatcher = new RevitDispatcher();
            _dispatcher.Event = ExternalEvent.Create(_dispatcher);   // must be created on the API thread (startup is)
            _server = new HttpServer(_dispatcher, "http://localhost:48884/");
            try
            {
                _server.Start();
            }
            catch (System.Exception e)
            {
                // port 48884 already taken (an orphaned listener / a second Revit): without this
                // the whole add-in fails to load with no explanation. Surface it and load anyway.
                TaskDialog.Show("BimAgent",
                    "BimAgent HTTP server failed to start on port 48884 — the agent cannot "
                    + "connect to THIS Revit instance.\n\n" + e.Message);
            }
            return Result.Succeeded;
        }

        public Result OnShutdown(UIControlledApplication application)
        {
            _server?.Stop();
            return Result.Succeeded;
        }
    }
}
