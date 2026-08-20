import ReactMarkdown from 'react-markdown'

function ChatMessage({ message }) {
  const isUser = message.role === 'user'
  const isError = message.role === 'error'

  return (
    <article className={`chat-message ${isUser ? 'is-user' : ''} ${isError ? 'is-error' : ''}`}>
      <div className="message-meta">
        <span>{isUser ? 'You' : isError ? 'System' : 'AquaNexus'}</span>
        {message.tools_used?.length > 0 && (
          <span className="message-tool">{message.tools_used.join(', ')}</span>
        )}
      </div>
      <ReactMarkdown>{message.text}</ReactMarkdown>
      {message.modules_used?.length > 0 && (
        <div className="module-chip-row">
          {message.modules_used.map((module) => (
            <span className="module-chip" key={module}>
              {module.toUpperCase()}
            </span>
          ))}
        </div>
      )}
    </article>
  )
}

export default ChatMessage
