"""3D 图档解析（OpenCascade / OCP）

支持 .stp / .step / .igs / .iges
返回每个实体（solid）的包围盒尺寸与体积。
注意：.x_t（Parasolid）需要商业引擎，本解析器不支持。
"""
import os


def parse_cad(path):
    lower = path.lower()
    if lower.endswith((".igs", ".iges")):
        from OCP.IGESControl import IGESControl_Reader
        reader = IGESControl_Reader()
    else:
        from OCP.STEPControl import STEPControl_Reader
        reader = STEPControl_Reader()

    status = reader.ReadFile(path)
    reader.TransferRoots()
    shape = reader.OneShape()

    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_SOLID
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    from OCP.GProp import GProp_GProps
    from OCP.BRepGProp import BRepGProp

    result = []
    exp = TopExp_Explorer(shape, TopAbs_SOLID)
    idx = 0
    while exp.More():
        solid = exp.Current()
        idx += 1
        bb = Bnd_Box()
        BRepBndLib.Add_s(solid, bb)
        pmin = bb.CornerMin()
        pmax = bb.CornerMax()
        props = GProp_GProps()
        BRepGProp.VolumeProperties_s(solid, props)
        result.append({
            "name": f"零件{idx}",
            "x": round(pmax.X() - pmin.X(), 2),
            "y": round(pmax.Y() - pmin.Y(), 2),
            "z": round(pmax.Z() - pmin.Z(), 2),
            "volume": round(props.Mass(), 2),
        })
        exp.Next()

    return result
