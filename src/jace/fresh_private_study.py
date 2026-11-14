"""Explicit local fresh-v1 study API, separate from legacy private_study.

No engine, CLI or web routing imports this module automatically. Each call needs
independent six-file pins and a new source/license/purpose declaration. Results
stay in memory; callers must separately authorize any disclosure. This is not a
legacy schema converter, training admission or scholarly validation.
"""
from ._fresh_study.consumer import (
    ConsumerError, ExpectedPins, StudyDeclaration, consume,
)

__all__ = ['ConsumerError', 'ExpectedPins', 'StudyDeclaration', 'consume']
