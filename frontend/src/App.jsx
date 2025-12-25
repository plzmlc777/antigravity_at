import { BrowserRouter as Router, Routes, Route, Link, useLocation, Navigate } from 'react-router-dom';
import Dashboard from './views/Dashboard';
import ManualTrading from './views/ManualTrading';
import AutoTrading from './views/AutoTrading';
import Login from './views/Login';
import StrategyView from './views/StrategyView';
import Settings from './views/Settings';
import StatusCard from './components/StatusCard';
import AccountStatusPanel from './components/AccountStatusPanel';
import { useState, useEffect } from 'react';
import { getSystemStatus } from './api/client';
import { AuthProvider, useAuth } from './context/AuthContext';

import { MarketDataProvider } from './context/MarketDataContext';

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

// Protected Route Component
const RequireAuth = ({ children }) => {
    const { token, loading } = useAuth();
    if (loading) return null; // Or a loading spinner

    if (!token) {
        return <Navigate to="/login" replace />;
    }
    return children;
};

function AppContent() {
    const { logout, user } = useAuth();
    const location = useLocation();

    // Hide Navbar on Login page
    if (location.pathname === '/login') return null;

    return (
        <div className="min-h-screen bg-[#0a0a0f] text-white selection:bg-blue-500/30">
            {/* Navbar */}
            <nav className="border-b border-white/10 bg-black/20 backdrop-blur-md sticky top-0 z-50">
                <div className="max-w-7xl mx-auto px-6 h-20 flex items-center justify-between">
                    <div className="flex items-center gap-8">
                        <div className="font-bold text-xl tracking-tight bg-gradient-to-r from-blue-400 to-indigo-500 bg-clip-text text-transparent">
                            Antigravity
                        </div>
                        <div className="flex gap-2">
                            <NavLink to="/">Dashboard</NavLink>
                            <NavLink to="/manual">Manual</NavLink>
                            <NavLink to="/auto">Auto Strategy</NavLink>
                            <NavLink to="/settings">Settings</NavLink>
                        </div>
                    </div>
                    <div className="flex items-center gap-4">
                        {/* Mode Toggle */}
                        {/* Mode Toggle Moved to Settings */}
                        <StatusCard />
                        <button onClick={logout} className="text-gray-400 hover:text-white text-sm">Logout</button>
                    </div>
                </div>
            </nav>

            {/* Account Status Panel */}
            <AccountStatusPanel />

            {/* Main Content */}
            <main className="max-w-7xl mx-auto px-6 py-8">
                <Routes>
                    <Route path="/" element={<RequireAuth><Dashboard /></RequireAuth>} />
                    <Route path="/manual" element={<RequireAuth><ManualTrading /></RequireAuth>} />
                    <Route path="/auto" element={<RequireAuth><AutoTrading /></RequireAuth>} />
                    <Route path="/strategies" element={<RequireAuth><StrategyView /></RequireAuth>} /> {/* New Route */}
                    <Route path="/settings" element={<RequireAuth><Settings /></RequireAuth>} />
                </Routes>
            </main>
        </div>
    );
}

function App() {
    return (
        <Router>
            <AuthProvider>
                <MarketDataProvider>
                    <Routes>
                        <Route path="/login" element={<Login />} />
                        <Route path="/*" element={<AppContent />} />
                    </Routes>
                </MarketDataProvider>
            </AuthProvider>
        </Router>
    );
}

export default App;
