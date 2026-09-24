using System;
using System.Collections.Generic;
using System.Text.Json;

namespace BimAgent
{
    /// Thin typed reader over an action's "params" JSON object. Lengths/coordinates are in METRES
    /// (the actor already converted mm->m, like the Archicad path; the Revit side converts m->feet).
    /// The JsonElement is cloned so it survives the request's JsonDocument being disposed.
    public class Params
    {
        private readonly JsonElement _e;
        private readonly bool _ok;

        public Params() { _ok = false; }

        public Params(JsonElement e)
        {
            _ok = e.ValueKind == JsonValueKind.Object;
            if (_ok) _e = e.Clone();
        }

        private bool Get(string k, out JsonElement v)
        {
            v = default;
            return _ok && _e.TryGetProperty(k, out v) && v.ValueKind != JsonValueKind.Null;
        }

        public bool Has(string k) => Get(k, out _);

        /// An EMPTY string reads as ABSENT. Every caller here tests `Str(k) != null` to mean
        /// "the caller asked for this", and a model habitually fills the params it is not
        /// using with "" — which then trips the mutually-exclusive guards ("give
        /// composite_guid OR composite_name, not both") or sends a name lookup after "".
        /// The Python tool layer strips empty strings too; this is the backstop for anything
        /// that reaches the route directly.
        public string Str(string k)
        {
            if (!Get(k, out var v) || v.ValueKind != JsonValueKind.String) return null;
            var s = v.GetString();
            return string.IsNullOrWhiteSpace(s) ? null : s;
        }

        public double? Num(string k) => Get(k, out var v) && v.ValueKind == JsonValueKind.Number ? v.GetDouble() : (double?)null;

        /// An integer param (step_num, floor_index). GetInt32() THROWS on a JSON number written
        /// with a decimal point — and "12.0" is ordinary model output — so a whole-valued double
        /// is accepted and rounded instead of failing the action with a FormatException.
        public int? Int(string k)
        {
            if (!Get(k, out var v) || v.ValueKind != JsonValueKind.Number) return null;
            if (v.TryGetInt32(out int i)) return i;
            return (int)Math.Round(v.GetDouble());
        }

        public bool Bool(string k) => Get(k, out var v) && v.ValueKind == JsonValueKind.True;

        /// The numeric components of ONE value, accepting BOTH point shapes the Python side
        /// emits: [x, y] and {"x":.., "y":.., "z":..}.
        ///
        /// This is not defensive decoration. `base._is_point` deliberately validates both forms
        /// and the mm->m converter preserves whichever the model produced, so either can arrive
        /// here; the Archicad backend normalises them in one shared place for exactly this
        /// reason (actions/points.py). Without the same thing on this side an {x,y} point became
        /// NULL — a NullReferenceException in the readers that do not null-check, and a silently
        /// DROPPED vertex in every polygon (a 4-point outline arriving as 0 points).
        private static double[] Comps(JsonElement v)
        {
            var list = new List<double>();
            if (v.ValueKind == JsonValueKind.Array)
            {
                foreach (var it in v.EnumerateArray())
                    if (it.ValueKind == JsonValueKind.Number) list.Add(it.GetDouble());
                return list.ToArray();
            }
            if (v.ValueKind == JsonValueKind.Object)
            {
                foreach (var key in new[] { "x", "y", "z" })
                    if (v.TryGetProperty(key, out var c) && c.ValueKind == JsonValueKind.Number)
                        list.Add(c.GetDouble());
                return list.Count >= 2 ? list.ToArray() : null;
            }
            return null;
        }

        /// A flat numeric array, e.g. "begin":[x,y] or "move":[dx,dy,dz]. An {x,y} object is
        /// accepted too (see Comps).
        public double[] Arr(string k) => Get(k, out var v) ? Comps(v) : null;

        /// A list of points, e.g. "polygon_xy":[[x,y],...] / "baseline_xy":[[x,y],...].
        /// Individual points may be [x,y] or {x,y}; one unusable entry is skipped rather than
        /// silently shortening the outline into a different shape.
        public List<double[]> Pts(string k)
        {
            if (!Get(k, out var v) || v.ValueKind != JsonValueKind.Array) return null;
            var pts = new List<double[]>();
            foreach (var it in v.EnumerateArray())
            {
                var c = Comps(it);
                if (c != null && c.Length >= 2) pts.Add(c);
            }
            return pts;
        }

        /// A string array, e.g. "use_with":["Wall"] / ["Slab"].
        public List<string> Strs(string k)
        {
            if (!Get(k, out var v) || v.ValueKind != JsonValueKind.Array) return null;
            var list = new List<string>();
            foreach (var it in v.EnumerateArray())
                if (it.ValueKind == JsonValueKind.String) list.Add(it.GetString());
            return list;
        }

        /// A list of sub-objects, e.g. "skins":[{material,type,thickness},...].
        public List<Params> Objs(string k)
        {
            if (!Get(k, out var v) || v.ValueKind != JsonValueKind.Array) return null;
            var objs = new List<Params>();
            foreach (var it in v.EnumerateArray())
                objs.Add(new Params(it));
            return objs;
        }
    }
}
