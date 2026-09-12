"""Time-varying hedge ratio via a Kalman filter.

OLS fits one hedge ratio over a window and asserts it held throughout. It did
not. A cointegrating relationship drifts -- ADR ratios change, index weights
rebalance, one company grows into a different business -- and a static beta
absorbs that drift into the residual, where it looks like a persistent spread
that never reverts.

The filter treats beta as a hidden state that random-walks, and updates it each
observation:

    state        [slope, intercept]_t = [slope, intercept]_{t-1} + w,  w ~ N(0, Q)
    observation  y_t = slope_t * x_t + intercept_t + v,                v ~ N(0, R)

The output that matters is not beta. It is the **normalised innovation**:

    z_t = (y_t - prediction_t) / sqrt(S_t)

where S_t is the filter's own predicted variance for that observation. This is a
z-score whose denominator is derived rather than scraped off a rolling window,
and it has a property no rolling z-score has: when the relationship weakens, the
filter's uncertainty S_t grows, so z shrinks, and the detector quietly stops
firing. It self-mutes on a dying relationship instead of alerting harder as the
residual widens.

Q is set by `delta`, the standard parameterisation: Q = delta/(1-delta) * I.
Small delta means beta is believed to move slowly. It is the one real knob here,
and it is a prior about how fast the relationship drifts, not a fitted value --
so it should be stated, not tuned until the backtest looks good.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class KalmanStep:
    """One filter update."""

    beta: float           # current slope estimate
    intercept: float
    beta_var: float       # uncertainty on the slope
    prediction: float     # what the filter expected y to be
    innovation: float     # y - prediction, in price units
    innovation_var: float # S_t, the filter's own variance for this prediction
    z: float              # innovation / sqrt(S_t)

    @property
    def confident(self) -> bool:
        """Is the filter's own uncertainty small enough to trust the z?

        A filter that has just started, or one watching a relationship that has
        come apart, produces a large S_t and therefore a small z. That is
        correct behaviour, but it also means a near-zero z can mean "no
        deviation" or "no idea" -- and those should not be confused.
        """
        return self.innovation_var > 0 and self.beta_var < 1.0


class KalmanHedge:
    """Rolling estimate of y ~ beta*x + intercept, with uncertainty."""

    def __init__(
        self,
        *,
        delta: float = 1e-4,
        observation_var: float = 1e-3,
        initial_beta: float = 1.0,
        initial_var: float = 1.0,
    ) -> None:
        if not 0 < delta < 1:
            raise ValueError("delta must sit in (0, 1)")
        self.delta = delta
        self.R = observation_var
        # Q scales the state noise. delta -> 0 means a nearly-static beta.
        self.Q = np.eye(2) * (delta / (1 - delta))
        self.state = np.array([initial_beta, 0.0], dtype=float)
        self.P = np.eye(2) * initial_var
        self.steps = 0

    def update(self, y: float, x: float) -> KalmanStep:
        """Advance one observation. y is the reference leg, x the other."""
        H = np.array([x, 1.0], dtype=float)

        # Predict: beta random-walks, so the state is unchanged and only the
        # covariance grows.
        P_pred = self.P + self.Q

        prediction = float(H @ self.state)
        S = float(H @ P_pred @ H.T + self.R)
        innovation = float(y - prediction)

        # Update
        K = (P_pred @ H.T) / S
        self.state = self.state + K * innovation
        self.P = P_pred - np.outer(K, H @ P_pred)
        self.steps += 1

        return KalmanStep(
            beta=float(self.state[0]),
            intercept=float(self.state[1]),
            beta_var=float(self.P[0, 0]),
            prediction=prediction,
            innovation=innovation,
            innovation_var=S,
            z=innovation / np.sqrt(S) if S > 0 else 0.0,
        )

    def warmup(self, ys: list[float], xs: list[float]) -> None:
        """Run history through the filter without returning anything.

        A fresh filter starts at initial_beta with large covariance, so its
        first few dozen z-scores are dominated by its own ignorance. Warming it
        on history is the difference between a detector that is ready at startup
        and one that spends its first week learning in public.
        """
        for y, x in zip(ys, xs):
            self.update(y, x)
