import { User, Network, Terminal, LayoutTemplate, Play, Loader } from 'lucide-react'

function ControlCenter({ projectBrief, setProjectBrief, pipelineStatus, handleStartSwarm }) {
  const maxCharacters = 1000
  const isRunningPm = pipelineStatus === 'running_pm'
  const isButtonDisabled = projectBrief.trim().length === 0 || pipelineStatus !== 'idle'

  const handleClear = () => {
    setProjectBrief('')
  }

  const STATUS_STYLES = {
    Idle: 'bg-gray-500',
    Processing: 'bg-blue-500',
    Completed: 'bg-green-500',
    Failed: 'bg-red-500'
  }

  const statusByAgent = {
    pm: 'Idle',
    architect: 'Idle',
    backend: 'Idle',
    frontend: 'Idle'
  }

  if (pipelineStatus === 'running_pm') {
    statusByAgent.pm = 'Processing'
  } else if (pipelineStatus === 'review_prd') {
    statusByAgent.pm = 'Completed'
  } else if (pipelineStatus === 'running_architect') {
    statusByAgent.pm = 'Completed'
    statusByAgent.architect = 'Processing'
  } else if (pipelineStatus === 'review_contract') {
    statusByAgent.pm = 'Completed'
    statusByAgent.architect = 'Completed'
  } else if (pipelineStatus === 'running_downstream') {
    statusByAgent.pm = 'Completed'
    statusByAgent.architect = 'Completed'
    statusByAgent.backend = 'Processing'
    statusByAgent.frontend = 'Processing'
  } else if (pipelineStatus === 'completed') {
    statusByAgent.pm = 'Completed'
    statusByAgent.architect = 'Completed'
    statusByAgent.backend = 'Completed'
    statusByAgent.frontend = 'Completed'
  } else if (pipelineStatus === 'failed') {
    statusByAgent.pm = 'Failed'
    statusByAgent.architect = 'Failed'
    statusByAgent.backend = 'Failed'
    statusByAgent.frontend = 'Failed'
  }

  const agents = [
    {
      id: 1,
      name: 'PM Agent',
      title: 'Product Manager',
      status: statusByAgent.pm,
      statusColor: STATUS_STYLES[statusByAgent.pm],
      icon: User,
      iconBg: 'bg-purple-900',
      iconColor: 'text-purple-400'
    },
    {
      id: 2,
      name: 'System Architect',
      title: 'Architecture',
      status: statusByAgent.architect,
      statusColor: STATUS_STYLES[statusByAgent.architect],
      icon: Network,
      iconBg: 'bg-blue-900',
      iconColor: 'text-blue-400'
    },
    {
      id: 3,
      name: 'Backend Engineer',
      title: 'Backend',
      status: statusByAgent.backend,
      statusColor: STATUS_STYLES[statusByAgent.backend],
      icon: Terminal,
      iconBg: 'bg-green-900',
      iconColor: 'text-green-400'
    },
    {
      id: 4,
      name: 'Front-end Engineer',
      title: 'Frontend',
      status: statusByAgent.frontend,
      statusColor: STATUS_STYLES[statusByAgent.frontend],
      icon: LayoutTemplate,
      iconBg: 'bg-orange-900',
      iconColor: 'text-orange-400'
    }
  ]

  return (
    <div className="bg-[#161925] border border-gray-800 rounded-lg p-4 flex flex-col h-full gap-6">
      {/* Section 1: Project Brief */}
      <div className="flex flex-col gap-3">
        <h3 className="text-sm font-semibold text-gray-200 uppercase tracking-wide flex items-center gap-2">
          <span className="bg-blue-600 text-white w-6 h-6 flex items-center justify-center rounded text-sm">1</span>
          CONTROL CENTER
        </h3>
        
        <div className="relative">
          <div className="absolute top-3 right-3 z-10">
            <button
              onClick={handleClear}
              className="px-3 py-1 bg-purple-600 hover:bg-purple-700 text-white text-xs font-medium rounded transition-colors"
            >
              Clear
            </button>
          </div>
          
          <textarea
            value={projectBrief}
            onChange={(e) => setProjectBrief(e.target.value.slice(0, maxCharacters))}
            placeholder="Enter project brief here..."
            className="w-full h-32 bg-gray-900 border border-gray-700 rounded p-3 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-purple-500 focus:ring-1 focus:ring-purple-500 resize-none"
          />
          
          <div className="absolute bottom-2 right-3 text-xs text-gray-500">
            {projectBrief.length} / {maxCharacters}
          </div>
        </div>

        <button
          onClick={handleStartSwarm}
          disabled={isButtonDisabled}
          className="bg-purple-600 hover:bg-purple-700 disabled:bg-gray-700 disabled:text-gray-400 disabled:cursor-not-allowed text-white font-medium rounded p-2 mt-4 flex items-center justify-center gap-2 transition-colors"
        >
          {isRunningPm ? <Loader size={16} className="animate-spin" /> : <Play size={16} />}
          {isRunningPm ? 'Booting Swarm...' : 'Start'}
        </button>
      </div>

      {/* Section 2: Agent Status Board */}
      <div className="flex flex-col gap-3 flex-1 overflow-hidden">
        <h3 className="text-sm font-semibold text-gray-200 uppercase tracking-wide">Agent Status Board</h3>
        
        <div className="flex flex-col gap-2 overflow-y-auto flex-1">
          {agents.map((agent) => (
            <div
              key={agent.id}
              className="flex items-center gap-3 bg-gray-900 border border-gray-800 rounded p-3 hover:bg-gray-800 transition-colors cursor-pointer group"
            >
              {/* Agent Icon */}
              <div className={`w-8 h-8 ${agent.iconBg} rounded flex-shrink-0 flex items-center justify-center transition-colors`}>
                <agent.icon size={16} className={agent.iconColor} />
              </div>
              
              {/* Agent Info */}
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium text-gray-200">{agent.name}</div>
                <div className="text-xs text-gray-500">{agent.title}</div>
              </div>
              
              {/* Status Badge */}
              <div className="flex items-center gap-2 flex-shrink-0">
                <span className={`w-2 h-2 rounded-full ${agent.statusColor}`}></span>
                <span className="text-xs text-gray-400">{agent.status}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

export default ControlCenter
