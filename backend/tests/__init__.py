"""Backend unittest package for discovery from the backend root."""

import warnings

warnings.filterwarnings(
	"ignore",
	message=".*HMAC key is .* below the minimum recommended length.*",
)