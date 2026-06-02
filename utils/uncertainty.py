"""
utils/uncertainty.py
=====================
Uncertainty quantification helpers — MC Dropout and Evidential Deep Learning.

Extracted from: phase1, phase2, phase4b inline implementations.

Two approaches:
  MC Dropout  — multiple stochastic forward passes, total uncertainty only
  EDL         — single forward pass, separates aleatoric from epistemic

Both return scalar uncertainty values and optionally spatial maps.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from typing import Tuple, Optional


# ── MC Dropout ────────────────────────────────────────────────────────────────

def enable_dropout(model: nn.Module) -> None:
    """
    Set all Dropout layers to train mode so they fire during inference.
    Call this before mc_dropout_passes(). Remember to call model.eval()
    afterward to restore other layers (BatchNorm etc.) to eval mode.
    """
    for m in model.modules():
        if isinstance(m, nn.Dropout):
            m.train()


def mc_dropout_passes(
    model: nn.Module,
    inputs: dict,
    n_passes: int = 10,
    device: str = "cuda"
) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """
    Run N stochastic forward passes with dropout enabled.

    Args:
        model:    SegFormer (or any model with Dropout layers)
        inputs:   dict with 'pixel_values' key (from SegformerImageProcessor)
        n_passes: number of MC samples (10 used in phases 1–3)
        device:   'cuda' or 'cpu'

    Returns:
        mean_logits:  [B, C, H, W]  — mean prediction across passes
        variance:     [B, C, H, W]  — pixel-wise variance (epistemic proxy)
        uncertainty:  [B]           — scalar uncertainty per image
                                      (mean of spatial variance map)

    Usage:
        enable_dropout(model)
        mean_logits, variance, uncertainty = mc_dropout_passes(model, inputs)
        model.eval()
    """
    all_logits = []

    for _ in range(n_passes):
        with torch.no_grad():
            out = model(**{k: v.to(device) for k, v in inputs.items()})
            # SegformerForSemanticSegmentation returns .logits
            logits = out.logits if hasattr(out, 'logits') else out
            all_logits.append(logits.unsqueeze(0))

    stacked = torch.cat(all_logits, dim=0)   # [N, B, C, H, W]
    mean_logits = stacked.mean(dim=0)
    variance    = stacked.var(dim=0)
    uncertainty = variance.mean(dim=(1, 2, 3))  # scalar per image

    return mean_logits, variance, uncertainty


def uncertainty_scalar(variance: torch.Tensor) -> float:
    """
    Collapse spatial variance map to a single uncertainty scalar.
    Matches the format used in Phase 2 (Uncertainty=0.00038 notation).
    """
    return float(variance.mean().item())


# ── Evidential Deep Learning ──────────────────────────────────────────────────

class EvidentialHead(nn.Module):
    """
    Evidential head replacing standard softmax classifier.
    Outputs Dirichlet distribution parameters α for uncertainty decomposition.

    Based on: Sensoy et al. 2018, "Evidential Deep Learning to Quantify
    Classification Uncertainty", NeurIPS 2018.

    Args:
        in_channels: feature channels from backbone last hidden state
        num_classes: segmentation classes (19 for Cityscapes)

    Outputs (forward pass):
        alpha:      Dirichlet parameters [B, K, H, W]
        epistemic:  scalar model uncertainty per image
        aleatoric:  scalar data uncertainty per image
        belief:     class belief mass [B, K, H, W]
    """

    def __init__(self, in_channels: int = 256, num_classes: int = 19):
        super().__init__()
        self.num_classes = num_classes
        self.evidence_net = nn.Sequential(
            nn.Conv2d(in_channels, 128, 1),
            nn.ReLU(),
            nn.Conv2d(128, num_classes, 1),
            nn.Softplus()     # α > 0 required for Dirichlet
        )

    def forward(self, features: torch.Tensor):
        evidence = self.evidence_net(features)          # [B, K, H, W]
        alpha    = evidence + 1.0                       # Dirichlet params
        S        = alpha.sum(dim=1, keepdim=True)       # strength

        # Belief mass
        belief = evidence / S

        # Total vacuity (epistemic + aleatoric combined)
        K = self.num_classes
        total_uncertainty = K / S.squeeze(1).mean(dim=(-2, -1))

        # Aleatoric: expected entropy E[H[p]]
        p_bar   = alpha / S
        log_p   = torch.log(p_bar + 1e-8)
        aleatoric = -(p_bar * log_p).sum(dim=1).mean(dim=(-2, -1))

        # Epistemic: mutual information (total − aleatoric)
        epistemic = total_uncertainty - aleatoric

        return alpha, epistemic.mean(), aleatoric.mean(), belief


def edl_decompose(
    model_features: torch.Tensor,
    edl_head: EvidentialHead
) -> Tuple[float, float, float]:
    """
    Run EDL decomposition on backbone feature map.

    Args:
        model_features: [B, C, H, W] last hidden state from SegFormer backbone
        edl_head:       EvidentialHead instance (attached to model)

    Returns:
        (epistemic, aleatoric, total) — scalar uncertainty values

    Usage:
        ep, al, total = edl_decompose(backbone_output.last_hidden_state, model.edl_head)
    """
    with torch.no_grad():
        _, epistemic, aleatoric, _ = edl_head(model_features)
    total = epistemic.item() + aleatoric.item()
    return epistemic.item(), aleatoric.item(), total


def aleatoric_fraction(epistemic: float, aleatoric: float) -> float:
    """
    Fraction of total uncertainty that is aleatoric (irreducible sensor noise).
    High value (>0.8) → known degradation (glare, rain).
    Low value (<0.4)  → novel scenario (model doesn't know this situation).
    """
    total = epistemic + aleatoric + 1e-8
    return aleatoric / total


# ── Calibration ───────────────────────────────────────────────────────────────

def expected_calibration_error(
    confidences: np.ndarray,
    accuracies: np.ndarray,
    n_bins: int = 10
) -> float:
    """
    Expected Calibration Error (ECE) — measures reliability of confidence scores.
    Well-calibrated model: confidence 0.8 → correct 80% of the time.

    Args:
        confidences: [N] predicted confidence per sample
        accuracies:  [N] binary correct/incorrect per sample
        n_bins:      number of confidence bins

    Returns:
        ECE in [0, 1] — lower is better (0 = perfect calibration)
    """
    bin_edges  = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    n   = len(confidences)

    for i in range(n_bins):
        lo, hi = bin_edges[i], bin_edges[i + 1]
        mask   = (confidences >= lo) & (confidences < hi)
        if mask.sum() == 0:
            continue
        bin_conf = confidences[mask].mean()
        bin_acc  = accuracies[mask].mean()
        ece += (mask.sum() / n) * abs(bin_conf - bin_acc)

    return float(ece)


# ── Uncertainty → planning mode thresholds ───────────────────────────────────
# Calibrated from Phase 3 sensitivity matrix results.

UNCERTAINTY_THRESHOLDS = {
    "NORMAL":       0.00035,   # u < 0.35×10⁻³
    "CAUTIOUS":     0.00045,   # 0.35 ≤ u < 0.45×10⁻³
    "CONSERVATIVE": 0.00060,   # 0.45 ≤ u < 0.60×10⁻³
    "EMERGENCY":    float('inf')
}


def uncertainty_to_mode(uncertainty: float) -> str:
    """
    Map scalar uncertainty to planning regime.
    Boundaries calibrated from Phase 3 7×7 sensitivity matrix.
    """
    if uncertainty < UNCERTAINTY_THRESHOLDS["NORMAL"]:
        return "NORMAL"
    elif uncertainty < UNCERTAINTY_THRESHOLDS["CAUTIOUS"]:
        return "CAUTIOUS"
    elif uncertainty < UNCERTAINTY_THRESHOLDS["CONSERVATIVE"]:
        return "CONSERVATIVE"
    else:
        return "EMERGENCY"
