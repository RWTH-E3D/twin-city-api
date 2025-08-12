from typing import List
from pyproj import Transformer


def check_geoext_overlap(
    geoExt: List[float],
    bbox: List[float],
    transformer: Transformer | None = None,
) -> bool:
    """
    Check if a geographical extent overlaps with a bounding box.

    Parameters
    ----------
    geoExt : List[float]
        List of geographical extent [minx, miny, minz, maxx, maxy, maxz]
    bbox : List[float]
        Bounding box [minx, miny, maxx, maxy]
    transformer : Transformer | None
        Transformer to convert geoExt to same CRS as bbox

    Returns
    -------
    bool
        True if there is overlap, False otherwise
    """
    if transformer is not None:
        minx, miny = transformer.transform(geoExt[0], geoExt[1])
        maxx, maxy = transformer.transform(geoExt[3], geoExt[4])
    else:
        minx, miny = geoExt[0], geoExt[1]
        maxx, maxy = geoExt[3], geoExt[4]

    return not (
        maxx < bbox[0] or minx > bbox[2] or maxy < bbox[1] or miny > bbox[3]
    )
