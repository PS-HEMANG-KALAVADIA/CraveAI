import { useChat } from './hooks/useChat'
import { useLocation } from './hooks/useLocation'
import { useSwiggyAuth } from './hooks/useSwiggyAuth'
import { ChatWindow } from './components/Chat/ChatWindow'
import { LocationPermission } from './components/Location/LocationPermission'
import { SwiggyAuth } from './components/Auth/SwiggyAuth'

function App() {
  const { locationState, requestLocation } = useLocation()
  const swiggyAuth = useSwiggyAuth()
  const { messages, isLoading, loadingMessage, error, sendMessage } = useChat(locationState, swiggyAuth)

  return (
    <div className="app-container">
      <div className="chat-interface">
        {/* Header */}
        <header className="chat-header">
          <div className="header-brand">
            <div className="header-icon" aria-hidden="true">🍲</div>
            <div className="header-title-group">
              <h1>CraveAI</h1>
              <p className="header-subtitle">Context-Aware Food Discovery</p>
            </div>
          </div>
          
          <div className="header-actions">
            <LocationPermission 
              locationState={locationState} 
              onRequest={requestLocation} 
            />
            <SwiggyAuth 
              status={swiggyAuth.status}
              loginUrl={swiggyAuth.loginUrl}
              onRefresh={swiggyAuth.checkStatus}
            />
          </div>
        </header>

        {error && (
          <div className="error-banner">
            <span>⚠️</span> {error}
          </div>
        )}

        {/* Main Chat Area */}
        <ChatWindow 
          messages={messages}
          isLoading={isLoading}
          loadingMessage={loadingMessage}
          onSendMessage={sendMessage}
        />
      </div>
    </div>
  )
}

export default App
