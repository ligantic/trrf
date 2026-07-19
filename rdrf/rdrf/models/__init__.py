# Ensure model modules outside definition/models.py are always imported so
# Django registers them for migrations and test-database creation.
from rdrf.models import pro_instruments  # noqa: F401
