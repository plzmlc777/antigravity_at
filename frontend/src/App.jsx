import { BrowserRouter as Router, Routes, Route, Link, useLocation } from 'react-router-dom';
import Dashboard from './views/Dashboard';
import ManualTrading from './views/ManualTrading';
import AutoTrading from './views/AutoTrading';
import StatusCard from './components/StatusCard';
import { useState, useEffect } from 'react';
import { getSystemStatus } from './api/client';

const NavLink = ({ to, children }) => {
    const location = useLocation();
    const isActive = location.pathname === to;

    return (
        <Link
            to={to}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${isActive
                    ? 'bg-blue-600 text-white shadow-lg shadow-blue-500/30'
                    : 'text-gray-400 hover:text-white hover:bg-white/5'
                }`}
        >
            {children}
        </Link>
    );
};

function App() {
    const [status, setStatus] = useState({ exchange: 'Unknown', status: 'offline' });

    useEffect(() => {
        const fetchStatus = async () => {
            try {
                const data = await getSystemStatus();
                setStatus(data);
            } catch (error) {
                setStatus({ exchange: 'Error', status: 'offline' });
            }
        };
        fetchStatus();
        const interval = setInterval(fetchStatus, 30000);
        return () => clearInterval(interval);
    }, []);

    return (
        <Router>
            <div className="min-h-screen bg-[#0a0a0f] text-white selection:bg-blue-500/30">
                {/* Navbar */}
                <nav className="border-b border-white/10 bg-black/20 backdrop-blur-md sticky top-0 z-50">
                    <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
                        <div className="flex items-center gap-8">
                            <div className="font-bold text-xl tracking-tight bg-gradient-to-r from-blue-400 to-indigo-500 bg-clip-text text-transparent">
                                Antigravity
                            </div>
                            <div className="flex gap-2">
                                <NavLink to="/">Dashboard</NavLink>
                                <NavLink to="/manual">Manual</NavLink>
                                <NavLink to="/auto">Auto Strategy</NavLink>
                            </div>
                        </div>
                        <StatusCard status={status} />
                    </div>
                </nav>

                {/* Main Content */}
                <main className="max-w-7xl mx-auto px-6 py-8">
                    <Routes>
                        <Route path="/" element={<Dashboard />} />
                        <Route path="/manual" element={<ManualTrading />} />
                        <Route path="/auto" element={<AutoTrading />} />
                    </Routes>
                </main>
            </div>
        </Router>
    );
}

export default App;
