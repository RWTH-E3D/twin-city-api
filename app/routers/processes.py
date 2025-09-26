from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import ValidationError
import logging
from app.models.base_models import LandingPage, Link, ConformanceClasses
from app.models.process_models import (
    ProcessList,
    StatusInfo,
    ExecuteRequest,
    Results,
    JobList,
    StatusCode,
)
from app.dependencies.process_manager import process_manager
from app.dependencies.process_registry import process_registry

router = APIRouter(
    prefix="/processes",
    tags=["processes"],
    responses={404: {"description": "Not found"}},
)
logger = logging.getLogger(__name__)


@router.get("/", response_model=LandingPage)
async def get_landing_page():
    return LandingPage(
        title="Twin City Processes API",
        description="Perform cityDPC processes",
        links=[
            Link(
                href="/",
                rel="self",
                type="application/json",
                title="this document",
            ),
            Link(
                href="/conformance",
                rel="conformance",
                type="application/json",
                title="conformance classes implemented by this server",
            ),
            Link(
                href="/processes",
                rel="processes",
                type="application/json",
                title="The processes",
            ),
        ],
    )


@router.get("/conformance", response_model=ConformanceClasses)
async def get_conformance():
    return ConformanceClasses(
        conformsTo=[
            "http://www.opengis.net/spec/ogcapi-processes/1.0/conf/core"
        ]
    )


@router.get("/processes", response_model=ProcessList)
async def get_processes():
    """Retrieve the list of available processes"""
    logger.info("Retrieving list of processes")
    return ProcessList(
        processes=process_registry.get_process_summaries(),
        links=[
            Link(
                href="/processes",
                rel="self",
                type="application/json",
                title="The processes",
            )
        ],
    )


@router.get("/processes/{process_id}")
async def get_process(process_id: str):
    """Retrieve information about a specific process"""
    process_summaries = process_registry.get_process_summaries()

    for process in process_summaries:
        if process.id == process_id:
            return process

    raise HTTPException(
        status_code=404,
        detail=f"Process '{process_id}' not found. "
        + "Available processes: "
        + str(process_registry.get_available_processes()),
    )


@router.post("/processes/{process_id}/execution", response_model=StatusInfo)
async def execute_process(
    process_id: str,
    execute_request: ExecuteRequest,
    background_tasks: BackgroundTasks,
):
    # Check if process exists
    process_func = process_registry.get_process(process_id)
    if not process_func:
        raise HTTPException(
            status_code=404,
            detail=f"Process '{process_id}' not found. "
            + "Available processes: "
            + str(process_registry.get_available_processes()),
        )

    try:
        validated_input = process_func.input_model(**execute_request.inputs)

        job = await process_manager.create_job(process_id)

        background_tasks.add_task(
            process_manager.start_job_processing,
            job.jobID,
            process_registry.execute_process,
            process_id=process_id,
            input_data=validated_input.model_dump(),
        )

        return job

    except ValidationError as e:
        raise HTTPException(
            status_code=422,
            detail=str(e),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=422,
            detail=str(e),
        )
    except Exception as e:
        logger.exception(f"Failed to start process {process_id}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start process: {str(e)}",
        )


@router.get("/jobs", response_model=JobList)
async def list_jobs():
    """List all jobs"""
    return process_manager.list_jobs()


@router.get("/jobs/{job_id}", response_model=StatusInfo)
async def get_job_status(job_id: str):
    """Get status of a job"""
    job = process_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.delete("/jobs/{job_id}", response_model=StatusInfo)
async def cancel_job(job_id: str):
    """Cancel a running job"""
    job = process_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status in (
        StatusCode.successful,
        StatusCode.failed,
        StatusCode.dismissed,
    ):
        raise HTTPException(status_code=400, detail="Job is already complete")

    cancelled = await process_manager.cancel_job(job_id)
    if not cancelled:
        raise HTTPException(status_code=400, detail="Could not cancel job")

    return process_manager.get_job(job_id)


@router.get("/jobs/{job_id}/results", response_model=Results)
async def get_job_results(job_id: str):
    """Get results of a completed job"""
    job = process_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status != StatusCode.successful:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot get results. Job status: {job.status}",
        )

    if not job.results:
        raise HTTPException(
            status_code=404, detail="No results found for this job"
        )

    # Wrap the results in the expected format
    return Results(result=job.results)
