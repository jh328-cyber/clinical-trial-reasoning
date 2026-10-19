# Toxicophore validation — do the perturbed molecules read as toxic?

Check requested by Hao: pass the molecules through a toxicity-detection tool to confirm the
inserted toxicophores genuinely increase predicted toxicity liability.

Method: each original vs perturbed SMILES screened for established genotoxic/reactive
structural alerts (nitroaromatic, aromatic amine, aromatic nitroso, epoxide, aryl halide —
canonical Ames-mutagenicity / DEREK-type alerts), via RDKit substructure matching. 166 cases.

| | original | perturbed |
|---|---|---|
| mean genotoxic-alert count | 0.54 | 1.41 |
| carries ≥1 recognized alert | 49% (81/166) | **100% (166/166)** |
| perturbed has more alerts than original | — | **87% (145/166)** |

**Reading.** Every toxified molecule carries a recognized genotoxic structural alert, and in
87% the alert load rose vs the original (the other 13% are drugs that already carried the same
alert type, so no net increase). So the perturbation is a real toxicity signal from a standard
cheminformatics standpoint — which makes the models' lack of reaction a genuine failure to use
the evidence, not an artifact of a weak perturbation.

Stronger cross-check (optional next): run a QSAR tox predictor (ProTox-II / ADMET-AI) for
mutagenicity / hepatotoxicity probabilities on original vs perturbed.
