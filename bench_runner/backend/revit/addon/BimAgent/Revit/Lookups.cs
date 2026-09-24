using System;
using System.Collections.Generic;
using System.Linq;
using Autodesk.Revit.DB;

namespace BimAgent
{
    /// Element lookups shared by reads + actions. Identity: Revit's **UniqueId** is the "guid" the
    /// agent sees (stable across calls, so the snapshot diff matches); the short human "id" is the
    /// ElementId integer (also used as the opening HOST reference).
    public static class Lookups
    {
        public static string NameOf(Element e)
        {
            try { return e?.Name; } catch { return null; }
        }

        public static string IdStr(Element e) => e.Id.Value.ToString();

        public static Element ByGuid(Document doc, string guid) =>
            string.IsNullOrEmpty(guid) ? null : doc.GetElement(guid);   // GetElement accepts a UniqueId string

        public static List<Level> Levels(Document doc) =>
            new FilteredElementCollector(doc).OfClass(typeof(Level)).Cast<Level>()
                .OrderBy(l => l.Elevation).ToList();

        /// The Level whose elevation is closest to z (metres); falls back to the lowest.
        public static Level LevelForZ(Document doc, double zM)
        {
            var ls = Levels(doc);
            if (ls.Count == 0) return null;
            double t = Units.MToFt(zM);
            return ls.OrderBy(l => Math.Abs(l.Elevation - t)).First();
        }

        public static Level LevelByIndex(Document doc, int? idx)
        {
            var ls = Levels(doc);
            if (ls.Count == 0) return null;
            if (idx == null) return ls[0];
            // an OUT-OF-RANGE index is the caller's mistake and must fail loudly — falling
            // back to ls[0] silently moved elements to the ground floor while reporting ok.
            return (idx >= 0 && idx < ls.Count) ? ls[idx.Value] : null;
        }

        /// Name match with the SAME semantics as the Archicad backend's composite_info:
        /// exact (case-insensitive) first, then two-way substring. Null when nothing matches.
        private static T MatchByName<T>(List<T> items, string name) where T : Element
        {
            string nl = name.Trim().ToLowerInvariant();
            var exact = items.FirstOrDefault(t => (NameOf(t) ?? "").Trim().ToLowerInvariant() == nl);
            if (exact != null) return exact;
            return items.FirstOrDefault(t =>
            {
                string cn = (NameOf(t) ?? "").Trim().ToLowerInvariant();
                return cn.Length > 0 && (cn.Contains(nl) || (cn.Length >= 4 && nl.Contains(cn)));
            });
        }

        /// A requested name/guid that doesn't match returns NULL — never an arbitrary type.
        /// The old FirstOrDefault fallback built the wall with whatever type came first and
        /// returned ok:true; composite tasks are graded by NAME, so that silent substitution
        /// is invisible to the whole verify loop. No name/guid at all -> any type (the
        /// duplication base for BuildComposite), which is the only legitimate fallback.
        public static WallType GetWallType(Document doc, string name = null, string guid = null)
        {
            if (!string.IsNullOrEmpty(guid)) return ByGuid(doc, guid) as WallType;
            var wts = new FilteredElementCollector(doc).OfClass(typeof(WallType)).Cast<WallType>().ToList();
            if (!string.IsNullOrEmpty(name)) return MatchByName(wts, name);
            // NO name/guid = "give me a sane default": the duplication base for BuildComposite,
            // and the type a plain (non-composite) create_wall places. It MUST be a BASIC wall. WallType also
            // covers the Curtain and Stacked kinds, a default template ships several of each,
            // and FirstOrDefault() picks by collector order — so this landed on "Curtain Wall"
            // and every composite task built a GLAZED wall. Worse silently: only a Basic wall
            // has a CompoundStructure at all, so SetCompoundStructure on a curtain type never
            // applies the layer stack the task is graded on, and the type comes out named
            // correctly with no layers in it.
            // Prefer a basic type that ALREADY carries a compound structure — duplicating one
            // that has none starts the new type from an invalid assembly.
            return wts.FirstOrDefault(t => t.Kind == WallKind.Basic && t.GetCompoundStructure() != null)
                ?? wts.FirstOrDefault(t => t.Kind == WallKind.Basic);
        }

        public static FloorType GetFloorType(Document doc, string name = null, string guid = null)
        {
            if (!string.IsNullOrEmpty(guid)) return ByGuid(doc, guid) as FloorType;
            var fts = new FilteredElementCollector(doc).OfClass(typeof(FloorType)).Cast<FloorType>().ToList();
            if (!string.IsNullOrEmpty(name)) return MatchByName(fts, name);
            // Same rule as walls: prefer a duplication base that already has a layer stack.
            // (FloorType has no Kind split, so there is no curtain-wall equivalent to exclude.)
            return fts.FirstOrDefault(t => t.GetCompoundStructure() != null) ?? fts.FirstOrDefault();
        }

        public static Material GetMaterial(Document doc, string name)
        {
            if (string.IsNullOrEmpty(name)) return null;
            return new FilteredElementCollector(doc).OfClass(typeof(Material)).Cast<Material>()
                .FirstOrDefault(m => NameOf(m) == name);
        }

        /// A FamilySymbol by "Family: Type" (or just the type name). A label that matches
        /// NOTHING returns null — never the first symbol of the category (a typo'd favorite
        /// must fail loudly, not place an arbitrary door type with ok:true). Only an EMPTY
        /// label (no favorite requested at all) falls back to any loaded symbol.
        public static FamilySymbol Symbol(Document doc, BuiltInCategory cat, string label)
        {
            string want = (label ?? "").Trim();
            var syms = new FilteredElementCollector(doc).OfCategory(cat).OfClass(typeof(FamilySymbol))
                .Cast<FamilySymbol>().ToList();
            if (want.Length == 0) return syms.FirstOrDefault();
            foreach (var s in syms)
            {
                string full = (s.Family != null ? s.Family.Name : "") + ": " + NameOf(s);
                if (full == want || NameOf(s) == want) return s;
            }
            return null;
        }

        public static Wall WallByRef(Document doc, string reference)
        {
            if (string.IsNullOrEmpty(reference)) return null;
            if (long.TryParse(reference, out long i))
            {
                var el = doc.GetElement(new ElementId(i));   // the snapshot 'id' is the ElementId value
                if (el is Wall w) return w;
            }
            return ByGuid(doc, reference) as Wall;            // or a UniqueId
        }
    }
}
