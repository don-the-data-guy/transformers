from typing import TYPE_CHECKING

from ...utils import (
    OptionalDependencyNotAvailable,
    _LazyModule,
    is_torch_available,
)


_import_structure = {
    "configuration_univnet": [
        "UnivNetGanConfig",
    ]
}

try:
    if not is_torch_available():
        raise OptionalDependencyNotAvailable()
except OptionalDependencyNotAvailable:
    pass
else:
    _import_structure["modeling_univnet"] = [
        "UnivNetGan",
    ]


if TYPE_CHECKING:
    from .configuration_univnet import (
        UnivNetGanConfig,
    )

    try:
        if not is_torch_available():
            raise OptionalDependencyNotAvailable()
    except OptionalDependencyNotAvailable:
        pass
    else:
        from .modeling_univnet import (
            UnivNetGan
        )

else:
    import sys

    sys.modules[__name__] = _LazyModule(__name__, globals()["__file__"], _import_structure, module_spec=__spec__)