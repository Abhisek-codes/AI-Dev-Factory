from __future__ import annotations

import asyncio
import inspect
import json
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse
from typing import Any, Awaitable, Callable, Mapping

from azure.identity import DefaultAzureCredential
from azure.storage.blob import (
	BlobServiceClient,
	BlobSasPermissions,
	generate_blob_sas,
)

from agents import build_agent_factory
from core.config import settings

logger = logging.getLogger(__name__)


class SwarmExecutionError(RuntimeError):
	"""Raised when the orchestrator cannot complete the AetherDev DAG."""


@dataclass(slots=True)
class SwarmArtifacts:
	user_prompt: str
	pm_spec: str = ""
	architecture: dict[str, Any] | None = None
	backend_code: str = ""
	backend_sas_url: str = ""
	frontend_code: str = ""
	frontend_sas_url: str = ""
	requirements_txt: str = ""
	requirements_sas_url: str = ""


class SwarmOrchestrator:
	def __init__(
		self,
		*,
		event_queue: asyncio.Queue[Mapping[str, Any]] | None = None,
	) -> None:
		self._event_queue = event_queue

		factory = build_agent_factory()
		self._pm_agent = factory.create_agent("pm_agent")
		self._architect_agent = factory.create_agent("architect_agent")
		self._backend_agent = factory.create_agent("backend_agent")
		self._frontend_agent = factory.create_agent("frontend_agent")
		self._dependency_agent = factory.create_agent("dependency_agent")

	async def run_pm_stage(
		self,
		project_brief: str,
		*,
		session_id: str | None = None,
	) -> tuple[str, str]:
		if not project_brief.strip():
			raise SwarmExecutionError("The project brief is empty.")

		active_session_id = session_id or str(uuid.uuid4())
		prd_document = await self._run_pm_step(project_brief)
		await self.write_text_blob(
			session_id=active_session_id,
			filename="prd.md",
			content=prd_document,
		)
		return active_session_id, prd_document

	async def run_architect_stage(
		self,
		*,
		session_id: str,
		prd_document: str | None = None,
	) -> dict[str, Any]:
		if not session_id.strip():
			raise SwarmExecutionError("session_id is required.")

		active_prd = prd_document
		if active_prd is None:
			active_prd = await self.read_text_blob(session_id=session_id, filename="prd.md")

		await self.write_text_blob(
			session_id=session_id,
			filename="prd.md",
			content=active_prd,
		)

		api_contract = await self._run_architect_step(active_prd)
		await self.write_json_blob(
			session_id=session_id,
			filename="contract.json",
			payload=api_contract,
		)
		return api_contract

	async def run_downstream_stage(
		self,
		*,
		session_id: str,
		on_event: Callable[[Mapping[str, Any]], Awaitable[None]] | None = None,
	) -> None:
		if not session_id.strip():
			raise SwarmExecutionError("session_id is required.")

		async def _noop_event_handler(_event: Mapping[str, Any]) -> None:
			return None

		event_handler = on_event or _noop_event_handler

		prd_document = await self.read_text_blob(session_id=session_id, filename="prd.md")
		api_contract = await self.read_json_blob(session_id=session_id, filename="contract.json")

		await event_handler(
			{
				"agent": "Backend Engineer",
				"status": "running",
				"stage": "downstream_backend",
				"message": "Backend generation started.",
			}
		)
		try:
			backend_code, _ = await self._run_backend_step(
				architecture=api_contract,
				session_id=session_id,
			)
			await event_handler(
				{
					"agent": "Backend Engineer",
					"status": "completed",
					"stage": "downstream_backend",
					"message": "Backend generation completed.",
				}
			)
		except Exception:
			await event_handler(
				{
					"agent": "Backend Engineer",
					"status": "failed",
					"stage": "downstream_backend",
					"message": "Backend generation failed.",
				}
			)
			raise

		await event_handler(
			{
				"agent": "Front-end Engineer",
				"status": "running",
				"stage": "downstream_frontend",
				"message": "Front-end generation started.",
			}
		)
		try:
			frontend_code, _ = await self._run_frontend_agent(
				prd_document=prd_document,
				api_contract=api_contract,
				session_id=session_id,
			)
			await event_handler(
				{
					"agent": "Front-end Engineer",
					"status": "completed",
					"stage": "downstream_frontend",
					"message": "Front-end generation completed.",
				}
			)
		except Exception:
			await event_handler(
				{
					"agent": "Front-end Engineer",
					"status": "failed",
					"stage": "downstream_frontend",
					"message": "Front-end generation failed.",
				}
			)
			raise

		await event_handler(
			{
				"agent": "Dependency Agent",
				"status": "running",
				"stage": "downstream_dependency",
				"message": "Dependency analysis started.",
			}
		)
		try:
			await self._run_dependency_agent(
				backend_code=backend_code,
				frontend_code=frontend_code,
				session_id=session_id,
			)
			await event_handler(
				{
					"agent": "Dependency Agent",
					"status": "completed",
					"stage": "downstream_dependency",
					"message": "Dependency analysis completed.",
				}
			)
		except Exception:
			await event_handler(
				{
					"agent": "Dependency Agent",
					"status": "failed",
					"stage": "downstream_dependency",
					"message": "Dependency analysis failed.",
				}
			)
			raise

	async def run_pipeline(
		self,
		user_prompt: str,
		*,
		event_queue: asyncio.Queue[Mapping[str, Any]] | None = None,
		session_id: str | None = None,
	) -> SwarmArtifacts:
		active_queue = event_queue or self._event_queue
		if not user_prompt.strip():
			raise SwarmExecutionError("The user prompt is empty.")

		if session_id is None:
			session_id = str(uuid.uuid4())

		artifacts = SwarmArtifacts(user_prompt=user_prompt)
		logger.info("Starting AetherDev swarm pipeline. session_id=%s", session_id)
		await self._emit_event(
			active_queue,
			agent="Swarm",
			status="Started",
			message="Pipeline execution started.",
		)

		try:
			await self._emit_event(
				active_queue,
				agent="PM",
				status="Thinking",
				message="Analyzing user requirements.",
			)
			artifacts.pm_spec = await self._run_pm_step(artifacts.user_prompt)
			await self._emit_event(
				active_queue,
				agent="PM",
				status="Completed",
				message="Product requirements generated.",
			)

			await self._emit_event(
				active_queue,
				agent="Architect",
				status="Thinking",
				message="Designing system architecture.",
			)
			artifacts.architecture = await self._run_architect_step(artifacts.pm_spec)
			await self._emit_event(
				active_queue,
				agent="Architect",
				status="Completed",
				message="Architecture blueprint generated.",
			)

			await self._emit_event(
				active_queue,
				agent="Backend",
				status="Thinking",
				message="Generating backend implementation.",
			)
			artifacts.backend_code, artifacts.backend_sas_url = await self._run_backend_step(
				architecture=artifacts.architecture,
				session_id=session_id,
			)
			await self._emit_event(
				active_queue,
				agent="Backend",
				status="Completed",
				message="Initial backend code generated and uploaded.",
				extra={"backend_sas_url": artifacts.backend_sas_url},
			)

			await self._emit_event(
				active_queue,
				agent="FrontEnd",
				status="Thinking",
				message="Generating Streamlit UI.",
			)
			artifacts.frontend_code, artifacts.frontend_sas_url = await self._run_frontend_agent(
				prd_document=artifacts.pm_spec,
				api_contract=artifacts.architecture,
				session_id=session_id,
			)
			await self._emit_event(
				active_queue,
				agent="FrontEnd",
				status="Completed",
				message="Streamlit app generated and uploaded.",
				extra={"frontend_sas_url": artifacts.frontend_sas_url},
			)

			await self._emit_event(
				active_queue,
				agent="Dependency",
				status="Thinking",
				message="Analyzing generated backend/frontend imports.",
			)
			artifacts.requirements_txt, artifacts.requirements_sas_url = await self._run_dependency_agent(
				backend_code=artifacts.backend_code,
				frontend_code=artifacts.frontend_code,
				session_id=session_id,
			)
			await self._emit_event(
				active_queue,
				agent="Dependency",
				status="Completed",
				message="requirements.txt generated and uploaded.",
				extra={"requirements_sas_url": artifacts.requirements_sas_url},
			)

			await self._emit_event(
				active_queue,
				agent="Swarm",
				status="Completed",
				message="Pipeline execution completed successfully.",
			)
		except SwarmExecutionError:
			await self._emit_event(
				active_queue,
				agent="Swarm",
				status="Fatal Error",
				message="Pipeline execution failed.",
			)
			logger.error("Swarm pipeline crashed:", exc_info=True)
			raise
		except Exception as exc:
			await self._emit_event(
				active_queue,
				agent="Swarm",
				status="Fatal Error",
				message=f"Unexpected pipeline failure: {exc}",
			)
			logger.error("Swarm pipeline crashed:", exc_info=True)
			raise SwarmExecutionError(f"Unexpected pipeline failure: {exc}") from exc

		logger.info("AetherDev swarm pipeline completed successfully.")
		return artifacts

	async def _run_pm_step(self, user_prompt: str) -> str:
		logger.info("Step 1/5: PM agent generating requirements spec.")
		response = await self._invoke_agent(self._pm_agent, user_prompt)
		pm_spec = self._normalize_text(response)
		if not pm_spec:
			raise SwarmExecutionError("PM agent returned empty output.")
		return pm_spec

	async def _run_architect_step(self, pm_spec: str) -> dict[str, Any]:
		logger.info("Step 2/5: Architect agent generating JSON architecture.")
		response = await self._invoke_agent(self._architect_agent, pm_spec)
		architecture = self._extract_json_object(response)
		return architecture

	async def _run_backend_step(
		self,
		*,
		architecture: dict[str, Any],
		session_id: str,
	) -> tuple[str, str]:
		logger.info("Step 3/5: Backend agent generating FastAPI application.")
		print("[Backend Agent] Generating backend implementation...")
		prompt = (
			"You must return exactly one markdown block containing the full code.\n\n"
			+ json.dumps(architecture, ensure_ascii=False, indent=2)
		)
		response = await self._invoke_agent(self._backend_agent, prompt)
		backend_code = self._extract_code_block(response)
		# logger.info(f"Backend agent generated code: {backend_code}")
		if not backend_code:
			raise SwarmExecutionError("Backend agent returned empty code.")

		backend_sas_url = await self._upload_code_artifact(
			code=backend_code,
			session_id=session_id,
			filename="main.py",
			agent_label="Backend Agent",
		)
		return backend_code, backend_sas_url

	async def _run_frontend_agent(
		self,
		*,
		prd_document: str,
		api_contract: dict[str, Any] | None,
		session_id: str,
	) -> tuple[str, str]:
		"""Generate a Streamlit app.py via the Front-End Agent and upload it to Azure Blob Storage.

		Returns:
			A (frontend_code, sas_url) tuple where sas_url is a 1-hour read-only SAS URL.
		"""
		print("[Front-End Agent] Generating Streamlit UI...")
		logger.info("Step 4/5: Front-End agent generating Streamlit application.")

		api_contract_json = json.dumps(api_contract, ensure_ascii=False, indent=2) if api_contract else "{}"
		prompt = (
			"You must return exactly one ```python code block containing the full Streamlit app.\n\n"
			"--- PRODUCT REQUIREMENTS DOCUMENT ---\n"
			f"{prd_document}\n\n"
			"--- API CONTRACT ---\n"
			f"{api_contract_json}"
		)

		response = await self._invoke_agent(self._frontend_agent, prompt)
		frontend_code = self._extract_code_block(response)
		if not frontend_code:
			raise SwarmExecutionError("Front-End agent returned empty code.")

		sas_url = await self._upload_code_artifact(
			code=frontend_code,
			session_id=session_id,
			filename="app.py",
			agent_label="Front-End Agent",
		)
		return frontend_code, sas_url

	async def _run_dependency_agent(
		self,
		backend_code: str,
		frontend_code: str,
		session_id: str,
	) -> tuple[str, str]:
		logger.info("Step 5/5: Dependency agent generating requirements.txt.")
		print("[Dependency Agent] Analyzing imports...")

		system_prompt = (
			"You are an automated dependency parsing tool. "
			"Scan the provided Python code and infer third-party dependencies only. "
			"Include common packages when imported, such as fastapi, streamlit, requests, uvicorn, pydantic. "
			"Output must be valid requirements.txt content using pip package names only, one package per line. "
			"Do not include markdown, backticks, explanations, bullets, comments, or any extra text."
		)
		prompt = (
			f"{system_prompt}\n\n"
			"--- BACKEND PYTHON CODE ---\n"
			f"{backend_code}\n\n"
			"--- FRONTEND PYTHON CODE ---\n"
			f"{frontend_code}\n"
		)

		response = await self._invoke_agent(self._dependency_agent, prompt)
		requirements_txt = self._sanitize_requirements_txt(response)
		if not requirements_txt:
			raise SwarmExecutionError("Dependency agent returned empty requirements output.")

		requirements_sas_url = await self._upload_code_artifact(
			code=requirements_txt,
			session_id=session_id,
			filename="requirements.txt",
			agent_label="Dependency Agent",
		)
		print("[Dependency Agent] Uploaded requirements.txt to Blob Storage...")
		return requirements_txt, requirements_sas_url

	def _build_blob_service_client(self) -> BlobServiceClient:
		if not settings.AZURE_STORAGE_ACCOUNT_URL:
			raise SwarmExecutionError(
				"AZURE_STORAGE_ACCOUNT_URL is not configured. Cannot access generated artifacts."
			)

		credential = DefaultAzureCredential()
		return BlobServiceClient(
			account_url=settings.AZURE_STORAGE_ACCOUNT_URL,
			credential=credential,
		)

	async def write_text_blob(self, *, session_id: str, filename: str, content: str) -> None:
		await asyncio.to_thread(
			self._write_blob_sync,
			session_id,
			filename,
			content.encode("utf-8"),
		)

	async def write_json_blob(self, *, session_id: str, filename: str, payload: Mapping[str, Any]) -> None:
		serialized = json.dumps(payload, ensure_ascii=False, indent=2)
		await self.write_text_blob(session_id=session_id, filename=filename, content=serialized)

	async def read_text_blob(self, *, session_id: str, filename: str) -> str:
		content = await asyncio.to_thread(self._read_blob_sync, session_id, filename)
		decoded = content.decode("utf-8").strip()
		if not decoded:
			raise SwarmExecutionError(f"Blob '{session_id}/{filename}' is empty.")
		return decoded

	async def read_json_blob(self, *, session_id: str, filename: str) -> dict[str, Any]:
		content = await self.read_text_blob(session_id=session_id, filename=filename)
		try:
			parsed = json.loads(content)
		except json.JSONDecodeError as exc:
			raise SwarmExecutionError(f"Blob '{session_id}/{filename}' is not valid JSON: {exc}") from exc
		if not isinstance(parsed, dict):
			raise SwarmExecutionError(f"Blob '{session_id}/{filename}' JSON root must be an object.")
		return parsed

	def _write_blob_sync(self, session_id: str, filename: str, data: bytes) -> None:
		blob_service_client = self._build_blob_service_client()
		container_name = settings.AZURE_STORAGE_CONTAINER_NAME
		blob_name = f"{session_id}/{filename}"

		blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)
		blob_client.upload_blob(data, overwrite=True)
		logger.info("Uploaded %s", blob_name)

	def _read_blob_sync(self, session_id: str, filename: str) -> bytes:
		blob_service_client = self._build_blob_service_client()
		container_name = settings.AZURE_STORAGE_CONTAINER_NAME
		blob_name = f"{session_id}/{filename}"

		try:
			blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)
			return blob_client.download_blob().readall()
		except Exception as exc:
			raise SwarmExecutionError(f"Failed to fetch blob '{blob_name}': {exc}") from exc

	async def _upload_code_artifact(
		self,
		*,
		code: str,
		session_id: str,
		filename: str,
		agent_label: str,
	) -> str:
		return await asyncio.to_thread(
			self._upload_code_artifact_sync,
			code,
			session_id,
			filename,
			agent_label,
		)

	def _upload_code_artifact_sync(
		self,
		code: str,
		session_id: str,
		filename: str,
		agent_label: str,
	) -> str:
		# --- Blob Storage upload (Claim Check Pattern) ---
		blob_service_client = self._build_blob_service_client()

		container_name = settings.AZURE_STORAGE_CONTAINER_NAME
		blob_name = f"{session_id}/{filename}"

		blob_client = blob_service_client.get_blob_client(
			container=container_name,
			blob=blob_name,
		)
		blob_client.upload_blob(
			code.encode("utf-8"),
			overwrite=True,
			content_settings=None,
		)
		print(f"[{agent_label}] Uploaded {filename} to Blob Storage: {container_name}/{blob_name}")
		logger.info("[%s] Uploaded %s → %s/%s", agent_label, filename, container_name, blob_name)

		# Request a User Delegation Key and generate a 1-hour read-only SAS URL.
		delegation_key_start = datetime.now(UTC) - timedelta(minutes=5)
		delegation_key_expiry = datetime.now(UTC) + timedelta(hours=1)
		user_delegation_key = blob_service_client.get_user_delegation_key(
			key_start_time=delegation_key_start,
			key_expiry_time=delegation_key_expiry,
		)

		parsed = urlparse(settings.AZURE_STORAGE_ACCOUNT_URL)
		account_name = parsed.hostname.split(".")[0] if parsed.hostname else ""

		sas_token = generate_blob_sas(
			account_name=account_name,
			container_name=container_name,
			blob_name=blob_name,
			user_delegation_key=user_delegation_key,
			permission=BlobSasPermissions(read=True),
			expiry=delegation_key_expiry,
		)

		sas_url = f"{settings.AZURE_STORAGE_ACCOUNT_URL}/{container_name}/{blob_name}?{sas_token}"
		print(f"[{agent_label}] SAS URL generated (valid 1 hour): {sas_url}")
		logger.info("[%s] SAS URL generated for %s/%s", agent_label, container_name, blob_name)
		return sas_url

	async def _emit_event(
		self,
		event_queue: asyncio.Queue[Mapping[str, Any]] | None,
		*,
		agent: str,
		status: str,
		message: str,
		extra: Mapping[str, Any] | None = None,
	) -> None:
		if event_queue is None:
			return

		event_payload: dict[str, Any] = {
			"agent": agent,
			"status": status,
			"message": message,
			"timestamp": datetime.now(UTC).isoformat(),
		}
		if extra:
			event_payload.update(dict(extra))

		logger.info("[%s] %s - %s", agent, status, message)
		await event_queue.put(event_payload)

	async def _invoke_agent(self, agent: Any, prompt: str) -> str:
		methods = [
			"run",
			"arun",
			"invoke",
			"ainvoke",
			"complete",
			"acomplete",
			"chat",
			"achat",
			"generate",
			"agenerate",
		]
		last_exception: Exception | None = None

		for method_name in methods:
			method = getattr(agent, method_name, None)
			if method is None:
				continue

			try:
				result = method(prompt)
				if inspect.isawaitable(result):
					result = await result
				text = self._normalize_text(result)
				if text:
					return text
			except Exception as exc:
				# logger.debug("Agent method '%s' failed: %s", method_name, exc)
				logger.error("Agent method '%s' failed: %s", method_name, exc, exc_info=True)
				last_exception = exc
				if self._is_connection_error(exc):
					raise SwarmExecutionError(self._build_connection_error_message(exc)) from exc
				continue

		if last_exception and self._is_connection_error(last_exception):
			raise SwarmExecutionError(self._build_connection_error_message(last_exception)) from last_exception

		raise SwarmExecutionError(
			f"Unable to invoke agent {type(agent).__name__}. No supported run/invoke method succeeded."
		)

	@staticmethod
	def _normalize_text(value: Any) -> str:
		if value is None:
			return ""

		if isinstance(value, str):
			return value.strip()

		for attribute in ("content", "text", "message"):
			candidate = getattr(value, attribute, None)
			if isinstance(candidate, str):
				return candidate.strip()

		if isinstance(value, dict):
			for key in ("content", "text", "message"):
				candidate = value.get(key)
				if isinstance(candidate, str):
					return candidate.strip()

		if isinstance(value, list):
			joined = "\n".join(SwarmOrchestrator._normalize_text(item) for item in value)
			return joined.strip()

		return str(value).strip()

	@staticmethod
	def _extract_code_block(text: str) -> str:
		cleaned = text.strip()
		pattern = re.compile(r"```(?:python|py|yaml|yml|json)?\n(.*?)```", re.DOTALL | re.IGNORECASE)
		match = pattern.search(cleaned)
		if match:
			return match.group(1).strip()
		return cleaned

	@staticmethod
	def _sanitize_requirements_txt(text: str) -> str:
		candidate = SwarmOrchestrator._extract_code_block(text)
		package_pattern = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
		packages: list[str] = []
		seen: set[str] = set()

		for raw_line in candidate.splitlines():
			line = raw_line.strip()
			if not line:
				continue
			if line.startswith("#"):
				continue
			if package_pattern.fullmatch(line) is None:
				continue

			package = line.lower()
			if package in seen:
				continue

			seen.add(package)
			packages.append(package)

		return "\n".join(packages)

	@staticmethod
	def _is_connection_error(exc: Exception) -> bool:
		message = str(exc).lower()
		indicators = (
			"connection error",
			"connecterror",
			"getaddrinfo failed",
			"name or service not known",
			"temporary failure in name resolution",
		)
		return any(indicator in message for indicator in indicators)

	@staticmethod
	def _build_connection_error_message(exc: Exception) -> str:
		endpoint = settings.AZURE_OPENAI_ENDPOINT.strip()
		host = urlparse(endpoint).hostname if endpoint else ""
		details = str(exc).strip() or type(exc).__name__
		if host:
			return (
				"Azure AI endpoint connectivity failed while invoking an agent. "
				f"Could not resolve or connect to host '{host}'. "
				"Verify AZURE_OPENAI_ENDPOINT, DNS/network access, and that the Azure resource exists. "
				f"Original error: {details}"
			)
		return (
			"Azure AI endpoint connectivity failed while invoking an agent. "
			"Verify AZURE_OPENAI_ENDPOINT and network/DNS access. "
			f"Original error: {details}"
		)

	@staticmethod
	def _extract_json_object(text: str) -> dict[str, Any]:
		candidate = SwarmOrchestrator._extract_code_block(text)
		try:
			parsed = json.loads(candidate)
		except json.JSONDecodeError:
			start = candidate.find("{")
			end = candidate.rfind("}")
			if start == -1 or end == -1 or end <= start:
				raise SwarmExecutionError("Architect output did not contain valid JSON architecture.")
			try:
				parsed = json.loads(candidate[start : end + 1])
			except json.JSONDecodeError as exc:
				raise SwarmExecutionError(
					f"Architect output could not be parsed as JSON: {exc}"
				) from exc

		if not isinstance(parsed, dict):
			raise SwarmExecutionError("Architect output JSON root must be an object.")
		return parsed

