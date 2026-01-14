from src.strategy.fade_strategy import FadeStrategy

def test_fade_strategy_atr_logic():
    strategy = FadeStrategy(
        anomaly_threshold=0.7,
        min_impact_per_volume=0.01,
        take_profit_bps=50,
        stop_loss_bps=30,
        time_stop_min=10,
        atr_window=5
    )
    
    market = "test_market"
    mid = 100.0
    features = {"impact_per_volume": 0.005}
    
    # 1. No signal if score < threshold
    signal = strategy.generate_signal(market, mid, 1.0, 0.5, features, 10)
    assert signal is None
    
    # 2. Sell signal on positive move
    signal = strategy.generate_signal(market, 101.0, 1.0, 0.8, features, 10)
    assert signal.side == "sell"
    assert signal.price < 101.0 # Due to negative offset for sell
    
    # 3. Dynamic SL/TP check
    # Need at least 2 prices for ATR > 0
    # Price sequence: 100, 101, 102
    # Returns: |101-100|=1, |102-101|=1 -> ATR=1.0
    signal = strategy.generate_signal(market, 102.0, 1.0, 0.8, features, 10)
    assert signal.features["atr"] == 1.0
    
    # Sell side: TP = price - 2*ATR, SL = price + 1.5*ATR
    price = signal.price
    assert signal.features["tp_price"] == min(price * (1 - 50/10000), price - 2.0)
    assert signal.features["sl_price"] == max(price * (1 + 30/10000), price + 1.5)

def test_fade_strategy_buy_signal():
    strategy = FadeStrategy(
        anomaly_threshold=0.7,
        min_impact_per_volume=0.01,
        take_profit_bps=50,
        stop_loss_bps=30,
        time_stop_min=10
    )
    market = "test_buy"
    features = {"impact_per_volume": 0.005}
    
    # Buy signal on negative move
    signal = strategy.generate_signal(market, 99.0, -1.0, 0.8, features, 10)
    assert signal.side == "buy"
    assert signal.price > 99.0 # Positive offset for buy
