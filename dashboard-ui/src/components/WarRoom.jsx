import { useEffect, useRef } from 'react'
import { User, Network, Terminal, LayoutTemplate } from 'lucide-react'

function WarRoom({ pipelineStatus, handleApprovePrd, handleApproveContract, handleEditSpecs, canEditCurrentReview, canApproveCurrentReview, approvalInProgress, currentStep, logs, streamConnectionState = 'idle' }) {
  const logContainerRef = useRef(null)

  const steps = [
    { id: 1, name: 'PM Agent', color: 'text-blue-400', icon: User },
    { id: 2, name: 'System Architect', color: 'text-purple-400', icon: Network },
    { id: 3, name: 'Backend Engineer', color: 'text-green-400', icon: Terminal },
    { id: 4, name: 'Front-end Engineer', color: 'text-yellow-400', icon: LayoutTemplate }
  ]

  const agentIcons = {
    'PM Agent': User,
    'System Architect': Network,
    'Backend Engineer': Terminal,
    'Front-end Engineer': LayoutTemplate
  }

  const agentColors = {
    'PM Agent': 'text-blue-400',
    'System Architect': 'text-purple-400',
    'Backend Engineer': 'text-green-400',
    'Front-end Engineer': 'text-yellow-400'
  }

  const pipelineStepMap = {
    idle: -1,
    running_pm: 0,
    review_prd: 0,
    running_architect: 1,
    review_contract: 1,
    running_downstream: 2,
    completed: 3,
    failed: 3
  }

  const effectiveStep =
    pipelineStepMap[pipelineStatus] !== undefined
      ? pipelineStepMap[pipelineStatus]
      : Math.max(-1, Math.min(3, Number(currentStep) || -1))

  const hasLiveLogs = Array.isArray(logs) && logs.length > 0
  const messages = hasLiveLogs
    ? logs.map((entry, index) => {
      if (typeof entry === 'string') {
        return {
          id: `log-${index}`,
          timestamp: '--:--:--',
          agent: 'PM Agent',
          color: agentColors['PM Agent'],
          message: entry
        }
      }

      const agentName = entry.agent || entry.source || 'PM Agent'
      return {
        id: entry.id || `log-${index}`,
        timestamp: entry.timestamp || '--:--:--',
        agent: agentName,
        color: agentColors[agentName] || 'text-gray-300',
        message: entry.message || entry.text || JSON.stringify(entry),
        event_status: entry.event_status || null
      }
    })
    : []

  const streamIndicatorClass =
    streamConnectionState === 'connected'
      ? 'bg-green-500 animate-pulse'
      : streamConnectionState === 'reconnecting'
        ? 'bg-yellow-500 animate-pulse'
        : streamConnectionState === 'connecting'
          ? 'bg-blue-500 animate-pulse'
          : streamConnectionState === 'disconnected'
            ? 'bg-red-500'
          : 'bg-gray-500'

  const streamLabelClass =
    streamConnectionState === 'connected'
      ? 'text-green-500'
      : streamConnectionState === 'reconnecting'
        ? 'text-yellow-400'
        : streamConnectionState === 'connecting'
          ? 'text-blue-400'
          : streamConnectionState === 'disconnected'
            ? 'text-red-400'
          : 'text-gray-400'

  const streamLabel =
    streamConnectionState === 'connected'
      ? 'Live'
      : streamConnectionState === 'reconnecting'
        ? 'Reconnecting'
        : streamConnectionState === 'connecting'
          ? 'Connecting'
          : streamConnectionState === 'disconnected'
            ? 'Disconnected'
          : 'Idle'

  const isPrdReview = pipelineStatus === 'review_prd'
  const isContractReview = pipelineStatus === 'review_contract'
  const showReviewBanner = isPrdReview || isContractReview
  const showProcessing = pipelineStatus === 'running_architect' || pipelineStatus === 'running_downstream'

  const reviewText = isPrdReview
    ? 'The PM Agent has finalized the Product Requirements.'
    : 'The System Architect has finalized the API Contract.'

  const approveLabel = isPrdReview ? 'Approve PRD' : 'Approve Architecture'
  const approveHandler = isPrdReview ? handleApprovePrd : handleApproveContract

  useEffect(() => {
    if (!logContainerRef.current) {
      return
    }

    logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight
  }, [messages.length])

  return (
    <div className="bg-[#161925] border border-gray-800 rounded-lg flex flex-col h-full relative pb-24">
      {/* Section 1: Live Workflow */}
      <div className="border-b border-gray-800 p-4">
        {/* Header with Toggle Buttons */}
        <div className="flex items-center mb-4">
          <h3 className="text-sm font-semibold text-gray-200 uppercase tracking-wide flex items-center gap-2">
            <span className="bg-blue-600 text-white w-6 h-6 flex items-center justify-center rounded text-sm">2</span>
            AGENT WAR ROOM
          </h3>
        </div>

        {/* Stepper Component */}
        <div className="flex items-center flex-wrap gap-2 pb-2">
          {steps.map((step, index) => {
            const isActiveOrCompleted = effectiveStep >= index
            const StepIcon = step.icon

            return (
              <div key={step.id} className="flex items-center">
                <div
                  className={`border rounded-md px-3 py-1.5 flex items-center gap-2 transition-all shrink-0 ${
                    isActiveOrCompleted
                      ? 'border-purple-500 bg-purple-500/10 text-gray-100'
                      : 'border-gray-700 text-gray-500'
                  }`}
                >
                  <span
                    className={`w-6 h-6 rounded flex items-center justify-center text-xs font-semibold ${
                      isActiveOrCompleted ? 'bg-purple-600 text-white' : 'bg-gray-800 text-gray-400'
                    }`}
                  >
                    {step.id}
                  </span>
                  <StepIcon size={14} className={isActiveOrCompleted ? step.color : 'text-gray-500'} />
                  <span className="text-xs font-medium whitespace-nowrap">{step.name}</span>
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Section 2: Communication Log */}
      <div className="flex-1 flex flex-col overflow-hidden p-4">
        <div className="flex items-center gap-2 mb-3">
          <h3 className="text-sm font-semibold text-gray-200 uppercase tracking-wide">Inter-Agent Communication Log</h3>
          <div className="flex items-center gap-1">
            <span className={`w-2 h-2 rounded-full ${streamIndicatorClass}`}></span>
            <span className={`text-xs font-medium ${streamLabelClass}`}>
              {streamLabel}
            </span>
          </div>
        </div>

        {/* Messages Container */}
        <div ref={logContainerRef} className="flex-1 overflow-y-auto space-y-3 pr-2">
          {messages.map((msg) => (
            <div key={msg.id} className="text-xs space-y-1">
              <div className="flex items-center gap-2">
                <span className="text-gray-500">{msg.timestamp}</span>
                {(() => {
                  const AgentIcon = agentIcons[msg.agent] || User
                  return <AgentIcon size={14} className={msg.color} />
                })()}
                <span className={`font-semibold ${msg.color}`}>{msg.agent}</span>
                {msg.event_status && (
                  <span className="px-1.5 py-0.5 rounded bg-gray-800 text-[10px] uppercase tracking-wide text-gray-300">
                    {msg.event_status}
                  </span>
                )}
              </div>
              <p className="text-gray-300 bg-gray-900 rounded p-2 ml-12">
                {msg.message}
              </p>
            </div>
          ))}
        </div>
      </div>

      {showReviewBanner && (
        <div className="absolute bottom-4 left-4 right-4 bg-[#1a130d] border border-orange-500 rounded-lg p-4 flex items-center justify-between">
          <span className="text-sm font-medium text-orange-300">
            {reviewText}
          </span>
          <div className="flex items-center gap-2">
            {canEditCurrentReview && (
              <button
                onClick={handleEditSpecs}
                className="px-3 py-1 bg-gray-800 hover:bg-gray-700 text-gray-200 text-xs font-medium rounded transition-colors"
              >
                Edit Specs
              </button>
            )}
            {canApproveCurrentReview && (
              <button
                onClick={approveHandler}
                disabled={approvalInProgress}
                className="px-3 py-1 bg-orange-600 hover:bg-orange-700 disabled:bg-gray-700 disabled:text-gray-400 disabled:cursor-not-allowed text-white text-xs font-medium rounded transition-colors"
              >
                {approveLabel}
              </button>
            )}
          </div>
        </div>
      )}

      {!showReviewBanner && showProcessing && (
        <div className="absolute bottom-4 left-4 right-4 flex items-center justify-center py-2">
          <span className="text-xs text-orange-300 animate-pulse tracking-wide">Processing...</span>
        </div>
      )}
    </div>
  )
}

export default WarRoom
