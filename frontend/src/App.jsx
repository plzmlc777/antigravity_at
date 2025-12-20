import Dashboard from './views/Dashboard'

function App() {
    return (
        <div className="min-h-screen bg-black text-white selection:bg-blue-500/30">
            <header className="border-b border-white/10 p-4">
                <h1 className="text-xl font-bold bg-gradient-to-r from-blue-400 to-indigo-400 bg-clip-text text-transparent">
                    Auto Trading System
                </h1>
            </header>
            <main className="p-4">
                <Dashboard />
            </main>
        </div>
    )
}

export default App
