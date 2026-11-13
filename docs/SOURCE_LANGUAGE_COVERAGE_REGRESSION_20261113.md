# Source-language coverage regression

Candidate d475a273f1ca9f81048f33a7f578df30ae797c21 plus exact Docker context allowlist correction for source_language_coverage.py. The first full run completed 858 tests in 72.530s, skipped 54 and failed one container-recipe assertion because the new source module was absent from the explicit Docker context allowlist. This failure is retained, not counted as a pass.

After adding only that source module to the allowlist, a fresh full run completed 858 tests in 71.126s: OK, 54 skipped, 804 executed successfully. Separate evaluate.py passed 8 cases. Seven focused coverage tests passed earlier. These are synthetic regression checks; no private corpus, trained model, semantic/scholarly validation, Docker startup or native Windows qualification.

Command: `PYTHONPATH=src python -m unittest discover -s tests -v`.

Source-only feature checkpoint. Main approval holds remain unchanged; no merge/deployment.
