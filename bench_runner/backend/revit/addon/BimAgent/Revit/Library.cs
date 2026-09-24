using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Autodesk.Revit.DB;

namespace BimAgent
{
    /// On-demand loading of loadable families (doors / windows / furniture) from the Revit library,
    /// so the agent can place a TYPE that isn't loaded in the project yet (e.g. a DOUBLE door when
    /// only single-flush is loaded). Library root:
    ///   C:\ProgramData\Autodesk\RVT &lt;version&gt;\Libraries\English\US
    /// (the metric "English" / US library, per the installed content).
    public static class Library
    {
        private static readonly Dictionary<BuiltInCategory, string> Folder = new Dictionary<BuiltInCategory, string>
        {
            [BuiltInCategory.OST_Doors] = "Doors",
            [BuiltInCategory.OST_Windows] = "Windows",
            [BuiltInCategory.OST_Furniture] = "Furniture",
            [BuiltInCategory.OST_Casework] = "Casework",
            [BuiltInCategory.OST_SpecialityEquipment] = "Specialty Equipment",
        };

        public static string Root(Document doc) =>
            Path.Combine(@"C:\ProgramData\Autodesk", "RVT " + doc.Application.VersionNumber, @"Libraries\English\US");

        private static string CatDir(Document doc, BuiltInCategory cat)
        {
            if (!Folder.TryGetValue(cat, out var sub)) return null;
            string d = Path.Combine(Root(doc), sub);
            if (Directory.Exists(d)) return d;
            return Directory.Exists(Root(doc)) ? Root(doc) : null;       // fall back to the whole library
        }

        /// Family names (.rfa file stems) available in the library for a category — surfaced in
        /// /favorites so the planner/actor can ask for a type that isn't loaded yet. Tags / hardware
        /// are filtered out (not placeable doors/windows).
        public static List<string> FamilyNames(Document doc, BuiltInCategory cat)
        {
            var dir = CatDir(doc, cat);
            if (dir == null) return new List<string>();
            try
            {
                return Directory.GetFiles(dir, "*.rfa", SearchOption.AllDirectories)
                    .Where(f => f.IndexOf(@"\Hardware\", StringComparison.OrdinalIgnoreCase) < 0)
                    .Select(Path.GetFileNameWithoutExtension)
                    .Where(n => n.IndexOf("Tag", StringComparison.OrdinalIgnoreCase) < 0)
                    .Distinct().OrderBy(n => n).ToList();
            }
            catch { return new List<string>(); }
        }

        private static string FindRfa(Document doc, BuiltInCategory cat, string famName)
        {
            var dir = CatDir(doc, cat);
            if (dir == null || string.IsNullOrEmpty(famName)) return null;
            try
            {
                var exact = Directory.GetFiles(dir, famName + ".rfa", SearchOption.AllDirectories);
                if (exact.Length > 0) return exact[0];
                var all = Directory.GetFiles(dir, "*.rfa", SearchOption.AllDirectories);
                return all.FirstOrDefault(f => Path.GetFileNameWithoutExtension(f).Equals(famName, StringComparison.OrdinalIgnoreCase))
                    ?? all.FirstOrDefault(f => Path.GetFileNameWithoutExtension(f).IndexOf(famName, StringComparison.OrdinalIgnoreCase) >= 0);
            }
            catch { return null; }
        }

        /// Resolve a `favorite` ("Family: Type" or a bare family name) to a placeable, ACTIVATED
        /// FamilySymbol: an exact already-loaded match first; else LOAD the matching family from the
        /// library and pick its type; else null (the caller decides the fallback).
        public static FamilySymbol EnsureSymbol(Document doc, BuiltInCategory cat, string favorite)
        {
            string fav = (favorite ?? "").Trim();
            if (fav.Length == 0) return null;
            string famName = fav, typeName = null;
            int i = fav.IndexOf(": ", StringComparison.Ordinal);
            if (i >= 0) { famName = fav.Substring(0, i); typeName = fav.Substring(i + 2); }

            var loaded = new FilteredElementCollector(doc).OfCategory(cat).OfClass(typeof(FamilySymbol))
                .Cast<FamilySymbol>().ToList();

            // 1. exact already-loaded match (Family: Type, or just the type/family name)
            foreach (var s in loaded)
            {
                string sf = s.Family != null ? s.Family.Name : "", st = Lookups.NameOf(s);
                if (fav == sf + ": " + st || fav == st || fav == sf)
                    return Activate(doc, s);
            }

            // 2. load the family from the library and pick a type
            var path = FindRfa(doc, cat, famName);
            if (path != null)
            {
                Family fam;
                if (!doc.LoadFamily(path, out fam) || fam == null)
                    fam = new FilteredElementCollector(doc).OfClass(typeof(Family)).Cast<Family>()
                          .FirstOrDefault(f => f.Name == Path.GetFileNameWithoutExtension(path));
                if (fam != null)
                {
                    FamilySymbol chosen = null;
                    foreach (var id in fam.GetFamilySymbolIds())
                    {
                        if (!(doc.GetElement(id) is FamilySymbol s)) continue;
                        if (typeName != null && Lookups.NameOf(s) == typeName) { chosen = s; break; }
                        if (chosen == null) chosen = s;
                    }
                    if (chosen != null) return Activate(doc, chosen);
                }
            }
            return null;
        }

        private static FamilySymbol Activate(Document doc, FamilySymbol s)
        {
            if (s != null && !s.IsActive) { s.Activate(); doc.Regenerate(); }
            return s;
        }
    }
}
