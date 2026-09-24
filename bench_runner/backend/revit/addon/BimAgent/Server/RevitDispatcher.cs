using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Threading.Tasks;
using Autodesk.Revit.UI;

namespace BimAgent
{
    /// Marshals work onto Revit's API thread.
    ///
    /// The HTTP server handles requests on background threads, but the Revit API can only be used in
    /// a valid API context (the main thread, when Revit is idle). So each HTTP handler builds a unit
    /// of work `Func&lt;UIApplication, object&gt;`, hands it to Submit(), and awaits the result. Submit
    /// enqueues the job and raises the ExternalEvent; Revit later calls Execute() on the API thread,
    /// which drains the queue, runs each job, and completes its Task. Exceptions become an
    /// {ok:false, error} result so one bad action never breaks the server.
    public class RevitDispatcher : IExternalEventHandler
    {
        /// One queued unit of work. `Cancel()` marks a job ABANDONED (the HTTP request that
        /// submitted it timed out): Execute() then SKIPS it instead of running the Revit work
        /// anyway — a "timed out" create that still executed later would put the element in
        /// the model AND let the repair round add a duplicate. (Best-effort: a job already
        /// mid-execution when the timeout fires cannot be stopped.)
        public class Job
        {
            internal Func<UIApplication, object> Work;
            internal readonly TaskCompletionSource<object> Tcs = new TaskCompletionSource<object>();
            internal volatile bool Cancelled;
            public Task<object> Task => Tcs.Task;
            public void Cancel() => Cancelled = true;
        }

        private readonly ConcurrentQueue<Job> _queue = new ConcurrentQueue<Job>();
        private IntPtr _hwnd = IntPtr.Zero;

        [DllImport("user32.dll")]
        private static extern bool PostMessage(IntPtr hWnd, uint msg, IntPtr wParam, IntPtr lParam);
        private const uint WM_NULL = 0x0000;

        /// Set by App after ExternalEvent.Create(this) on the API thread.
        public ExternalEvent Event { get; set; }

        public Job Submit(Func<UIApplication, object> work)
        {
            var job = new Job { Work = work };
            _queue.Enqueue(job);
            Event?.Raise();                              // schedules Execute() on the API thread
            // ExternalEvent only runs when Revit pumps its message loop, which stalls when Revit sits
            // idle in the BACKGROUND (the agent's normal case). Post a harmless WM_NULL to wake the
            // loop so the event fires promptly without the user having to touch Revit.
            if (_hwnd == IntPtr.Zero) _hwnd = Process.GetCurrentProcess().MainWindowHandle;
            if (_hwnd != IntPtr.Zero) PostMessage(_hwnd, WM_NULL, IntPtr.Zero, IntPtr.Zero);
            return job;
        }

        public void Execute(UIApplication app)
        {
            while (_queue.TryDequeue(out var job))
            {
                if (job.Cancelled) { job.Tcs.TrySetResult(null); continue; }
                try { job.Tcs.SetResult(job.Work(app)); }
                catch (Exception e) { job.Tcs.SetResult(Err(e)); }
            }
        }

        public string GetName() => "BimAgent.RevitDispatcher";

        public static Dictionary<string, object> Err(Exception e)
        {
            var d = new Dictionary<string, object> { ["ok"] = false, ["error"] = e.GetType().Name + ": " + e.Message };
            // the first add-in frame of the stack: a Revit API exception message alone
            // ("The referenced object is not valid") does not say WHICH call raised it
            try
            {
                var st = new StackTrace(e, false);
                foreach (var f in st.GetFrames() ?? Array.Empty<StackFrame>())
                {
                    var m = f.GetMethod();
                    if (m?.DeclaringType != null && m.DeclaringType.Namespace == "BimAgent")
                    { d["where"] = m.DeclaringType.Name + "." + m.Name; break; }
                }
            }
            catch { }
            return d;
        }
    }
}
