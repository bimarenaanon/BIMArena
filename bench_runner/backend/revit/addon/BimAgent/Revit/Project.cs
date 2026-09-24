using System;
using System.Collections.Generic;
using System.IO;
using Autodesk.Revit.DB;
using Autodesk.Revit.DB.Events;
using Autodesk.Revit.UI;
using Autodesk.Revit.UI.Events;

namespace BimAgent
{
    /// Project-level file operations for the bench HARNESS (not the agent): open a project
    /// and save the active one under a new name, through the API instead of keystrokes.
    ///
    /// The harness used to drive both by keyboard (Ctrl+O + pasted path, Alt,F,A,P + pasted
    /// path, blind waits, a rescue ladder for dialogs and edit modes). Every batch incident
    /// of the 2026-08 runs came from that path. These routes are deterministic and answer
    /// with the resulting document title, so the caller can VERIFY instead of sleeping.
    ///
    /// Both run on the API thread (dispatcher) under dialog/warning guards: a
    /// warning dialog or a modal raised by the operation would otherwise freeze the API
    /// thread until a human clicks it. A failure comes back as {ok:false, error} and the
    /// harness falls back to its keyboard path -- e.g. Revit inside a sketch/edit mode
    /// refuses both open and save-as through the API exactly as it greys the menu out.
    internal static class Project
    {
        /// Open `path` and make it the active document, then close EVERY other project
        /// document WITHOUT saving (`close_others`, default true). Revit refuses two open
        /// documents with the same title, every case env is `revit.rvt`, and a case's
        /// unsaved leftovers must never be written anywhere -- so the previous document is
        /// discarded, never saved.
        public static object Open(UIApplication app, string path, bool closeOthers)
        {
            if (string.IsNullOrWhiteSpace(path) || !File.Exists(path))
                return Fail("file not found: " + path);
            using (new UiGuards(app))
            {
                var closed = new List<string>();
                var failed = new List<string>();
                Document active = app.ActiveUIDocument?.Document;
                string activePath = active?.PathName ?? "";
                // 1) close every NON-active project document first (the active one cannot be
                //    closed through the API while it is active) -- also removes any
                //    same-title document that would make Revit refuse the open.
                if (closeOthers)
                {
                    foreach (var d in OpenProjectDocs(app))
                    {
                        if (active != null && d.Equals(active)) continue;
                        string title = SafeTitle(d);
                        try { d.Close(false); closed.Add(title); }
                        catch (Exception e) { failed.Add(title + ": " + e.Message); }
                    }
                }
                // 2) open + activate the requested project
                UIDocument uidoc = app.OpenAndActivateDocument(path);
                Document opened = uidoc?.Document;
                if (opened == null)
                    return Fail("OpenAndActivateDocument returned no document for " + path);
                // 3) now the previously active document is closable -- unless it IS the file
                //    just opened (Revit re-activates an already-open path)
                if (closeOthers && active != null
                    && !string.Equals(activePath, opened.PathName ?? "", StringComparison.OrdinalIgnoreCase))
                {
                    string title = SafeTitle(active);
                    try { active.Close(false); closed.Add(title); }
                    catch (Exception e) { failed.Add(title + ": " + e.Message); }
                }
                var r = new Dictionary<string, object>
                {
                    ["ok"] = true,
                    ["doc"] = opened.Title,
                    ["path"] = opened.PathName,
                    ["closed"] = closed,
                };
                if (failed.Count > 0) r["close_failed"] = failed;
                return r;
            }
        }

        /// Save the ACTIVE document as `path` (overwriting). The document's title becomes
        /// the new file's stem, which is what the harness verifies through /health.
        public static object SaveAs(UIApplication app, string path, bool overwrite)
        {
            Document doc = app.ActiveUIDocument?.Document;
            if (doc == null)
                return Fail("no active document");
            if (string.IsNullOrWhiteSpace(path))
                return Fail("no path given");
            if (doc.IsModifiable)
                return Fail("the document is being modified (an open transaction / edit mode) -- cannot save");
            string dir = Path.GetDirectoryName(path);
            if (!string.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);
            using (new UiGuards(app))
            {
                var opts = new SaveAsOptions { OverwriteExistingFile = overwrite, MaximumBackups = 1 };
                doc.SaveAs(path, opts);
                return new Dictionary<string, object>
                {
                    ["ok"] = true,
                    ["doc"] = doc.Title,
                    ["path"] = doc.PathName,
                    ["exists"] = File.Exists(path),
                };
            }
        }

        private static List<Document> OpenProjectDocs(UIApplication app)
        {
            var list = new List<Document>();
            foreach (Document d in app.Application.Documents)
            {
                if (d.IsLinked || d.IsFamilyDocument) continue;
                list.Add(d);
            }
            return list;
        }

        private static string SafeTitle(Document d)
        {
            try { return d.Title; } catch { return "?"; }
        }

        private static Dictionary<string, object> Fail(string msg) =>
            new Dictionary<string, object> { ["ok"] = false, ["error"] = msg };

        /// Warnings deleted, errors roll back, any dialog answered with its default (1) --
        /// dialog/warning guards, scoped to one operation.
        private sealed class UiGuards : IDisposable
        {
            private readonly UIApplication _app;
            private readonly EventHandler<FailuresProcessingEventArgs> _onFailures;
            private readonly EventHandler<DialogBoxShowingEventArgs> _onDialog;

            public UiGuards(UIApplication app)
            {
                _app = app;
                _onFailures = (s, e) =>
                {
                    var fa = e.GetFailuresAccessor();
                    bool hasError = false;
                    foreach (var f in fa.GetFailureMessages())
                    {
                        if (f.GetSeverity() == FailureSeverity.Warning) fa.DeleteWarning(f);
                        else hasError = true;
                    }
                    e.SetProcessingResult(hasError ? FailureProcessingResult.ProceedWithRollBack
                                                   : FailureProcessingResult.Continue);
                };
                _onDialog = (s, e) => { try { e.OverrideResult(1); } catch { } };
                _app.Application.FailuresProcessing += _onFailures;
                _app.DialogBoxShowing += _onDialog;
            }

            public void Dispose()
            {
                _app.Application.FailuresProcessing -= _onFailures;
                _app.DialogBoxShowing -= _onDialog;
            }
        }
    }
}
