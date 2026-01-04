# Quant Strategy Module

This module implements local quantitative trading strategies for the PPX client.

## Structure

- `base.py`: Defines the `BaseStrategy` class. All strategies should inherit from this.
- `grid.py`: Implementation of the Grid Trading strategy.
- `manager.py`: `StrategyManager` singleton to manage running strategy instances.
- `trader.py`: Wrapper for `easytrader` and `easyquotation` to handle real trading.
- `__init__.py`: Package initialization.

## Dependencies

To enable real trading, you need to install the following Python packages:

```bash
pip install easytrader easyquotation
```

**Note**: `easytrader` relies on Windows automation for most brokers. On macOS/Linux, it will fallback to Mock mode unless you use supported web interfaces (e.g., Xueqiu) or the remote client feature.

## Adding a New Strategy

1. Create a new file (e.g., `martingale.py`).
2. Define a class inheriting from `BaseStrategy`.
3. Implement the `run(self)` method with your logic.
4. Update `manager.py` to recognize and instantiate your new strategy based on `task_data`.

## API

The strategies are exposed to the frontend via `PPX/api/quant.py`, which is mixed into the main `API` class.

- `quant_startStrategy(task_data)`
- `quant_stopStrategy(task_id)`
- `quant_getRunningStrategies()`
