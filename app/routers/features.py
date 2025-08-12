from fastapi import APIRouter, HTTPException, Query, Response, Request
from typing import Optional
import json
from app.core.config import settings
from app.dependencies.collection_manager import catalog
from app.models.base_models import LandingPage, Link, ConformanceClasses

router = APIRouter(
    prefix="/features",
    tags=["features"],
    responses={404: {"description": "Not found"}},
)


@router.get("/")
async def features_landing():
    """Features API Landing page"""
    return LandingPage(
        title="Twin City Features API",
        description="Access to feature data",
        links=[
            Link(
                href="/features",
                rel="self",
                type="application/json",
                title="This document",
            ),
            Link(
                href="features/conformance",
                rel="conformance",
                type="application/json",
                title="Conformance",
            ),
            Link(
                href="features/collections",
                rel="data",
                type="application/json",
                title="Collections",
            ),
        ],
    )


@router.get("/conformance")
async def features_conformance():
    return ConformanceClasses(
        conformsTo=["https://www.cityjson.org/specs/2.0.1/"]
    )


@router.get("/collections")
async def get_collections():
    """Get all feature collections"""
    return {
        "collections": list(catalog.collections.values()),
        "links": [
            Link(
                href="/features/collections",
                rel="self",
                type="application/json",
                title="Collections",
            )
        ],
    }


@router.get("/collections/{collection_id}")
async def get_collection(collection_id: str):
    """Get specific collection"""
    collection = catalog.get_collection(collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")
    return collection


@router.get("/collections/{collection_id}/items")
async def get_features(
    collection_id: str,
    request: Request,
    bbox: Optional[str] = Query(
        None, description="Bounding box (minx,miny,maxx,maxy)"
    ),
    limit: Optional[int] = Query(10, ge=1, le=1000),
    offset: Optional[int] = Query(0, ge=0),
    f: Optional[str] = Query(None),
):
    """Get features from collection"""
    collection = catalog.get_collection(collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    if limit > settings.MAX_ITEMS_LIMIT:
        raise HTTPException(
            status_code=400,
            detail="Limit must be less than or equal to "
            + str(settings.MAX_ITEMS_LIMIT),
        )

    accept = request.headers.get("Accept")

    items, matched = await catalog.get_items_from_collection(
        collection_id, bbox, limit, offset
    )
    if (
        f is None
        or f == "city-json+seq"
        or (f is None and accept == "application/city-json+seq")
    ):
        return Response(
            content="\n".join(json.dumps(item) for item in items),
            media_type="application/city-json+seq",
        )
    elif f == "json" or (f is None and accept == "application/json"):
        return {
            "type": "FeatureCollection",
            "features": items[1:],
            "metadata": items[0],
            "links": [
                Link(
                    href=f"/features/collections/{collection_id}/items",
                    rel="self",
                    type="application/json",
                    title=f"Features in collection {collection_id}",
                ),
                Link(
                    href=f"/features/collections/{collection_id}/items?"
                    + f"offset={offset + limit}&limit={limit}",
                    rel="next",
                    type="application/json",
                    title=f"Collection {collection_id}",
                ),
            ],
            "numberMatched": matched,
            "numberReturned": len(items) - 1,
        }
    else:
        raise HTTPException(
            status_code=400, detail="Unsupported format requested"
        )


@router.get("/collections/{collection_id}/items/{item_id}")
async def get_feature(
    collection_id: str,
    item_id: str,
    request: Request,
    f: Optional[str] = Query(None),
):
    """Get specific feature from collection"""
    collection = catalog.get_collection(collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    items, matched = await catalog.get_items_from_collection(
        collection_id, None, -1, 0
    )

    cjBase = items[0]
    for item in items[1:]:
        if item["id"] == item_id:
            break
    else:
        return HTTPException(status_code=404, detail="Feature not found")

    accept = request.headers.get("Accept")

    if (
        f is None
        or f == "city-json+seq"
        or (f is None and accept == "application/city-json+seq")
    ):
        return Response(
            content="\n".join(json.dumps(i) for i in [cjBase, item]),
            media_type="application/city-json+seq",
            # media_type="text/plain",
        )
    elif f == "json" or (f is None and accept == "application/json"):
        return {
            "feature": item,
            "id": item_id,
            "links": [
                Link(
                    href=f"/features/collections/{collection_id}/items/"
                    + item_id,
                    rel="self",
                    type="application/json",
                    title=f"Feature {item_id}",
                ),
                Link(
                    href=f"/features/collections/{collection_id}/items",
                    rel="collection",
                    type="application/json",
                    title=f"Collection {collection_id}",
                ),
            ],
            "metadata": cjBase,
        }

    raise HTTPException(status_code=404, detail="Feature not found")
