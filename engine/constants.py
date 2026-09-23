"""kromi_app.engine.constants — facade over the topical constant modules.

Split in v34.35 into cabinet_geometry, sizing_factors, override_schema, and
classification_tables; this module re-exports the whole surface so every
existing import keeps working unchanged. New code may import from the
topical modules directly.
"""

from .cabinet_geometry import *  # noqa: F401,F403
from .sizing_factors import *  # noqa: F401,F403
from .override_schema import *  # noqa: F401,F403
from .classification_tables import *  # noqa: F401,F403
