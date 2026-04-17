# Policy Design Linting Rules — Indicator Redundancy & Efficiency

## Purpose
This document defines best practices and linting rules for building trading policies using shared indicators.

## Core Principle
Valid is not the same as sensible.

## Key Rules
1. Avoid redundant indicators (e.g., EMA 9/10/11/12)
2. Avoid clustering (near-identical parameters)
3. Avoid over-constrained logic (too many required conditions)
4. Avoid duplicate signal families (RSI + Stochastic as hard gates)
5. Avoid false diversity (multiple indicators expressing same idea)
6. Watch signal sparsity (too few trades)
7. Allow intentional complexity with acknowledgment

## System Responsibilities
- Detect redundancy
- Classify indicators
- Warn on bad design
- Evaluate signal frequency

## Final Statement
A good policy adds distinct, meaningful information.
