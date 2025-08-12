from typing import Dict, List
from fastapi import HTTPException
import os
import glob
import json
from app.dependencies.file_loader import load_file_to_dataset
from app.dependencies.geo_utils import check_geoext_overlap
from pyproj import Transformer
from citydpc import Dataset
from citydpc.core.output.cityjsonOutput import write_cityjson_file
from app.core.config import settings
from app.models.base_models import Link
import logging

logger = logging.getLogger(__name__)


class CollectionManager:
    def __init__(self):
        self.collections = {}
        self.is_initialized = False
        self._collectionsPath = settings.COLLECTIONS_BASE_DIR
        self._loadedPath = settings.LOADED_COLLECTIONS_DIR
        self._importedPath = settings.IMPORTED_COLLECTIONS_DIR

    async def initialize(self):
        if self.is_initialized:
            return
        logger.info("initializing CollectionManager")
        await self.load_collections()
        self.is_initialized = True

    async def cleanup(self):
        logger.info("Cleaning up CollectionManager")
        self.collections = {}
        self.is_initialized = False

    async def _load_single_collection(
        self, item_path: str, moveToPath: str = None
    ) -> tuple[bool, str]:
        """
        Load a single collection from a file or directory path.

        Args:
            item_path (str): Path to the collection file or directory
            moveToPath (str): Path to move the collection to after loading

        Returns:
            tuple[bool, str]: (success status, collection basename or error
            message)
        """
        try:
            item = os.path.basename(item_path)
            logger.info(f"Loading single collection from {item}")

            newDataset = Dataset()

            if os.path.isdir(item_path):
                logger.info(f"Creating collection from directory {item}")
                for file in os.listdir(item_path):
                    file_path = os.path.join(item_path, file)
                    newDataset = load_file_to_dataset(file_path, newDataset)
                basename = item
            else:
                logger.info(f"Creating collection from file {item}")
                newDataset = load_file_to_dataset(item_path, newDataset)
                if item.endswith(".gml") or item.endswith(".xml"):
                    basename = item.rsplit(".", maxsplit=1)[0]
                elif item.endswith(".city.json") or item.endswith(
                    ".city.jsonl"
                ):
                    basename = item.rsplit(".", maxsplit=2)[0]
                else:
                    return False, f"Unsupported file type: {item}"

            if len(newDataset) < 1:
                return False, f"No features found in {item}"

            ldedName = os.path.join(self._loadedPath, f"{basename}.city.jsonl")
            if os.path.exists(ldedName):
                return False, f"Collection {basename} already exists"

            write_cityjson_file(newDataset, ldedName, cityJSONSeq=True)
            logger.info(f"Created collection {basename}")

            if moveToPath is None:
                moveToPath = self._importedPath
            if os.path.isdir(item_path):
                logger.info(f"Moving directory {item} to imported")
                for file in os.listdir(item_path):
                    os.rename(
                        os.path.join(item_path, file),
                        os.path.join(moveToPath, file),
                    )
                os.rmdir(item_path)
            else:
                logger.info(f"Moving file {item} to imported")
                os.rename(item_path, os.path.join(moveToPath, item))

            return True, basename

        except Exception as e:
            logger.error(f"Error loading collection: {str(e)}")
            return False, str(e)

    async def load_single_collection(
        self, item_path: str, moveToPath: str = None
    ) -> tuple[bool, str]:
        """
        Public method to load a single collection after initialization.

        Args:
            item_path (str): Path to the collection file or directory
            moveToPath (str): Path to move the collection to after loading

        Returns:
            tuple[bool, str]: (success status, collection basename or error
            message)
        """
        if not self.is_initialized:
            return False, "CollectionManager not initialized"

        if not os.path.exists(item_path):
            return False, f"Path does not exist: {item_path}"

        return await self._load_single_collection(item_path, moveToPath)

    async def load_collections(self):
        """Load all collections from the collections directory"""
        logger.info("Loading collections")

        reservedDirs = [
            os.path.basename(p)
            for p in [
                settings.LOADED_COLLECTIONS_DIR,
                settings.IMPORTED_COLLECTIONS_DIR,
                settings.UPLOADED_COLLECTIONS_DIR,
            ]
        ]

        logger.info("Checking collections folder")
        for item in os.listdir(self._collectionsPath):
            print("checking", item)
            itemPath = os.path.join(self._collectionsPath, item)

            if os.path.isdir(itemPath) and item in reservedDirs:
                continue

            success, result = await self._load_single_collection(itemPath)
            if not success:
                logger.warning(f"Failed to load collection {item}: {result}")

        logger.info("Loading processed collections")
        cjseqs = glob.glob(str(self._loadedPath) + "/*.city.jsonl")
        for cjseq in cjseqs:
            basename = os.path.basename(cjseq).rsplit(".", maxsplit=2)[0]
            if basename not in self.collections:
                logger.info(f"Loading processed collection: {basename}")

                try:
                    with open(cjseq, "r") as f:
                        listOfDicts = [json.loads(line) for line in f]

                    data = listOfDicts[0]
                    if "metadata" not in data:
                        logger.warning(f"Metadata not found in {cjseq}")
                        continue

                    meta = data["metadata"]
                    if (
                        "geographicalExtent" not in meta
                        or "referenceSystem" not in meta
                    ):
                        logger.warning(
                            "Geographical extent or reference system not found"
                            + f" in {cjseq}"
                        )
                        continue

                    geoExt = meta["geographicalExtent"]
                    referenceSystem = meta["referenceSystem"]
                    refSysSplit = referenceSystem.rsplit("/", maxsplit=1)[-1]

                    transformer = Transformer.from_crs(
                        f"EPSG:{refSysSplit}", "EPSG:4326", always_xy=True
                    )
                    minx, miny = transformer.transform(geoExt[0], geoExt[1])
                    maxx, maxy = transformer.transform(geoExt[3], geoExt[4])
                    bbox = [minx, miny, maxx, maxy]

                    numOfFeatures = len(listOfDicts) - 1
                    ids = [f["id"] for f in listOfDicts[1:]]

                    collection = {
                        "id": basename,
                        "title": basename,
                        "description": f"Collection {basename} of buildings "
                        + f"loaded from {cjseq} using CityDPC",
                        "itemType": "feature",
                        "links": [
                            Link(
                                href=f"/features/collections/{basename}/",
                                rel="self",
                                type="application/city-json",
                                title=f"{basename} collection",
                            ),
                            Link(
                                href=f"/features/collections/{basename}/items",
                                rel="items",
                                type="application/city+json-seq",
                                title=f"{basename} items",
                            ),
                        ],
                        "extent": {
                            "spatial": {
                                "bbox": bbox,
                                "crs": "https://www.opengis.net/def/crs/"
                                + "EPSG/0/4326",
                            }
                        },
                        "crs": [referenceSystem],
                        "storageCrs": referenceSystem,
                        "numOfItems": numOfFeatures,
                        "buildingIds": ids,
                    }

                    if "title" in meta:
                        collection["title"] = meta["title"]

                    self.collections[basename] = collection
                    logger.info(f"Loaded processed collection: {basename}")

                except Exception as e:
                    logger.error(
                        f"Error loading processed collection {basename}: "
                        + str(e)
                    )

        logger.info("Collections loading complete")
        logger.info(f"Available collections: {self.collections}")

    def get_collection(self, collection_id: str) -> Dict:
        return self.collections.get(collection_id)

    async def get_items_from_collection(
        self, collectionId: str, bbox: List[float], limit: int, offset: int
    ) -> tuple[List[Dict], int]:
        collection = self.get_collection(collectionId)
        file = os.path.join(self._loadedPath, f"{collectionId}.city.jsonl")
        if not collection or not os.path.isfile(file):
            raise HTTPException(status_code=404, detail="Collection not found")

        with open(file, "r") as f:
            listOfDicts = [json.loads(line) for line in f]

        cjBase = listOfDicts[0]
        cjFeatures = listOfDicts[1:]
        validIndices = []
        stopIndex = min(offset + limit, len(cjFeatures))

        if stopIndex < 0:
            stopIndex = len(cjFeatures)

        if bbox is not None:
            if len(bbox) != 4:
                raise HTTPException(400, "bbox parameter has invalid length")

            mData = cjBase["metadata"]
            refSysSplit = mData["referenceSystem"].rsplit("/", maxsplit=1)[-1]
            geoExt = mData["geographicalExtent"]

            transformer = Transformer.from_crs(
                f"EPSG:{refSysSplit}", "EPSG:4326", always_xy=True
            )
            overlap = check_geoext_overlap(geoExt, bbox, transformer)
            if not overlap:
                return ([cjBase, []], 0)

            for i, feature in enumerate(cjFeatures):
                id = feature["id"]
                mainFeature = feature["CityObjects"][id]
                fGeoExt = mainFeature["geographicalExtent"]
                fOverlap = check_geoext_overlap(fGeoExt, bbox, transformer)
                if fOverlap:
                    validIndices.append(i)
            return (
                [
                    cjBase,
                    *[cjFeatures[i] for i in validIndices[offset:stopIndex]],
                ],
                len(validIndices),
            )

        return ([cjBase, *cjFeatures[offset:stopIndex]], len(cjFeatures))


catalog = CollectionManager()
