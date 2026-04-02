import warnings

def _warn():
    warnings.warn(
        "ANVIL code generation is deprecated. "
        "ANVIL v4 is a pure validation engine. Use AI to generate code. "
        "Old generation modules are located in _ARCHIVED/.",
        DeprecationWarning,
        stacklevel=2,
    )

def generate_html(*args, **kwargs):
    _warn()
    raise NotImplementedError("Code generation has been removed from ANVIL.")

def layout_engine(*args, **kwargs):
    _warn()
    raise NotImplementedError("Code generation has been removed from ANVIL.")

def replicate(*args, **kwargs):
    _warn()
    raise NotImplementedError("The old replicate generation loop has been removed.")
