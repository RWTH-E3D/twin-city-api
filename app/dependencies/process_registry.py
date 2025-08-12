from dataclasses import dataclass
from typing import Callable, Dict, Optional, Type, List, Any
from pydantic import BaseModel, ValidationError
from app.models.process_models import ProcessSummary, JobControlOptions
from app.models.base_models import Link
import logging
import json
from app.core.config import settings
from pydantic import Field, field_validator
from app.dependencies.collection_manager import catalog
from citydpc import Dataset
from citydpc.core.input.cityjsonInput import (
    load_buildings_from_json_file,
    load_buildings_from_dict,
)
from citydpc.tools.partywall import get_party_walls

logger = logging.getLogger(__name__)


class ProcessExecutionError(Exception):
    """Custom exception for process execution errors"""

    pass


class ProcessValidationError(ProcessExecutionError):
    """Custom exception for input validation errors"""

    pass


@dataclass
class ProcessDefinition:
    process_func: Callable
    summary: ProcessSummary
    input_model: Type[BaseModel]
    output_model: Type[BaseModel]


class ProcessRegistry:
    def __init__(self):
        self._processes: Dict[str, ProcessDefinition] = {}

    def _create_schema_dict(self, model: Type[BaseModel]) -> dict[str, Any]:
        """Convert Pydantic model schema to a simplified, readable format"""
        schema = model.model_json_schema()
        for key in ["title", "$defs", "$schema"]:
            schema.pop(key, None)
        return schema

    def register_process(
        self,
        process_id: str,
        process_func: Callable,
        title: str,
        description: str,
        input_model: Type[BaseModel],
        output_model: Type[BaseModel],
        version: str = "1.0.0",
    ) -> None:
        input_schema = self._create_schema_dict(input_model)
        output_schema = self._create_schema_dict(output_model)
        summary = ProcessSummary(
            id=process_id,
            title=title,
            description=description,
            version=version,
            jobControlOptions=[JobControlOptions.async_execute],
            links=[
                Link(
                    href=f"/processes/{process_id}",
                    rel="self",
                    type="application/json",
                )
            ],
            inputs=input_schema,
            outputs=output_schema,
        )

        self._processes[process_id] = ProcessDefinition(
            process_func=process_func,
            summary=summary,
            input_model=input_model,
            output_model=output_model,
        )

    async def execute_process(self, process_id: str, input_data: dict) -> dict:
        """Execute a process with input validation"""
        process = self._processes.get(process_id)
        if not process:
            raise ProcessExecutionError(f"Process '{process_id}' not found")

        try:
            validated_input = process.input_model(**input_data)

            result = await process.process_func(validated_input.model_dump())

            validated_output = process.output_model(**result)

            return validated_output.model_dump()

        except ValidationError as e:
            raise ProcessValidationError(f"Validation error: {str(e)}")
        except Exception as e:
            raise ProcessExecutionError(f"Process execution failed: {str(e)}")

    def get_process(self, process_id: str) -> Optional[ProcessDefinition]:
        """Get process definition by ID"""
        return self._processes.get(process_id)

    def get_process_summaries(self) -> list[ProcessSummary]:
        """Get list of all process summaries"""
        return [proc.summary for proc in self._processes.values()]

    def get_available_processes(self) -> list[str]:
        """Get list of available process IDs"""
        return list(self._processes.keys())


process_registry = ProcessRegistry()


class cjSeqInputModel(BaseModel):
    cj_base: dict = Field(
        ...,
        description="CityJSON base data to save",
    )
    cj_features: List[dict] = Field(
        ...,
        description="CityJSON features to save",
    )

    @field_validator("cj_base", mode="after")
    def validate_cjBase(cls, v: List[dict]) -> List[dict]:
        if not v:
            raise ValueError("cj_base cannot be empty")
        return v

    @field_validator("cj_features", mode="after")
    def validate_cjFeatures(cls, v: List[dict]) -> List[dict]:
        if not v:
            raise ValueError("cj_features cannot be empty")
        return v


class BasicOutputModel(BaseModel):
    numBuildings: int = Field(
        ..., description="Number of buildings in collection"
    )
    status: str = Field(..., description="Processing status")


async def process_sent_collection(input_data: dict) -> dict:
    """Save a collection with given IDs"""
    try:
        cjBase = input_data["cj_base"]
        cjFeatures = input_data["cj_features"]
        newDataset = Dataset()
        load_buildings_from_dict(newDataset, cjBase, cjFeatures)
        numBuildings = len(newDataset.buildings)
        return {
            "numBuildings": numBuildings,
            "status": "success",
        }
    except Exception as e:
        logger.exception("Error in sending collection")
        raise RuntimeError(f"Process failed: {str(e)}")


process_registry.register_process(
    "process_sent_collection",
    process_sent_collection,
    "Process Sent Collection",
    "Process a collection sent in CityJSON format",
    input_model=cjSeqInputModel,
    output_model=BasicOutputModel,
)


class PartyWallInput(BaseModel):
    model_config = {
        "validate_all": False,
    }
    collection_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Name of the collection to process",
    )
    ids: List[str] = Field(
        default=[],
        min_items=0,
        max_items=1000,
        description="List of IDs to process from the collection. "
        + "Must be empty or contain at least 2 unique IDs.",
    )

    @field_validator("collection_name")
    def validate_collection_name(cls, v: str) -> str:
        v = v.strip()
        if not v.replace("_", "").isalnum():
            raise ValueError(
                "Collection name must contain only letters, numbers, and "
                + "underscores"
            )
        if v not in catalog.collections:
            raise ValueError("Collection not found in catalog")
        cls._collection_data = catalog.get_collection(v)
        return v

    @field_validator("ids", mode="after")
    def validate_ids(cls, v: List[str], info) -> List[str]:
        collection_data = getattr(cls, "_collection_data", None)
        if collection_data is None:
            raise ValueError("Cannot validate IDs without valid collection")

        if not v:
            return v

        if len(v) < 2:
            raise ValueError("If IDs are provided, at least 2 must be given")

        unique_ids = list(dict.fromkeys(v))
        if len(unique_ids) < 2:
            raise ValueError("At least 2 unique IDs must be provided")

        bIds = collection_data["buildingIds"]

        for id in unique_ids:
            id = id.strip()
            if not id:
                raise ValueError("IDs cannot be empty")
            if id not in bIds:
                raise ValueError(f"ID '{id}' not found in collection")
        return unique_ids


class PartyWallOutput(BaseModel):
    processed_collection: str = Field(
        ..., description="Name of the processed collection"
    )
    processed_ids: List[str] = Field(..., description="List of processed IDs")
    party_walls: List[dict] = Field(..., description="Party wall information")
    status: str = Field(..., description="Processing status")


async def calculate_partywalls_on_saved_collection(input_data: dict) -> dict:
    """Process a collection with given IDs"""
    try:
        collection_name = input_data["collection_name"]
        ids = input_data["ids"]
        if not ids:
            ids = catalog.get_collection(collection_name)["buildingIds"]

        newDataset = Dataset()
        load_buildings_from_json_file(
            newDataset,
            str(settings.LOADED_COLLECTIONS_DIR)
            + f"/{collection_name}.city.jsonl",
            cityJSONSeq=True,
            allowedIDs=ids,
        )
        partyWalls = get_party_walls(newDataset)
        detailed = []
        for entry in partyWalls:
            detailed.append(
                {
                    "bID0": entry[0],
                    "wID0": entry[1],
                    "bID1": entry[2],
                    "wID1": entry[3],
                    "area": entry[4],
                    "surface": entry[5],
                }
            )

        result = {
            "processed_collection": collection_name,
            "processed_ids": ids,
            "party_walls": detailed,
            "status": "success",
        }

        return result
    except Exception as e:
        logger.exception("Error in party wall calculation")
        raise RuntimeError(f"Process failed: {str(e)}")


process_registry.register_process(
    "partywall_calculation",
    calculate_partywalls_on_saved_collection,
    "Party Wall Calculation on saved collections",
    "Calculate party wall information for a saved collection",
    input_model=PartyWallInput,
    output_model=PartyWallOutput,
)


async def calculate_partywalls_on_sent_collection(input_data: dict) -> dict:
    """Process a collection with given IDs"""
    try:
        cjBase = input_data["cj_base"]
        cjFeatures = input_data["cj_features"]
        newDataset = Dataset()
        load_buildings_from_dict(newDataset, cjBase, cjFeatures)
        partyWalls = get_party_walls(newDataset)
        detailed = []
        for entry in partyWalls:
            lOfFloats = [
                [float(i[0]), float(i[1]), float(i[2])] for i in entry[5]
            ]
            detailed.append(
                {
                    "bID0": entry[0],
                    "wID0": entry[1],
                    "bID1": entry[2],
                    "wID1": entry[3],
                    "area": float(entry[4]),
                    "surface": lOfFloats,
                }
            )
        print(detailed)

        result = {
            "processed_collection": "sent_collection",
            "processed_ids": list(newDataset.buildings.keys()),
            "party_walls": detailed,
            "status": "success",
        }

        return result
    except Exception as e:
        logger.exception("Error in party wall calculation")
        raise RuntimeError(f"Process failed: {str(e)}")


process_registry.register_process(
    "partywall_calculation_sent",
    calculate_partywalls_on_sent_collection,
    "Party Wall Calculation on sent data",
    "Calculate party wall information for a sent features",
    input_model=cjSeqInputModel,
    output_model=PartyWallOutput,
)


class SaveInputModel(BaseModel):
    new_collection_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Name of the collection to save",
    )
    cj_base: dict = Field(
        ...,
        description="CityJSON base data to save",
    )
    cj_features: List[dict] = Field(
        ...,
        description="CityJSON features to save",
    )

    @field_validator("new_collection_name")
    def validate_collection_name(cls, v: str) -> str:
        v = v.strip()
        if not v.replace("_", "").isalnum():
            raise ValueError(
                "Collection name must contain only letters, numbers, and "
                + "underscores"
            )
        if v in catalog.collections:
            raise ValueError("Collection already found in catalog")
        cls._collection_data = catalog.get_collection(v)
        return v

    @field_validator("cj_base", mode="after")
    def validate_cjBase(cls, v: List[dict]) -> List[dict]:
        if not v:
            raise ValueError("cj_base cannot be empty")
        return v

    @field_validator("cj_features", mode="after")
    def validate_cjFeatures(cls, v: List[dict]) -> List[dict]:
        if not v:
            raise ValueError("cj_features cannot be empty")
        return v


class SaveOutputModel(BaseModel):
    new_collection_name: str = Field(
        ..., description="Name of the saved collection"
    )
    status: str = Field(..., description="Processing status")


async def save_collection(input_data: dict) -> dict:
    """Save a collection with given IDs"""
    collection_name = input_data["new_collection_name"]
    cjBase = input_data["cj_base"]
    cjFeatures = input_data["cj_features"]
    newFilePath = (
        str(settings.COLLECTIONS_BASE_DIR) + f"/{collection_name}.city.jsonl"
    )
    try:
        with open(newFilePath, "w") as f:
            f.write(json.dumps(cjBase) + "\n")
            for feature in cjFeatures:
                f.write(json.dumps(feature) + "\n")

        success, _ = await catalog.load_single_collection(
            newFilePath, settings.UPLOADED_COLLECTIONS_DIR
        )

        if not success:
            raise RuntimeError("Failed to load collection")

        result = {
            "new_collection_name": collection_name,
            "status": "success",
        }

        return result

    except Exception as e:
        logger.exception("Error in saving collection")
        raise RuntimeError(f"Process failed: {str(e)}")


process_registry.register_process(
    "save_collection",
    save_collection,
    "Save Collection",
    "Save a new collection to the catalog",
    input_model=SaveInputModel,
    output_model=SaveOutputModel,
)


class CityJSONFeatureModel(BaseModel):
    cityJSONHeader: dict = Field(
        ...,
        description="CityJSON dict containing: type, version, transform, "
        + "translate",
    )
    cityJSONFeatureObject: dict = Field(
        ...,
        description="CityJSONFeature Object, containing the keys: type, id, "
        + "CityObjects, vertices",
    )

    @field_validator("cityJSONHeader")
    def validate_cityJSONHeader(cls, v: dict) -> dict:
        neededKeys = ["type", "version", "transform", "translate"]
        for key in neededKeys:
            if key not in v.keys():
                raise ValueError(f"Object missing '{key}' key")

    @field_validator("cityJSONFeatureObject")
    def validate_cityJSONFeatureObject(cls, v: dict) -> dict:
        neededKeys = ["type", "id", "CityObjects", "vertices"]
        for key in neededKeys:
            if key not in v.keys():
                raise ValueError(f"Object missing '{key}' key")


class GeneralOutputModel(BaseModel):
    dictionary: dict = Field(
        ..., description="Dictionary containing the result"
    )


async def process_cityjson_feature(
    cityJSONHeader: dict, cityJSONFeature
) -> dict:
    """Process a CityJSON feature"""
    try:
        return {
            "len": len(cityJSONFeature["CityObjects"]),
            "hasHeader": bool(len(cityJSONHeader.keys())),
        }
    except Exception as e:
        logger.exception("Error in processing CityJSON feature")
        raise RuntimeError(f"Process failed: {str(e)}")


process_registry.register_process(
    "process_cityjson_feature",
    process_cityjson_feature,
    "Process CityJSON Feature",
    "Perform a basic operation on a CityJSON feature",
    input_model=CityJSONFeatureModel,
    output_model=GeneralOutputModel,
)
