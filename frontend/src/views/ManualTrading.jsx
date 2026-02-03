import ManualTrade from '../components/ManualTrade';
import SymbolSelector from '../components/SymbolSelector';
import TradingInfoPanel from '../components/TradingInfoPanel';
import ApiLogPanel from '../components/ApiLogPanel';
import Card from '../components/common/Card';
import { useWatchlist } from '../context/WatchlistContext';

const ManualTrading = () => {
    // Use shared watchlist context (synced with DB)
    const { currentSymbol, setCurrentSymbol, savedSymbols, setSavedSymbols } = useWatchlist();

    return (
        <div className="space-y-6">
            <Card title="Market Selection">
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
                <div className="lg:col-span-2">
                    <Card title="Manual Trading Execution">
                        <p className="text-gray-400 mb-6 text-sm">
                            Execute buy and sell orders manually using Limit or Market prices.
                        </p>
                        <div className="max-w-xl">
                            <ManualTrade defaultSymbol={currentSymbol} />
                        </div>
                    </Card>
                </div>
                <div>
                    <Card title="System Logs">
                        <ApiLogPanel />
                    </Card>
                </div>
            </div>
        </div>
    );
};

export default ManualTrading;
