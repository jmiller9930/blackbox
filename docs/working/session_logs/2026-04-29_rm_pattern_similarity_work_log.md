# Work log — 2026-04-29 — Reasoning Model evolution & Pattern Similarity v2 focus

## RM trajectory

We started with the Reasoning Model (RM) acting mostly like a deterministic indicator engine: indicators were calculated, a score was produced, and a decision was sealed.

We added RM state modeling so the system could describe the market context, such as trend, volatility, structure, and momentum.

We added RM pattern memory so the system could record prior trade outcomes and retrieve similar prior setups.

We added expected value (EV) inside RM so the system could ask whether a trade was worth taking based on prior outcomes and risk.

We added the RM decision gate so expected value could change the final sealed decision instead of only nudging the score.

We proved the Student can receive RM context, return valid structured JSON, and pass through authority and seal.

We proved the full RM chain works: state, memory, expected value, Student reasoning, decision authority, seal, and fingerprint.

We proved a trade cycle can write promoted learning records, retrieve them later, and change later decisions.

We proved loss avoidance can happen over time on repeated patterns.

## Authority model (unchanged)

The decision router / authority layer still matters: RM computes state, memory, expected value, and decision pressure; the Student proposes structured reasoning; the authority/seal path decides what becomes final. The Student is not the uncontrolled decision maker.

## Current gap — generalization (GT051)

The system can learn from repeated or very close patterns, but GT051 showed it does not yet generalize reliably across similar-but-not-identical market conditions.

That means memory works, learning works, expected value works, and the RM decision chain works, but the similarity function is too weak or too coarse.

## Next focus

Pattern Similarity v2 inside RM: improve how the system measures similarity so memory and expected value apply correctly to new market situations, not just near-repeats.
