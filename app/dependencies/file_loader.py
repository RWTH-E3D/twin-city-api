import os
from citydpc import Dataset
from citydpc.core.input.citygmlInput import load_buildings_from_xml_file
from citydpc.core.input.cityjsonInput import load_buildings_from_json_file


def load_file_to_dataset(file_path: str, dataset=Dataset) -> Dataset:
    """Load a file into a CityDPC dataset"""
    if not os.path.isfile(file_path):
        print(f"File not file: {file_path}")
        return dataset

    try:
        if file_path.endswith((".gml", ".xml")):
            load_buildings_from_xml_file(dataset, file_path)
        elif file_path.endswith(".city.json"):
            load_buildings_from_json_file(dataset, file_path)
        elif file_path.endswith(".city.jsonl"):
            load_buildings_from_json_file(dataset, file_path, cityJSONSeq=True)
        else:
            print(f"Unsupported file format: {file_path}")
    except Exception as e:
        print(f"Error while loading {file_path}:", e)

    return dataset
