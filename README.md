# TwinCityAPI

TwinCityAPI is a standardized server implementation for managing and processing 3D city models. Built on OGC API specifications, it provides both Features and Processes endpoints for comprehensive urban data management. For an optimal user experience, it is recommended to use this API with the [TwinCityViewer](https://github.com/RWTH-E3D/twin-city-viewer) frontend application.

## Key Features

- OGC API Features compliant endpoint for CityJSONSeq data delivery
- OGC API Processes endpoint for computational operations
- Built with FastAPI and [CityDPC](https://github.com/RWTH-E3D/CityDPC)
- Automatic CityGML/CityJSON import processing
- File-based data management system

## License

Available under the Apache 2.0 [License](License.md).
See the _Cite this repository_ function or the [CITATION.cff](CITATION.cff) for citation of this repository.

### Caveats

To load CityJSON/CityGML files please place them in the collections directory.
Please make sure that the coordinate system is given following the [CityJSON specification](https://www.cityjson.org/specs/2.0.1/#referencesystem-crs).

### Usage

Please make sure to install the required dependecies using

```bash
pip install -r requirements.txt
```

You can start the API by running

```bash
uvicorn app.main:app --reload
```

in your terminal.
Alternatively you can also run the [Dockerfile](Dockerfile)
