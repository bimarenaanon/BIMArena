using System;
using System.Collections.Generic;
using System.IO;
using System.Net;
using System.Text;
using System.Text.Json;
using System.Threading;
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;

namespace BimAgent
{
    /// Local HTTP server (HttpListener) serving the bim-agent route contract (see
    /// bench_runner/backend/revit/client.py). Runs its accept loop + per-request handling on
    /// background threads; every route delegates the actual Revit work to the dispatcher so it runs on
    /// the API thread. Results are JSON.
    public class HttpServer
    {
        private const int JobTimeoutMs = 120000;

        private readonly HttpListener _listener = new HttpListener();
        private readonly RevitDispatcher _dispatcher;
        private Thread _thread;
        private volatile bool _running;

        public HttpServer(RevitDispatcher dispatcher, string prefix)
        {
            _dispatcher = dispatcher;
            _listener.Prefixes.Add(prefix);              // "http://localhost:48884/" — localhost needs no urlacl
        }

        public void Start()
        {
            _listener.Start();
            _running = true;
            _thread = new Thread(Loop) { IsBackground = true, Name = "BimAgentHttp" };
            _thread.Start();
        }

        public void Stop()
        {
            _running = false;
            try { _listener.Stop(); } catch { /* ignore */ }
        }

        private void Loop()
        {
            while (_running)
            {
                HttpListenerContext ctx;
                try { ctx = _listener.GetContext(); }
                catch { if (!_running) break; else continue; }
                ThreadPool.QueueUserWorkItem(_ => Handle(ctx));
            }
        }

        private void Handle(HttpListenerContext ctx)
        {
            object result;
            byte[] json;
            try
            {
                result = Route(ctx.Request);
                json = JsonSerializer.SerializeToUtf8Bytes(result);
            }
            catch (Exception e)
            {
                result = RevitDispatcher.Err(e);        // serialization inside the try too — an
                json = JsonSerializer.SerializeToUtf8Bytes(result);   // unserializable result must
            }                                           // not take down the handler thread
            // A failed GET read must NOT be HTTP 200: the Python client treats any 200 body as
            // data, and an {ok:false} dict is truthy — a failed /snapshot would silently become
            // "the (empty) model". POST /action stays 200: per-action failures ARE the data the
            // pipeline records per call.
            if (ctx.Request.HttpMethod == "GET" && IsErr(result))
                ctx.Response.StatusCode = 500;
            ctx.Response.ContentType = "application/json";
            ctx.Response.ContentLength64 = json.Length;
            try { ctx.Response.OutputStream.Write(json, 0, json.Length); } catch { }
            try { ctx.Response.OutputStream.Close(); } catch { }
        }

        private static bool IsErr(object r) =>
            r is Dictionary<string, object> d && d.TryGetValue("ok", out var ok)
            && ok is bool b && !b;

        private object Route(HttpListenerRequest req)
        {
            string path = req.Url.AbsolutePath.Trim('/');     // "snapshot", "favorites/Door", ...
            string method = req.HttpMethod;

            if (method == "GET" && path == "health")
                return Run(app => new Dictionary<string, object> { ["ok"] = true, ["doc"] = Doc(app)?.Title });
            if (method == "GET" && path == "snapshot")
                return Run(app => WithDoc(app, d => Reads.Snapshot(d)));
            if (method == "GET" && path == "materials")
                return Run(app => WithDoc(app, d => Reads.Materials(d)));
            if (method == "GET" && path == "composites")
                return Run(app => WithDoc(app, d => Reads.Composites(d)));
            if (method == "GET" && path.StartsWith("favorites/"))
            {
                string t = Uri.UnescapeDataString(path.Substring("favorites/".Length));
                return Run(app => WithDoc(app, d => Reads.Favorites(d, t)));
            }
            if (method == "GET" && path == "elements")
                return Run(app => WithDoc(app, d => Reads.Elements(d)));
            if (method == "POST" && (path == "open" || path == "saveas"))
            {
                // HARNESS routes (bench_runner): open a project / save the active one under a
                // new name through the API, replacing the keyboard-driven open and Save As.
                // Opening a big project can take a while -- give it the long timeout.
                string body = ReadBody(req);
                string file = null;
                bool closeOthers = true, overwrite = true;
                using (JsonDocument jd = JsonDocument.Parse(string.IsNullOrEmpty(body) ? "{}" : body))
                {
                    JsonElement root = jd.RootElement;
                    file = root.TryGetProperty("path", out var p) ? p.GetString() : null;
                    if (root.TryGetProperty("close_others", out var c) && c.ValueKind == JsonValueKind.False) closeOthers = false;
                    if (root.TryGetProperty("overwrite", out var o) && o.ValueKind == JsonValueKind.False) overwrite = false;
                }
                if (string.IsNullOrWhiteSpace(file))
                    return new Dictionary<string, object> { ["ok"] = false, ["error"] = "no path given — POST {\"path\": \"<file.rvt>\"}" };
                return path == "open"
                    ? Run(app => Project.Open(app, file, closeOthers), 300000)
                    : Run(app => Project.SaveAs(app, file, overwrite), 300000);
            }
            if (method == "POST" && path == "action")
            {
                string body = ReadBody(req);
                string action;
                Params prms;
                using (JsonDocument jd = JsonDocument.Parse(string.IsNullOrEmpty(body) ? "{}" : body))
                {
                    JsonElement root = jd.RootElement;
                    action = root.TryGetProperty("action", out var a) ? a.GetString() : null;
                    prms = root.TryGetProperty("params", out var p) ? new Params(p) : new Params();
                }
                if (action == "select_elements")     // selection lives on UIDocument, not Document
                    return Run(app => Actions.SelectElements(app.ActiveUIDocument, prms));
                if (action == "set_active_story")    // the active view lives on UIDocument too
                    return Run(app => Actions.SetActiveStory(app.ActiveUIDocument, prms));
                return Run(app => Actions.Run(Doc(app), action, prms));
            }
            return new Dictionary<string, object> { ["ok"] = false, ["error"] = "no route: " + method + " /" + path };
        }

        /// Submit work to the API thread and block this background thread until it completes.
        private object Run(Func<UIApplication, object> work, int timeoutMs = JobTimeoutMs)
        {
            var job = _dispatcher.Submit(work);
            if (!job.Task.Wait(timeoutMs))
            {
                // Mark the job ABANDONED so the dispatcher skips it if it hasn't started yet —
                // otherwise a "timed out" action still executes minutes later, AFTER the agent
                // recorded it as failed and re-emitted it (duplicate elements, and the model
                // mutating behind the snapshot that judged it).
                job.Cancel();
                return new Dictionary<string, object> { ["ok"] = false, ["error"] = "Revit job timed out" };
            }
            return job.Task.Result;
        }

        private static Document Doc(UIApplication app) => app.ActiveUIDocument?.Document;

        /// Read routes with NO document open must return a clean error (-> HTTP 500 via IsErr),
        /// not a NullReferenceException from deep inside Reads.
        private static object WithDoc(UIApplication app, Func<Document, object> f)
        {
            var d = Doc(app);
            return d == null
                ? new Dictionary<string, object> { ["ok"] = false, ["error"] = "no active document — open a project in Revit" }
                : f(d);
        }

        private static string ReadBody(HttpListenerRequest req)
        {
            using (var r = new StreamReader(req.InputStream, req.ContentEncoding ?? Encoding.UTF8))
                return r.ReadToEnd();
        }
    }
}
