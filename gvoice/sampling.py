"""Sampling parameters of a take (0.4.1): which values the engine samples with and how they are resolved.

The layers, field by field (also inside ``subTalker``): the order, then ``sampling`` of the project configuration,
then ``sampling`` of the engine catalog (the checkpoint's own values). A ``line`` never inherits the sampling of its
voice (another model). The result is always complete, so a take can record exactly what made it (and be replayed).
The shape is ``common.schema.json#/$defs/sampling``."""
import copy
from typing import Optional

from . import models, projects

ENGINE = "qwentts"  # the catalog whose ``sampling`` is the last layer (the fake engine uses the same values)
SUB = "subTalker"


def defaults() -> dict:
    """The catalog's own values (a copy)."""
    return copy.deepcopy(models.load(ENGINE)["sampling"])


def merge(*layers: Optional[dict]) -> dict:
    """Field-by-field merge; the first layer that has a field wins, ``subTalker`` too. Layers may be ``None``.
    With a complete last layer the result is complete."""
    out: dict = {}
    for layer in reversed([x for x in layers if x]):
        for name, value in layer.items():
            if name == SUB:
                out[SUB] = dict(out.get(SUB, {}), **value)
            else:
                out[name] = value
    return out


def resolve(order: Optional[dict] = None, config: Optional[dict] = None) -> dict:
    """The effective sampling: `order` (its ``sampling`` field, or ``None``) over `config` (the project's) over the
    catalog. A new complete dict."""
    return merge(order, config, defaults())


def effective(project: str, order: dict) -> dict:
    """The effective sampling of a take of `order` (a stored order record) in `project`."""
    return resolve(order.get("sampling"), projects.get(project)["config"].get("sampling"))
