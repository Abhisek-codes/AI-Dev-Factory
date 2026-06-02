import { useEffect, useRef, useState } from 'react'
import { Hexagon } from 'lucide-react'
import { Group, Panel, Separator } from 'react-resizable-panels'
import ControlCenter from './components/ControlCenter'
import WarRoom from './components/WarRoom'
import Workspace from './components/Workspace'
import './App.css'

const STEP_BY_STATUS = {
  idle: 0,
  running_pm: 1,
  review_prd: 1,
  running_architect: 2,
  review_contract: 2,
  running_downstream: 3,
  completed: 3,
  failed: 3
}

const STATUS_RANK = {
  idle: 0,
  running_pm: 1,
  review_prd: 2,
  running_architect: 3,
  review_contract: 4,
  running_downstream: 5,
  completed: 6,
  failed: 7
}

function App() {
  const [approvalInProgress, setApprovalInProgress] = useState(false)
  const [streamConnectionState, setStreamConnectionState] = useState('idle')
  const [masterState, setMasterState] = useState({
    pipelineStatus: 'idle',
    currentStep: 0,
    logs: [],
    files: [],
    sessionId: null,
    projectBrief: '',
    prdDocument: '',
    apiContract: null,
    editRequest: { target: null, token: 0 },
    stageEdits: {
      prdSaved: false,
      architectureSaved: false
    },
    stageApprovals: {
      prdApproved: false,
      architectureApproved: false
    }
  })
  const pollingRef = useRef(null)
  const pollingAbortRef = useRef(null)
  const pollingFailuresRef = useRef(0)
  const approvalInProgressRef = useRef(false)
  const eventSourceRef = useRef(null)
  const streamReconnectRef = useRef(null)
  const streamReconnectAttemptsRef = useRef(0)

  const {
    pipelineStatus,
    currentStep,
    logs,
    files,
    sessionId,
    projectBrief,
    prdDocument,
    apiContract,
    editRequest,
    stageEdits,
    stageApprovals
  } = masterState

  const clearPolling = () => {
    if (pollingRef.current) {
      clearTimeout(pollingRef.current)
      pollingRef.current = null
    }

    if (pollingAbortRef.current) {
      pollingAbortRef.current.abort()
      pollingAbortRef.current = null
    }

    pollingFailuresRef.current = 0
  }

  const clearStreamReconnect = () => {
    if (streamReconnectRef.current) {
      clearTimeout(streamReconnectRef.current)
      streamReconnectRef.current = null
    }
  }

  const closeEventStream = () => {
    clearStreamReconnect()
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
    }
  }

  const appendIncomingLog = (existingLogs, incomingLog) => {
    const currentLogs = Array.isArray(existingLogs) ? existingLogs : []
    if (!incomingLog || typeof incomingLog !== 'object') {
      return currentLogs
    }

    const incomingId = incomingLog.id
    if (incomingId && currentLogs.some((entry) => entry?.id === incomingId)) {
      return currentLogs
    }

    if (!incomingId) {
      const duplicate = currentLogs.some(
        (entry) =>
          entry?.agent === incomingLog.agent &&
          entry?.timestamp === incomingLog.timestamp &&
          entry?.message === incomingLog.message
      )
      if (duplicate) {
        return currentLogs
      }
    }

    return [...currentLogs, incomingLog]
  }

  const connectEventStream = (targetSessionId = sessionId) => {
    if (!targetSessionId) {
      return
    }

    closeEventStream()
    setStreamConnectionState('connecting')

    const eventSource = new EventSource(`/api/pipeline/events/${targetSessionId}`)
    eventSourceRef.current = eventSource

    eventSource.onopen = () => {
      streamReconnectAttemptsRef.current = 0
      setStreamConnectionState('connected')
      clearPolling()
    }

    eventSource.onmessage = (event) => {
      let payload = null
      try {
        payload = JSON.parse(event.data)
      } catch (error) {
        console.error('Failed to parse stream event:', error)
        return
      }

      setMasterState((prev) => {
        const nextPipelineStatus = payload?.status || prev.pipelineStatus
        const resolvedStatus = STEP_BY_STATUS[nextPipelineStatus] !== undefined ? nextPipelineStatus : prev.pipelineStatus

        return {
          ...prev,
          pipelineStatus: resolvedStatus,
          currentStep: STEP_BY_STATUS[resolvedStatus] ?? prev.currentStep,
          logs: appendIncomingLog(prev.logs, payload)
        }
      })

      if (payload?.status === 'completed' || payload?.status === 'failed') {
        closeEventStream()
        setStreamConnectionState('idle')
        pollStatus(targetSessionId)
      }
    }

    eventSource.onerror = () => {
      closeEventStream()
      setStreamConnectionState('reconnecting')

      pollStatus(targetSessionId)

      const attempts = streamReconnectAttemptsRef.current + 1
      streamReconnectAttemptsRef.current = attempts
      const reconnectDelayMs = Math.min(2000 * Math.max(1, attempts), 10000)

      streamReconnectRef.current = setTimeout(() => {
        connectEventStream(targetSessionId)
      }, reconnectDelayMs)
    }
  }

  const setApprovalState = (value) => {
    approvalInProgressRef.current = value
    setApprovalInProgress(value)
  }

  const pollStatus = (targetSessionId = sessionId) => {
    if (!targetSessionId) return

    clearPolling()

    const runPoll = async () => {
      pollingAbortRef.current = new AbortController()

      try {
        if (approvalInProgressRef.current) {
          pollingRef.current = setTimeout(runPoll, 2000)
          return
        }

        const response = await fetch(`/api/pipeline/status/${targetSessionId}`, {
          signal: pollingAbortRef.current.signal
        })

        if (!response.ok) {
          throw new Error(`Status poll failed with ${response.status}`)
        }

        pollingFailuresRef.current = 0
        const data = await response.json()
        const nextStatus = data.status ?? 'idle'

        setMasterState((prev) => ({
          // Polling can race with optimistic transitions. Keep monotonic progression
          // so stale backend snapshots do not move the UI back to an older stage.
          // Example blocked: running_architect -> review_prd.
          ...(function resolveStatus() {
            const currentRank = STATUS_RANK[prev.pipelineStatus] ?? -1
            const incomingRank = STATUS_RANK[nextStatus] ?? -1
            const resolvedStatus = incomingRank >= currentRank ? nextStatus : prev.pipelineStatus
            return {
              ...prev,
              pipelineStatus: resolvedStatus,
              currentStep: STEP_BY_STATUS[resolvedStatus] ?? prev.currentStep,
              logs: Array.isArray(data.logs) ? data.logs : prev.logs,
              files: Array.isArray(data.files) ? data.files : prev.files
            }
          })()
        }))

        if (nextStatus === 'completed' || nextStatus === 'failed') {
          clearPolling()
          closeEventStream()
          setStreamConnectionState('idle')
          return
        }
      } catch (error) {
        if (error.name === 'AbortError') {
          return
        }

        pollingFailuresRef.current += 1
        console.error('Polling error:', error)

        if (pollingFailuresRef.current >= 5) {
          clearPolling()
          setStreamConnectionState('disconnected')
          setMasterState((prev) => ({
            ...prev,
            pipelineStatus: 'idle',
            currentStep: STEP_BY_STATUS.idle,
            logs: [
              ...(Array.isArray(prev.logs) ? prev.logs : []),
              {
                id: `poll-error-${Date.now()}`,
                timestamp: '--:--:--',
                agent: 'Swarm',
                message: 'Stopped live polling after repeated status endpoint failures.'
              }
            ]
          }))
          return
        }
      } finally {
        pollingAbortRef.current = null
      }

      pollingRef.current = setTimeout(runPoll, 2000)
    }

    runPoll()
  }

  const handleStartSwarm = async () => {
    closeEventStream()
    setStreamConnectionState('idle')
    setMasterState((prev) => ({
      ...prev,
      pipelineStatus: 'running_pm',
      currentStep: STEP_BY_STATUS.running_pm,
      logs: [],
      files: [],
      sessionId: null,
      prdDocument: '',
      apiContract: null,
      editRequest: { target: null, token: 0 },
      stageEdits: {
        prdSaved: false,
        architectureSaved: false
      },
      stageApprovals: {
        prdApproved: false,
        architectureApproved: false
      }
    }))

    try {
      const response = await fetch('/api/pipeline/start', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ project_brief: projectBrief })
      })

      if (!response.ok) {
        throw new Error(`Start swarm failed with ${response.status}`)
      }

      const data = await response.json()

      setMasterState((prev) => ({
        ...prev,
        sessionId: data.session_id ?? prev.sessionId,
        prdDocument: data.prd_document ?? prev.prdDocument,
        pipelineStatus: 'review_prd',
        currentStep: STEP_BY_STATUS.review_prd
      }))

      if (data.session_id) {
        connectEventStream(data.session_id)
        pollStatus(data.session_id)
      }
    } catch (error) {
      console.error('Start swarm error:', error)
      setMasterState((prev) => ({ ...prev, pipelineStatus: 'idle', currentStep: STEP_BY_STATUS.idle }))
    }
  }

  const handleApprovePrd = async () => {
    if (!sessionId || approvalInProgressRef.current) return

    clearPolling()
    setApprovalState(true)

    setMasterState((prev) => ({
      ...prev,
      pipelineStatus: 'running_architect',
      currentStep: STEP_BY_STATUS.running_architect
    }))

    try {
      const response = await fetch('/api/pipeline/approve-prd', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          session_id: sessionId,
          prd_document: prdDocument
        })
      })

      if (!response.ok) {
        throw new Error(`Approve PRD failed with ${response.status}`)
      }

      const data = await response.json()

      setMasterState((prev) => ({
        ...prev,
        apiContract: data.api_contract ?? prev.apiContract,
        pipelineStatus: 'review_contract',
        currentStep: STEP_BY_STATUS.review_contract,
        stageApprovals: {
          ...prev.stageApprovals,
          prdApproved: true
        }
      }))

      connectEventStream(sessionId)
      pollStatus(sessionId)
    } catch (error) {
      console.error('Approve PRD error:', error)
    } finally {
      setApprovalState(false)
    }
  }

  const handleApproveContract = async () => {
    if (!sessionId || approvalInProgressRef.current) return

    clearPolling()
    setApprovalState(true)

    setMasterState((prev) => ({
      ...prev,
      pipelineStatus: 'running_downstream',
      currentStep: STEP_BY_STATUS.running_downstream
    }))

    try {
      const response = await fetch('/api/pipeline/approve-contract', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          session_id: sessionId,
          api_contract: apiContract
        })
      })

      if (!response.ok) {
        throw new Error(`Approve contract failed with ${response.status}`)
      }

      await response.json()
      setMasterState((prev) => ({
        ...prev,
        stageApprovals: {
          ...prev.stageApprovals,
          architectureApproved: true
        }
      }))
      connectEventStream(sessionId)
      pollStatus(sessionId)
    } catch (error) {
      console.error('Approve contract error:', error)
    } finally {
      setApprovalState(false)
    }
  }

  useEffect(() => {
    return () => {
      clearPolling()
      closeEventStream()
    }
  }, [])

  const setProjectBrief = (value) => {
    setMasterState((prev) => ({ ...prev, projectBrief: value }))
  }

  const handleEditSpecs = () => {
    setMasterState((prev) => {
      const target =
        prev.pipelineStatus === 'review_prd'
          ? 'pr-spec'
          : prev.pipelineStatus === 'review_contract'
            ? 'architecture'
            : null

      if (!target) {
        return prev
      }

      return {
        ...prev,
        editRequest: {
          target,
          token: Date.now()
        }
      }
    })
  }

  const handlePrdDocumentUpdate = (nextPrdDocument) => {
    setMasterState((prev) => ({
      ...prev,
      prdDocument: nextPrdDocument
    }))
  }

  const handleApiContractUpdate = (nextApiContract) => {
    setMasterState((prev) => ({
      ...prev,
      apiContract: nextApiContract
    }))
  }

  const handleMarkStageEdited = (target) => {
    setMasterState((prev) => ({
      ...prev,
      stageEdits: {
        prdSaved: target === 'pr-spec' ? true : prev.stageEdits.prdSaved,
        architectureSaved: target === 'architecture' ? true : prev.stageEdits.architectureSaved
      }
    }))
  }

  const canEditCurrentReview =
    (pipelineStatus === 'review_prd' && !stageEdits.prdSaved) ||
    (pipelineStatus === 'review_contract' && !stageEdits.architectureSaved)

  const canApproveCurrentReview =
    (pipelineStatus === 'review_prd' && !stageApprovals.prdApproved) ||
    (pipelineStatus === 'review_contract' && !stageApprovals.architectureApproved)

  return (
    <div className="h-screen w-screen bg-[#0f111a] text-gray-200 overflow-hidden font-sans flex flex-col">
      {/* Top Navigation Bar */}
      <nav className="h-[60px] bg-gray-900 border-b border-gray-700 flex items-center px-4">
        <div className="flex items-center gap-3">
          <Hexagon className="text-purple-500" size={32} fill="#7c3aed" strokeWidth={1.5} />
          <h1 className="text-xl font-semibold">AI Dev Factory</h1>
        </div>
      </nav>

      {/* Resizable Panel Container */}
      <div className="flex-1 p-4 overflow-hidden">
        <Group orientation="horizontal" className="flex h-full gap-2">
          <Panel defaultSize={25} minSize={20}>
            <div className="h-full overflow-hidden">
              <ControlCenter
                pipelineStatus={pipelineStatus}
                currentStep={currentStep}
                sessionId={sessionId}
                projectBrief={projectBrief}
                prdDocument={prdDocument}
                apiContract={apiContract}
                logs={logs}
                files={files}
                setProjectBrief={setProjectBrief}
                handleStartSwarm={handleStartSwarm}
                handleApprovePrd={handleApprovePrd}
                handleApproveContract={handleApproveContract}
              />
            </div>
          </Panel>

          <Separator className="w-1.5 bg-gray-800 hover:bg-purple-600 cursor-col-resize transition-colors rounded" />

          <Panel defaultSize={45} minSize={30}>
            <div className="h-full relative overflow-hidden">
              <WarRoom
                pipelineStatus={pipelineStatus}
                currentStep={currentStep}
                streamConnectionState={streamConnectionState}
                sessionId={sessionId}
                projectBrief={projectBrief}
                prdDocument={prdDocument}
                apiContract={apiContract}
                logs={logs}
                files={files}
                setProjectBrief={setProjectBrief}
                handleStartSwarm={handleStartSwarm}
                handleApprovePrd={handleApprovePrd}
                handleApproveContract={handleApproveContract}
                handleEditSpecs={handleEditSpecs}
                canEditCurrentReview={canEditCurrentReview}
                canApproveCurrentReview={canApproveCurrentReview}
                approvalInProgress={approvalInProgress}
              />
            </div>
          </Panel>

          <Separator className="w-1.5 bg-gray-800 hover:bg-purple-600 cursor-col-resize transition-colors rounded" />

          <Panel defaultSize={30} minSize={25}>
            <div className="h-full overflow-hidden">
              <Workspace
                pipelineStatus={pipelineStatus}
                currentStep={currentStep}
                sessionId={sessionId}
                projectBrief={projectBrief}
                prdDocument={prdDocument}
                apiContract={apiContract}
                logs={logs}
                files={files}
                editRequest={editRequest}
                setProjectBrief={setProjectBrief}
                handleStartSwarm={handleStartSwarm}
                handleApprovePrd={handleApprovePrd}
                handleApproveContract={handleApproveContract}
                onUpdatePrdDocument={handlePrdDocumentUpdate}
                onUpdateApiContract={handleApiContractUpdate}
                onMarkStageEdited={handleMarkStageEdited}
              />
            </div>
          </Panel>
        </Group>
      </div>
    </div>
  )
}

export default App
