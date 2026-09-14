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

THE FILTER RUNS ON A NORMALISED SCALE, AND IT HAS TO.

Q and R are absolute variances. Q is a prior on how far the SLOPE moves per
step; R is a prior on observation noise in PRICE units. But the slope's
contribution to the predicted variance S is x^2 * P[0,0], so the same delta
means something completely different at x = 0.6 than at x = 56,000 -- and this
universe spans both (JPYINR at 0.62, BANKNIFTY at 56,606).

Measured, before this was fixed: the same AUDINR/USDINR*AUDUSD identity, whose
true beta is 0.998 at every scale because multiplying both legs cannot change a
ratio, came back as

    both legs x0.01   ->  beta 0.783,  z sd 0.08,  |z| > 2 never fired
    both legs x1      ->  beta 0.962,  z sd 0.64
    both legs x100    ->  beta 1.003,  z sd 0.66

The filter was answering a question about units. At the low end it was also
effectively muted, which is the dangerous direction: a detector that silently
stops firing looks exactly like a market with nothing to report.

So both legs are divided by a scale fixed at the first observation. Beta is
invariant under a common scaling, so it is reported unchanged; prediction,
innovation and S are scaled back to price units on the way out, which leaves
z untouched because z = innovation / sqrt(S) and innovation ~ s while S ~ s^2.
The model is the same model -- it is just no longer expressed in whatever units
the instrument happens to quote in.
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
        delta: float = 1e-7,
        observation_var: float = 1e-5,
        initial_beta: float = 1.0,
        initial_var: float = 1.0,
    ) -> None:
        if not 0 < delta < 1:
            raise ValueError("delta must sit in (0, 1)")
        # delta is a PRIOR, stated rather than fitted: 1e-7 gives the slope a
        # per-step standard deviation of ~3.2e-4, so a hedge ratio can drift
        # about half a percent over a trading year. That is a sentence about
        # how fast these relationships actually change -- ADR ratios move on
        # corporate actions, index weights on rebalances -- not a number chosen
        # because it made a backtest look better.
        #
        # The previous default of 1e-4 allowed a per-step sd of 0.01, which
        # compounds to a +/-22% random walk over 500 observations. Measured on
        # the AUDINR triangular identity, whose beta is provably 0.998: the
        # filter returned 0.816 and z collapsed to sd 0.42, so the detector
        # quietly under-fired. Beta was absorbing the spread instead of
        # reporting it.
        self.delta = delta
        # In units of the first observation, because the filter normalises.
        # 1e-5 is a variance, so an observation-noise prior of ~32 bps, which
        # is the order of the residual on the computable linkages (19-46 bps).
        self.R = observation_var
        # Q scales the state noise. delta -> 0 means a nearly-static beta.
        self.Q = np.eye(2) * (delta / (1 - delta))
        self.state = np.array([initial_beta, 0.0], dtype=float)
        self.P = np.eye(2) * initial_var
        self.steps = 0
        # Fixed on the first observation and never revised. A scale that moved
        # with the data would make Q and R mean something different from one
        # step to the next, which is the problem being solved, not a refinement
        # of it.
        self.scale: float | None = None

    def update(self, y: float, x: float) -> KalmanStep:
        """Advance one observation. y is the reference leg, x the other."""
        if self.scale is None:
            # abs() because a spread leg can legitimately be negative; the
            # fallback to 1.0 keeps a first observation of exactly zero from
            # dividing everything by nothing.
            self.scale = float(abs(y)) or float(abs(x)) or 1.0

        s = self.scale
        yn, xn = y / s, x / s
        H = np.array([xn, 1.0], dtype=float)

        # Predict: beta random-walks, so the state is unchanged and only the
        # covariance grows.
        P_pred = self.P + self.Q

        prediction_n = float(H @ self.state)
        S_n = float(H @ P_pred @ H.T + self.R)
        innovation_n = float(yn - prediction_n)

        # Update
        K = (P_pred @ H.T) / S_n
        self.state = self.state + K * innovation_n
        self.P = P_pred - np.outer(K, H @ P_pred)
        self.steps += 1

        # Back to price units on the way out. beta and z are already scale-free.
        return KalmanStep(
            beta=float(self.state[0]),
            intercept=float(self.state[1]) * s,
            beta_var=float(self.P[0, 0]),
            prediction=prediction_n * s,
            innovation=innovation_n * s,
            innovation_var=S_n * s * s,
            z=innovation_n / np.sqrt(S_n) if S_n > 0 else 0.0,
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

    # ---- persistence -------------------------------------------------------
    #
    # The filter's whole value is that it has been running. A process restart
    # that throws away `state` and `P` does not lose a cache -- it loses the
    # only thing that distinguishes this filter from a fresh one, and the
    # detector goes back to reporting its own ignorance for a hundred cycles.

    def snapshot(self) -> dict:
        """Everything needed to resume this exact filter."""
        return {
            "delta": self.delta,
            "observation_var": self.R,
            "state": self.state.tolist(),
            "P": self.P.tolist(),
            "steps": self.steps,
            "scale": self.scale,
        }

    @classmethod
    def restore(cls, snapshot: dict) -> KalmanHedge:
        filt = cls(delta=snapshot["delta"], observation_var=snapshot["observation_var"])
        filt.state = np.array(snapshot["state"], dtype=float)
        filt.P = np.array(snapshot["P"], dtype=float)
        filt.steps = int(snapshot["steps"])
        # Absent in snapshots written before the filter was normalised. Those
        # states were fitted in raw price units, so resuming one would carry the
        # scale bug forward; leaving scale as None makes the next observation
        # set it, and the fingerprint check discards genuinely stale state
        # anyway.
        scale = snapshot.get("scale")
        filt.scale = float(scale) if scale else None
        return filt
