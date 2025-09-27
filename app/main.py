from contextlib import asynccontextmanager
from fastapi import FastAPI
from .routers import features, processes
from fastapi.middleware.cors import CORSMiddleware
from app.dependencies.collection_manager import catalog
from app.dependencies.process_manager import process_manager
from app.models.base_models import LandingPage, Link
from app.core.config import settings
from app.core.logging_config import setup_logging

setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting up Twin City API...")
    await catalog.initialize()
    await process_manager.initialize()
    print("Twin City API initialization complete!")
    yield
    print("Shutting down Twin City API...")
    await process_manager.cleanup()
    await catalog.cleanup()
    print("Twin City API shutdown complete!")


app = FastAPI(
    title=settings.APP_NAME,
    description="OGC API Features and Processes implementation",
    version=settings.API_VERSION,
    lifespan=lifespan,
    openapi_tags=[
        {
            "name": "default",
            "description": "Main API endpoints",
        },
        {
            "name": "features",
            "description": "OGC API Features endpoints for building data",
            "externalDocs": {
                "description": "OGC API Features Specification",
                "url": "https://docs.ogc.org/is/17-069r3/17-069r3.html",
            },
        },
        {
            "name": "processes",
            "description": "OGC API Processes endpoints for building data "
            + "processing",
            "externalDocs": {
                "description": "OGC API Processes Specification",
                "url": "https://docs.ogc.org/is/18-062r2/18-062r2.html",
            },
        },
    ],
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", tags=["default"])
async def landing_page():
    """API Landing page"""
    return LandingPage(
        title="Twin City API",
        description="Access to feature data and processes",
        links=[
            Link(
                href="/",
                rel="self",
                type="application/json",
                title="This document",
            ),
            Link(
                href="/features",
                rel="features",
                type="application/json",
                title="Features API",
            ),
            Link(
                href="/processes",
                rel="processes",
                type="application/json",
                title="Processes API",
            ),
            Link(
                href="/docs",
                rel="documentation",
                type="text/html",
                title="API Documentation",
            ),
        ],
    )


app.include_router(features.router)
app.include_router(processes.router)
