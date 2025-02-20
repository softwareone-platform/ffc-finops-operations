class InvalidParameters(Exception):
    pass


class DatabaseError(Exception):
    pass


class NotFoundError(DatabaseError):
    pass


class CannotDeleteError(DatabaseError):
    pass


class ConstraintViolationError(DatabaseError):
    pass


class NullViolationError(DatabaseError):
    pass
