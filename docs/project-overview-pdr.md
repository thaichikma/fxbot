# Project Overview & Product Development Requirements (PDR)

## Vision
The objective is to architect and implement a robust, fully automated trading system bridging Python with MetaTrader 5 (MT5), specifically built to safely pass and maintain FTMO prop firm trading accounts without violating their firm constraints.

## Target Audience
- FTMO Prop-Firm Traders ($10,000 Swing 2-Step Challenge focus)
- Personal VPS deployment managers

## Core Value Proposition
- **Risk Avoidance First**: Protect account capital automatically independent of emotional trading behaviors via the `FTMOGuardian`.
- **SMC Focused**: Pure focus on unadulterated price action logic using Smart Money Concepts instead of relying on lagging technical indicators.
- **VPS Ready**: Built on asynchronous Python natively compatible with Windows VPS `MetaTrader5` connections.

## Technical Milestones
1. **Foundation**: Build config system, Mock-MT5 dev-mode for Mac, Guardian bounds, and Daily reset/Tracker logic.
2. **Strategy Engine**: SMC mapping (BOS, CHoCH, liquidity sweeps).
3. **Execution & Hybrid mode**: Position sizing algorithms, partial scaling (TP1 50%, TP2 30%, TP3 20%), and continuous Telegram oversight.

## Future Plans (AI/ML)
Implementation of Machine Learning models (LightGBM/XGBoost) to evaluate incoming signal quality (A/B ranking scale 0-100) before authorizing standard volume entries.
