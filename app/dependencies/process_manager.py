from typing import Dict, Optional, Any
import uuid
import datetime
import asyncio
import logging
import json
import pathlib
from app.models.process_models import (
    StatusInfo,
    StatusCode,
    JobList,
    Link,
    ProcessError,
)

logger = logging.getLogger(__name__)


class ProcessManager:
    def __init__(self, storage_path: str = "process/process_data.json"):
        self.jobs: Dict[str, StatusInfo] = {}
        self.active_tasks: Dict[str, asyncio.Task] = {}
        self.results: Dict[str, Any] = {}
        self.storage_path = pathlib.Path(storage_path)

    async def initialize(self):
        """Initialize the ProcessManager and load saved state"""
        logger.info("Initializing ProcessManager...")

        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

        await self.load_state()

    async def cleanup(self):
        """Clean up ProcessManager state and save data"""
        logger.info("Cleaning up ProcessManager...")

        # Cancel all active tasks
        for job_id, task in self.active_tasks.items():
            if not task.done():
                logger.info(f"Cancelling active job {job_id}")
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    await self.update_job_status(
                        job_id,
                        StatusCode.dismissed,
                        message="Job cancelled due to server shutdown",
                        error={
                            "code": "server_shutdown",
                            "description": "The job was cancelled due to "
                            + "server shutdown",
                        },
                    )

        # Save final state
        await self.save_state()

    async def load_state(self):
        """Load saved jobs and results from storage"""
        try:
            if self.storage_path.exists():
                async with asyncio.Lock():
                    content = await asyncio.to_thread(
                        self.storage_path.read_text
                    )
                    data = json.loads(content)

                    # Restore jobs (converting dict to StatusInfo objects)
                    for job_data in data.get("jobs", []):
                        for date_field in [
                            "created",
                            "updated",
                            "started",
                            "finished",
                        ]:
                            if job_data.get(date_field):
                                job_data[date_field] = (
                                    datetime.datetime.fromisoformat(
                                        job_data[date_field]
                                    )
                                )

                        if job_data.get("errors"):
                            for error in job_data["errors"]:
                                if error.get("timestamp"):
                                    error["timestamp"] = (
                                        datetime.datetime.fromisoformat(
                                            error["timestamp"]
                                        )
                                    )

                        status = StatusInfo(**job_data)
                        if status.status == StatusCode.successful:
                            self.jobs[status.jobID] = status
                            if status.results:
                                self.results[status.jobID] = status.results

                logger.info(
                    f"Loaded {len(self.jobs)} completed jobs from storage"
                )
        except Exception as e:
            logger.error(f"Error loading state: {str(e)}")
            # Continue with empty state if load fails
            self.jobs = {}
            self.results = {}

    async def save_state(self):
        """Save current jobs and results to storage"""
        try:
            async with asyncio.Lock():
                # Filter for completed jobs only
                completed_jobs = {
                    job_id: job
                    for job_id, job in self.jobs.items()
                    if job.status == StatusCode.successful
                }

                # Prepare data for serialization
                data = {
                    "jobs": [
                        {
                            **job.model_dump(),
                            "created": job.created.isoformat(),
                            "updated": job.updated.isoformat(),
                            "started": (
                                job.started.isoformat()
                                if job.started
                                else None
                            ),
                            "finished": (
                                job.finished.isoformat()
                                if job.finished
                                else None
                            ),
                            "errors": (
                                [
                                    {
                                        **error.model_dump(),
                                        "timestamp": error.timestamp.isoformat(),
                                    }
                                    for error in (job.errors or [])
                                ]
                                if job.errors
                                else None
                            ),
                        }
                        for job in completed_jobs.values()
                    ]
                }

                # Save to file
                json_str = json.dumps(data, indent=2)
                await asyncio.to_thread(self.storage_path.write_text, json_str)

                logger.info(
                    f"Saved {len(completed_jobs)} completed jobs to storage"
                )
        except Exception as e:
            logger.error(f"Error saving state: {str(e)}")

    async def create_job(self, process_id: str) -> StatusInfo:
        """Create a new job"""
        job_id = str(uuid.uuid4())
        now = datetime.datetime.now(datetime.timezone.utc)

        status = StatusInfo(
            processID=process_id,
            jobID=job_id,
            status=StatusCode.accepted,
            created=now,
            updated=now,
            progress=0,
        )

        self.jobs[job_id] = status
        return status

    async def update_job_status(
        self,
        job_id: str,
        status: StatusCode,
        message: Optional[str] = None,
        progress: Optional[int] = None,
        error: Optional[Dict] = None,
        results: Optional[Dict] = None,
    ) -> Optional[StatusInfo]:
        """Update job status with error handling and persistence"""
        job = self.get_job(job_id)
        if not job:
            return None

        now = datetime.datetime.now(datetime.timezone.utc)
        job.status = status
        job.updated = now

        if message:
            job.message = message
        if progress is not None:
            job.progress = progress
        if error:
            if job.errors is None:
                job.errors = []
            job.errors.append(
                ProcessError(
                    code=error.get("code", "unknown_error"),
                    description=error.get(
                        "description", "An unknown error occurred"
                    ),
                    timestamp=now,
                )
            )
        if results is not None:
            job.results = results

        if status == StatusCode.running and not job.started:
            job.started = now
        elif status in (StatusCode.successful, StatusCode.failed):
            job.finished = now

        # Save state when a job completes successfully
        if status == StatusCode.successful:
            await self.save_state()

        return job

    def get_job(self, job_id: str) -> Optional[StatusInfo]:
        return self.jobs.get(job_id)

    def list_jobs(self) -> JobList:
        return JobList(
            jobs=list(self.jobs.values()),
            links=[
                Link(
                    href="/processes/jobs",
                    rel="self",
                    type="application/json",
                    title="List of jobs",
                )
            ],
        )

    async def start_job_processing(self, job_id: str, process_func, **kwargs):
        """Start processing a job with error handling"""
        try:
            # Create and store the task
            task = asyncio.create_task(
                self._process_job(job_id, process_func, **kwargs)
            )
            self.active_tasks[job_id] = task

            # Wait for completion
            await task

        except Exception as e:
            logger.exception(f"Error processing job {job_id}")
            await self.update_job_status(
                job_id,
                StatusCode.failed,
                message="Unexpected error during processing",
                error={"code": "processing_error", "description": str(e)},
            )
        finally:
            # Clean up
            self.active_tasks.pop(job_id, None)

    async def _process_job(self, job_id: str, process_func, **kwargs):
        """Internal method to handle job processing"""
        try:
            # Update status to running
            await self.update_job_status(
                job_id,
                StatusCode.running,
                message="Processing started",
                progress=0,
            )

            # Execute the actual process
            results = await process_func(**kwargs)

            # Update with success
            await self.update_job_status(
                job_id,
                StatusCode.successful,
                message="Processing completed successfully",
                progress=100,
                results=results,
            )

        except Exception as e:
            logger.exception(f"Process execution failed for job {job_id}")
            await self.update_job_status(
                job_id,
                StatusCode.failed,
                message="Process execution failed",
                error={"code": "execution_error", "description": str(e)},
            )
            raise

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a running job"""
        task = self.active_tasks.get(job_id)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                await self.update_job_status(
                    job_id,
                    StatusCode.dismissed,
                    message="Job was cancelled",
                    error={
                        "code": "job_cancelled",
                        "description": "The job was cancelled by user request",
                    },
                )
                return True
        return False

    def get_results(self, job_id: str) -> Optional[Dict]:
        return self.results.get(job_id)


process_manager = ProcessManager()
