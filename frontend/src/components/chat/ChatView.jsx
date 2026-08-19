import { SendHorizontal, Sparkles } from 'lucide-react'
import { useMemo, useState } from 'react'
import { sendChatMessage } from '../../services/api.js'
import ChatMessage from './ChatMessage.jsx'
import EvidencePanel from './EvidencePanel.jsx'

const SUGGESTED_PROMPTS = [
  'What are the ocean conditions near Kochi?',
  'What is the temperature at 100 m near Kochi?',
  'What are the ocean conditions in the Arabian Sea?',
]

const WELCOME_MESSAGE = {
  id: 'welcome',
  role: 'assistant',
  text:
    'AquaNexus is connected to location-aware ocean intelligence. Ask about a place, sea, region, or coordinate inside the coverage area.',
  modules_used: [],
  tools_used: [],
}

function ChatView() {
  const [messages, setMessages] = useState([WELCOME_MESSAGE])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [latestEvidence, setLatestEvidence] = useState([])
  const [latestTools, setLatestTools] = useState([])
  const [latestModules, setLatestModules] = useState([])

  const canSubmit = useMemo(() => input.trim().length > 0 && !isLoading, [input, isLoading])

  async function submitMessage(value = input) {
    const message = value.trim()
    if (!message || isLoading) return

    setInput('')
    setIsLoading(true)
    setMessages((current) => [
      ...current,
      { id: crypto.randomUUID(), role: 'user', text: message },
    ])

    try {
      const response = await sendChatMessage(message)
      setLatestEvidence(response.evidence || [])
      setLatestTools(response.tools_used || [])
      setLatestModules(response.modules_used || [])
      setMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: 'assistant',
          text: response.text || 'No narrative response was returned.',
          modules_used: response.modules_used || [],
          tools_used: response.tools_used || [],
        },
      ])
    } catch (error) {
      setMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: 'error',
          text: error.message || 'The backend request failed.',
        },
      ])
    } finally {
      setIsLoading(false)
    }
  }

  function handleSubmit(event) {
    event.preventDefault()
    submitMessage()
  }

  return (
    <div className="chat-layout">
      <section className="chat-console" aria-label="AquaNexus chat">
        <div className="console-header">
          <div>
            <p className="eyebrow">Command Channel</p>
            <h1>Ask natural ocean questions</h1>
          </div>
          <div className="console-chip">
            <Sparkles size={16} />
            Live agent tools
          </div>
        </div>

        <div className="suggested-prompts" aria-label="Suggested prompts">
          {SUGGESTED_PROMPTS.map((prompt) => (
            <button
              key={prompt}
              type="button"
              onClick={() => submitMessage(prompt)}
              disabled={isLoading}
            >
              {prompt}
            </button>
          ))}
        </div>

        <div className="message-list" aria-live="polite">
          {messages.map((message) => (
            <ChatMessage key={message.id} message={message} />
          ))}
          {isLoading && (
            <div className="querying-indicator">
              <span />
              Querying ocean intelligence...
            </div>
          )}
        </div>

        <form className="chat-input-row" onSubmit={handleSubmit}>
          <label className="sr-only" htmlFor="chat-input">
            Message
          </label>
          <input
            id="chat-input"
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder="Ask: What is the temperature near Kochi?"
            disabled={isLoading}
          />
          <button type="submit" disabled={!canSubmit} aria-label="Send message">
            <SendHorizontal size={20} />
          </button>
        </form>
      </section>

      <EvidencePanel evidence={latestEvidence} toolsUsed={latestTools} modulesUsed={latestModules} />
    </div>
  )
}

export default ChatView
