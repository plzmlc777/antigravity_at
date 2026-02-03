import Diagram from '../components/Diagram';
import SymbolSelector from '../components/SymbolSelector';
import TradingInfoPanel from '../components/TradingInfoPanel';
import ApiLogPanel from '../components/ApiLogPanel';
import Card from '../components/common/Card';
import { useWatchlist } from '../context/WatchlistContext';

const Dashboard = () => {
    // Use shared watchlist context (synced with DB)
    const { currentSymbol, setCurrentSymbol, savedSymbols, setSavedSymbols } = useWatchlist();

    return (
        <div className="space-y-6">
            {/* Symbol Selection Area */}
            <Card title="Watchlist & Search">
                <SymbolSelector
                    currentSymbol={currentSymbol}
                    setCurrentSymbol={setCurrentSymbol}
                    savedSymbols={savedSymbols}
                    setSavedSymbols={setSavedSymbols}
                />
            </Card>

            <Card title="Market Overview">
                <TradingInfoPanel
                    currentSymbol={currentSymbol}
                    setSavedSymbols={setSavedSymbols}
                />
            </Card>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div className="lg:col-span-2 space-y-6">
                    <Card title="Process Visualization">
                        <Diagram />
                    </Card>
                </div>

                <div className="space-y-6">
                    <Card title="System Logs">
                        <ApiLogPanel />
                    </Card>
                </div>
            </div>
        </div>
    );
};

export default Dashboard;
