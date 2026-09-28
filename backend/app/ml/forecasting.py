"""Cash-flow forecasting.

Model selection is driven by how much history exists, because fitting a
seasonal model to five data points produces a confident-looking line with no
information in it:

    >= 24 months : Holt-Winters exponential smoothing with additive seasonality
    >= 12 months : Holt's linear trend (damped)
    >=  6 months : simple exponential smoothing
    >=  3 months : weighted moving average (recent months weighted higher)
    <   3 months : no forecast - we say so instead of inventing one

Prediction intervals come from the in-sample residual standard deviation and
widen with the horizon (sigma * sqrt(h)), which is the standard random-walk
assumption. They are indicative, not guarantees, and the API says so.
"""

from __future__ import annotations

import logging
import math
import warnings
from dataclasses import dataclass
from datetime import date

import numpy as np

logger = logging.getLogger(__name__)

MIN_MONTHS_FOR_FORECAST = 3
MIN_MONTHS_SEASONAL = 24
MIN_MONTHS_TREND = 12
MIN_MONTHS_SES = 6

# 80% prediction interval - deliberately not 95%: on 6-12 monthly observations a
# 95% band is so wide it tells the user nothing.
Z_SCORE_80 = 1.2816


@dataclass
class ForecastResult:
    method: str
    method_detail: str
    fitted: list[float]
    forecast: list[float]
    lower: list[float]
    upper: list[float]
    residual_std: float

    @property
    def has_interval(self) -> bool:
        return self.residual_std > 0


def _weighted_moving_average(values: np.ndarray, horizon: int) -> ForecastResult:
    """Linear-weighted average of the last up-to-3 months."""
    window = values[-3:]
    weights = np.arange(1, len(window) + 1, dtype=float)
    point = float(np.average(window, weights=weights))

    fitted: list[float] = []
    for index in range(len(values)):
        if index == 0:
            fitted.append(float(values[0]))
            continue
        past = values[max(0, index - 3) : index]
        w = np.arange(1, len(past) + 1, dtype=float)
        fitted.append(float(np.average(past, weights=w)))

    residuals = values - np.array(fitted)
    std = float(np.std(residuals, ddof=1)) if len(residuals) > 1 else 0.0

    forecast = [point] * horizon
    lower = [max(0.0, point - Z_SCORE_80 * std * math.sqrt(h + 1)) for h in range(horizon)]
    upper = [point + Z_SCORE_80 * std * math.sqrt(h + 1) for h in range(horizon)]

    return ForecastResult(
        method="weighted_moving_average",
        method_detail=(
            "Weighted moving average over the last 3 months (most recent month "
            "weighted highest). Used because there is not yet enough history to "
            "estimate a trend reliably."
        ),
        fitted=fitted,
        forecast=forecast,
        lower=lower,
        upper=upper,
        residual_std=std,
    )


def _statsmodels_forecast(values: np.ndarray, horizon: int) -> ForecastResult | None:
    """Exponential smoothing via statsmodels, with the variant chosen by length."""
    try:
        from statsmodels.tsa.holtwinters import ExponentialSmoothing, SimpleExpSmoothing
    except ImportError:  # pragma: no cover - statsmodels is a hard dependency
        logger.warning("statsmodels unavailable; falling back to moving average")
        return None

    n = len(values)
    try:
        with warnings.catch_warnings():
            # Short series legitimately trigger convergence chatter; we handle
            # the quality question through the interval width instead.
            warnings.simplefilter("ignore")

            if n >= MIN_MONTHS_SEASONAL:
                model = ExponentialSmoothing(
                    values,
                    trend="add",
                    seasonal="add",
                    seasonal_periods=12,
                    initialization_method="estimated",
                )
                fit = model.fit(optimized=True)
                method = "holt_winters_additive"
                detail = (
                    "Holt-Winters exponential smoothing with additive trend and "
                    "12-month additive seasonality, fitted on "
                    f"{n} months of history."
                )
            elif n >= MIN_MONTHS_TREND:
                model = ExponentialSmoothing(
                    values,
                    trend="add",
                    damped_trend=True,
                    seasonal=None,
                    initialization_method="estimated",
                )
                fit = model.fit(optimized=True)
                method = "holt_damped_trend"
                detail = (
                    "Holt's linear trend method with damping, fitted on "
                    f"{n} months of history. Damping prevents a short-run trend "
                    "from being extrapolated indefinitely."
                )
            elif n >= MIN_MONTHS_SES:
                model = SimpleExpSmoothing(values, initialization_method="estimated")
                fit = model.fit(optimized=True)
                method = "simple_exponential_smoothing"
                detail = (
                    f"Simple exponential smoothing fitted on {n} months of "
                    "history. No trend or seasonal component is estimated - "
                    "there is not enough data to separate them from noise."
                )
            else:
                return None

            predictions = np.asarray(fit.forecast(horizon), dtype=float)
            fitted = np.asarray(fit.fittedvalues, dtype=float)
    except Exception:
        logger.exception("Exponential smoothing failed; falling back to moving average")
        return None

    if not np.all(np.isfinite(predictions)):
        logger.warning("Forecast produced non-finite values; falling back")
        return None

    residuals = values - fitted
    std = float(np.std(residuals, ddof=1)) if len(residuals) > 1 else 0.0

    point = [max(0.0, float(v)) for v in predictions]
    lower = [max(0.0, point[h] - Z_SCORE_80 * std * math.sqrt(h + 1)) for h in range(horizon)]
    upper = [point[h] + Z_SCORE_80 * std * math.sqrt(h + 1) for h in range(horizon)]

    return ForecastResult(
        method=method,
        method_detail=detail,
        fitted=[float(v) for v in fitted],
        forecast=point,
        lower=lower,
        upper=upper,
        residual_std=std,
    )


def forecast_series(values: list[float], horizon: int = 3) -> ForecastResult | None:
    """Forecast ``horizon`` future periods, or ``None`` with too little history."""
    if len(values) < MIN_MONTHS_FOR_FORECAST:
        return None

    array = np.array(values, dtype=float)
    if not np.all(np.isfinite(array)):  # pragma: no cover - defensive
        return None

    # A completely flat series has nothing to smooth; return it directly rather
    # than letting the optimiser wander.
    if float(np.std(array)) == 0.0:
        point = float(array[-1])
        return ForecastResult(
            method="constant",
            method_detail=(
                "Your monthly total has been identical across the observed "
                "period, so the forecast repeats it."
            ),
            fitted=[point] * len(array),
            forecast=[point] * horizon,
            lower=[point] * horizon,
            upper=[point] * horizon,
            residual_std=0.0,
        )

    result = _statsmodels_forecast(array, horizon)
    if result is not None:
        return result
    return _weighted_moving_average(array, horizon)


def limitations(months_of_history: int, method: str) -> list[str]:
    """Honest, specific caveats shown alongside every forecast."""
    items = [
        "Forecasts are statistical projections of your past behaviour, not predictions "
        "of the future. Any change in your circumstances invalidates them.",
        "The shaded band is an 80% prediction interval derived from how far past months "
        "deviated from the fitted model. Roughly one month in five is expected to fall "
        "outside it.",
        "One-off events (a large purchase, a bonus, a medical bill) are treated as "
        "ordinary variation and widen the interval rather than being excluded.",
    ]
    if months_of_history < MIN_MONTHS_SEASONAL:
        items.append(
            f"With {months_of_history} months of history there is not enough data to "
            "model seasonality (festive spending, annual premiums). At least 24 months "
            "would be needed."
        )
    if months_of_history < MIN_MONTHS_TREND:
        items.append(
            f"{months_of_history} months is a short series. The interval is wide on "
            "purpose, and accuracy will improve as you record more months."
        )
    if method == "weighted_moving_average":
        items.append(
            "No trend is being extrapolated: the forecast is a weighted average of "
            "recent months and will stay flat until more history accumulates."
        )
    return items


def insufficient_data_message(months: int) -> str:
    return (
        f"Cash-flow forecasting needs at least {MIN_MONTHS_FOR_FORECAST} complete "
        f"months of transaction history. You currently have {months}. "
        "Add more transactions (or run the demo seed) to enable forecasting - "
        "Finora will not invent a projection from insufficient data."
    )


def next_periods(last_month: date, horizon: int) -> list[date]:
    from app.utils.dates import add_months

    return [add_months(last_month, i + 1) for i in range(horizon)]
