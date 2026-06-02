import { useEffect, useMemo, useRef, useState } from 'react'

function Workspace({
  pipelineStatus,
  sessionId,
  prdDocument,
  apiContract,
  files,
  editRequest,
  onUpdatePrdDocument,
  onUpdateApiContract,
  onMarkStageEdited
}) {
  const [manualActiveTab, setManualActiveTab] = useState(null)
  const [selectedFile, setSelectedFile] = useState(null)
  const [editingTab, setEditingTab] = useState(null)
  const [prdDraft, setPrdDraft] = useState('')
  const [architectureDraft, setArchitectureDraft] = useState('{}')
  const [editorError, setEditorError] = useState('')
  const [fileContentMap, setFileContentMap] = useState({})
  const [isLoadingFile, setIsLoadingFile] = useState(false)
  const [fileLoadError, setFileLoadError] = useState('')
  const lastHandledEditTokenRef = useRef(0)

  const availableFiles = Array.isArray(files) ? files : []

  const hasPrdArtifact = Boolean(prdDocument?.trim())
  const hasArchitectureArtifact = Boolean(apiContract && Object.keys(apiContract).length > 0)
  const hasCodeArtifacts = availableFiles.length > 0

  const tabs = [
    { id: 'pr-spec', label: 'PR Spec', enabled: hasPrdArtifact },
    { id: 'architecture', label: 'Architecture', enabled: hasArchitectureArtifact },
    { id: 'code', label: 'Code', enabled: hasCodeArtifacts }
  ]

  const forcedActiveTab =
    pipelineStatus === 'review_prd'
      ? 'pr-spec'
      : pipelineStatus === 'review_contract'
        ? 'architecture'
        : null

  const firstEnabledTab = tabs.find((tab) => tab.enabled)?.id ?? null
  const activeTabCandidate = forcedActiveTab ?? manualActiveTab ?? firstEnabledTab
  const activeTab = tabs.some((tab) => tab.id === activeTabCandidate && tab.enabled)
    ? activeTabCandidate
    : firstEnabledTab

  useEffect(() => {
    setPrdDraft(prdDocument || '')
  }, [prdDocument])

  useEffect(() => {
    const contractText = apiContract ? JSON.stringify(apiContract, null, 2) : '{}'
    setArchitectureDraft(contractText)
  }, [apiContract])

  useEffect(() => {
    if (!selectedFile && availableFiles.length > 0) {
      setSelectedFile(availableFiles[0])
      return
    }

    if (selectedFile && !availableFiles.includes(selectedFile)) {
      setSelectedFile(availableFiles[0] ?? null)
    }
  }, [availableFiles, selectedFile])

  useEffect(() => {
    const loadSelectedArtifact = async () => {
      if (activeTab !== 'code' || !sessionId || !selectedFile) {
        return
      }

      if (fileContentMap[selectedFile] !== undefined) {
        setFileLoadError('')
        return
      }

      setIsLoadingFile(true)
      setFileLoadError('')

      try {
        const response = await fetch(`/api/pipeline/artifacts/${sessionId}/${encodeURIComponent(selectedFile)}`)
        if (!response.ok) {
          throw new Error(`Failed to load ${selectedFile}`)
        }

        const data = await response.json()
        setFileContentMap((prev) => ({
          ...prev,
          [selectedFile]: typeof data.content === 'string' ? data.content : ''
        }))
      } catch (error) {
        setFileLoadError(error instanceof Error ? error.message : `Failed to load ${selectedFile}`)
      } finally {
        setIsLoadingFile(false)
      }
    }

    loadSelectedArtifact()
  }, [activeTab, fileContentMap, selectedFile, sessionId])

  useEffect(() => {
    if (!editRequest?.target || !editRequest?.token) {
      return
    }

    if (lastHandledEditTokenRef.current === editRequest.token) {
      return
    }

    const targetTab = editRequest.target
    const targetEnabled = tabs.some((tab) => tab.id === targetTab && tab.enabled)
    if (!targetEnabled) {
      return
    }

    lastHandledEditTokenRef.current = editRequest.token

    setManualActiveTab(targetTab)
    setEditingTab(targetTab)
    setEditorError('')
  }, [editRequest, tabs])

  const viewerText = useMemo(() => {
    if (!activeTab) {
      return ''
    }

    if (activeTab === 'pr-spec') {
      return prdDocument || ''
    }

    if (activeTab === 'architecture') {
      return JSON.stringify(apiContract ?? {}, null, 2)
    }

    if (activeTab === 'code') {
      if (!selectedFile) {
        return ''
      }

      if (fileLoadError) {
        return `Failed to load ${selectedFile}.\n\n${fileLoadError}`
      }

      if (isLoadingFile) {
        return `Loading ${selectedFile}...`
      }

      return fileContentMap[selectedFile] ?? ''
    }

    return ''
  }, [activeTab, apiContract, fileContentMap, fileLoadError, isLoadingFile, prdDocument, selectedFile])

  const handleDownloadSelectedFile = () => {
    if (!selectedFile || fileContentMap[selectedFile] === undefined) {
      return
    }

    const blob = new Blob([fileContentMap[selectedFile]], { type: 'text/plain;charset=utf-8' })
    const objectUrl = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = objectUrl
    anchor.download = selectedFile
    document.body.appendChild(anchor)
    anchor.click()
    document.body.removeChild(anchor)
    URL.revokeObjectURL(objectUrl)
  }

  const escapeHtml = (text) =>
    text
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')

  const highlightSyntax = (text) => {
    const escaped = escapeHtml(text)
    const tokenPattern = /("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')|\b(from|import|class|async\s+def|def|return|True|False|null|const|let|var|function)\b|\b(\d+)\b/g

    return escaped.replace(tokenPattern, (match, stringToken, keywordToken, numberToken) => {
      if (stringToken) {
        return `<span class="text-yellow-300">${stringToken}</span>`
      }

      if (keywordToken) {
        return `<span class="text-pink-500">${keywordToken}</span>`
      }

      if (numberToken) {
        return `<span class="text-cyan-300">${numberToken}</span>`
      }

      return match
    })
  }

  const handleSaveEdit = () => {
    setEditorError('')

    if (editingTab === 'pr-spec') {
      onUpdatePrdDocument?.(prdDraft)
      onMarkStageEdited?.('pr-spec')
      setEditingTab(null)
      return
    }

    if (editingTab === 'architecture') {
      try {
        const parsed = JSON.parse(architectureDraft)
        onUpdateApiContract?.(parsed)
        onMarkStageEdited?.('architecture')
        setEditingTab(null)
      } catch {
        setEditorError('Architecture must be valid JSON before saving.')
      }
    }
  }

  const handleCancelEdit = () => {
    if (editingTab === 'pr-spec') {
      setPrdDraft(prdDocument || '')
    }

    if (editingTab === 'architecture') {
      setArchitectureDraft(apiContract ? JSON.stringify(apiContract, null, 2) : '{}')
    }

    setEditorError('')
    setEditingTab(null)
  }

  return (
    <div className="bg-[#161925] border border-gray-800 rounded-lg flex flex-col h-full">
      {/* Top Bar */}
      <div className="border-b border-gray-800 p-4">
        <h3 className="text-sm font-semibold text-gray-200 uppercase tracking-wide flex items-center gap-2 mb-3">
          <span className="bg-blue-600 text-white w-6 h-6 flex items-center justify-center rounded text-sm">3</span>
          WORKSPACE ARTIFACTS
        </h3>

        {/* Tabs */}
        <div className="flex gap-4">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              disabled={!tab.enabled}
              onClick={() => {
                if (!tab.enabled) {
                  return
                }
                setManualActiveTab(tab.id)
                setEditingTab(null)
                setEditorError('')
              }}
              className={`text-sm font-medium pb-2 border-b-2 transition-colors ${
                activeTab === tab.id
                  ? 'text-purple-400 border-b-purple-400'
                  : tab.enabled
                    ? 'text-gray-400 border-b-transparent hover:text-gray-300'
                    : 'text-gray-600 border-b-transparent cursor-not-allowed'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Workspace Content */}
      <div className="flex-1 flex overflow-hidden">
        {activeTab === 'code' && (
          <div className="w-[30%] border-r border-gray-800 overflow-y-auto">
            {availableFiles.length === 0 && (
              <div className="h-full flex items-center justify-center text-xs text-gray-500 px-4 text-center">
                No generated files yet.
              </div>
            )}

            {availableFiles.map((file) => (
              <button
                key={file}
                onClick={() => setSelectedFile(file)}
                className={`w-full text-left px-4 py-2 text-xs font-medium border-l-4 transition-colors ${
                  selectedFile === file
                    ? 'bg-blue-900 border-l-blue-500 text-blue-200'
                    : 'border-l-transparent text-gray-300 hover:bg-gray-800'
                }`}
              >
                {file}
              </button>
            ))}
          </div>
        )}

        <div className="flex-1 bg-[#0f111a] font-mono text-sm p-4 overflow-y-auto">
          {activeTab === 'code' && selectedFile && (
            <div className="flex items-center justify-end mb-3">
              <button
                onClick={handleDownloadSelectedFile}
                disabled={isLoadingFile || fileContentMap[selectedFile] === undefined}
                className="px-3 py-1 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-700 disabled:text-gray-400 disabled:cursor-not-allowed text-white text-xs font-medium rounded transition-colors"
              >
                Download
              </button>
            </div>
          )}

          {!activeTab && (
            <div className="h-full flex items-center justify-center text-gray-500 text-sm text-center px-6">
              Workspace is idle. Artifacts will appear after agent execution.
            </div>
          )}

          {activeTab === 'pr-spec' && editingTab === 'pr-spec' && (
            <div className="h-full flex flex-col gap-3">
              <textarea
                value={prdDraft}
                onChange={(event) => setPrdDraft(event.target.value)}
                className="flex-1 bg-gray-900 border border-gray-700 rounded p-3 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-purple-500 focus:ring-1 focus:ring-purple-500 resize-none"
                placeholder="Edit PRD document..."
              />
              <div className="flex items-center justify-end gap-2">
                <button
                  onClick={handleCancelEdit}
                  className="px-3 py-1 bg-gray-800 hover:bg-gray-700 text-gray-200 text-xs font-medium rounded transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={handleSaveEdit}
                  className="px-3 py-1 bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium rounded transition-colors"
                >
                  Save
                </button>
              </div>
            </div>
          )}

          {activeTab === 'architecture' && editingTab === 'architecture' && (
            <div className="h-full flex flex-col gap-3">
              <textarea
                value={architectureDraft}
                onChange={(event) => setArchitectureDraft(event.target.value)}
                className="flex-1 bg-gray-900 border border-gray-700 rounded p-3 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-purple-500 focus:ring-1 focus:ring-purple-500 resize-none"
                placeholder="Edit architecture JSON..."
              />
              {editorError && <p className="text-xs text-red-400">{editorError}</p>}
              <div className="flex items-center justify-end gap-2">
                <button
                  onClick={handleCancelEdit}
                  className="px-3 py-1 bg-gray-800 hover:bg-gray-700 text-gray-200 text-xs font-medium rounded transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={handleSaveEdit}
                  className="px-3 py-1 bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium rounded transition-colors"
                >
                  Save
                </button>
              </div>
            </div>
          )}

          {activeTab && editingTab !== activeTab && (
            <pre className="text-gray-300">
              <code dangerouslySetInnerHTML={{ __html: highlightSyntax(viewerText || 'No content available.') }} />
            </pre>
          )}
        </div>
      </div>
    </div>
  )
}

export default Workspace
