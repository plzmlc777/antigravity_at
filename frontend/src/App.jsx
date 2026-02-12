import { BrowserRouter as Router, Routes, Route, Link, useLocation, Navigate } from 'react-router-dom';
import Dashboard from './views/Dashboard';
import ManualTrading from './views/ManualTrading';
import LiveTradingView from './views/LiveTradingView';
import Login from './views/Login';
import StrategyView from './views/StrategyView';
import Settings from './views/Settings';
import AdminView from './views/AdminView';
import StatusCard from './components/StatusCard';
import AccountStatusPanel from './components/AccountStatusPanel';
import { useState, useEffect } from 'react';
import { getSystemStatus, getSystemVersion } from './api/client';
import { AuthProvider, useAuth } from './context/AuthContext';

import { MarketDataProvider } from './context/MarketDataContext';
import { WatchlistProvider } from './context/WatchlistContext';
import { LiveTradingProvider } from './context/LiveTradingContext';
import { StrategiesProvider } from './context/StrategiesContext';
import { APP_VERSION, COMMIT_HASH, CODE_NAME } from './version';

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

// Admin Only Route Component
const RequireAdmin = ({ children }) => {
    const { user, token, loading } = useAuth();
    if (loading) return null;

    if (!token) return <Navigate to="/login" replace />;
    if (!user?.is_admin) return <Navigate to="/" replace />;

    return children;
};

function AppContent() {
    const { logout, user } = useAuth();
    const location = useLocation();
    const [backendVersion, setBackendVersion] = useState(null);

    useEffect(() => {
        const fetchVersion = async () => {
            try {
                const data = await getSystemVersion();
                if (data.version) {
                    const ver = data.version.startsWith('v') ? data.version : 'v' + data.version;
                    setBackendVersion(ver);
                }
            } catch (err) {
                console.error("Failed to fetch backend version", err);
            }
        };
        fetchVersion();
    }, []);

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
                            <NavLink to="/live">Live</NavLink>
                            <NavLink to="/strategies">Strategies</NavLink>
                            <NavLink to="/settings">Settings</NavLink>
                            {user?.is_admin && <NavLink to="/admin">Admin</NavLink>}
                        </div>
                    </div>
                    <div className="flex items-center gap-4">
                        {/* Mode Toggle */}
                        {/* Mode Toggle Moved to Settings */}
                        <StatusCard />
                        <div className="flex flex-col items-end mr-4">
                            <span className="text-xs font-bold text-blue-400">{backendVersion || APP_VERSION}</span>
                            <span className="text-[10px] font-mono text-gray-500">{CODE_NAME}</span>
                        </div>
                        <button onClick={logout} className="text-gray-400 hover:text-white text-sm">Logout</button>
                    </div>
                </div>
            </nav>

            {/* Account Status Panel - hidden on /live and /strategies pages */}
            {location.pathname !== '/live' && location.pathname !== '/strategies' && <AccountStatusPanel />}

            {/* Main Content */}
            <main className="max-w-7xl mx-auto px-6 py-8">
                <Routes>
                    <Route path="/" element={<RequireAuth><Dashboard /></RequireAuth>} />
                    <Route path="/manual" element={<RequireAuth><ManualTrading /></RequireAuth>} />
                    <Route path="/live" element={<RequireAuth><LiveTradingView /></RequireAuth>} />
                    <Route path="/strategies" element={<RequireAuth><StrategyView /></RequireAuth>} />
                    <Route path="/settings" element={<RequireAuth><Settings /></RequireAuth>} />
                    <Route path="/admin" element={<RequireAdmin><AdminView /></RequireAdmin>} />
                </Routes>
            </main>
        </div>
    );
}

function App() {
    return (
        <Router>
            <AuthProvider>
                <Routes>
                    <Route path="/login" element={<Login />} />
                    <Route path="/*" element={
                        <MarketDataProvider>
                            <WatchlistProvider>
                                <LiveTradingProvider>
                                    <StrategiesProvider>
                                        <AppContent />
                                    </StrategiesProvider>
                                </LiveTradingProvider>
                            </WatchlistProvider>
                        </MarketDataProvider>
                    } />
                </Routes>
            </AuthProvider>
        </Router>
    );
}

export default App;
