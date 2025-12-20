import { BrowserRouter as Router, Routes, Route, Link, useLocation } from 'react-router-dom';
import Dashboard from './views/Dashboard';
import ManualTrading from './views/ManualTrading';

const NavLink = ({ to, children }) => {
    const location = useLocation();
    const isActive = location.pathname === to;
    return (
        <Link
            to={to}
            className={`px-3 py-1.5 rounded transition-colors text-sm font-medium ${isActive
                    ? 'bg-blue-500/20 text-blue-300 border border-blue-500/30'
                    : 'text-gray-400 hover:text-white hover:bg-white/5'
                }`}
        >
            {children}
        </Link>
    );
};

function App() {
    return (
        <Router>
            <div className="min-h-screen bg-black text-white selection:bg-blue-500/30">
                <header className="border-b border-white/10 p-4">
                    <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                        <h1 className="text-xl font-bold bg-gradient-to-r from-blue-400 to-indigo-400 bg-clip-text text-transparent">
                            Auto Trading System
                        </h1>
                        <nav className="flex gap-2">
                            <NavLink to="/">Dashboard</NavLink>
                            <NavLink to="/manual">Manual Trading</NavLink>
                        </nav>
                    </div>
                </header>
                <main className="p-4">
                    <Routes>
                        <Route path="/" element={<Dashboard />} />
                        <Route path="/manual" element={<ManualTrading />} />
                    </Routes>
                </main>
            </div>
        </Router>
    );
}

export default App;
