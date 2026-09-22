# AI Quant Trading Terminal — Frontend Workstation

Professional trading analysis terminal and decision support workstation built with Vue 3, Vite, and native HTML5 Canvas.

## Architecture & Integration

```
MT5 Terminal
  → Windows MT5 Bridge (:8765)
    → FastAPI Backend (:8000)
      → Vue 3 Frontend Workstation (:5173)
```

> **IMPORTANT SAFETY NOTICE:**
> The system is **MANUAL EXECUTION ONLY**.
> The AI reasoning engine and backend algorithms provide probabilistic decision support and risk models.
> Orders are **NEVER** placed automatically by the platform; all trades remain under direct manual execution by the trader in the MT5 Terminal.

## Features & Components

- **Top Bar & Ticker:** Active instrument selector (`EURUSDm`, `XAUUSDm`, etc.), real-time price & spread readout, MT5 bridge feed status, UTC timestamp, manual refresh, and auto-poll toggles.
- **Market Overview Cards:** 6 high-density cards for Overall/HTF/Intraday/Entry Bias, Active Scenario, Trigger Confirmation status, Live Price, Volatility (ATR 14), and Trade Plan Risk status.
- **Interactive Candlestick Chart:** Native HTML5 Canvas chart displaying authentic MT5 candle feeds, timeframe toggles (`M1` through `D1`), hover crosshair with OHLCV readouts, and overlays for Support, Resistance, Trigger, and Invalidation levels.
- **Multi-Timeframe Alignment:** Matrix evaluating `D1`, `H4`, `H1`, `M30`, `M15`, `M5`, `M1` across Trend, Structure, EMAs (20/50/200), RSI (14), MACD (Line, Signal, Histogram), and ATR.
- **Market Structure Tracker:** Visual swing points flow classifying `HH`, `HL`, `LH`, `LL` structures per timeframe.
- **Key Level Zones:** Confluent support and resistance bands with touch counts, distance metrics, and scenario trigger/invalidation demarcation.
- **Scenario Evaluation Engine:** Multi-conditional directional models (Bullish Reversal, Bearish Continuation, Range Compression) with distance-to-trigger metrics.
- **Trade Plan & Risk Management:** Mathematical position sizing, volume lot calculation, and stop-loss invalidation thresholds.
- **AI Reasoning Console:** Dedicated cyber-terminal intelligence window summarizing probabilistic market context, scenario interpretations, and warnings from Gemini / Claude.
- **System Settings & Diagnostics:** Live API endpoint configuration, latency tests, bridge health diagnostics, and session management.

## Development & Execution

```bash
# Install dependencies
npm install

# Start development server
npm run dev

# Build for production
npm run build
```

API configuration is managed via `VITE_API_BASE_URL` in `.env` or interactively inside the **System Settings** tab of the terminal.

