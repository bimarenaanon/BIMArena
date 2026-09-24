using System;
using System.Collections.Generic;
using Autodesk.Revit.DB;

namespace BimAgent
{
    /// metre/mm <-> Revit internal feet. The agent speaks METRES at the toolbox boundary; Revit's
    /// internal unit is decimal feet. (UnitTypeId is Revit 2021+.)
    public static class Units
    {
        public static double MToFt(double m) => UnitUtils.ConvertToInternalUnits(m, UnitTypeId.Meters);
        public static double FtToM(double ft) => UnitUtils.ConvertFromInternalUnits(ft, UnitTypeId.Meters);

        /// Build a Revit XYZ (feet) from metre coordinates.
        public static XYZ Pt(double xM, double yM, double zM = 0.0) =>
            new XYZ(MToFt(xM), MToFt(yM), MToFt(zM));

        /// A Revit XYZ (feet) -> {"x","y","z"} in metres, rounded — the snapshot's coordinate shape.
        public static Dictionary<string, object> XyzM(XYZ p) => new Dictionary<string, object>
        {
            ["x"] = Math.Round(FtToM(p.X), 3),
            ["y"] = Math.Round(FtToM(p.Y), 3),
            ["z"] = Math.Round(FtToM(p.Z), 3),
        };

        public static double R3(double v) => Math.Round(v, 3);
    }
}
