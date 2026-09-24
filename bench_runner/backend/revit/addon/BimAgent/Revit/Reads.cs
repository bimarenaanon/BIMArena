using System;
using System.Collections.Generic;
using System.Linq;
using Autodesk.Revit.DB;
using Autodesk.Revit.DB.Architecture;

namespace BimAgent
{
    /// Read endpoints. `Snapshot` returns the SAME structure as ults/model_snapshot.py (geometry in
    /// METRES, stories with elevation_mm + an `active` flag) so the planner/verifier + diff/clash work
    /// unchanged. Each bucket is wrapped so one failing read never kills the whole snapshot.
    ///
    /// First cut: dimension extraction for openings/slabs/stairs is best-effort and the most likely
    /// thing to need tuning against a real model.
    public static class Reads
    {
        // ---- simple lists ----
        public static object Materials(Document doc) =>
            new FilteredElementCollector(doc).OfClass(typeof(Material)).Cast<Material>()
                .Select(Lookups.NameOf).Where(n => n != null).Distinct().OrderBy(n => n).ToList();

        public static object Composites(Document doc)
        {
            var outList = new List<object>();
            foreach (var t in CompoundTypes(doc))
            {
                CompoundStructure cs = GetCompound(t);
                if (cs == null || cs.LayerCount <= 1) continue;
                var skins = new List<object>();
                double total = 0;
                for (int i = 0; i < cs.LayerCount; i++)
                {
                    var mat = doc.GetElement(cs.GetMaterialId(i));
                    double thick = Units.R3(Units.FtToM(cs.GetLayerWidth(i)));
                    total += thick;
                    skins.Add(new Dictionary<string, object>
                    {
                        ["material"] = mat != null ? Lookups.NameOf(mat) : null,
                        ["thickness_m"] = thick,
                        ["type"] = (int)cs.GetLayerFunction(i) == (int)MaterialFunctionAssignment.Structure ? "Core" : "Finish",
                    });
                }
                outList.Add(new Dictionary<string, object>
                {
                    ["name"] = Lookups.NameOf(t),
                    ["total_thickness_m"] = Units.R3(total),
                    ["skins_outer_to_inner"] = skins,
                });
            }
            return outList;
        }

        private static IEnumerable<Element> CompoundTypes(Document doc) =>
            new FilteredElementCollector(doc).OfClass(typeof(WallType)).Cast<Element>()
            .Concat(new FilteredElementCollector(doc).OfClass(typeof(FloorType)).Cast<Element>());

        private static CompoundStructure GetCompound(Element t)
        {
            try
            {
                if (t is HostObjAttributes hoa) return hoa.GetCompoundStructure();
            }
            catch { }
            return null;
        }

        private static readonly Dictionary<string, BuiltInCategory> FavCat = new Dictionary<string, BuiltInCategory>
        {
            ["Door"] = BuiltInCategory.OST_Doors,
            ["Window"] = BuiltInCategory.OST_Windows,
            ["Object"] = BuiltInCategory.OST_Furniture,
        };

        public static object Favorites(Document doc, string elementType)
        {
            if (!FavCat.TryGetValue(elementType, out var cat)) return new List<object>();
            // loaded "Family: Type" PLUS the loadable library families (e.g. a double-door family the
            // project hasn't loaded yet) — place_door/window load these on demand via Library.
            var names = new SortedSet<string>(StringComparer.Ordinal);
            foreach (var n in SymbolNames(doc, cat)) names.Add(n);
            foreach (var n in Library.FamilyNames(doc, cat)) names.Add(n);
            return names.ToList();
        }

        private static List<string> SymbolNames(Document doc, BuiltInCategory cat)
        {
            var names = new HashSet<string>();
            foreach (FamilySymbol s in new FilteredElementCollector(doc).OfCategory(cat)
                         .OfClass(typeof(FamilySymbol)).Cast<FamilySymbol>())
                names.Add((s.Family != null ? s.Family.Name : "") + ": " + Lookups.NameOf(s));
            return names.OrderBy(n => n).ToList();
        }

        public static object Elements(Document doc)
        {
            var outList = new List<object>();
            var cats = new Dictionary<string, BuiltInCategory>
            {
                ["Wall"] = BuiltInCategory.OST_Walls, ["Door"] = BuiltInCategory.OST_Doors,
                ["Window"] = BuiltInCategory.OST_Windows, ["Slab"] = BuiltInCategory.OST_Floors,
                ["Zone"] = BuiltInCategory.OST_Rooms, ["Stair"] = BuiltInCategory.OST_Stairs,
                ["Object"] = BuiltInCategory.OST_Furniture,
            };
            foreach (var kv in cats)
                foreach (var el in new FilteredElementCollector(doc).OfCategory(kv.Value)
                             .WhereElementIsNotElementType())
                    outList.Add(new Dictionary<string, object>
                    { ["guid"] = el.UniqueId, ["type"] = kv.Key, ["id"] = Lookups.IdStr(el) });
            return outList;
        }

        // ---- the snapshot ----
        public static object Snapshot(Document doc)
        {
            var snap = new Dictionary<string, object>();
            foreach (var b in new[] { "stories", "walls", "doors", "windows", "slabs", "rooms", "stairs", "objects" })
                snap[b] = new List<object>();

            var levels = Lookups.Levels(doc);
            var idx = new Dictionary<long, int>();
            for (int i = 0; i < levels.Count; i++) idx[levels[i].Id.Value] = i;
            int? act = ActiveStoryIndex(doc, idx);

            var stories = (List<object>)snap["stories"];
            var storyLevelM = new Dictionary<int, double>();
            for (int i = 0; i < levels.Count; i++)
            {
                stories.Add(new Dictionary<string, object>
                {
                    ["index"] = i, ["name"] = Lookups.NameOf(levels[i]),
                    ["elevation_mm"] = (int)Math.Round(Units.FtToM(levels[i].Elevation) * 1000),
                    ["active"] = (act != null && i == act.Value),
                });
                storyLevelM[i] = Units.R3(Units.FtToM(levels[i].Elevation));
            }

            // walls (+ a map so openings can name their host consistently)
            var wallIdByEid = new Dictionary<long, string>();
            var wallLineByEid = new Dictionary<long, Line>();
            var walls = (List<object>)snap["walls"];
            foreach (Wall w in new FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Walls)
                         .WhereElementIsNotElementType().Cast<Wall>())
            {
                try
                {
                    var line = (w.Location as LocationCurve)?.Curve as Line;
                    if (line == null) continue;
                    wallIdByEid[w.Id.Value] = Lookups.IdStr(w);
                    wallLineByEid[w.Id.Value] = line;
                    walls.Add(new Dictionary<string, object>
                    {
                        ["guid"] = w.UniqueId, ["id"] = Lookups.IdStr(w), ["floor"] = FloorOf(w, idx),
                        ["begCoordinate"] = Units.XyzM(line.GetEndPoint(0)),
                        ["endCoordinate"] = Units.XyzM(line.GetEndPoint(1)),
                        ["height"] = ParamM(w, BuiltInParameter.WALL_USER_HEIGHT_PARAM),
                        ["width"] = Units.R3(Units.FtToM(w.Width)),
                        ["composite"] = Lookups.NameOf(w.WallType),
                        // which way the build-up faces — see Orient()
                        ["orient"] = Orient(w, line),
                    });
                }
                catch { }
            }

            // doors + windows
            foreach (var kv in new[] { ("doors", BuiltInCategory.OST_Doors), ("windows", BuiltInCategory.OST_Windows) })
            {
                var bucket = (List<object>)snap[kv.Item1];
                foreach (FamilyInstance inst in new FilteredElementCollector(doc).OfCategory(kv.Item2)
                             .WhereElementIsNotElementType().Cast<FamilyInstance>())
                {
                    try
                    {
                        var host = inst.Host;
                        long? heid = host != null ? host.Id.Value : (long?)null;
                        var lp = inst.Location as LocationPoint;
                        XYZ pt = lp?.Point;
                        object center = pt != null
                            ? new List<object> { Units.R3(Units.FtToM(pt.X)), Units.R3(Units.FtToM(pt.Y)) } : null;
                        object off = null;
                        if (heid != null && wallLineByEid.TryGetValue(heid.Value, out var line) && pt != null)
                        {
                            XYZ b = line.GetEndPoint(0);
                            XYZ d = line.GetEndPoint(1) - b;
                            double dl = d.GetLength(); if (dl == 0) dl = 1;
                            off = Units.R3(Units.FtToM((pt - b).DotProduct(d / dl)));
                        }
                        var sym = doc.GetElement(inst.GetTypeId());
                        // dims live on the TYPE for the stock metric families — fall back to
                        // the symbol's params when the instance carries none
                        object width = ParamM(inst, BuiltInParameter.DOOR_WIDTH, BuiltInParameter.WINDOW_WIDTH,
                                              BuiltInParameter.FAMILY_WIDTH_PARAM)
                                       ?? ParamM(sym, BuiltInParameter.DOOR_WIDTH, BuiltInParameter.WINDOW_WIDTH,
                                                 BuiltInParameter.FAMILY_WIDTH_PARAM);
                        object height = ParamM(inst, BuiltInParameter.DOOR_HEIGHT, BuiltInParameter.WINDOW_HEIGHT,
                                               BuiltInParameter.FAMILY_HEIGHT_PARAM)
                                        ?? ParamM(sym, BuiltInParameter.DOOR_HEIGHT, BuiltInParameter.WINDOW_HEIGHT,
                                                  BuiltInParameter.FAMILY_HEIGHT_PARAM);
                        bucket.Add(new Dictionary<string, object>
                        {
                            ["guid"] = inst.UniqueId, ["id"] = Lookups.IdStr(inst), ["floor"] = FloorOf(inst, idx),
                            ["type"] = QualifiedType(sym),
                            ["host"] = heid != null && wallIdByEid.ContainsKey(heid.Value) ? wallIdByEid[heid.Value] : null,
                            ["width"] = width,
                            ["height"] = height,
                            ["sill"] = ParamM(inst, BuiltInParameter.INSTANCE_SILL_HEIGHT_PARAM),
                            ["center_offset"] = off, ["center"] = center,
                            // Swing / facing so the drawn arc can be graded. The BOOLEANS are
                            // relative to the family's DEFAULT insertion, so they only mean
                            // something to a reader that knows that default — the VECTORS below
                            // are absolute (Revit recomputes them after every flip) and are what
                            // the grader consumes: facing = the side the leaf opens toward,
                            // hand = the along-wall hand axis (hinge side).
                            ["facing_flipped"] = inst.FacingFlipped,
                            ["hand_flipped"] = inst.HandFlipped,
                            ["facing"] = Vec2(inst.FacingOrientation),
                            ["hand"] = Vec2(inst.HandOrientation),
                        });
                    }
                    catch { }
                }
            }

            // floors (slabs)
            var slabs = (List<object>)snap["slabs"];
            foreach (var fl in new FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Floors)
                         .WhereElementIsNotElementType())
            {
                try
                {
                    var ft = doc.GetElement(fl.GetTypeId()) as HostObjAttributes;
                    var cs = ft?.GetCompoundStructure();
                    object thick = cs != null ? (object)Units.R3(Units.FtToM(cs.GetWidth()))
                                              : ParamM(fl, BuiltInParameter.FLOOR_ATTR_THICKNESS_PARAM);
                    int? fidx = FloorOf(fl, idx);
                    double off = 0;                     // height offset from level -> ABSOLUTE level
                    try
                    {
                        var hp = fl.get_Parameter(BuiltInParameter.FLOOR_HEIGHTABOVELEVEL_PARAM);
                        if (hp != null && hp.HasValue) off = Units.FtToM(hp.AsDouble());
                    }
                    catch { }
                    var loops = FloorLoops(doc, fl);    // real sketch boundary + holes (a stairwell
                                                        // opening must survive into the snapshot —
                                                        // exclude_region grading reads `holes`)
                    slabs.Add(new Dictionary<string, object>
                    {
                        ["guid"] = fl.UniqueId, ["id"] = Lookups.IdStr(fl),
                        ["floor"] = fidx,               // every bucket is floor-tagged (contract —
                                                        // storey scoping drops untagged elements)
                        ["thickness"] = thick,
                        ["level"] = fidx != null && storyLevelM.ContainsKey(fidx.Value)
                            ? Units.R3(storyLevelM[fidx.Value] + off) : Units.R3(off),
                        ["composite"] = ft != null ? Lookups.NameOf(ft) : null,
                        ["polygonOutline"] = loops.Item1,
                        ["holes"] = loops.Item2,
                    });
                }
                catch { }
            }

            // rooms
            var rooms = (List<object>)snap["rooms"];
            var opts = new SpatialElementBoundaryOptions();
            foreach (var rm in new FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Rooms)
                         .WhereElementIsNotElementType())
            {
                try
                {
                    var sp = rm as SpatialElement;
                    if (sp == null || sp.Area == 0) continue;          // unplaced room
                    var poly = new List<object>();
                    var loops = sp.GetBoundarySegments(opts);
                    if (loops != null && loops.Count > 0)
                        foreach (var seg in loops[0])
                        {
                            var p = seg.GetCurve().GetEndPoint(0);
                            poly.add_xy(p);
                        }
                    rooms.Add(new Dictionary<string, object>
                    {
                        ["guid"] = rm.UniqueId, ["id"] = Lookups.IdStr(rm),
                        ["floor"] = FloorOf(rm, idx),   // contract: every bucket is floor-tagged
                        ["name"] = StrParam(rm, BuiltInParameter.ROOM_NAME),
                        ["numberStr"] = StrParam(rm, BuiltInParameter.ROOM_NUMBER),
                        ["polygonOutline"] = poly,
                    });
                }
                catch { }
            }

            // stairs (best-effort dims + bbox footprint)
            var stairs = (List<object>)snap["stairs"];
            foreach (var st in new FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Stairs)
                         .WhereElementIsNotElementType())
            {
                try
                {
                    var bb = st.get_BoundingBox(null);
                    object fp = bb != null
                        ? new List<object> { Units.R3(Units.FtToM(bb.Min.X)), Units.R3(Units.FtToM(bb.Min.Y)),
                                             Units.R3(Units.FtToM(bb.Max.X)), Units.R3(Units.FtToM(bb.Max.Y)) }
                        : null;
                    // TOTAL rise, matching the Archicad snapshot's General_Height (~2.7 m). The old
                    // STAIRS_ACTUAL_RISER_HEIGHT is ONE step (~0.18 m) — a verifier comparing it to
                    // a 2700 mm spec would emit stair "fixes" every loop, forever.
                    object height = ParamM(st, BuiltInParameter.STAIRS_STAIRS_HEIGHT);
                    if (height == null)
                    {
                        var nr = st.get_Parameter(BuiltInParameter.STAIRS_ACTUAL_NUM_RISERS);
                        var rh = st.get_Parameter(BuiltInParameter.STAIRS_ACTUAL_RISER_HEIGHT);
                        if (nr != null && nr.HasValue && rh != null && rh.HasValue)
                            height = Units.R3(Units.FtToM(nr.AsInteger() * rh.AsDouble()));
                    }
                    object fw = null;                   // real run width (Stairs API), not the bbox
                    if (st is Stairs stObj)
                    {
                        foreach (var rid in stObj.GetStairsRuns())
                        {
                            if (doc.GetElement(rid) is StairsRun run)
                            { fw = Units.R3(Units.FtToM(run.ActualRunWidth)); break; }
                        }
                    }
                    stairs.Add(new Dictionary<string, object>
                    {
                        ["guid"] = st.UniqueId, ["id"] = Lookups.IdStr(st), ["floor"] = FloorOf(st, idx),
                        ["flight_width"] = fw,
                        ["height"] = height,
                        ["footprint"] = fp,
                    });
                }
                catch { }
            }

            // furniture objects
            var objects = (List<object>)snap["objects"];
            foreach (var cat in new[] { BuiltInCategory.OST_Furniture, BuiltInCategory.OST_Casework })
                foreach (FamilyInstance ob in new FilteredElementCollector(doc).OfCategory(cat)
                             .WhereElementIsNotElementType().Cast<FamilyInstance>())
                {
                    try
                    {
                        var lp = ob.Location as LocationPoint;
                        XYZ pt = lp?.Point;
                        var sym = doc.GetElement(ob.GetTypeId());
                        objects.Add(new Dictionary<string, object>
                        {
                            ["guid"] = ob.UniqueId, ["id"] = Lookups.IdStr(ob), ["floor"] = FloorOf(ob, idx),
                            ["type"] = QualifiedType(sym),
                            ["center"] = pt != null
                                ? new List<object> { Units.R3(Units.FtToM(pt.X)), Units.R3(Units.FtToM(pt.Y)) } : null,
                        });
                    }
                    catch { }
                }

            // boundary / reference LINES (room separation lines + model lines): several
            // cases seed the task as drawn boundaries ("the boundaries have already been
            // created"), which no element bucket carries — without this the API-route
            // agent is blind to them (the GUI route sees them on screen).
            var lines = new List<object>();
            snap["lines"] = lines;
            foreach (ModelCurve mc in new FilteredElementCollector(doc).OfClass(typeof(CurveElement))
                         .WhereElementIsNotElementType().OfType<ModelCurve>())
            {
                try
                {
                    var cur = mc.GeometryCurve;
                    if (cur == null || !cur.IsBound) continue;
                    XYZ a = cur.GetEndPoint(0), b = cur.GetEndPoint(1);
                    string kind = mc.Category != null
                        && mc.Category.Id.Value == (long)BuiltInCategory.OST_RoomSeparationLines
                        ? "room_separation" : "model_line";
                    lines.Add(new Dictionary<string, object>
                    {
                        ["guid"] = mc.UniqueId, ["id"] = Lookups.IdStr(mc),
                        ["kind"] = kind,
                        ["beg"] = new List<object> { Units.R3(Units.FtToM(a.X)), Units.R3(Units.FtToM(a.Y)) },
                        ["end"] = new List<object> { Units.R3(Units.FtToM(b.X)), Units.R3(Units.FtToM(b.Y)) },
                    });
                }
                catch { }
            }

            return snap;
        }

        // ---- helpers ----
        private static int? ActiveStoryIndex(Document doc, Dictionary<long, int> idx)
        {
            try
            {
                var gl = (doc.ActiveView as ViewPlan)?.GenLevel;
                if (gl != null && idx.TryGetValue(gl.Id.Value, out int i)) return i;
            }
            catch { }
            // NO fallback to storey 0: with a 3D/other view active (Revit's normal state after
            // a build) the active storey is simply UNKNOWN — flagging the ground floor active
            // would make the whole pipeline silently plan/verify/place against storey 0.
            // No storey flagged -> the pipeline degrades gracefully (planner sees no active
            // story; the actor injects no level). README: activate a plan view before a run.
            return null;
        }

        private static int? FloorOf(Element el, Dictionary<long, int> idx)
        {
            foreach (var bip in new[] { BuiltInParameter.WALL_BASE_CONSTRAINT, BuiltInParameter.FAMILY_LEVEL_PARAM,
                BuiltInParameter.LEVEL_PARAM, BuiltInParameter.SCHEDULE_LEVEL_PARAM,
                BuiltInParameter.STAIRS_BASE_LEVEL_PARAM, BuiltInParameter.ROOM_LEVEL_ID })
            {
                try
                {
                    var p = el.get_Parameter(bip);
                    if (p != null && p.AsElementId() != null && idx.TryGetValue(p.AsElementId().Value, out int i))
                        return i;
                }
                catch { }
            }
            try { if (el.LevelId != null && idx.TryGetValue(el.LevelId.Value, out int j)) return j; } catch { }
            return null;
        }

        private static object ParamM(Element el, params BuiltInParameter[] bips)
        {
            foreach (var bip in bips)
            {
                try
                {
                    var p = el.get_Parameter(bip);
                    // return the value INCLUDING 0: a door sill of 0 is the normal case, and the
                    // old `v != 0` skip both reported it as null (breaking the verifier's
                    // within-tolerance comparison and the opening clash check, which filters on
                    // width) and let the loop fall through to a DIFFERENT parameter's value.
                    if (p != null && p.HasValue) return Units.R3(Units.FtToM(p.AsDouble()));
                }
                catch { }
            }
            return null;
        }

        private static string StrParam(Element el, BuiltInParameter bip)
        {
            try { var p = el.get_Parameter(bip); return p != null ? p.AsString() : null; } catch { return null; }
        }

        /// A world-space direction as a PLAN unit vector [x, y] (null when it is vertical).
        /// Revit recomputes FacingOrientation/HandOrientation after every flip, so unlike the
        /// FacingFlipped/HandFlipped booleans these need no knowledge of the family's default.
        private static object Vec2(XYZ v)
        {
            if (v == null) return null;
            double x = v.X, y = v.Y, L = Math.Sqrt(x * x + y * y);
            if (L < 1e-9) return null;
            return new List<object> { Math.Round(x / L, 4), Math.Round(y / L, 4) };
        }

        /// Which way a wall's build-up faces — the counterpart of the ArchiCAD snapshot's
        /// `orient` (ults/snapshot.py:_fill_wall_orientation), in the SAME shape and units so the
        /// grader's faces / body_side checks work on both backends:
        ///   ref       - the Location Line setting, informational
        ///   left_mm   - how far the wall BODY extends to the LEFT of the location curve
        ///   right_mm  - ... and to the right ("left" = left of the begin->end direction)
        ///   exterior  - [x, y]: Wall.Orientation, the normal pointing out of the EXTERIOR face
        ///               (compound-structure layer 0 is the exterior one). This is exact, so a
        ///               reader should prefer it over inferring the facing from the extents.
        private static object Orient(Wall w, Line line)
        {
            try
            {
                XYZ d = line.GetEndPoint(1) - line.GetEndPoint(0);
                double dl = Math.Sqrt(d.X * d.X + d.Y * d.Y);
                if (dl < 1e-9) return null;
                XYZ leftN = new XYZ(-d.Y / dl, d.X / dl, 0);      // left of begin->end, in plan
                XYZ ext = w.Orientation;                          // exterior-face normal
                double width = Units.FtToM(w.Width) * 1000.0;     // mm

                // distance from the location curve to the EXTERIOR face, per Location Line
                double outside = 0, core = 0;
                var cs = (w.WallType as HostObjAttributes)?.GetCompoundStructure();
                if (cs != null)
                {
                    int first = cs.GetFirstCoreLayerIndex(), last = cs.GetLastCoreLayerIndex();
                    for (int i = 0; i < cs.LayerCount; i++)
                    {
                        double lw = Units.FtToM(cs.GetLayerWidth(i)) * 1000.0;
                        if (i < first) outside += lw; else if (i <= last) core += lw;
                    }
                }
                int ll = 0;
                var lp = w.get_Parameter(BuiltInParameter.WALL_KEY_REF_PARAM);
                if (lp != null && lp.HasValue) ll = lp.AsInteger();
                string refName;
                double dExt;
                switch ((WallLocationLine)ll)
                {
                    case WallLocationLine.FinishFaceExterior: refName = "Finish Face: Exterior"; dExt = 0; break;
                    case WallLocationLine.FinishFaceInterior: refName = "Finish Face: Interior"; dExt = width; break;
                    case WallLocationLine.CoreExterior: refName = "Core Face: Exterior"; dExt = outside; break;
                    case WallLocationLine.CoreInterior: refName = "Core Face: Interior"; dExt = outside + core; break;
                    case WallLocationLine.CoreCenterline: refName = "Core Centerline"; dExt = outside + core / 2.0; break;
                    default: refName = "Wall Centerline"; dExt = width / 2.0; break;
                }
                // A FLIP mirrors the wall about its location curve but leaves WALL_KEY_REF_PARAM
                // untouched — a flipped "Finish Face: Exterior" wall has the curve on its
                // INTERIOR face. Without this, every hand-flipped wall reads its body on the
                // wrong side and the verifier marks a correct wall one thickness off (observed:
                // a GT loop measured right in Revit graded 350 mm short on every flipped wall).
                if (w.Flipped) dExt = width - dExt;
                // The parameter arithmetic above is only a FALLBACK: on hand-drawn walls the
                // location-line + Flipped bookkeeping proved unreliable twice against on-screen
                // measurements (live GT sessions 2026-08-02). The SOLID's own exterior side
                // face is the ground truth, so when it resolves it overrides the estimate.
                try
                {
                    var sideRefs = HostObjectUtils.GetSideFaces(w, ShellLayerType.Exterior);
                    if (sideRefs != null && sideRefs.Count > 0 && ext != null)
                    {
                        var pf = w.GetGeometryObjectFromReference(sideRefs[0]) as PlanarFace;
                        double eL = Math.Sqrt(ext.X * ext.X + ext.Y * ext.Y);
                        if (pf != null && eL > 1e-9)
                        {
                            XYZ eu = new XYZ(ext.X / eL, ext.Y / eL, 0);
                            double g = Units.FtToM((pf.Origin - line.GetEndPoint(0)).DotProduct(eu)) * 1000.0;
                            if (g > -1.0 && g < width + 1.0) dExt = Math.Max(0, Math.Min(width, g));
                        }
                    }
                }
                catch { }
                double dInt = width - dExt;
                bool extLeft = ext != null && (ext.X * leftN.X + ext.Y * leftN.Y) > 0;
                return new Dictionary<string, object>
                {
                    ["ref"] = refName,
                    ["left_mm"] = Math.Round(extLeft ? dExt : dInt, 1),
                    ["right_mm"] = Math.Round(extLeft ? dInt : dExt, 1),
                    // Only for a COMPOUND type: a single-layer wall has no finish side, so
                    // "which way the build-up faces" is vacuous and a reader must not grade it
                    // (same rule as the ArchiCAD snapshot's outward flag). The extents above
                    // stay for every wall — body position is meaningful either way.
                    ["exterior"] = (cs != null && cs.LayerCount > 1) ? Vec2(ext) : null,
                };
            }
            catch { return null; }
        }

        /// "Family: Type" for a family symbol (matches the /favorites naming), plain
        /// type name otherwise — a bare "2150 x 1350mm" says nothing about the family.
        private static string QualifiedType(Element sym)
        {
            if (sym == null) return null;
            var name = Lookups.NameOf(sym);
            try
            {
                if (sym is FamilySymbol fs && fs.Family != null)
                    return fs.Family.Name + ": " + name;
            }
            catch { }
            return name;
        }

        /// A floor's REAL sketch loops: (outer boundary, hole loops). The bbox fallback
        /// hid stairwell openings — exclude_region grading needs the holes.
        private static (List<object>, List<List<object>>) FloorLoops(Document doc, Element fl)
        {
            var holes = new List<List<object>>();
            List<object> outer = null;
            try
            {
                var f = fl as Floor;
                if (f != null && f.SketchId != null && f.SketchId != ElementId.InvalidElementId
                    && doc.GetElement(f.SketchId) is Sketch sk)
                {
                    var loops = new List<(double area, List<object> pts)>();
                    foreach (CurveArray ca in sk.Profile)
                    {
                        var pts = new List<XYZ>();
                        foreach (Curve c in ca)
                        {
                            if (c is Line) pts.Add(c.GetEndPoint(0));
                            else pts.AddRange(c.Tessellate().Take(Math.Max(1, c.Tessellate().Count - 1)));
                        }
                        if (pts.Count < 3) continue;
                        double a = 0;                    // shoelace (abs) to rank loops by size
                        for (int i = 0; i < pts.Count; i++)
                        {
                            var p = pts[i]; var q = pts[(i + 1) % pts.Count];
                            a += p.X * q.Y - q.X * p.Y;
                        }
                        var poly = pts.Select(p => (object)new Dictionary<string, object>
                        { ["x"] = Units.R3(Units.FtToM(p.X)), ["y"] = Units.R3(Units.FtToM(p.Y)) }).ToList();
                        loops.Add((Math.Abs(a) / 2, poly));
                    }
                    if (loops.Count > 0)
                    {
                        loops.Sort((u, v) => v.area.CompareTo(u.area));   // biggest = outer
                        foreach (var l in loops.Skip(1)) holes.Add(l.pts.ToList());
                        outer = loops[0].pts;
                    }
                }
            }
            catch { }
            // A cut made by `create_slab_opening` (doc.Create.NewOpening) is a SEPARATE
            // Opening element, NOT a sketch loop — the sketch-only read above was blind to
            // it, so a perfectly-cut stairwell still graded "slab covers the stair footprint"
            // (the D6/F2/F5 bench cluster's read-side half). Append their boundaries as holes.
            try
            {
                foreach (var oid in fl.GetDependentElements(new ElementClassFilter(typeof(Opening))))
                {
                    if (!(doc.GetElement(oid) is Opening op)) continue;
                    var pts = new List<object>();
                    if (op.IsRectBoundary && op.BoundaryRect != null && op.BoundaryRect.Count >= 2)
                    {
                        XYZ a = op.BoundaryRect[0], b = op.BoundaryRect[1];
                        foreach (var (x, y) in new[] { (a.X, a.Y), (b.X, a.Y), (b.X, b.Y), (a.X, b.Y) })
                            pts.Add(new Dictionary<string, object>
                            { ["x"] = Units.R3(Units.FtToM(x)), ["y"] = Units.R3(Units.FtToM(y)) });
                    }
                    else if (op.BoundaryCurves != null)
                    {
                        foreach (Curve c in op.BoundaryCurves)
                        {
                            var p = c.GetEndPoint(0);
                            pts.Add(new Dictionary<string, object>
                            { ["x"] = Units.R3(Units.FtToM(p.X)), ["y"] = Units.R3(Units.FtToM(p.Y)) });
                        }
                    }
                    if (pts.Count >= 3) holes.Add(pts);
                }
            }
            catch { }
            return (outer ?? (List<object>)BBoxOutline(fl), holes);
        }

        private static object BBoxOutline(Element el)
        {
            try
            {
                var bb = el.get_BoundingBox(null);
                if (bb == null) return new List<object>();
                double x0 = Units.R3(Units.FtToM(bb.Min.X)), y0 = Units.R3(Units.FtToM(bb.Min.Y));
                double x1 = Units.R3(Units.FtToM(bb.Max.X)), y1 = Units.R3(Units.FtToM(bb.Max.Y));
                return new List<object>
                {
                    new Dictionary<string, object> { ["x"] = x0, ["y"] = y0 },
                    new Dictionary<string, object> { ["x"] = x1, ["y"] = y0 },
                    new Dictionary<string, object> { ["x"] = x1, ["y"] = y1 },
                    new Dictionary<string, object> { ["x"] = x0, ["y"] = y1 },
                };
            }
            catch { return new List<object>(); }
        }
    }

    /// small extension so the rooms loop reads cleanly.
    internal static class PolyExt
    {
        public static void add_xy(this List<object> poly, XYZ p) =>
            poly.Add(new Dictionary<string, object> { ["x"] = Units.R3(Units.FtToM(p.X)), ["y"] = Units.R3(Units.FtToM(p.Y)) });
    }
}
