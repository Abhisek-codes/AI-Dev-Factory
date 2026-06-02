from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from core.orchestrator import SwarmExecutionError, SwarmOrchestrator
from core.config import settings

logger = logging.getLogger(__name__)

_SESSION_STATUS: dict[str, dict[str, Any]] = {}
_SESSION_SUBSCRIBERS: dict[str, set[asyncio.Queue[dict[str, Any]]]] = {}
_SESSION_STATUS_LOCK = asyncio.Lock()


def _build_log_event(
	session_id: str,
	*,
	agent: str,
	status: str,
	message: str,
	stage: str | None = None,
	extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
	event_payload: dict[str, Any] = {
		"id": f"evt-{uuid.uuid4().hex[:12]}",
		"session_id": session_id,
		"agent": agent,
		"status": status,
		"stage": stage or status,
		"timestamp": datetime.now().strftime("%H:%M:%S"),
		"message": message,
	}
	if extra:
		event_payload.update(extra)
	return event_payload


async def _register_session_subscriber(session_id: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
	async with _SESSION_STATUS_LOCK:
		subscribers = _SESSION_SUBSCRIBERS.setdefault(session_id, set())
		subscribers.add(queue)


async def _unregister_session_subscriber(session_id: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
	async with _SESSION_STATUS_LOCK:
		subscribers = _SESSION_SUBSCRIBERS.get(session_id)
		if not subscribers:
			return
		subscribers.discard(queue)
		if not subscribers:
			_SESSION_SUBSCRIBERS.pop(session_id, None)


def _publish_to_subscribers(
	queues: list[asyncio.Queue[dict[str, Any]]],
	event_payload: dict[str, Any],
) -> None:
	for queue in queues:
		try:
			queue.put_nowait(dict(event_payload))
		except asyncio.QueueFull:
			# Drop old updates for slow consumers to keep producers non-blocking.
			continue


async def _set_session_status(
	session_id: str,
	*,
	status: str,
	message: str,
	agent: str = "Swarm",
	stage: str | None = None,
	extra: dict[str, Any] | None = None,
) -> None:
	event_payload = _build_log_event(
		session_id,
		agent=agent,
		status=status,
		message=message,
		stage=stage,
		extra=extra,
	)

	async with _SESSION_STATUS_LOCK:
		snapshot = _SESSION_STATUS.setdefault(session_id, {"logs": []})
		snapshot["status"] = status
		snapshot["logs"].append(event_payload)
		subscribers = list(_SESSION_SUBSCRIBERS.get(session_id, set()))

	_publish_to_subscribers(subscribers, event_payload)


async def _get_session_status(session_id: str) -> dict[str, Any] | None:
	async with _SESSION_STATUS_LOCK:
		snapshot = _SESSION_STATUS.get(session_id)
		if snapshot is None:
			return None
		return {
			"status": snapshot.get("status", "idle"),
			"logs": list(snapshot.get("logs", [])),
		}


def _configure_logging() -> None:
	level = logging.DEBUG if settings.DEBUG else logging.INFO
	root_logger = logging.getLogger()
	root_logger.setLevel(level)

	# If the host process did not register any handlers, attach one for terminal output.
	if not root_logger.handlers:
		handler = logging.StreamHandler()
		handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s"))
		root_logger.addHandler(handler)


_configure_logging()

FRONTEND_URL = settings.FRONTEND_URL

app = FastAPI(title="AetherDev Backend", version="1.0.0")

app.add_middleware(
	CORSMiddleware,
	allow_origins=[FRONTEND_URL],
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
)


class PipelineStartRequest(BaseModel):
	project_brief: str = Field(min_length=1)


class LegacyDeployRequest(BaseModel):
	prompt: str = Field(min_length=1)


class PipelineStartResponse(BaseModel):
	session_id: str
	prd_document: str


class ApprovePrdRequest(BaseModel):
	session_id: str = Field(min_length=1)
	prd_document: str | None = None


class ApprovePrdResponse(BaseModel):
	session_id: str
	api_contract: dict[str, Any]


class ApproveContractRequest(BaseModel):
	session_id: str = Field(min_length=1)
	api_contract: dict[str, Any] | None = None


class AcceptedResponse(BaseModel):
	session_id: str
	status: str
	message: str


@app.get("/health")
async def health_check() -> dict[str, str]:
	return {"status": "healthy"}


@app.post("/api/pipeline/start", response_model=PipelineStartResponse)
async def start_pipeline(request: PipelineStartRequest) -> PipelineStartResponse:
	if not request.project_brief.strip():
		raise HTTPException(status_code=400, detail="project_brief cannot be empty")

	orchestrator = SwarmOrchestrator()
	session_id = str(uuid.uuid4())
	try:
		await _set_session_status(
			session_id,
			status="running_pm",
			agent="PM Agent",
			message="PM stage started.",
		)
		session_id, prd_document = await orchestrator.run_pm_stage(
			request.project_brief,
			session_id=session_id,
		)
		await _set_session_status(
			session_id,
			status="review_prd",
			agent="PM Agent",
			message="PM Agent completed PRD generation.",
		)
	except SwarmExecutionError as exc:
		await _set_session_status(
			session_id,
			status="failed",
			agent="PM Agent",
			message=f"PM stage failed: {exc}",
		)
		raise HTTPException(status_code=500, detail=str(exc)) from exc

	return PipelineStartResponse(session_id=session_id, prd_document=prd_document)


@app.post("/api/v1/swarm/deploy", response_model=PipelineStartResponse, deprecated=True)
async def deploy_swarm_legacy(request: LegacyDeployRequest) -> PipelineStartResponse:
	if not request.prompt.strip():
		raise HTTPException(status_code=400, detail="prompt cannot be empty")

	orchestrator = SwarmOrchestrator()
	try:
		session_id, prd_document = await orchestrator.run_pm_stage(request.prompt)
	except SwarmExecutionError as exc:
		raise HTTPException(status_code=500, detail=str(exc)) from exc

	return PipelineStartResponse(session_id=session_id, prd_document=prd_document)


@app.post("/api/pipeline/approve-prd", response_model=ApprovePrdResponse)
async def approve_prd(request: ApprovePrdRequest) -> ApprovePrdResponse:
	orchestrator = SwarmOrchestrator()
	try:
		await _set_session_status(
			request.session_id,
			status="running_architect",
			agent="System Architect",
			message="Architecture stage started.",
		)
		api_contract = await orchestrator.run_architect_stage(
			session_id=request.session_id,
			prd_document=request.prd_document,
		)
		await _set_session_status(
			request.session_id,
			status="review_contract",
			agent="System Architect",
			message="System Architect completed API contract.",
		)
	except SwarmExecutionError as exc:
		await _set_session_status(
			request.session_id,
			status="failed",
			agent="System Architect",
			message=f"Architecture stage failed: {exc}",
		)
		raise HTTPException(status_code=500, detail=str(exc)) from exc

	return ApprovePrdResponse(session_id=request.session_id, api_contract=api_contract)


async def _run_downstream_agents(session_id: str) -> None:
	orchestrator = SwarmOrchestrator()

	async def _handle_downstream_event(event: dict[str, Any]) -> None:
		event_status = str(event.get("status", "running"))
		await _set_session_status(
			session_id,
			status="failed" if event_status == "failed" else "running_downstream",
			agent=str(event.get("agent", "Swarm")),
			stage=str(event.get("stage", "running_downstream")),
			message=str(event.get("message", "Downstream update.")),
			extra={"event_status": event_status},
		)

	try:
		await orchestrator.run_downstream_stage(
			session_id=session_id,
			on_event=_handle_downstream_event,
		)
		await _set_session_status(
			session_id,
			status="completed",
			agent="Swarm",
			stage="completed",
			message="Downstream agents completed successfully.",
		)
		logger.info("Downstream pipeline finished. session_id=%s", session_id)
	except Exception:
		await _set_session_status(
			session_id,
			status="failed",
			agent="Swarm",
			stage="failed",
			message="Downstream agents failed.",
		)
		logger.exception("Downstream pipeline failed. session_id=%s", session_id)


@app.get("/api/pipeline/events/{session_id}")
async def stream_pipeline_events(session_id: str) -> StreamingResponse:
	queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=200)
	await _register_session_subscriber(session_id, queue)

	status_snapshot = await _get_session_status(session_id)
	if status_snapshot is not None:
		for log_entry in status_snapshot.get("logs", []):
			try:
				queue.put_nowait(dict(log_entry))
			except asyncio.QueueFull:
				break

	async def event_stream() -> Any:
		try:
			yield "retry: 2000\n\n"
			while True:
				try:
					event_payload = await asyncio.wait_for(queue.get(), timeout=20)
				except asyncio.TimeoutError:
					yield ": keep-alive\n\n"
					continue

				event_data = json.dumps(event_payload, ensure_ascii=False)
				event_id = event_payload.get("id")
				if event_id:
					yield f"id: {event_id}\n"
				yield f"data: {event_data}\n\n"
		finally:
			await _unregister_session_subscriber(session_id, queue)

	return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post(
	"/api/pipeline/approve-contract",
	response_model=AcceptedResponse,
	status_code=202,
)
async def approve_contract(
	request: ApproveContractRequest,
	background_tasks: BackgroundTasks,
) -> AcceptedResponse:
	orchestrator = SwarmOrchestrator()
	try:
		# Validate PRD artifact and optionally persist a user-edited architecture contract.
		await orchestrator.read_text_blob(session_id=request.session_id, filename="prd.md")
		if request.api_contract is not None:
			await orchestrator.write_json_blob(
				session_id=request.session_id,
				filename="contract.json",
				payload=request.api_contract,
			)

		# Validate that the contract is present before scheduling background generation.
		await orchestrator.read_json_blob(session_id=request.session_id, filename="contract.json")
		await _set_session_status(
			request.session_id,
			status="running_downstream",
			agent="Swarm",
			message="Backend and Front-end generation started.",
		)
	except SwarmExecutionError as exc:
		raise HTTPException(status_code=500, detail=str(exc)) from exc

	background_tasks.add_task(_run_downstream_agents, request.session_id)
	return AcceptedResponse(
		session_id=request.session_id,
		status="accepted",
		message="Downstream agents started in the background.",
	)


@app.get("/api/pipeline/status/{session_id}")
async def get_pipeline_status(session_id: str) -> dict[str, Any]:
	orchestrator = SwarmOrchestrator()
	files: list[str] = []

	# Discover artifacts first so status can be inferred even after service restarts.
	prd_exists = True
	contract_exists = True
	requirements_exists = True

	try:
		await orchestrator.read_text_blob(session_id=session_id, filename="prd.md")
		files.append("prd.md")
	except SwarmExecutionError:
		prd_exists = False

	try:
		await orchestrator.read_json_blob(session_id=session_id, filename="contract.json")
		files.append("contract.json")
	except SwarmExecutionError:
		contract_exists = False

	for filename in ("main.py", "app.py", "requirements.txt"):
		try:
			await orchestrator.read_text_blob(session_id=session_id, filename=filename)
			files.append(filename)
		except SwarmExecutionError:
			if filename == "requirements.txt":
				requirements_exists = False

	status_snapshot = await _get_session_status(session_id)
	logs = status_snapshot.get("logs", []) if status_snapshot else []
	status = status_snapshot.get("status") if status_snapshot else None

	if requirements_exists:
		status = "completed"
	elif status in {"running_downstream", "failed"}:
		pass
	elif contract_exists:
		status = "review_contract"
	elif prd_exists:
		status = "review_prd"
	else:
		raise HTTPException(status_code=404, detail="Unknown session_id")

	return {
		"session_id": session_id,
		"status": status,
		"logs": logs,
		"files": files,
	}


@app.get("/api/pipeline/artifacts/{session_id}/{filename}")
async def get_pipeline_artifact(session_id: str, filename: str) -> dict[str, str]:
	if "/" in filename or "\\" in filename:
		raise HTTPException(status_code=400, detail="Invalid filename")

	orchestrator = SwarmOrchestrator()
	try:
		if filename.endswith(".json"):
			payload = await orchestrator.read_json_blob(session_id=session_id, filename=filename)
			content = json.dumps(payload, ensure_ascii=False, indent=2)
		else:
			content = await orchestrator.read_text_blob(session_id=session_id, filename=filename)
	except SwarmExecutionError as exc:
		raise HTTPException(status_code=404, detail=str(exc)) from exc

	return {
		"filename": filename,
		"content": content,
	}

