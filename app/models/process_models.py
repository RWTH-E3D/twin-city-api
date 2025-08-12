from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
from datetime import datetime
from enum import Enum

from app.models.base_models import Link


class StatusCode(str, Enum):
    accepted = "accepted"
    running = "running"
    successful = "successful"
    failed = "failed"
    dismissed = "dismissed"


class JobControlOptions(str, Enum):
    sync_execute = "sync-execute"
    async_execute = "async-execute"
    dismiss = "dismiss"


class ProcessSummary(BaseModel):
    id: str
    title: Optional[str] = None
    description: Optional[str] = None
    version: str
    jobControlOptions: List[JobControlOptions]
    links: List[Link]
    inputs: Optional[dict] = Field(
        None, description="JSON Schema for process inputs"
    )
    outputs: Optional[dict] = Field(
        None, description="JSON Schema for process outputs"
    )


class ProcessList(BaseModel):
    processes: List[ProcessSummary]
    links: List[Link]


class ProcessError(BaseModel):
    code: str
    description: str
    timestamp: datetime


class StatusInfo(BaseModel):
    processID: str
    jobID: str
    status: StatusCode
    message: Optional[str] = None
    created: datetime
    started: Optional[datetime] = None
    finished: Optional[datetime] = None
    updated: datetime
    progress: Optional[int] = Field(None, ge=0, le=100)
    errors: Optional[List[ProcessError]] = None
    results: Optional[Dict[str, Any]] = None


class JobList(BaseModel):
    jobs: List[StatusInfo]
    links: List[Link]


class ExecuteRequest(BaseModel):
    inputs: Dict[str, Any]


class Results(BaseModel):
    result: Dict[str, Any]
