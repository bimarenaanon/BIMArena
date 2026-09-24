using System;
using System.Collections.Generic;
using System.Linq;
using Autodesk.Revit.DB;
using Autodesk.Revit.DB.Architecture;
using Autodesk.Revit.DB.Structure;

namespace BimAgent
{
    /// Maps ONE toolbox action (same names/params as prompt/toolbox.md, lengths in METRES) to the
    /// Revit API, wrapped in a Transaction, returning {ok, guid?, ...} — the same result shape the
    /// Archicad toolbox returns, so the agent's run_actions loop and `$id.field` references work.
    ///
    /// Door/window dimensions are often TYPE-driven (set best-effort on the instance); rooms
    /// need a plan view + separation lines; stairs use StairsEditScope. Boundary/outline edits
    /// follow the Archicad backend's contract: delete + recreate (new guid,
    /// "replaced" carries the old one). replace_door/replace_window swap the family symbol IN
    /// PLACE (ChangeTypeId — Revit can, Archicad can't), keeping the guid.
    public static class Actions
    {
        public static object Run(Document doc, string action, Params p)
        {
            if (doc == null) return Err("no active document");
            if (string.IsNullOrEmpty(action) || !Map.ContainsKey(action))
                return Err("unknown action '" + action + "'");
            if (action == "create_stair")                // StairsEditScope manages its own transactions
                return Safe(() => CreateStair(doc, p));
            if (action == "modify_slab" && p.Pts("polygon_xy") != null)
                return Safe(() => ModifySlabReshape(doc, p));  // SketchEditScope owns its Tx
            return Tx(doc, action, () => Map[action](doc, p));
        }

        private static readonly Dictionary<string, Func<Document, Params, object>> Map =
            new Dictionary<string, Func<Document, Params, object>>
            {
                ["set_stories"] = SetStories, ["create_composite"] = CreateComposite,
                ["create_family_type"] = CreateFamilyType,
                ["create_wall"] = CreateWall,
                ["create_composite_slab"] = CreateCompositeSlab, ["create_slab_opening"] = CreateSlabOpening,
                ["place_door"] = (d, p) => PlaceOpening(d, p, BuiltInCategory.OST_Doors),
                ["place_window"] = (d, p) => PlaceOpening(d, p, BuiltInCategory.OST_Windows),
                ["create_stair"] = (d, p) => CreateStair(d, p),     // also in Map for membership; routed via Safe above
                ["create_zone"] = CreateZone,
                ["modify_wall"] = ModifyWall, ["modify_zone"] = ModifyZone, ["modify_slab"] = ModifySlab,
                ["modify_door"] = ModifyOpening, ["modify_window"] = ModifyOpening,
                ["delete_element"] = DeleteElement,
                ["replace_door"] = (d, p) => ReplaceOpening(d, p, BuiltInCategory.OST_Doors),
                ["replace_window"] = (d, p) => ReplaceOpening(d, p, BuiltInCategory.OST_Windows),
                ["flip_wall"] = FlipWall, ["load_family_type"] = LoadFamilyType,
                ["create_zone_separation_line"] = CreateZoneSeparationLine,
            };

        // ===================================================== atom-vocabulary additions

        /// Wall.Flip — the wall keeps its guid, Revit recomputes Orientation and every
        /// hosted opening's facing. The dedicated flip action (the modify_wall
        /// endpoint-swap route stays for old callers).
        ///
        /// WHICH LINE THE MIRROR IS ABOUT is the caller's choice (`reference_line`, a
        /// Location Line name). Wall.Flip mirrors the body about the CURRENT location line,
        /// and this backend pins walls to Finish Face: Exterior — flipping about a face
        /// translates the whole body by its thickness (measured live: four flips shifted a
        /// whole envelope by one wall width). The DEFAULT is therefore "Wall Centerline":
        /// the location line is temporarily re-anchored there (which re-derives the curve
        /// INSIDE the standing body without moving it), the flip mirrors about it
        /// (orientation swaps, body stays put), and the original anchoring is restored.
        /// Passing another name flips about that line instead; "current" keeps the wall's
        /// own location line (the raw Wall.Flip, body displacement included).
        private static readonly Dictionary<string, int> RefLineNames =
            new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase)
            {
                ["wall centerline"] = 0, ["centerline"] = 0,
                ["core centerline"] = 1,
                ["finish face: exterior"] = 2, ["finish face exterior"] = 2,
                ["finish face: interior"] = 3, ["finish face interior"] = 3,
                ["core face: exterior"] = 4, ["core face exterior"] = 4,
                ["core face: interior"] = 5, ["core face interior"] = 5,
            };

        private static object FlipWall(Document doc, Params p)
        {
            if (!(Lookups.ByGuid(doc, p.Str("guid")) is Wall w)) return Err("wall not found");
            string want = (p.Str("reference_line") ?? "").Trim();
            var refParam = w.get_Parameter(BuiltInParameter.WALL_KEY_REF_PARAM);
            int oldRef = refParam != null && refParam.HasValue ? refParam.AsInteger() : 0;
            int flipRef;
            if (want.Length == 0) flipRef = 0;                       // default: centerline
            else if (want.Equals("current", StringComparison.OrdinalIgnoreCase)
                     || want.Equals("keep", StringComparison.OrdinalIgnoreCase))
                flipRef = oldRef;                                    // raw Wall.Flip semantics
            else if (!RefLineNames.TryGetValue(want, out flipRef))
                return Err("unknown reference_line '" + want + "' — use a Location Line " +
                           "name (e.g. 'Wall Centerline', 'Finish Face: Exterior') or " +
                           "'current'");
            bool retarget = refParam != null && !refParam.IsReadOnly && flipRef != oldRef;
            try
            {
                if (retarget)
                {
                    refParam.Set(flipRef);
                    doc.Regenerate();                      // Flip must see the re-anchored curve
                }
                w.Flip();
            }
            catch (Exception e) { return Err("this wall cannot be flipped: " + e.Message); }
            finally
            {
                try
                {
                    if (retarget)
                    {
                        doc.Regenerate();
                        refParam.Set(oldRef);
                    }
                }
                catch { /* restoring the anchor must not undo a successful flip */ }
            }
            return Ok(("guid", w.UniqueId), ("flipped", true),
                      ("flipped_about", flipRef == 0 ? "Wall Centerline" : want));
        }

        /// Explicitly load a door/window family from the installed library (EnsureSymbol's
        /// resolution surfaced as its own action) — nothing is placed. place_/replace_ load
        /// on demand anyway; this exists for tasks whose deliverable is availability.
        private static object LoadFamilyType(Document doc, Params p)
        {
            var cat = string.Equals(p.Str("element_type"), "Window", StringComparison.OrdinalIgnoreCase)
                ? BuiltInCategory.OST_Windows : BuiltInCategory.OST_Doors;
            var sym = Library.EnsureSymbol(doc, cat, p.Str("family"));
            if (sym == null)
                return Err("no loaded or loadable family matches '" + p.Str("family") + "'");
            return Ok(("guid", sym.UniqueId),
                      ("family", sym.Family != null ? sym.Family.Name : null),
                      ("type", Lookups.NameOf(sym)));
        }

        /// Room separation lines along a polyline — the boundary a room needs where no wall
        /// bounds it (ZoneCore draws a closed ring of them; this is the standalone tool for
        /// an open edge, e.g. splitting an open-plan area into two rooms).
        private static object CreateZoneSeparationLine(Document doc, Params p)
        {
            var poly = p.Pts("polyline_xy") ?? p.Pts("polygon_xy");
            if (poly == null || poly.Count < 2) return Err("polyline needs >= 2 points");
            var lvl = Lookups.LevelByIndex(doc, p.Int("floor_index"));
            if (lvl == null) return Err("no level for the separation line");
            var view = doc.ActiveView;
            var plane = Plane.CreateByNormalAndOrigin(XYZ.BasisZ, new XYZ(0, 0, lvl.Elevation));
            var sp = SketchPlane.Create(doc, plane);
            var pts = poly.Select(pt => Units.Pt(pt[0], pt[1], Units.FtToM(lvl.Elevation))).ToList();
            var ca = new CurveArray();
            for (int i = 0; i < pts.Count - 1; i++) ca.Append(Line.CreateBound(pts[i], pts[i + 1]));
            var made = doc.Create.NewRoomBoundaryLines(sp, ca, view);
            return Ok(("count", made != null ? made.Size : 0));
        }

        // ===================================================== create
        private static object SetStories(Document doc, Params p)
        {
            // SetStories REPLACES the WHOLE storey stack (the Tapir/Archicad contract the planner
            // builds to — planner.prompt always emits the COMPLETE stack). The old code only
            // created/updated the requested levels and LEFT Revit's default Level 1/Level 2 in
            // place, so "create 6 storeys" ended with 8 and the verifier never converged. Reuse
            // any leftover (non-requested) level by RENAMING it into a requested slot first — this
            // consumes the defaults without a delete (a delete of the active view's level could
            // fail and, with the error-rollback preprocessor, discard the whole transaction).
            var stories = p.Objs("stories") ?? new List<Params>();
            var all = Lookups.Levels(doc).ToList();
            var byName = new Dictionary<string, Level>();
            foreach (var l in all) byName[Lookups.NameOf(l)] = l;
            var requested = new HashSet<string>(
                stories.Select(s => s.Str("name")).Where(n => n != null));
            var spare = new Queue<Level>(all.Where(l => !requested.Contains(Lookups.NameOf(l))));
            var outList = new List<object>();
            foreach (var s in stories)
            {
                string nm = s.Str("name");
                double elev = Units.MToFt(s.Num("level") ?? 0.0);
                Level L = (nm != null && byName.ContainsKey(nm)) ? byName[nm] : null;
                if (L == null && spare.Count > 0)            // repurpose a leftover default level
                {
                    L = spare.Dequeue();
                    if (nm != null) try { L.Name = nm; } catch { }
                    L.Elevation = elev;
                }
                else if (L == null) { L = Level.Create(doc, elev); try { L.Name = nm; } catch { } }
                else L.Elevation = elev;
                EnsurePlanView(doc, L);              // GUI "Make Plan View" parity (see helper)
                outList.Add(new Dictionary<string, object> { ["name"] = nm, ["guid"] = L.UniqueId });
            }
            // The model had MORE levels than the requested stack — the surplus violates the
            // whole-stack contract, so delete it (Archicad SetStories parity). CAUTION:
            // doc.Delete(levelId) CASCADES to every dependent element (walls based on it, its
            // plan views) with no error — only the active view's level refuses. Report what
            // each delete took with it so a storey full of geometry never vanishes silently.
            var cascaded = new List<string>();
            while (spare.Count > 0)
            {
                var lvl = spare.Dequeue();
                try
                {
                    var deps = lvl.GetDependentElements(new ElementClassFilter(typeof(Wall)));
                    if (deps != null && deps.Count > 0)
                        cascaded.Add(Lookups.NameOf(lvl) + " (took " + deps.Count + " wall(s) with it)");
                    doc.Delete(lvl.Id);
                }
                catch { }                              // the active view's level may refuse — keep going
            }
            var stRes = Ok(("stories", outList));
            if (cascaded.Count > 0)
                stRes["note"] = "surplus level(s) deleted WITH their hosted geometry: "
                                + string.Join(", ", cascaded);
            return stRes;
        }

        /// GUI "Make Plan View" parity: Level.Create makes NO floor-plan view (that checkbox
        /// is a GUI-tool behavior), which leaves API-created storeys invisible in the Project
        /// Browser and strands the hybrid GUI route's plan-view navigation. Ensure one exists
        /// per requested level; the CALLER supplies the transaction.
        private static void EnsurePlanView(Document doc, Level level)
        {
            var plan = new FilteredElementCollector(doc).OfClass(typeof(ViewPlan)).Cast<ViewPlan>()
                .FirstOrDefault(v => !v.IsTemplate && v.ViewType == ViewType.FloorPlan
                                     && v.GenLevel != null && v.GenLevel.Id == level.Id);
            if (plan == null)
            {
                var vft = new FilteredElementCollector(doc).OfClass(typeof(ViewFamilyType))
                    .Cast<ViewFamilyType>().FirstOrDefault(t => t.ViewFamily == ViewFamily.FloorPlan);
                if (vft == null) return;             // no FloorPlan view family type: nothing to do
                plan = ViewPlan.Create(doc, vft.Id, level.Id);
            }
            try { plan.Name = Lookups.NameOf(level); } catch { }   // name taken: keep the default
        }

        private static object CreateComposite(Document doc, Params p)
        {
            bool isSlab = (p.Strs("use_with") ?? new List<string> { "Wall" }).Contains("Slab");
            return BuildComposite(doc, p.Str("name") ?? "Composite", p.Objs("skins") ?? new List<Params>(), isSlab);
        }

        /// Explicit door/window family-TYPE creation — the type-SETUP path: nothing is placed.
        /// Duplicates a base family type under the requested name and sets its TYPE-level
        /// width/height. A same-named type of the category is resized IN PLACE instead
        /// (BuildComposite's overwrite-by-name parity — an auto-suffixed duplicate would break
        /// every name-graded task). place_/replace_ realise sizes implicitly via SizedSymbol;
        /// this action exists for tasks whose deliverable IS a named type of a given size.
        private static object CreateFamilyType(Document doc, Params p)
        {
            string kind = (p.Str("element_type") ?? "").Trim();
            BuiltInCategory cat;
            if (kind.Equals("Door", StringComparison.OrdinalIgnoreCase)) cat = BuiltInCategory.OST_Doors;
            else if (kind.Equals("Window", StringComparison.OrdinalIgnoreCase)) cat = BuiltInCategory.OST_Windows;
            else return Err("element_type must be \"Door\" or \"Window\"");
            string name = (p.Str("name") ?? "").Trim();
            if (name.Length == 0) return Err("name is required");
            double? wM = p.Num("width"), hM = p.Num("height");

            var existing = Lookups.Symbol(doc, cat, name);
            if (existing != null && Lookups.NameOf(existing) == name)
            {
                var missed0 = new List<string>();
                if (!SetLenM(existing, wM, WidthBips)) missed0.Add("width");
                if (!SetLenM(existing, hM, HeightBips)) missed0.Add("height");
                if (missed0.Count > 0)
                    return Err("type '" + name + "' exists but its " + string.Join("/", missed0)
                               + " is not writable at type level");
                if (!existing.IsActive) { existing.Activate(); doc.Regenerate(); }
                return Ok(("guid", existing.UniqueId), ("name", Lookups.NameOf(existing)),
                          ("family", existing.Family != null ? existing.Family.Name : null),
                          ("overwritten", true));
            }

            var base_ = Library.EnsureSymbol(doc, cat, p.Str("family"));
            if (base_ == null)
                return Err("base family '" + p.Str("family") + "' not found for " + kind
                           + " — pick a name from the family list");
            FamilySymbol dup;
            try { dup = base_.Duplicate(name) as FamilySymbol; }
            catch (Exception e)
            {
                return Err("cannot duplicate '" + Lookups.NameOf(base_) + "' as '" + name + "': "
                           + e.Message);
            }
            if (dup == null) return Err("duplicating '" + Lookups.NameOf(base_) + "' returned no type");
            var missed = new List<string>();
            if (!SetLenM(dup, wM, WidthBips)) missed.Add("width");
            if (!SetLenM(dup, hM, HeightBips)) missed.Add("height");
            if (missed.Count > 0)
            {
                try { doc.Delete(dup.Id); } catch { }   // don't leave a half-sized orphan type
                return Err("the family's " + string.Join("/", missed) + " is not writable at type "
                           + "level — the size cannot be realised on '" + p.Str("family") + "'");
            }
            if (!dup.IsActive) { dup.Activate(); doc.Regenerate(); }
            return Ok(("guid", dup.UniqueId), ("name", Lookups.NameOf(dup)),
                      ("family", dup.Family != null ? dup.Family.Name : null));
        }

        /// Duplicate a Wall/Floor type and set its CompoundStructure from the skins. `isSlab` MUST be
        /// passed explicitly (the slab path has no use_with in its params), and a floor compound
        /// structure needs NoEndCap (walls have end caps; floors/roofs reject them).
        ///
        /// Name collision = OVERWRITE the existing type's compound structure (the Archicad backend's
        /// CreateComposites overwriteExisting=True semantics). The old auto-suffix ("name (2)")
        /// broke every name-graded composite task: a verify->fix re-emission created "Name (2)"
        /// while the verifier kept judging "Name", so the loop could never converge.
        private static object BuildComposite(Document doc, string name, List<Params> skins, bool isSlab)
        {
            ElementType base_ = isSlab ? (ElementType)Lookups.GetFloorType(doc) : Lookups.GetWallType(doc);
            if (base_ == null) return Err("no base type to duplicate");

            var existing = new FilteredElementCollector(doc).OfClass(base_.GetType()).Cast<Element>()
                .FirstOrDefault(t => Lookups.NameOf(t) == name);
            // Overwriting only works on a type that CAN hold a layer stack. A same-named Curtain
            // or Stacked wall type (Revit forbids a second type with that name, so it cannot be
            // duplicated past) would take SetCompoundStructure without ever applying it and come
            // back reporting success. Say so instead — the stale type has to be removed or
            // renamed, and a silent pass here is invisible to the whole verify loop.
            if (existing is WallType exw && exw.Kind != WallKind.Basic)
                return Err($"a {exw.Kind} wall type named '{name}' already exists; a layered " +
                           "(composite) wall type must be a Basic wall — delete or rename that " +
                           "type first");
            var nt = existing is HostObjAttributes ex ? ex : (HostObjAttributes)base_.Duplicate(name);
            var layers = new List<CompoundStructureLayer>();
            foreach (var sk in skins)
            {
                double widthM = sk.Num("thickness") ?? 0.0;
                var mat = Lookups.GetMaterial(doc, sk.Str("material"));
                layers.Add(new CompoundStructureLayer(Units.MToFt(widthM), LayerFunc(sk.Str("type"), widthM),
                    mat != null ? mat.Id : ElementId.InvalidElementId));
            }
            // Revit CompoundStructure needs at least one STRUCTURE (core) layer to form a valid core
            // boundary; if the LLM labelled none as Core, promote the thickest layer so the assembly
            // is valid instead of throwing "CompoundStructure is not valid".
            if (layers.Count > 0 && !layers.Any(l => l.Function == MaterialFunctionAssignment.Structure))
            {
                int thickest = 0;
                for (int i = 1; i < layers.Count; i++)
                    if (layers[i].Width > layers[thickest].Width) thickest = i;
                layers[thickest] = new CompoundStructureLayer(layers[thickest].Width,
                    MaterialFunctionAssignment.Structure, layers[thickest].MaterialId);
            }
            if (layers.Count > 0)
            {
                var cs = CompoundStructure.CreateSimpleCompoundStructure(layers);
                if (isSlab) cs.EndCap = EndCapCondition.NoEndCap;   // floors/roofs use no end cap
                nt.SetCompoundStructure(cs);
            }
            double total = skins.Sum(sk => sk.Num("thickness") ?? 0.0);
            return Ok(("guid", nt.UniqueId), ("total_thickness_m", Units.R3(total)));
        }

        /// Map the plan's skin `type` to a valid Revit layer function. The critical rule Revit
        /// enforces (and the old Core?Structure:Finish?Finish1:Membrane mapping violated): a
        /// MEMBRANE layer MUST be zero-thickness, so a real-thickness skin the LLM tagged "Other"/
        /// null/insulation-but-mislabelled would produce an invalid CompoundStructure. Any layer
        /// that carries thickness therefore gets a thickness-bearing function (Structure / Insulation
        /// / Finish1 / Substrate); only a zero-width skin may be a Membrane.
        private static MaterialFunctionAssignment LayerFunc(string type, double widthM)
        {
            string t = (type ?? "").Trim().ToLowerInvariant();
            if (t == "core" || t.Contains("struct")) return MaterialFunctionAssignment.Structure;
            if (t.Contains("insul") || t.Contains("thermal")) return MaterialFunctionAssignment.Insulation;
            if (t.Contains("finish")) return MaterialFunctionAssignment.Finish1;
            if (widthM <= 1e-9) return MaterialFunctionAssignment.Membrane;
            return MaterialFunctionAssignment.Substrate;
        }

        private static object CreateCompositeWall(Document doc, Params p)
        {
            var wt = Lookups.GetWallType(doc, p.Str("composite_name"), p.Str("composite_guid"));
            if (wt == null)
                return Err(p.Str("composite_name") != null
                    ? "no existing wall type named '" + p.Str("composite_name") + "'"
                    : "no wall type");
            double z = p.Num("z") ?? 0.0;
            var lvl = Lookups.LevelForZ(doc, z);
            if (lvl == null) return Err("no levels in the project");
            var b = p.Arr("begin"); var e = p.Arr("end");
            if (b == null || e == null) return Err("begin and end are required");
            var line = Line.CreateBound(Units.Pt(b[0], b[1], z), Units.Pt(e[0], e[1], z));
            double h = Units.MToFt(p.Num("height") ?? 2.7);
            var w = Wall.Create(doc, line, wt.Id, lvl.Id, h, 0.0, false, false);
            var refNote = SetWallReference(doc, w, line, p.Str("reference"));
            var res = Ok(("guid", w.UniqueId));
            if (refNote != null) res["note"] = refNote;
            return res;
        }

        /// Merged create_walls/create_composite_wall (2026-08-03): ONE wall per call, the
        /// structure picked by the params — composite_name/composite_guid -> that layered type;
        /// material and/or thickness -> a basic single-layer type (duplicated from the default,
        /// ModifyWall's building_material parity — the old create_walls silently IGNORED both);
        /// nothing -> the default basic type. Always returns one referenceable guid.
        private static object CreateWall(Document doc, Params p)
        {
            if (p.Str("composite_name") != null || p.Str("composite_guid") != null)
            {
                if (p.Str("material") != null)
                    return Err("give ONE structure: composite_name/composite_guid OR material — not both");
                return CreateCompositeWall(doc, p);
            }
            var wt = Lookups.GetWallType(doc);
            if (wt == null) return Err("no wall type");
            if (p.Str("material") != null || p.Num("thickness") != null)
            {
                var mat = p.Str("material") != null ? Lookups.GetMaterial(doc, p.Str("material")) : null;
                if (p.Str("material") != null && mat == null)
                    return Err("no material named '" + p.Str("material") + "'");
                var cs0 = wt.GetCompoundStructure();
                double width = p.Num("thickness") != null ? Units.MToFt(p.Num("thickness").Value)
                             : (cs0 != null ? cs0.GetWidth() : Units.MToFt(0.2));
                var matId = mat != null ? mat.Id
                          : (cs0 != null && cs0.GetLayers().Count > 0 ? cs0.GetLayers()[0].MaterialId
                                                                      : ElementId.InvalidElementId);
                string wanted = "Basic " + (mat != null ? Lookups.NameOf(mat) + " " : "")
                              + Math.Round(Units.FtToM(width) * 1000) + "mm";
                // reuse a type this convention already created — 10 same-spec walls must not
                // mint 10 duplicate types
                var reuse = new FilteredElementCollector(doc).OfClass(typeof(WallType))
                    .Cast<WallType>().FirstOrDefault(t => t.Kind == WallKind.Basic
                                                          && Lookups.NameOf(t) == wanted);
                if (reuse != null) wt = reuse;
                else
                {
                    var nt = (WallType)wt.Duplicate(UniqueTypeName(doc, typeof(WallType), wanted));
                    var layer = new CompoundStructureLayer(width,
                        MaterialFunctionAssignment.Structure, matId);
                    nt.SetCompoundStructure(CompoundStructure.CreateSimpleCompoundStructure(
                        new List<CompoundStructureLayer> { layer }));
                    wt = nt;
                }
            }
            double z = p.Num("z") ?? 0.0;
            var lvl = Lookups.LevelForZ(doc, z);
            if (lvl == null) return Err("no levels in the project");
            var b = p.Arr("begin"); var e = p.Arr("end");
            if (b == null || e == null) return Err("begin and end are required");
            var line = Line.CreateBound(Units.Pt(b[0], b[1], z), Units.Pt(e[0], e[1], z));
            double h = Units.MToFt(p.Num("height") ?? 2.7);
            var w = Wall.Create(doc, line, wt.Id, lvl.Id, h, 0.0, false, false);
            var refNote = SetWallReference(doc, w, line, p.Str("reference"));
            var res = Ok(("guid", w.UniqueId));
            if (refNote != null) res["note"] = refNote;
            return res;
        }

        /// Which line of the wall the caller's coordinates are — the `reference` tool param,
        /// mapped to this application's Location Line. Unknown/absent = the documented default.
        private static WallLocationLine RefLine(string reference, out ShellLayerType? seat)
        {
            switch ((reference ?? "").Trim().ToLowerInvariant())
            {
                case "center":
                case "centre":
                    seat = null;                        // the curve IS the centreline: nothing to seat
                    return WallLocationLine.WallCenterline;
                case "inside":
                    seat = ShellLayerType.Interior;
                    return WallLocationLine.FinishFaceInterior;
                default:
                    seat = ShellLayerType.Exterior;
                    return WallLocationLine.FinishFaceExterior;
            }
        }

        /// Place the wall against `line` in the convention `reference` names, with the outer skin
        /// facing RIGHT of begin->end (the shared cross-application facing contract). Wall.Create
        /// always hands back a CENTRELINE-located wall whose exterior faces the LEFT of the draw
        /// direction, so both have to be corrected here.
        ///
        /// Three silent failure modes the 2026-08 bench walked into, in the order they were found:
        ///   1. `lc.Curve = line` THROWS on a wall that auto-joined a neighbour at a corner
        ///      (every loop wall after the first) — the blanket catch swallowed it and the wall
        ///      stayed at the centerline position, exactly t/2 off, reported ok.
        ///   2. Revit's default exterior side is the LEFT of the draw direction — the OPPOSITE
        ///      of the contract — so even a successful pin put the body on the wrong side.
        ///   3. (2026-08-12) WALL_KEY_REF_PARAM is a LABEL, not a move — see SeatFace. Setting it
        ///      and pinning the curve left EVERY wall half a thickness out, and the pin's own
        ///      check could not see it.
        /// So: flip from the LIVE Orientation (never assumed), pin the curve (releasing corner
        /// joins when refused), then seat the named FACE by measuring the solid. Any residual
        /// comes back as a note, never swallowed.
        private static string SetWallReference(Document doc, Wall w, Line line, string reference)
        {
            var notes = new List<string>();
            try
            {
                ShellLayerType? shell;
                WallLocationLine ll = RefLine(reference, out shell);
                XYZ d = line.GetEndPoint(1) - line.GetEndPoint(0);
                double L = Math.Sqrt(d.X * d.X + d.Y * d.Y);
                XYZ rightN = L > 1e-9 ? new XYZ(d.Y / L, -d.X / L, 0) : null;
                doc.Regenerate();                       // Orientation is stale until regenerated
                if (rightN != null && w.Orientation != null
                    && (w.Orientation.X * rightN.X + w.Orientation.Y * rightN.Y) < 0)
                    w.Flip();                           // exterior must face RIGHT of begin->end
                var pr = w.get_Parameter(BuiltInParameter.WALL_KEY_REF_PARAM);
                if (pr != null && !pr.IsReadOnly)
                    pr.Set((int)ll);                    // a label for readers; it moves nothing
                doc.Regenerate();
                string pin = PinCurve(doc, w, line);    // curve ON the coords, verified
                if (pin != null) notes.Add(pin);
                if (shell != null)                      // ... and the named FACE on them too
                {
                    string seat = SeatFace(doc, w, line, shell.Value);
                    if (seat != null) notes.Add(seat);
                }
            }
            catch (Exception e) { notes.Add("wall reference-line placement failed: " + e.Message); }
            return notes.Count > 0 ? string.Join("; ", notes) : null;
        }

        /// Signed distance from `line` to one of the wall's side FACES, measured along the
        /// exterior normal, in feet (positive = the face lies outside the line). Read off the
        /// SOLID, which is the only trustworthy source — see SeatFace. Null when unresolvable.
        private static double? FaceGap(Wall w, Line line, ShellLayerType shell)
        {
            try
            {
                XYZ ext = w.Orientation;
                if (ext == null) return null;
                double eL = Math.Sqrt(ext.X * ext.X + ext.Y * ext.Y);
                if (eL < 1e-9) return null;
                XYZ eu = new XYZ(ext.X / eL, ext.Y / eL, 0);
                var refs = HostObjectUtils.GetSideFaces(w, shell);
                if (refs == null || refs.Count == 0) return null;
                var pf = w.GetGeometryObjectFromReference(refs[0]) as PlanarFace;
                if (pf == null) return null;
                return (pf.Origin - line.GetEndPoint(0)).DotProduct(eu);
            }
            catch { return null; }
        }

        /// The face a LIVE wall's own Location Line names — so a MOVE re-seats the wall in the
        /// convention it was created with instead of forcing every moved wall to the outside.
        private static ShellLayerType? SeatOfWall(Wall w)
        {
            try
            {
                var pr = w.get_Parameter(BuiltInParameter.WALL_KEY_REF_PARAM);
                if (pr == null || !pr.HasValue) return ShellLayerType.Exterior;
                switch ((WallLocationLine)pr.AsInteger())
                {
                    case WallLocationLine.FinishFaceExterior:
                    case WallLocationLine.CoreExterior:
                        return ShellLayerType.Exterior;
                    case WallLocationLine.FinishFaceInterior:
                    case WallLocationLine.CoreInterior:
                        return ShellLayerType.Interior;
                    default:
                        return null;                    // centreline: the curve already IS it
                }
            }
            catch { return ShellLayerType.Exterior; }
        }

        /// Put the named FACE of the wall on `line`.
        ///
        /// WALL_KEY_REF_PARAM is a LABEL, not a move: setting it on an EXISTING wall re-labels
        /// which reference the location curve represents but does NOT re-anchor the curve, so a
        /// wall from Wall.Create stays geometrically CENTRELINE-located whatever it says.
        /// PinCurve then lands that centreline on the plan line and the body sits half a thickness
        /// off — and PinCurve's own check compares the CURVE with the line it was just set to, so
        /// it always passed. Measured live on B_element_creation2 (2026-08-12): all six loop walls
        /// reported ll=FinishFaceExterior with the exterior face +175 mm off a 350 mm type, i.e.
        /// the whole envelope 175 mm oversize, and the grader's SW-corner alignment then split
        /// that uniform error into "half the walls perfect, half 350 mm out".
        ///
        /// So: measure the face off the solid and re-pin against the residual until it lands.
        /// Iterates because a joined wall's regeneration can shift it again.
        private static string SeatFace(Document doc, Wall w, Line line, ShellLayerType shell)
        {
            string what = shell == ShellLayerType.Interior ? "interior" : "exterior";
            double tol = Units.MToFt(0.001);
            Line pinned = line;
            double? gap = null;
            for (int pass = 0; pass < 3; pass++)
            {
                doc.Regenerate();
                gap = FaceGap(w, line, shell);
                if (gap == null)
                    return "could not read the wall's " + what + " face — seating skipped";
                if (Math.Abs(gap.Value) <= tol) return null;
                XYZ ext = w.Orientation;
                double eL = Math.Sqrt(ext.X * ext.X + ext.Y * ext.Y);
                if (eL < 1e-9)
                    return "wall orientation is vertical — cannot seat the " + what + " face";
                XYZ shift = new XYZ(ext.X / eL, ext.Y / eL, 0) * -gap.Value;
                pinned = Line.CreateBound(pinned.GetEndPoint(0) + shift, pinned.GetEndPoint(1) + shift);
                string note = PinCurve(doc, w, pinned);
                if (note != null) return note;
            }
            return "wall " + what + " face is " + Math.Round(Units.FtToM(Math.Abs(gap ?? 0)) * 1000)
                 + " mm off the given coordinates (reference-line seating did not converge)";
        }

        /// Set a wall's location curve so it ACTUALLY lands on `line`, releasing corner joins
        /// when Revit refuses the set because of them ("can't keep elements joined"), and
        /// verifying the result LATERALLY (joins legitimately extend the curve axially, so only
        /// the perpendicular residual is an error). Returns a note on any residual — the caller
        /// must surface it; this is the failure the whole wall-offset cluster hid behind.
        private static string PinCurve(Document doc, Wall w, Line line)
        {
            if (!(w.Location is LocationCurve lc)) return "wall has no location curve";
            try { lc.Curve = line; }
            catch
            {
                try
                {
                    WallUtils.DisallowWallJoinAtEnd(w, 0);
                    WallUtils.DisallowWallJoinAtEnd(w, 1);
                    lc.Curve = line;
                }
                catch (Exception e2) { return "cannot move the wall onto the given line: " + e2.Message; }
            }
            doc.Regenerate();
            var got = (w.Location as LocationCurve)?.Curve as Line;
            XYZ d = line.GetEndPoint(1) - line.GetEndPoint(0);
            double L = Math.Sqrt(d.X * d.X + d.Y * d.Y);
            if (got == null || L < 1e-9) return null;
            XYZ n = new XYZ(-d.Y / L, d.X / L, 0);
            double lat = Math.Abs((got.GetEndPoint(0).X - line.GetEndPoint(0).X) * n.X
                                + (got.GetEndPoint(0).Y - line.GetEndPoint(0).Y) * n.Y);
            if (lat > Units.MToFt(0.005))
                return "wall line is " + Math.Round(Units.FtToM(lat) * 1000)
                     + " mm off the given coordinates (location pin did not take)";
            return null;
        }

        private static object CreateCompositeSlab(Document doc, Params p)
        {
            FloorType ft;
            object compGuid, totalM;
            string reuse = p.Str("composite_name");
            var skins = p.Objs("skins");
            if (!string.IsNullOrEmpty(reuse))
            {
                // REUSE an existing floor type by name — THE form the BUILD `slabs` task uses
                // (mirrors the Archicad backend + create_composite_wall). Fail loudly on a
                // name miss: composite tasks are graded by NAME, so building with an arbitrary
                // type while returning ok would be invisible to the whole verify loop.
                ft = Lookups.GetFloorType(doc, reuse);
                if (ft == null) return Err("no existing floor type named '" + reuse + "'");
                compGuid = ft.UniqueId;
                var cs = ft.GetCompoundStructure();
                totalM = cs != null ? (object)Units.R3(Units.FtToM(cs.GetWidth())) : null;
            }
            else
            {
                var comp = BuildComposite(doc, p.Str("name") ?? "Slab",
                                          skins ?? new List<Params>(), true)
                           as Dictionary<string, object>;
                if (comp == null || !(bool)comp["ok"]) return comp;
                ft = Lookups.ByGuid(doc, (string)comp["guid"]) as FloorType;
                if (ft == null) return Err("composite was created but is not a floor type");
                compGuid = comp["guid"];
                totalM = comp["total_thickness_m"];
            }
            double z = p.Num("level") ?? 0.0;
            var lvl = Lookups.LevelForZ(doc, z);
            if (lvl == null) return Err("no levels in the project");
            var loop = Loop(p.Pts("polygon_xy"), z);
            var floor = Floor.Create(doc, new List<CurveLoop> { loop }, ft.Id, lvl.Id);
            return Ok(("slab_guid", floor.UniqueId), ("composite_guid", compGuid),
                      ("total_thickness_m", totalM));
        }

        private static object CreateSlabOpening(Document doc, Params p)
        {
            var slab = Lookups.ByGuid(doc, p.Str("slab_guid"));
            if (slab == null) return Err("slab not found");
            var bxy = p.Arr("base_xy");
            if (bxy == null || bxy.Length < 2) return Err("base_xy must be a point [x, y]");
            double x = bxy[0], y = bxy[1], w = p.Num("width") ?? 0, h = p.Num("height") ?? 0;
            // The profile must lie in the HOST's plane. The old code trusted the caller's z
            // (default 0), so an opening in any upper-storey slab was created at z=0, never
            // intersected the slab, and cut NOTHING while returning ok (the D6/F2/F5 bench
            // cluster: "slab covers 100% of the stair footprint" after a successful call).
            // The hole follows its slab (the Archicad contract), so derive z from the slab
            // itself and ignore any caller z.
            double zft = 0;
            if (slab is Floor fslab)
            {
                var flvl = doc.GetElement(fslab.LevelId) as Level;
                zft = (flvl != null ? flvl.Elevation : 0)
                    + (fslab.get_Parameter(BuiltInParameter.FLOOR_HEIGHTABOVELEVEL_PARAM)
                            ?.AsDouble() ?? 0);
            }
            var c = new[]
            {
                new XYZ(Units.MToFt(x), Units.MToFt(y), zft),
                new XYZ(Units.MToFt(x + w), Units.MToFt(y), zft),
                new XYZ(Units.MToFt(x + w), Units.MToFt(y + h), zft),
                new XYZ(Units.MToFt(x), Units.MToFt(y + h), zft),
            };
            var ca = new CurveArray();
            for (int i = 0; i < 4; i++) ca.Append(Line.CreateBound(c[i], c[(i + 1) % 4]));
            var op = doc.Create.NewOpening(slab, ca, true);
            return Ok(("guid", op.UniqueId));
        }

        private static object PlaceOpening(Document doc, Params p, BuiltInCategory cat)
        {
            var host = Lookups.WallByRef(doc, p.Str("host"));
            if (host == null) return Err("host wall '" + p.Str("host") + "' not found");
            // resolve the requested type: load it from the Revit library if it isn't in the project
            // yet (e.g. a DOUBLE door when only single-flush is loaded); else fall back to any loaded.
            var sym = Library.EnsureSymbol(doc, cat, p.Str("favorite"));
            if (sym == null)
            {
                sym = Lookups.Symbol(doc, cat, p.Str("favorite"));
                if (sym != null && !sym.IsActive) { sym.Activate(); doc.Regenerate(); }
            }
            if (sym == null) return Err("no family symbol for " + cat + " (favorite=" + p.Str("favorite") + ")");
            // realise the requested size at TYPE level (matching sibling type / duplicated type) —
            // door/window W/H are type parameters, the instance SetLenM below no-ops on them
            sym = SizedSymbol(doc, sym, p.Num("width"), p.Num("height"));
            if (sym == null)
                return Err("cannot realise the requested width/height on family '" + p.Str("favorite")
                           + "' — no matching type and the size parameters are not writable on a duplicate");
            var lvl = host.LevelId != ElementId.InvalidElementId ? doc.GetElement(host.LevelId) as Level
                                                                 : Lookups.LevelForZ(doc, 0.0);
            double elev = lvl != null ? lvl.Elevation : 0.0;
            var line = (host.Location as LocationCurve)?.Curve as Line;
            if (line == null)                          // an arc/curved wall would NRE below —
                return Err("host wall has no straight location curve");  // fail with a real message
            XYZ b = line.GetEndPoint(0);
            XYZ d = line.GetEndPoint(1) - b;
            double dl = d.GetLength(); if (dl == 0) dl = 1;
            XYZ dir = d / dl;
            var center = p.Arr("center");
            if (center == null) return Err("center is required");
            XYZ raw = Units.Pt(center[0], center[1], 0.0);
            double t = (raw - b).DotProduct(dir);
            // same guard as the Archicad backend's _place_opening: a centre projecting outside
            // the host's span means a WRONG host wall / wrong point — this exact error message
            // is what triggers the pipeline's one-shot wrong-host repair.
            if (t < -1e-6 || t > dl + 1e-6)
                return Err("opening centre projects " + Units.R3(Units.FtToM(Math.Max(-t, t - dl)))
                           + " m outside the host wall's span (" + Units.R3(Units.FtToM(dl))
                           + " m long) — wrong host wall or wrong centre point");
            XYZ pt = new XYZ((b + dir * t).X, (b + dir * t).Y, elev);
            var inst = doc.Create.NewFamilyInstance(pt, sym, host, lvl, StructuralType.NonStructural);
            var missed = new List<string>();
            // instance set covers instance-sized families; TypeCarries covers type-sized ones
            // (SizedSymbol above already realised those) — missed only when NEITHER holds
            if (!SetLenM(inst, p.Num("width"), WidthBips) && !TypeCarries(inst.Symbol, p.Num("width"), WidthBips)) missed.Add("width");
            if (!SetLenM(inst, p.Num("height"), HeightBips) && !TypeCarries(inst.Symbol, p.Num("height"), HeightBips)) missed.Add("height");
            if (!SetLenM(inst, p.Num("sill"), BuiltInParameter.INSTANCE_SILL_HEIGHT_PARAM)) missed.Add("sill");
            var swingNote = ApplySwing(doc, inst, p);
            var res = WithDimNote(Ok(("guid", inst.UniqueId)), missed);
            if (swingNote != null)
                res["note"] = res.ContainsKey("note") ? res["note"] + "; " + swingNote : swingNote;
            return res;
        }

        private static object CreateZone(Document doc, Params p)
        {
            var lvl = Lookups.LevelByIndex(doc, p.Int("floor_index"));
            string number = p.Has("number") ? (p.Str("number") ?? p.Int("number").ToString()) : null;
            return ZoneCore(doc, p.Pts("polygon_xy"), lvl, p.Str("name"), number);
        }

        /// Shared room-authoring core: separation lines along the polygon + a seed-point room —
        /// used by create_zone AND by modify_zone's boundary path (delete + recreate).
        private static object ZoneCore(Document doc, List<double[]> poly, Level lvl,
                                       string name, string number)
        {
            if (poly == null || poly.Count < 3) return Err("polygon needs >= 3 points");
            if (lvl == null) return Err("no level for the room");
            var view = doc.ActiveView;
            var plane = Plane.CreateByNormalAndOrigin(XYZ.BasisZ, new XYZ(0, 0, lvl.Elevation));
            var sp = SketchPlane.Create(doc, plane);
            var pts = poly.Select(pt => Units.Pt(pt[0], pt[1], Units.FtToM(lvl.Elevation))).ToList();
            if (!pts[0].IsAlmostEqualTo(pts[pts.Count - 1])) pts.Add(pts[0]);
            var ca = new CurveArray();
            for (int i = 0; i < pts.Count - 1; i++) ca.Append(Line.CreateBound(pts[i], pts[i + 1]));
            try { doc.Create.NewRoomBoundaryLines(sp, ca, view); } catch { /* walls may already bound it */ }
            doc.Regenerate();
            double cx = poly.Average(pt => pt[0]), cy = poly.Average(pt => pt[1]);
            var rm = doc.Create.NewRoom(lvl, new UV(Units.MToFt(cx), Units.MToFt(cy)));
            if (rm == null) return Err("room seed point not in an enclosed region");
            // get_Parameter returns NULL for a parameter the element does not carry — setting
            // through it would NRE and lose the room that was just created successfully.
            SetStr(rm, BuiltInParameter.ROOM_NAME, name);
            SetStr(rm, BuiltInParameter.ROOM_NUMBER, number);
            return Ok(("guid", rm.UniqueId));
        }

        /// Set a string parameter when the element actually has it and it is writable.
        private static void SetStr(Element el, BuiltInParameter bip, string value)
        {
            if (value == null) return;
            var pr = el.get_Parameter(bip);
            if (pr != null && !pr.IsReadOnly) { try { pr.Set(value); } catch { } }
        }

        private static object CreateStair(Document doc, Params p)
        {
            var baseLine = p.Pts("baseline_xy");
            return CreateStairCore(doc, baseLine, p.Num("z") ?? 0.0, p.Num("flight_width"));
        }

        private static object CreateStairCore(Document doc, List<double[]> baseLine, double z,
                                              double? width)
        {
            // baseline_xy is the walking line: 2 points -> a straight stair; 3+ points -> one straight
            // RUN per segment (L = 2 runs / one 90° turn, U = 3 runs / two turns). Revit's
            // stairs-by-component model creates the LANDINGS between consecutive runs and distributes
            // the risers across all runs to span base->top level on Commit.
            if (baseLine == null || baseLine.Count < 2) return Err("baseline needs >= 2 points");
            var blvl = Lookups.LevelForZ(doc, z);
            if (blvl == null) return Err("no levels in the project — run the stories task first");
            var tlvl = Lookups.Levels(doc).FirstOrDefault(l => l.Elevation > blvl.Elevation + 1e-6);
            if (tlvl == null)
                // Revit stairs span LEVEL to LEVEL; starting the edit scope with top == base
                // builds a zero-height stair that fails at commit with an opaque error.
                return Err("no level above '" + Lookups.NameOf(blvl) + "' for the stair's top — "
                           + "create the upper storey first (run the stories task); total_height "
                           + "alone cannot set a Revit stair's top");

            using (var scope = new StairsEditScope(doc, "bim-agent: stair"))
            {
                try
                {
                    ElementId sid = scope.Start(blvl.Id, tlvl.Id);
                    var runs = new List<StairsRun>();
                    var runsHandler = new WarningSwallower();
                    using (var t = new Transaction(doc, "bim-agent: stair runs"))
                    {
                        t.Start();
                        var fo = t.GetFailureHandlingOptions()
                                  .SetFailuresPreprocessor(runsHandler);
                        t.SetFailureHandlingOptions(fo);
                        for (int i = 0; i + 1 < baseLine.Count; i++)
                        {
                            var a = Units.Pt(baseLine[i][0], baseLine[i][1], z);
                            var b = Units.Pt(baseLine[i + 1][0], baseLine[i + 1][1], z);
                            var run = StairsRun.CreateStraightRun(doc, sid, Line.CreateBound(a, b), StairsRunJustification.Center);
                            if (width != null) run.ActualRunWidth = Units.MToFt(width.Value);
                            runs.Add(run);
                        }
                        // connect consecutive runs with an automatic landing (the L/U turns); ignore a
                        // pair that can't (adjacent runs are auto-landed on commit anyway).
                        for (int i = 0; i + 1 < runs.Count; i++)
                        {
                            try { StairsLanding.CreateAutomaticLanding(doc, runs[i].Id, runs[i + 1].Id); }
                            catch { }
                        }
                        // an un-ignorable Revit error rolls the runs transaction back
                        // (ProceedWithRollBack) — committing the scope over a run-less stair
                        // would surface only as a NullReferenceException with the real error lost.
                        if (t.Commit() != TransactionStatus.Committed)
                        {
                            scope.Cancel();
                            return Err(runsHandler.Errors.Count > 0
                                       ? "stair runs: " + string.Join("; ", runsHandler.Errors)
                                       : "stair runs transaction rolled back");
                        }
                    }
                    var scopeHandler = new WarningSwallower();
                    scope.Commit(scopeHandler);                // the stairs id came from Start
                    var el = doc.GetElement(sid);
                    if (el == null)                            // scope commit failed/rolled back
                        return Err(scopeHandler.Errors.Count > 0
                                   ? "stair commit: " + string.Join("; ", scopeHandler.Errors)
                                   : "stair edit-scope commit failed (no stair created)");
                    return Ok(("guid", el.UniqueId), ("runs", runs.Count));
                }
                catch (Exception e) { try { scope.Cancel(); } catch { } return Err("stair: " + e.Message); }
            }
        }

        // ===================================================== modify / delete
        private static object ModifyWall(Document doc, Params p)
        {
            if (!(Lookups.ByGuid(doc, p.Str("guid")) is Wall w)) return Err("wall not found");
            int structureArgs = (p.Str("composite_guid") != null ? 1 : 0)
                + (p.Str("composite_name") != null ? 1 : 0)
                + (p.Str("building_material") != null ? 1 : 0);
            if (structureArgs > 1)
                return Err("give ONE of composite_guid / composite_name / building_material");
            var begin = p.Arr("begin"); var end = p.Arr("end");
            bool flipped = false;
            if (begin != null || end != null)
            {
                // either endpoint alone is a valid move (Archicad parity) — keep the other
                // from the current location curve instead of silently dropping the change.
                var cur = (w.Location as LocationCurve)?.Curve as Line;
                if (cur == null) return Err("wall has no straight location curve");
                double z = Units.FtToM(cur.GetEndPoint(0).Z);
                XYZ nb = begin != null ? Units.Pt(begin[0], begin[1], z) : cur.GetEndPoint(0);
                XYZ ne = end != null ? Units.Pt(end[0], end[1], z) : cur.GetEndPoint(1);
                // The documented FLIP gesture is a begin/end swap (Archicad parity), but Revit
                // refuses a reversed location curve outright ("Element is reversed") — so a
                // reversed-DIRECTION request must become Wall.Flip(). Detected by direction,
                // not endpoint equality: joins EXTEND a joined wall's location curve past the
                // authored endpoints (± half the neighbour's width), so the swapped points
                // rarely match the live endpoints exactly.
                double tol = Units.MToFt(0.005);
                XYZ c0 = cur.GetEndPoint(0), c1 = cur.GetEndPoint(1);
                XYZ axis = (c1 - c0).Normalize();
                XYZ req = ne - nb;
                if (req.GetLength() > 1e-9 && axis.DotProduct(req.Normalize()) < -0.999)
                {
                    w.Flip();
                    flipped = true;
                    XYZ t = nb; nb = ne; ne = t;   // realign the request with the curve direction
                }
                double latB = (nb - c0 - axis * (nb - c0).DotProduct(axis)).GetLength();
                double latE = (ne - c0 - axis * (ne - c0).DotProduct(axis)).GetLength();
                bool sameEnds = nb.DistanceTo(c0) < tol && ne.DistanceTo(c1) < tol;
                // Skip the curve set when nothing moves laterally: after a flip, axial-only
                // differences are join extensions, not a move; and even an IDENTICAL curve
                // set is refused on a joined wall ("Can't keep elements joined").
                if (!(sameEnds || (flipped && latB < tol && latE < tol)))
                {
                    // PinCurve, not a raw curve set: a JOINED wall refuses the set outright
                    // ("can't keep elements joined") — release the corner joins and verify the
                    // wall really landed (a residual comes back as an error, never silently).
                    var want = Line.CreateBound(nb, ne);
                    string pin = PinCurve(doc, w, want);
                    if (pin != null) return Err(pin);
                    // ... and seat the FACE on the request, like the create path: the location
                    // curve is not that face however WALL_KEY_REF_PARAM reads (see SeatFace), so
                    // a moved wall would otherwise land half a thickness off exactly like a
                    // created one did. WHICH face is the wall's own Location Line — a move must
                    // not silently re-reference a wall the caller created on its centreline.
                    ShellLayerType? shell = SeatOfWall(w);
                    if (shell != null)
                    {
                        string seat = SeatFace(doc, w, want, shell.Value);
                        if (seat != null) return Err(seat);
                    }
                }
            }
            string heightNote = null;
            if (p.Num("height") != null)
            {
                double wantH = Units.MToFt(p.Num("height").Value);
                var pr = w.get_Parameter(BuiltInParameter.WALL_USER_HEIGHT_PARAM);
                if (pr != null && pr.IsReadOnly)
                {
                    // Top-constrained wall: the unconnected height is read-only, so the old code
                    // returned a note and the height silently never changed (the C10 bench
                    // cluster: 8 walls "set" to 3500 all still 4000). Unconnect the top first
                    // (WALL_HEIGHT_TYPE = InvalidElementId), which frees the height parameter.
                    var top = w.get_Parameter(BuiltInParameter.WALL_HEIGHT_TYPE);
                    if (top != null && !top.IsReadOnly)
                    {
                        top.Set(ElementId.InvalidElementId);
                        doc.Regenerate();
                        pr = w.get_Parameter(BuiltInParameter.WALL_USER_HEIGHT_PARAM);
                    }
                }
                if (pr != null && !pr.IsReadOnly)
                {
                    pr.Set(wantH);
                    doc.Regenerate();
                    double got = w.get_Parameter(BuiltInParameter.WALL_USER_HEIGHT_PARAM)?.AsDouble() ?? 0;
                    if (Math.Abs(got - wantH) > Units.MToFt(0.002))
                        return Err("height set did not take effect (wall reports "
                                   + Math.Round(Units.FtToM(got) * 1000) + " mm)");
                }
                else return Err("height not applied — no writable height parameter on this wall "
                                + "(top constraint could not be unconnected)");
            }
            if (p.Str("composite_guid") != null)
            {
                var wt = Lookups.GetWallType(doc, guid: p.Str("composite_guid"));
                if (wt == null)                        // a bad guid must fail, not silently skip
                    return Err("no wall type with guid '" + p.Str("composite_guid") + "'");
                w.WallType = wt;
            }
            if (p.Str("composite_name") != null)       // switch to an EXISTING type by NAME (the
            {                                          // modify twin of create's composite_name)
                var wt = Lookups.GetWallType(doc, name: p.Str("composite_name"));
                if (wt == null)                        // strict — no arbitrary-type fallback
                    return Err("no wall type named '" + p.Str("composite_name") + "'");
                w.WallType = wt;
            }
            if (p.Str("building_material") != null)
            {
                // mirror the Archicad structureType="Basic" semantics: duplicate the wall's current
                // type into a single-layer structure carrying this material, keeping the thickness.
                var mat = Lookups.GetMaterial(doc, p.Str("building_material"));
                if (mat == null) return Err("no material named '" + p.Str("building_material") + "'");
                double width = w.Width;                   // capture BEFORE the type swap
                var nt = (WallType)w.WallType.Duplicate(UniqueTypeName(doc, typeof(WallType),
                    Lookups.NameOf(w.WallType) + " - " + Lookups.NameOf(mat)));
                var layer = new CompoundStructureLayer(width, MaterialFunctionAssignment.Structure, mat.Id);
                nt.SetCompoundStructure(CompoundStructure.CreateSimpleCompoundStructure(
                    new List<CompoundStructureLayer> { layer }));
                w.WallType = nt;
            }
            var res = Ok(("guid", w.UniqueId));
            if (flipped) res["flipped"] = true;
            if (p.Num("thickness") != null) res["note"] = "wall " + ThicknessNote;
            if (heightNote != null)
                res["note"] = res.ContainsKey("note") ? res["note"] + "; " + heightNote : heightNote;
            return res;
        }

        private static object ModifyZone(Document doc, Params p)
        {
            var rm = Lookups.ByGuid(doc, p.Str("guid"));
            if (rm == null) return Err("room not found");
            string number = p.Has("number") ? (p.Str("number") ?? p.Int("number").ToString())
                                            : rm.get_Parameter(BuiltInParameter.ROOM_NUMBER)?.AsString();
            var poly = p.Pts("polygon_xy");
            if (poly == null)                             // in-place rename / renumber
            {
                if (p.Str("name") != null) rm.get_Parameter(BuiltInParameter.ROOM_NAME).Set(p.Str("name"));
                if (p.Has("number")) rm.get_Parameter(BuiltInParameter.ROOM_NUMBER).Set(number);
                return Ok(("guid", rm.UniqueId));
            }
            // boundary change -> delete + recreate (the Archicad modify_zone contract). Current
            // name/number/level are read FIRST; explicit params override. NOTE: the old room's
            // separation lines are not tracked, so they stay in place.
            string name = p.Str("name") ?? rm.get_Parameter(BuiltInParameter.ROOM_NAME)?.AsString();
            Level lvl = p.Int("floor_index") != null ? Lookups.LevelByIndex(doc, p.Int("floor_index"))
                                                     : doc.GetElement(rm.LevelId) as Level;
            string old = rm.UniqueId;
            doc.Delete(rm.Id);
            var res = ZoneCore(doc, poly, lvl, name, number) as Dictionary<string, object>;
            if (res != null && res.TryGetValue("ok", out var ok) && ok is bool b && b)
                res["replaced"] = old;
            return res;
        }

        private const string ThicknessNote =
            "thickness is type-driven on Revit — assign a composite/floor type instead";

        private static object ModifySlab(Document doc, Params p) => ModifySlabImpl(doc, p, false);

        /// The RESHAPE variant (polygon_xy given). Run() routes it OUTSIDE Tx(), because the
        /// in-place sketch edit uses SketchEditScope, which manages its own transactions and
        /// throws inside an open one. Every mutation below therefore opens its own.
        private static object ModifySlabReshape(Document doc, Params p) =>
            ModifySlabImpl(doc, p, true);

        private static object ModifySlabImpl(Document doc, Params p, bool ownTx)
        {
            // On the normal route a transaction is already open, so mutations run directly; on
            // the reshape route there is none, so each opens its own — through Tx(), keeping the
            // same warning-swallowing and roll-back-on-error semantics.
            object Mutate(string name, Func<object> fn) => ownTx ? Tx(doc, name, fn) : fn();

            if (!(Lookups.ByGuid(doc, p.Str("guid")) is Floor fl)) return Err("slab not found");
            if (p.Str("composite_guid") != null && p.Str("composite_name") != null)
                return Err("give composite_guid OR composite_name, not both");
            FloorType wantType = null;
            if (p.Str("composite_guid") != null)
            {
                wantType = Lookups.GetFloorType(doc, guid: p.Str("composite_guid"));
                if (wantType == null)                  // a bad guid must fail, not silently skip
                    return Err("no floor type with guid '" + p.Str("composite_guid") + "'");
            }
            if (p.Str("composite_name") != null)       // switch to an EXISTING type by NAME
            {
                wantType = Lookups.GetFloorType(doc, name: p.Str("composite_name"));
                if (wantType == null)                  // strict — no arbitrary-type fallback
                    return Err("no floor type named '" + p.Str("composite_name") + "'");
            }
            if (wantType != null)
            {
                var swap = Mutate("modify_slab type",
                                  () => { fl.FloorType = wantType; return Ok(("ok2", true)); });
                if (IsErrDict(swap)) return swap;
            }
            var poly = p.Pts("polygon_xy");
            double? levelM = p.Num("level");           // ABSOLUTE elevation (m) — Archicad parity
            if (poly != null || levelM != null)
            {
                // outline and/or level change -> delete + recreate with the (possibly just-
                // swapped) type — the Archicad modify_slab contract; the slab gets a NEW guid.
                // `level` used to be silently IGNORED here (the A3/C5 bench cluster: a "move the
                // slab" call returned ok, the slab never moved — or, with a polygon alongside,
                // was rebuilt on the old level and then judged "none on the right floor").
                var ft = fl.FloorType;
                var oldLvl = doc.GetElement(fl.LevelId) as Level;
                if (oldLvl == null) return Err("slab has no level");
                double oldOff = fl.get_Parameter(BuiltInParameter.FLOOR_HEIGHTABOVELEVEL_PARAM)
                                  ?.AsDouble() ?? 0;
                Level lvl = oldLvl;
                double offFt = oldOff;
                if (levelM != null)
                {
                    lvl = Lookups.LevelForZ(doc, levelM.Value);
                    if (lvl == null) return Err("no level for elevation " + levelM);
                    offFt = Units.MToFt(levelM.Value) - lvl.Elevation;
                }
                double zM = Units.FtToM(lvl.Elevation + offFt);
                List<CurveLoop> loops;
                if (poly != null)
                    loops = new List<CurveLoop> { Loop(poly, zM) };
                else
                {
                    // level-only change: keep the CURRENT outline — read it from the slab's own
                    // sketch and lift it to the new elevation (holes are not kept; Archicad parity).
                    var sk = doc.GetElement(fl.SketchId) as Sketch;
                    if (sk == null) return Err("cannot read the slab's outline for the level change");
                    loops = new List<CurveLoop>();
                    double curZ = sk.Profile.get_Item(0).get_Item(0).GetEndPoint(0).Z;
                    var lift = Transform.CreateTranslation(
                        new XYZ(0, 0, lvl.Elevation + offFt - curZ));
                    foreach (CurveArray arr in sk.Profile)
                    {
                        var loop2 = new CurveLoop();
                        foreach (Curve cu in arr) loop2.Append(cu.CreateTransformed(lift));
                        loops.Add(loop2);
                        break;                          // outer boundary only (holes not kept)
                    }
                }
                // IN-PLACE FIRST. A reshape used to be delete+recreate unconditionally, which
                // throws the element away: the guid changes (so `preserve.slabs` fails and any
                // guid the agent still holds goes stale) and every Opening element hosted on
                // the floor — everything `create_slab_opening` cut — dies with it. Editing the
                // sketch keeps all of that. It is not an optional nicety: a floor sketch drawn
                // by picking walls is CONSTRAINED to them, so changing a wall type drags the
                // floor outline with it (measured on A_setup_types5: 200mm -> 460mm walls moved
                // every floor edge 100mm inward), and the corrective "put the outline back" is
                // a genuine reshape that must not cost the element.
                // Only same-level reshapes go in place; a level move still rebuilds.
                string why = null;
                if (poly != null && lvl.Id == oldLvl.Id
                    && TryReshapeSketch(doc, fl, loops[0], out why))
                {
                    if (Math.Abs(offFt - oldOff) > 1e-9)
                        Mutate("modify_slab offset", () =>
                        {
                            fl.get_Parameter(BuiltInParameter.FLOOR_HEIGHTABOVELEVEL_PARAM)
                              ?.Set(offFt);
                            return Ok(("ok2", true));
                        });
                    var okRep = Ok(("guid", fl.UniqueId), ("reshaped_in_place", true));
                    if (p.Num("thickness") != null) okRep["note"] = ThicknessNote;
                    return okRep;
                }
                // Say WHY the cheap path was refused, in the RESULT: a silent fall-through to
                // the destructive one is exactly how this went unnoticed for so long, and the
                // agent is the one that needs to know its guid just changed.
                string fallback = (poly != null && lvl.Id == oldLvl.Id) ? why : null;
                string old = fl.UniqueId;
                string newGuid = null;
                var built = Mutate("modify_slab rebuild", () =>
                {
                    doc.Delete(fl.Id);
                    var nf2 = Floor.Create(doc, loops, ft.Id, lvl.Id);
                    if (Math.Abs(offFt) > 1e-9)
                        nf2.get_Parameter(BuiltInParameter.FLOOR_HEIGHTABOVELEVEL_PARAM)?.Set(offFt);
                    newGuid = nf2.UniqueId;
                    return Ok(("guid", nf2.UniqueId));
                });
                if (IsErrDict(built)) return built;
                var rep = Ok(("guid", newGuid), ("replaced", old));
                if (fallback != null)
                    rep["rebuilt_because"] = "the sketch could not be edited in place ("
                                             + fallback + "), so the slab was rebuilt "
                                             + "under a NEW guid";
                if (p.Num("thickness") != null) rep["note"] = ThicknessNote;
                return rep;
            }
            var res = Ok(("guid", fl.UniqueId));
            if (p.Num("thickness") != null) res["note"] = ThicknessNote;
            return res;
        }

        private static object ModifyOpening(Document doc, Params p)
        {
            if (!(Lookups.ByGuid(doc, p.Str("guid")) is FamilyInstance inst)) return Err("opening not found");
            var center = p.Arr("center");
            double? off = p.Num("center_offset");
            if ((center != null || off != null) && inst.Host != null)
            {
                var line = (inst.Host.Location as LocationCurve)?.Curve as Line;
                if (line == null) return Err("host wall has no straight location curve");
                XYZ b = line.GetEndPoint(0);
                XYZ d = line.GetEndPoint(1) - b; double dl = d.GetLength(); if (dl == 0) dl = 1;
                XYZ dir = d / dl;
                double t;
                if (center != null)                    // [x,y] -> along-wall projection
                {
                    XYZ raw = Units.Pt(center[0], center[1], 0.0);
                    t = (raw - b).DotProduct(dir);
                }
                else                                   // the documented raw alternative — this
                    t = Units.MToFt(off.Value);        // used to be silently ignored (ok:true, no-op)
                if (t < -1e-6 || t > dl + 1e-6)
                    return Err("opening centre projects outside the host wall's span — wrong "
                               + "host wall or wrong centre (nothing modified)");
                XYZ on = b + dir * t;
                XYZ cur = (inst.Location as LocationPoint).Point;
                ElementTransformUtils.MoveElement(doc, inst.Id, new XYZ(on.X - cur.X, on.Y - cur.Y, 0));
            }
            // size change: realise at TYPE level first (matching sibling / duplicated type) —
            // width/height are type parameters in stock families, instance sets no-op on them
            if (p.Num("width") != null || p.Num("height") != null)
            {
                var sized = SizedSymbol(doc, inst.Symbol, p.Num("width"), p.Num("height"));
                if (sized == null)
                    return Err("cannot realise the requested width/height on this opening's family — "
                               + "no matching type and the size parameters are not writable on a duplicate");
                if (sized.Id != inst.Symbol.Id) { inst.ChangeTypeId(sized.Id); doc.Regenerate(); }
            }
            var missed = new List<string>();
            if (!SetLenM(inst, p.Num("width"), WidthBips) && !TypeCarries(inst.Symbol, p.Num("width"), WidthBips)) missed.Add("width");
            if (!SetLenM(inst, p.Num("height"), HeightBips) && !TypeCarries(inst.Symbol, p.Num("height"), HeightBips)) missed.Add("height");
            if (!SetLenM(inst, p.Num("sill"), BuiltInParameter.INSTANCE_SILL_HEIGHT_PARAM)) missed.Add("sill");
            var swingNote = ApplySwing(doc, inst, p);
            var res = WithDimNote(Ok(("guid", inst.UniqueId)), missed);
            if (swingNote != null)
                res["note"] = res.ContainsKey("note") ? res["note"] + "; " + swingNote : swingNote;
            return res;
        }

        private static object DeleteElement(Document doc, Params p)
        {
            var el = Lookups.ByGuid(doc, p.Str("guid"));
            if (el == null) return Err("element not found");
            doc.Delete(el.Id);
            return Ok(("deleted", p.Str("guid")));
        }

        /// Change the user's on-screen SELECTION (UIDocument.Selection.SetElementIds) — a UI
        /// aid, no Transaction needed. Routed separately in HttpServer (it needs the
        /// UIDocument, which Run()'s Document-only signature doesn't carry). mode: "replace"
        /// Make a storey's floor plan the ACTIVE view. Revit-only capability (Tapir has no
        /// active-storey command — probed), so this tool has NO Archicad twin. `story` is a
        /// level NAME or an INDEX into the elevation-sorted level stack (the same index
        /// `observation`'s stories carry). A level created by set_stories has no plan view
        /// yet, so one is CREATED when missing — inside a transaction, which must be CLOSED
        /// before ActiveView is set (the setter refuses during an open transaction).
        public static object SetActiveStory(Autodesk.Revit.UI.UIDocument uidoc, Params p)
        {
            if (uidoc == null) return Err("no active document — open a project in Revit");
            var doc = uidoc.Document;
            string want = p.Str("story");
            if (string.IsNullOrWhiteSpace(want)) return Err("set_active_story needs `story` (a level name or index)");
            var levels = Lookups.Levels(doc).OrderBy(l => l.Elevation).ToList();
            Level level = levels.FirstOrDefault(l =>
                string.Equals(Lookups.NameOf(l), want.Trim(), StringComparison.OrdinalIgnoreCase));
            if (level == null && int.TryParse(want.Trim(), out int idx) && idx >= 0 && idx < levels.Count)
                level = levels[idx];
            if (level == null)
                return Err("no storey matching '" + want + "'; levels: "
                           + string.Join(", ", levels.Select(Lookups.NameOf)));
            var plan = new FilteredElementCollector(doc).OfClass(typeof(ViewPlan)).Cast<ViewPlan>()
                .FirstOrDefault(v => !v.IsTemplate && v.ViewType == ViewType.FloorPlan
                                     && v.GenLevel != null && v.GenLevel.Id == level.Id);
            if (plan == null)
            {
                var vft = new FilteredElementCollector(doc).OfClass(typeof(ViewFamilyType))
                    .Cast<ViewFamilyType>().FirstOrDefault(t => t.ViewFamily == ViewFamily.FloorPlan);
                if (vft == null) return Err("the project has no FloorPlan view family type");
                using (var tx = new Transaction(doc, "create floor plan"))
                {
                    tx.Start();
                    plan = ViewPlan.Create(doc, vft.Id, level.Id);
                    plan.Name = Lookups.NameOf(level);
                    tx.Commit();                 // MUST commit before ActiveView below
                }
            }
            uidoc.ActiveView = plan;             // legal here: the external event runs on the UI thread
            return new Dictionary<string, object> {
                ["ok"] = true, ["story"] = Lookups.NameOf(level), ["view"] = plan.Name };
        }

        /// (default) = the selection becomes exactly these guids; "add" / "remove" = adjust
        /// the current selection. Unknown guids fail loudly (same policy as the named lookups).
        public static object SelectElements(Autodesk.Revit.UI.UIDocument uidoc, Params p)
        {
            if (uidoc == null) return Err("no active document — open a project in Revit");
            var doc = uidoc.Document;
            var guids = p.Strs("guids") ?? new List<string>();
            string mode = p.Str("mode") ?? "replace";
            var ids = new List<ElementId>();
            var missing = new List<string>();
            foreach (var g in guids)
            {
                var el = Lookups.ByGuid(doc, g);
                if (el == null) missing.Add(g); else ids.Add(el.Id);
            }
            if (missing.Count > 0) return Err("element(s) not found: " + string.Join(", ", missing));
            ICollection<ElementId> target;
            if (mode == "add" || mode == "remove")
            {
                var current = new HashSet<ElementId>(uidoc.Selection.GetElementIds());
                if (mode == "add") current.UnionWith(ids); else current.ExceptWith(ids);
                target = current.ToList();
            }
            else target = ids;                       // "replace" (and any unknown mode string)
            uidoc.Selection.SetElementIds(target);
            return Ok(("mode", mode), ("selected", target.Count));
        }

        /// Change an opening's TYPE. On Revit this is an IN-PLACE family-symbol swap
        /// (ChangeTypeId), so — unlike the Archicad backend's delete+recreate — the element
        /// KEEPS its guid; "replaced" mirrors the Archicad result shape for the pipeline.
        /// The favorite is resolved STRICTLY (loaded match or library load); no wrong-type
        /// fallback — a silent swap to an arbitrary family would defeat the action's purpose.
        private static object ReplaceOpening(Document doc, Params p, BuiltInCategory cat)
        {
            if (!(Lookups.ByGuid(doc, p.Str("guid")) is FamilyInstance inst))
                return Err("opening not found");
            string fav = p.Str("favorite");
            if (!string.IsNullOrEmpty(fav))
            {
                var sym = Library.EnsureSymbol(doc, cat, fav);
                if (sym == null)
                    return Err("no " + cat + " family matching '" + fav + "' — not replacing");
                sym = SizedSymbol(doc, sym, p.Num("width"), p.Num("height"));
                if (sym == null)
                    return Err("cannot realise the requested width/height on family '" + fav
                               + "' — no matching type and the size parameters are not writable on a duplicate");
                inst.ChangeTypeId(sym.Id);
                doc.Regenerate();
                // VERIFY the swap took: ChangeTypeId can silently no-op (e.g. an incompatible
                // host condition) — the C3 bench case returned ok with the old family intact.
                if (inst.GetTypeId() != sym.Id)
                    return Err("type swap did not take effect — the opening still is '"
                               + Lookups.NameOf(doc.GetElement(inst.GetTypeId())) + "'");
            }
            else if (p.Num("width") != null || p.Num("height") != null)
            {
                var sized = SizedSymbol(doc, inst.Symbol, p.Num("width"), p.Num("height"));
                if (sized == null)
                    return Err("cannot realise the requested width/height on this opening's family — "
                               + "no matching type and the size parameters are not writable on a duplicate");
                if (sized.Id != inst.Symbol.Id) { inst.ChangeTypeId(sized.Id); doc.Regenerate(); }
            }
            var missed = new List<string>();
            if (!SetLenM(inst, p.Num("width"), WidthBips) && !TypeCarries(inst.Symbol, p.Num("width"), WidthBips)) missed.Add("width");
            if (!SetLenM(inst, p.Num("height"), HeightBips) && !TypeCarries(inst.Symbol, p.Num("height"), HeightBips)) missed.Add("height");
            if (!SetLenM(inst, p.Num("sill"), BuiltInParameter.INSTANCE_SILL_HEIGHT_PARAM)) missed.Add("sill");
            var swingNote = ApplySwing(doc, inst, p);
            var res = WithDimNote(Ok(("guid", inst.UniqueId), ("replaced", inst.UniqueId)), missed);
            if (swingNote != null)
                res["note"] = res.ContainsKey("note") ? res["note"] + "; " + swingNote : swingNote;
            return res;
        }

        // ===================================================== helpers
        private static object Tx(Document doc, string name, Func<object> fn)
        {
            using (var t = new Transaction(doc, "bim-agent: " + name))
            {
                t.Start();
                // Swallow WARNINGS and ROLL BACK on ERRORS (see WarningSwallower): without this a
                // modal dialog blocks the API thread, stalls every queued job, and times out all
                // HTTP requests until a human clicks it away.
                var handler = new WarningSwallower();
                var fo = t.GetFailureHandlingOptions()
                          .SetFailuresPreprocessor(handler)
                          .SetClearAfterRollback(true);
                t.SetFailureHandlingOptions(fo);
                try
                {
                    var r = fn();
                    // fn() returned an ERROR after possibly mutating the document (e.g. a
                    // delete followed by failed validation): committing would persist the
                    // partial mutation behind an {ok:false} result — permanently losing the
                    // deleted element / stacking retry debris. Roll everything back instead.
                    if (IsErrDict(r))
                    {
                        t.RollBack();
                        return r;
                    }
                    var status = t.Commit();
                    // A commit that rolled back (an un-ignorable Revit error, e.g. an opening that
                    // won't cut its wall) must be reported as a failure — otherwise fn()'s optimistic
                    // {ok:true} would claim an element that was never actually created.
                    if (status != TransactionStatus.Committed)
                        return Err(handler.Errors.Count > 0
                                   ? string.Join("; ", handler.Errors)
                                   : "transaction " + status + " (no element created)");
                    return r;
                }
                catch (Exception e) { if (t.HasStarted() && !t.HasEnded()) t.RollBack(); return Err(e.GetType().Name + ": " + e.Message); }
            }
        }

        private static object Safe(Func<object> fn)
        {
            try { return fn(); } catch (Exception e) { return Err(e.GetType().Name + ": " + e.Message); }
        }

        /// Replace a floor's sketch profile with `want`, KEEPING the element (and therefore its
        /// guid, its hosted Opening cuts and anything referencing it).
        ///
        /// `SketchEditScope` is the only API that edits an existing sketch; it wraps its own
        /// transaction, so this must NOT be called from inside one (the /action route runs each
        /// action in a Tx — see the caller's note). The scope is ABORTED on any failure and the
        /// caller falls back to delete+recreate, so a Revit version or a constraint set that
        /// refuses the edit degrades to the old behaviour instead of failing the action.
        ///
        /// Hole loops are dropped, matching the delete+recreate path's documented behaviour
        /// (`create_slab_opening` cuts are separate Opening elements, not sketch loops, and
        /// those now SURVIVE because the floor does).
        private static bool TryReshapeSketch(Document doc, Floor fl, CurveLoop want,
                                             out string why)
        {
            why = null;
            SketchEditScope scope = null;
            try
            {
                if (fl.SketchId == null || fl.SketchId == ElementId.InvalidElementId)
                { why = "the floor has no editable sketch"; return false; }
                var sketch = doc.GetElement(fl.SketchId) as Sketch;
                if (sketch == null) { why = "the sketch could not be read"; return false; }

                scope = new SketchEditScope(doc, "Reshape floor outline");
                scope.Start(fl.SketchId);
                using (var t = new Transaction(doc, "reshape floor outline"))
                {
                    t.Start();
                    // Drop every existing profile curve, then lay the wanted loop down on the
                    // SAME sketch plane. Deleting first matters: leaving the old curves makes
                    // the profile self-intersecting and the scope refuses to commit.
                    var plane = sketch.SketchPlane;
                    var oldCurves = new List<ElementId>();
                    foreach (var id in sketch.GetAllElements())
                        if (doc.GetElement(id) is CurveElement) oldCurves.Add(id);
                    if (oldCurves.Count == 0)
                    { t.RollBack(); why = "the sketch exposes no editable curves"; return false; }
                    doc.Delete(oldCurves);
                    // Flatten onto the sketch plane's elevation — `want` was built at the
                    // floor's z, but a sketch curve off its own plane is rejected.
                    double z = plane.GetPlane().Origin.Z;
                    foreach (Curve c in want)
                    {
                        XYZ a = c.GetEndPoint(0), b = c.GetEndPoint(1);
                        doc.Create.NewModelCurve(
                            Line.CreateBound(new XYZ(a.X, a.Y, z), new XYZ(b.X, b.Y, z)), plane);
                    }
                    t.Commit();
                }
                scope.Commit(new WarningSwallower());
                return true;
            }
            catch (Exception e)
            {
                why = e.GetType().Name + ": " + e.Message;
                try { if (scope != null && scope.IsActive) scope.Cancel(); } catch { }
                return false;
            }
            finally
            {
                try { scope?.Dispose(); } catch { }
            }
        }

        private static CurveLoop Loop(List<double[]> poly, double z = 0.0)
        {
            var pts = poly.Select(pt => Units.Pt(pt[0], pt[1], z)).ToList();
            if (pts.Count > 0 && !pts[0].IsAlmostEqualTo(pts[pts.Count - 1])) pts.Add(pts[0]);
            var loop = new CurveLoop();
            for (int i = 0; i < pts.Count - 1; i++) loop.Append(Line.CreateBound(pts[i], pts[i + 1]));
            return loop;
        }

        /// A type name not yet used by any element of `cls` ("name", "name (2)", ...).
        private static string UniqueTypeName(Document doc, Type cls, string want)
        {
            var names = new FilteredElementCollector(doc).OfClass(cls).Cast<Element>()
                .Select(Lookups.NameOf).ToHashSet();
            string nm = want; int i = 1;
            while (names.Contains(nm)) { i++; nm = want + " (" + i + ")"; }
            return nm;
        }

        /// Set a length (m) on the first writable matching parameter. Returns TRUE when nothing
        /// was requested OR the set landed; FALSE when a value WAS requested but no instance
        /// parameter is writable — in stock families door/window sizes are TYPE parameters, so
        /// the request silently kept the family default. Callers surface that as a `note`
        /// (otherwise the verifier keeps emitting size fixes that can never take effect).
        private static bool SetLenM(Element el, double? m, params BuiltInParameter[] bips)
        {
            if (m == null) return true;
            foreach (var bip in bips)
            {
                try
                {
                    var p = el.get_Parameter(bip);
                    if (p != null && !p.IsReadOnly) { p.Set(Units.MToFt(m.Value)); return true; }
                }
                catch { }
            }
            return false;
        }

        private static readonly BuiltInParameter[] WidthBips =
            { BuiltInParameter.DOOR_WIDTH, BuiltInParameter.WINDOW_WIDTH, BuiltInParameter.FAMILY_WIDTH_PARAM };
        private static readonly BuiltInParameter[] HeightBips =
            { BuiltInParameter.DOOR_HEIGHT, BuiltInParameter.WINDOW_HEIGHT, BuiltInParameter.FAMILY_HEIGHT_PARAM };

        /// First present double-valued parameter among bips, in feet (null = none carries it).
        private static double? LenOf(Element el, params BuiltInParameter[] bips)
        {
            foreach (var bip in bips)
            {
                try
                {
                    var p = el.get_Parameter(bip);
                    if (p != null && p.StorageType == StorageType.Double && p.HasValue) return p.AsDouble();
                }
                catch { }
            }
            return null;
        }

        /// True when no size was requested, OR the symbol's TYPE-level dimension already equals it.
        private static bool TypeCarries(FamilySymbol s, double? m, params BuiltInParameter[] bips)
        {
            if (m == null || s == null) return true;
            double? cur = LenOf(s, bips);
            return cur != null && Math.Abs(cur.Value - Units.MToFt(m.Value)) < 0.004; // ~1.2 mm
        }

        /// Door/window WIDTH/HEIGHT are TYPE parameters in stock Revit families — setting them on
        /// the INSTANCE (SetLenM) silently no-ops, which is how a bare family-name favorite placed
        /// 300 x 2000 doors while reporting ok:true (and every verifier size-fix no-oped too).
        /// Resolve the requested size at the TYPE level instead: keep the symbol if it already
        /// matches, else switch to a same-family sibling type that matches, else DUPLICATE the
        /// type and set its width/height. Returns null when the size genuinely cannot be realised
        /// — the caller must fail loudly, never place a wrong-size opening as a success.
        private static FamilySymbol SizedSymbol(Document doc, FamilySymbol sym, double? wM, double? hM)
        {
            if (sym == null) return null;
            if (wM == null && hM == null) return sym;
            // a family whose sizes are INSTANCE parameters exposes no type-level W/H — the
            // caller's instance SetLenM handles those; nothing to do at type level
            if (LenOf(sym, WidthBips) == null && LenOf(sym, HeightBips) == null) return sym;

            bool Matches(FamilySymbol s) => TypeCarries(s, wM, WidthBips) && TypeCarries(s, hM, HeightBips);
            FamilySymbol Activated(FamilySymbol s)
            {
                if (!s.IsActive) { s.Activate(); doc.Regenerate(); }
                return s;
            }

            if (Matches(sym)) return Activated(sym);
            if (sym.Family != null)
                foreach (var id in sym.Family.GetFamilySymbolIds())
                    if (doc.GetElement(id) is FamilySymbol sib && Matches(sib))
                        return Activated(sib);

            string label = (wM != null ? Math.Round(wM.Value * 1000).ToString("0") : "w") + " x "
                         + (hM != null ? Math.Round(hM.Value * 1000).ToString("0") : "h") + "mm (agent)";
            for (int n = 0; n < 3; n++)
            {
                FamilySymbol dup;
                try { dup = sym.Duplicate(n == 0 ? label : label + " " + (n + 1)) as FamilySymbol; }
                catch { continue; }                    // name collision -> try the next suffix
                if (dup == null) return null;
                bool wSet = wM == null || SetLenM(dup, wM, WidthBips);
                bool hSet = hM == null || SetLenM(dup, hM, HeightBips);
                if (wSet && hSet) return Activated(dup);
                try { doc.Delete(dup.Id); } catch { } // don't leave a half-sized orphan type
                return null;                          // type params unwritable -> not realisable
            }
            return null;
        }

        /// Apply an opening's swing/facing flags as ABSOLUTE geometry. `oSide`/`reflected`
        /// (computed by the Python side from the plan's opens_toward/hinge_toward points) are
        /// absolute side statements — oSide = the leaf opens toward the LEFT of the host's
        /// begin->end, reflected = the hinge sits at the END-side jamb. flipFacing()/flipHand()
        /// are RELATIVE toggles from whatever state the family happened to place in, so the old
        /// "flip when the flag is true" made the result depend on the host wall's own
        /// orientation: the same call was right on one wall and mirrored on its twin, and every
        /// default-state door reported ok with an unset swing (the B9/B10/C7 bench cluster).
        /// Read the LIVE FacingOrientation/HandOrientation and flip only on disagreement; a
        /// residual disagreement after the flip is returned as a note, never swallowed.
        private static string ApplySwing(Document doc, FamilyInstance inst, Params p)
        {
            if (!p.Has("oSide") && !p.Has("reflected")) return null;
            var line = (inst.Host?.Location as LocationCurve)?.Curve as Line;
            if (line == null) return "swing not applied — host wall has no straight location curve";
            XYZ d = line.GetEndPoint(1) - line.GetEndPoint(0);
            double L = Math.Sqrt(d.X * d.X + d.Y * d.Y);
            if (L < 1e-9) return "swing not applied — degenerate host curve";
            XYZ u = new XYZ(d.X / L, d.Y / L, 0);
            XYZ leftN = new XYZ(-u.Y, u.X, 0);
            doc.Regenerate();                    // orientations are stale until regenerated
            var notes = new List<string>();
            if (p.Has("oSide"))
            {
                XYZ want = p.Bool("oSide") ? leftN : leftN.Negate();
                try
                {
                    var f = inst.FacingOrientation;
                    if (f.X * want.X + f.Y * want.Y < 0) { inst.flipFacing(); doc.Regenerate(); }
                    f = inst.FacingOrientation;
                    if (f.X * want.X + f.Y * want.Y < 0)
                        notes.Add("facing flip did not take effect");
                }
                catch (Exception e) { notes.Add("facing flip failed: " + e.Message); }
            }
            if (p.Has("reflected"))
            {
                // hand axis convention: points from the BEGIN-side jamb toward END when the
                // hinge is at BEGIN — hinge at the END-side jamb wants the reversed axis.
                XYZ want = p.Bool("reflected") ? u.Negate() : u;
                try
                {
                    var h2 = inst.HandOrientation;
                    if (h2.X * want.X + h2.Y * want.Y < 0) { inst.flipHand(); doc.Regenerate(); }
                    h2 = inst.HandOrientation;
                    if (h2.X * want.X + h2.Y * want.Y < 0)
                        notes.Add("hand flip did not take effect");
                }
                catch (Exception e) { notes.Add("hand flip failed: " + e.Message); }
            }
            return notes.Count > 0 ? string.Join("; ", notes) : null;
        }

        private static Dictionary<string, object> WithDimNote(Dictionary<string, object> res,
                                                              List<string> missed)
        {
            if (missed.Count > 0)
                res["note"] = "could not set " + string.Join("/", missed) + " — the dimension "
                            + "is TYPE-driven in this family (no writable instance parameter); "
                            + "the family default was kept";
            return res;
        }

        private static Dictionary<string, object> Ok(params (string k, object v)[] kv)
        {
            var d = new Dictionary<string, object> { ["ok"] = true };
            foreach (var (k, v) in kv) d[k] = v;
            return d;
        }

        private static Dictionary<string, object> Err(string msg) =>
            new Dictionary<string, object> { ["ok"] = false, ["error"] = msg };

        /// An action-function result that reports failure ({ok:false}) — Tx() must roll the
        /// transaction back for these instead of committing whatever fn() mutated first.
        private static bool IsErrDict(object r) =>
            r is Dictionary<string, object> d && d.TryGetValue("ok", out var v)
            && v is bool ok && !ok;
    }

    /// Failure preprocessor for every bim-agent transaction (+ StairsEditScope.Commit). WARNINGS
    /// (overlapping walls, room not enclosed, duplicate instances — things this agent triggers
    /// constantly) are deleted so Revit never pops a modal for them (Continue alone does NOT
    /// suppress them). An ERROR ("Can't cut instance ... out of Wall", "Instance(s) ... not cutting
    /// anything") is NOT deletable and, left to Continue, pops an "Error - cannot be ignored" MODAL
    /// that freezes the API thread and wedges every queued job until a human clicks it away. So on
    /// ANY error we capture its text and ProceedWithRollBack: the transaction rolls back cleanly, no
    /// modal appears, and Tx() surfaces the captured message as {ok:false}.
    internal class WarningSwallower : IFailuresPreprocessor
    {
        public List<string> Errors { get; } = new List<string>();

        public FailureProcessingResult PreprocessFailures(FailuresAccessor a)
        {
            var errors = a.GetFailureMessages()
                          .Where(m => m.GetSeverity() == FailureSeverity.Error)
                          .ToList();
            if (errors.Count > 0)
            {
                foreach (var m in errors)
                {
                    var txt = m.GetDescriptionText();
                    if (!string.IsNullOrWhiteSpace(txt)) Errors.Add(txt);
                }
                return FailureProcessingResult.ProceedWithRollBack;
            }
            a.DeleteAllWarnings();
            return FailureProcessingResult.Continue;
        }
    }
}
