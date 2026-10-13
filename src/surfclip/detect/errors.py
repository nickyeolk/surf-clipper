"""Detection errors, importable without loading torch."""


class ModelMissingError(RuntimeError):
    """The pretrained weights are not on disk; processing never downloads them (FR-025)."""
