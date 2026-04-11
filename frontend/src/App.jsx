import { BrowserRouter as Router, Routes, Route, Link, useLocation, Navigate } from 'react-router-dom';
import Login from './views/Login';
import Settings from './views/Settings';
import AdminView from './views/AdminView';
import MissionControl from './views/MissionControl';
import Organization from './views/Organization';
import DecisionTimeline from './views/DecisionTimeline';
import KnowledgeBase from './views/KnowledgeBase';
import Audition from './views/Audition';
import Workflow from './views/Workflow';
import Calibration from './views/Calibration';
import ManualTrading from './views/ManualTrading';
import StatusCard from './components/StatusCard';
import KpiGoalHeader from './components/KpiGoalHeader';
import { useState, useEffect } from 'react';
import { getSystemVersion } from './api/client';
import { AuthProvider, useAuth } from './context/AuthContext';
import { ThemeProvider } from './context/ThemeContext';
import { WatchlistProvider } from './context/WatchlistContext';
import { LiveTradingProvider } from './context/LiveTradingContext';
import { APP_VERSION, CODE_NAME } from './version';

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
                            My Auto Trading
                        </div>
                        <div className="flex gap-2">
                            <NavLink to="/">Mission</NavLink>
                            <NavLink to="/organization">조직도</NavLink>
                            <NavLink to="/decisions">결정</NavLink>
                            <NavLink to="/knowledge">KB</NavLink>
                            <NavLink to="/audition">오디션</NavLink>
                            <NavLink to="/workflow">Workflow</NavLink>
                            <NavLink to="/calibration">CIR</NavLink>
                            <NavLink to="/manual">수동매매</NavLink>
                            <NavLink to="/settings">Settings</NavLink>
                            {user?.is_admin && <NavLink to="/admin">Admin</NavLink>}
                        </div>
                    </div>
                    <div className="flex items-center gap-4">
                        <KpiGoalHeader />
                        <StatusCard />
                        <div className="flex flex-col items-end mr-4">
                            <span className="text-xs font-bold text-blue-400">{backendVersion || APP_VERSION}</span>
                            <span className="text-[10px] font-mono text-gray-500">{CODE_NAME}</span>
                        </div>
                        <button onClick={logout} className="text-gray-400 hover:text-white text-sm">Logout</button>
                    </div>
                </div>
            </nav>

            {/* Main Content */}
            <main className="max-w-7xl mx-auto px-6 py-8">
                <Routes>
                    <Route path="/" element={<MissionControl />} />
                    <Route path="/organization" element={<Organization />} />
                    <Route path="/decisions" element={<DecisionTimeline />} />
                    <Route path="/knowledge" element={<KnowledgeBase />} />
                    <Route path="/audition" element={<Audition />} />
                    <Route path="/workflow" element={<Workflow />} />
                    <Route path="/calibration" element={<Calibration />} />
                    <Route path="/manual" element={<RequireAuth><ManualTrading /></RequireAuth>} />
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
            <ThemeProvider>
            <AuthProvider>
                <Routes>
                    <Route path="/login" element={<Login />} />
                    <Route path="/*" element={
                        <WatchlistProvider>
                            <LiveTradingProvider>
                                <AppContent />
                            </LiveTradingProvider>
                        </WatchlistProvider>
                    } />
                </Routes>
            </AuthProvider>
            </ThemeProvider>
        </Router>
    );
}

export default App;
